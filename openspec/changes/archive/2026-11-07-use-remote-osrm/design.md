# Design

## Context

See `proposal.md` for the motivation. The specs are in `specs/remote-routers/spec.md` and the three deltas.

Observed state:

- `french_tolls/osrm.py:22-23` fixes `TOLL_URL` and `OPTIMAL_URL` to the service names. `Routers` uses `TOLL_URL` for snap, distance check, match and the fast route. It uses `OPTIMAL_URL` for the optimal route. `route.py:200` passes `osrm.OPTIMAL_URL` to `route_via`.
- `Routers._get` opens one `aiohttp.ClientSession` per request and calls `resp.json(content_type=None)`. A body that is not JSON raises `json.JSONDecodeError`. The client does not catch it, so it is not a `RouterUnavailable`.
- `config.py` declares every setting. Each field default is read once, at import. Tests replace a module's `config` with `dataclasses.replace(...)`, as `test_refine.py:221` does.
- `route.py:21` loads the booth files at import. So the unit suite cannot import `api.py`, and the relay must be testable without it.
- `api.py` builds `app` at import with two routes. `web.py` calls `web.run_app(app, host="0.0.0.0", port=8080)`.
- nginx proxies all of `/api` to `web:8080` with `$request_uri`, so a relay path reaches `web` without a new location.
- `equivalence.matched_nodes` sends a whole trace in one GET request. At a 250 m spacing this is about 2 000 points, or 40 to 120 KB of URL.
- Measured in the `french_tolls-web` image (aiohttp 3.14.3): a 200 KB request line gets 400 by default. With `max_line_size=1048576` passed to `AppRunner`, it gets 200. `run_app` forwards extra keyword arguments to `AppRunner`.
- nginx refuses a request line longer than one `large_client_header_buffers` buffer (8 KB by default) with 414.
- The Makefile reads `.env` with `-include .env` and `export`. So make variables can see `OSRM_TOLL_URL` and `OSRM_OPTIMAL_URL`.
- Compose fails to load the whole project when `OSRM_TOLL_PATH` is unset: `invalid spec: :/osrm: empty section between colons`. Five services mount a graph path: `osrm-toll`, `osrm-optimal`, `osrm-toll-tools`, `osrm-optimal-tools` and `builder`.
- `evaluation/build_test_cities.py:43` already reads `OSRM_TOLL_URL`, with `urllib`. A 401 from `urlopen` raises `HTTPError`.
- The `web`, `bot`, `integration`, `recorder` and `evaluation` services use `env_file: .env`. They receive the new settings with no Compose change. `tests` has no `env_file`, so the unit suite sees no router address.
- The `build-pipeline` spec says the two routers publish host ports. `docker-compose.yml` publishes none. This change does not touch that difference.

## Goals / Non-Goals

**Goals:**

- One place decides each router's address: the setting, with the service name as the default.
- The relay passes a request through byte for byte. A borrower sees the same answers as a deployment with local graphs.
- No internal router runs when its address is configured. No placeholder process runs in its place.

**Non-Goals:**

- A connection pool for remote routers.
- A POST transport or any other way around a URL length limit outside this project.
- Rate limits, several tokens, or token rotation on the relay.
- Router addresses for the build pipeline.

## Decisions

### Three settings in `config.py`, read when a request is sent

```python
osrm_toll_url: str = getenv("OSRM_TOLL_URL", "http://osrm-toll:5000").rstrip("/")
osrm_optimal_url: str = getenv("OSRM_OPTIMAL_URL", "http://osrm-optimal:5000").rstrip("/")
osrm_access_token: str = getenv("OSRM_ACCESS_TOKEN")
```

`osrm.py` deletes `TOLL_URL` and `OPTIMAL_URL`. Each method reads `config.osrm_toll_url` or `config.osrm_optimal_url` when it is called. `route.py:200` passes `config.osrm_optimal_url`.

*Alternative considered:* keep the module names and assign `TOLL_URL = config.osrm_toll_url`. Rejected. A test that replaces `osrm.config` does not move a name bound at import. The project rules also forbid a name that only renames a value.

### The client sends `X-Auth` on every router request when the token is set

`_get` adds the header for the internal and the remote routers alike. OSRM ignores a header it does not know. One rule is easier to test than a rule per address. It also lets a relay forward to another relay.

*Alternative considered:* send the token only to a configured URL. Rejected. It adds a branch per graph and protects nothing, because the internal router is in the same deployment.

### An answer that is not a JSON object is `RouterUnavailable`

`_get` catches `ValueError` from `resp.json`, and checks that the body is a `dict`. The message names `base` and `resp.status`. A remote address puts proxies on the path, and they answer errors as HTML. The `route-service` spec requires that a failure names its cause, not a Python exception.

### The relay is its own module and installs itself

`french_tolls/relay.py` has `install(app)`. It adds the routes only when `config.osrm_access_token` is set. `api.py` calls `relay.install(app)`.

```python
web.get("/api/osrm/{graph:toll|optimal}/{rest:.*}", relay, allow_head=False)
```

`allow_head=False` keeps the method set to GET. aiohttp answers 405 for any other method on a matched path, and 404 for another graph name.

The handler does these steps in order:

1. It compares `X-Auth` with the token by `hmac.compare_digest` on the two strings. The token is ASCII. A non-ASCII header makes `compare_digest` raise, and that caller gets 500. This is accepted.
2. It takes the rest of the target from `request.raw_path` after `/api/osrm/<graph>`. The match info is decoded, and a decoded hint loses its `%2B` and `%3D`.
3. It sends a GET to `yarl.URL(base + rest, encoded=True)`, with `X-Auth`. `encoded=True` stops a second round of quoting.
4. It returns the router's status and body, and copies the `Content-Type` header unchanged.

On `aiohttp.ClientError` or `TimeoutError`, it answers 502 with `{"code": "RouterUnavailable", "message": "the <graph> router did not answer"}`. It uses the client's `REQUEST_TIMEOUT_S` and opens one session per request, as the client does.

*Alternative considered:* routes in `api.py`. Rejected. The unit suite cannot import `api.py`, because `route.py` loads the booth files at import.

### The relay forwards to the router that the deployment uses

The relay's base is `config.osrm_toll_url` or `config.osrm_optimal_url`. On a lender these are the service names. On a deployment that also has a URL set, the relay forwards to that URL.

*Alternative considered:* always forward to the service name. Rejected. With a URL set, that container does not run, so every relay request fails. One setting per graph also keeps one answer to "where does this graph live".

### Both servers accept a request line of 1 MiB

- nginx: `large_client_header_buffers 4 1m;` in the `server` block. nginx allocates a large buffer only when a request needs one.
- aiohttp: `web.run_app(app, host="0.0.0.0", port=8080, max_line_size=1048576)`.

1 MiB is about eight times the largest trace measured. It stays a limit, so a request that skipped the thinning still fails early. The `route-service` spec gives the same reason for the router's matching size.

### The Makefile starts only the local routers

```make
LOCAL_ROUTERS  := $(if $(strip $(OSRM_TOLL_URL)),,osrm-toll) $(if $(strip $(OSRM_OPTIMAL_URL)),,osrm-optimal)
REMOTE_ROUTERS := $(if $(strip $(OSRM_TOLL_URL)),osrm-toll) $(if $(strip $(OSRM_OPTIMAL_URL)),osrm-optimal)
```

A new phony target, `routers`:

- depends on the guard for the local routers only: `guard-osrm-paths-differ` for both, `guard-osrm-path` for `osrm-toll` alone, `guard-osrm-optimal-path` for `osrm-optimal` alone, and none when both are remote;
- runs `$(COMPOSE) up -d $(LOCAL_ROUTERS)` when the list is not empty;
- runs `$(COMPOSE) stop $(REMOTE_ROUTERS)` when that list is not empty.

`web`, `bot`, `test_cities`, `test_google_routes` and `test_google` depend on `routers`. They no longer run `up -d osrm-toll osrm-optimal` themselves. Pipeline steps keep their own `up -d osrm-toll`.

*Alternative considered:* the container runs `sleep infinity` when its URL is set. Rejected. The user asked for it only as a fallback, and the Makefile makes it unnecessary. It also breaks the pipeline on such a host: a build step starts `osrm-toll` and gets a container that does not listen.

*Alternative considered:* a Compose profile from interpolation, `profiles: ["${OSRM_TOLL_URL:+remote}"]`. Rejected. Tested, it relies on how Compose treats an empty profile name. With `--profile app` the service drops out even when no URL is set.

### Compose loads without a graph path

Each of the five graph mounts uses the long syntax:

```yaml
- type: bind
  source: ${OSRM_TOLL_PATH:-/OSRM_TOLL_PATH-is-unset}
  target: /osrm
  bind:
    create_host_path: false
```

`OSRM_OPTIMAL_PATH` uses the same form. Tested: with the path unset, Compose loads, the start fails with `bind source path does not exist: /OSRM_TOLL_PATH-is-unset`, and no directory is created. The Makefile guards still stop every pipeline step first. The Makefile already runs `mkdir -p` on both paths before a step writes there, so `create_host_path: false` changes nothing for the pipeline.

*Alternative considered:* the short syntax with the same default. Rejected. The short syntax creates the directory as root, and `restart: always` then loops `osrm-routed` on an empty graph.

### The evaluation sends the token through `urllib`

`build_test_cities.get` builds a `urllib.request.Request` with `X-Auth` when `OSRM_ACCESS_TOKEN` is set. The evaluation is outside the application package, so the "one place reads the environment" rule does not apply. The script reads it directly, as it reads `OSRM_TOLL_URL` now.

## Risks / Trade-offs

- [A CDN or proxy in front of the lender can cap the URL length. Cloudflare's cap is about 16 KB.] → The relay then refuses the match requests, and the bot loses Google equivalence on the borrower. The apply phase proves the path inside one host only. Before a borrower relies on it, the operator sends one 200 KB request through the lender's public address. If something refuses it, a later change needs another transport.
- [A deployment whose URL names its own relay forwards each request to itself until the timeout.] → `README.md` says that a lender keeps both URLs unset. The integration check plays the borrower from a separate container, so it does not loop.
- [A connection per request costs a TLS handshake per request on a remote router. A journey can make up to 327 requests.] → At 30 ms round trip, this adds about 10 s to the worst journey. The `route-service` spec forbids reuse because of failures with a local pool. A measured follow-up can change that for remote routers only.
- [The relay puts a public route in front of the routers.] → It exists only with a token, compares in constant time, and accepts GET only. A long random token is the operator's duty, and `.env.example` says so.
- [The aiohttp and nginx access logs record each relayed request line, up to 120 KB for a match.] → The logs do not contain the token, because it is a header. Log size grows on the lender. If it hurts, a follow-up can drop relay lines from the access log.
- [A value in `.env` with quotes reaches make with the quotes.] → This already applies to every variable the Makefile reads. `README.md` shows the values without quotes.
- [A router from before the switch keeps running until a make target stops it.] → `routers` stops it. A plain `docker compose up` still starts both routers, as the specs require.

## Migration Plan

1. Deploy the lender first: set `OSRM_ACCESS_TOKEN`, then run `make web` (or `make app`). Its own routes are unchanged, because the URLs stay unset.
2. On the borrower, set `OSRM_TOLL_URL=https://<lender>/api/osrm/toll`, `OSRM_OPTIMAL_URL=https://<lender>/api/osrm/optimal`, and the same token. Then run `make web` or `make app`.
3. To roll back the borrower, clear the two URLs and set the graph paths. `make web` then starts the local routers again.
4. To roll back the lender, clear the token and run `make web`. The relay routes disappear.
