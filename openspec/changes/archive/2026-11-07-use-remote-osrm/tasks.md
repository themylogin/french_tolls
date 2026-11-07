# Tasks

## 1. Router addresses and the token in the client

- [x] 1.1 Add `osrm_toll_url`, `osrm_optimal_url` and `osrm_access_token` to `french_tolls/config.py`, each with a sentence on its use, as in design.md. Verify with a new `french_tolls/tests/test_osrm_client.py` test: with an empty environment, `config.osrm_toll_url` is `"http://osrm-toll:5000"`, `config.osrm_optimal_url` is `"http://osrm-optimal:5000"`, and `config.osrm_access_token` is `""`.
- [x] 1.2 Delete `TOLL_URL` and `OPTIMAL_URL` from `french_tolls/osrm.py`. Make each `Routers` method read `config.osrm_toll_url` or `config.osrm_optimal_url` when it is called. Change `route.py:200` to pass `config.osrm_optimal_url`. Verify with a test that replaces `osrm.config`, sets the toll URL to `"https://example.org/api/osrm/toll"`, and checks the bases that `snap`, `distance_to_road_network`, `match`, `fast` and `optimal` ask. Verify that `test_the_trace_is_matched_on_the_untouched_graph` still passes.
- [x] 1.3 Send `X-Auth` from `Routers._get` when the token is set. Verify with a test against an `aiohttp.test_utils.TestServer` that records request headers: with the token `"s3cret"`, the router receives `X-Auth: s3cret`; with no token, it receives no `X-Auth`.
- [x] 1.4 Make `Routers._get` raise `RouterUnavailable` for a body that is not a JSON object, naming the base and the HTTP status. Verify with two tests against the same kind of server. A 502 HTML page gives a `RouterUnavailable` whose message contains `502`. A 401 `{"code": "Unauthorized", ...}` gives a message that contains `Unauthorized` and does not contain the token.
- [x] 1.5 Add `OSRM_TOLL_URL`, `OSRM_OPTIMAL_URL` and `OSRM_ACCESS_TOKEN` to `.env.example`, empty, each with a comment line. The token comment asks for a long random value. Verify that `grep -c '^OSRM_\(TOLL_URL\|OPTIMAL_URL\|ACCESS_TOKEN\)=$' .env.example` prints `3`.

## 2. The relay

- [x] 2.1 Create `french_tolls/relay.py` with `install(app)` and the handler, as design.md describes. Call `relay.install(app)` in `french_tolls/api.py`. Verify that `make test` still passes.
- [x] 2.2 Add `french_tolls/tests/test_relay.py`. Use a bare `web.Application`, `relay.install`, a replaced `relay.config`, and a fake router on a `TestServer` that records the raw path and headers. Verify each scenario of the relay requirements in `specs/remote-routers/spec.md`:
  - no token gives 404;
  - `/api/osrm/fast/...` gives 404;
  - `POST` gives 405;
  - a missing or wrong `X-Auth` gives 401 with `"code": "Unauthorized"`, and the fake router receives nothing;
  - a holder of the token gets the router's status, `Content-Type` and body;
  - `%2B`, `%2F` and `%3D` in the query reach the router unchanged;
  - a 400 `NoSegment` answer passes through;
  - a stopped router gives 502 with `"code": "RouterUnavailable"`, a message that names the graph, and no token in the body;
  - the router receives `X-Auth` with the token.
- [x] 2.3 Add a "Lend the routers" section to `README.md`. The lender sets `OSRM_ACCESS_TOKEN`, keeps both URLs unset, and runs `make web`. Show one `curl` with `-H "X-Auth: ..."` to `/api/osrm/toll/nearest/v1/driving/2.35,48.86`. Verify the command in 6.2.

## 3. Long request lines

- [x] 3.1 Pass `max_line_size=1048576` to `web.run_app` in `french_tolls/web.py`. Verify in 6.2 that a 200 KB request line reaches the router.
- [x] 3.2 Add `large_client_header_buffers 4 1m;` to the `server` block of `www/nginx.conf`. Verify that `docker compose --profile app build nginx` succeeds. The image build runs `nginx -t`.

## 4. Starting only the local routers

- [x] 4.1 Change the five graph mounts in `docker-compose.yml` to the long syntax with a `/OSRM_TOLL_PATH-is-unset` or `/OSRM_OPTIMAL_PATH-is-unset` default and `create_host_path: false`. Verify these three results:
  - `docker compose --env-file /dev/null config --quiet` exits 0;
  - `docker compose --env-file /dev/null run --rm osrm-toll-tools true` fails with an error that names `/OSRM_TOLL_PATH-is-unset`;
  - `ls -ld /OSRM_TOLL_PATH-is-unset` then fails.
- [x] 4.2 Verify that the pipeline still mounts the graphs: `docker compose config` with the real `.env` shows the configured `OSRM_TOLL_PATH` and `OSRM_OPTIMAL_PATH` as the sources.
- [x] 4.3 Add `LOCAL_ROUTERS`, `REMOTE_ROUTERS` and the phony `routers` target to the `Makefile`, with the guard chosen as in design.md. Make `web`, `bot`, `test_cities`, `test_google_routes` and `test_google` depend on `routers`. Remove their own `up -d osrm-toll osrm-optimal`. Update the comment above the application targets. Verify with `make -n`:
  - with `OSRM_TOLL_URL= OSRM_OPTIMAL_URL=`, `make -n web` prints `up -d osrm-toll osrm-optimal` and no `stop`;
  - with `OSRM_TOLL_URL=x OSRM_OPTIMAL_URL=`, `make -n web` prints `up -d osrm-optimal` and `stop osrm-toll`;
  - with both URLs set, `OSRM_TOLL_PATH=` and `OSRM_OPTIMAL_PATH=`, `make -n web` prints no `up -d osrm-` and no guard message;
  - with `OSRM_TOLL_URL= OSRM_OPTIMAL_URL= OSRM_TOLL_PATH=`, `make web` stops with the `OSRM_TOLL_PATH` message.
- [x] 4.4 Verify that a pipeline step ignores the URLs: with `OSRM_TOLL_URL=x`, `make -n build_route_set` still prints `up -d osrm-toll` and `--osrm http://osrm-toll:5000`.
- [x] 4.5 Update `README.md`. In "Configuration", say that each graph path is necessary only for a router that runs locally. Add a "Use another deployment's routers" section: set both URLs to the lender's `/api/osrm/toll` and `/api/osrm/optimal`, set the same token, and do not use quotes. Say that a lender keeps both URLs unset. Verify that the variable names and the paths in the section match `.env.example` and the relay routes.

## 5. Evaluation

- [x] 5.1 Make `evaluation/build_test_cities.py` send `X-Auth` through a `urllib.request.Request` when `OSRM_ACCESS_TOKEN` is set. Verify with a one-off `python3 -I` run that points `OSRM_TOLL_URL` at a local `http.server` that prints the request headers, and check that `X-Auth` is present.

## 6. Integration checks

- [x] 6.1 Run `make test`, and verify that the unit suite and the builder suite pass.
- [x] 6.2 Play the lender on this host. Set `OSRM_ACCESS_TOKEN` in `.env` and run `make web`. From a container on the Compose network, verify these results through `nginx`:
  - the README's `curl` gives 200 and `"code":"Ok"`;
  - the same request without `X-Auth` gives 401;
  - a `/api/osrm/toll/match/v1/driving/...` request with a 200 KB request line gets an OSRM answer, and not 414 or 400.
  - Ask the user before you leave the token in `.env` after the checks.
- [ ] 6.3 Play the borrower from a separate container. Run the integration suite with `-e OSRM_TOLL_URL=http://nginx/api/osrm/toll -e OSRM_OPTIMAL_URL=http://nginx/api/osrm/optimal`, with the lender still up. Verify that every pinned journey passes, and that the `web` log shows relay requests.
- [x] 6.4 Run `openspec validate use-remote-osrm --strict`, and verify that it reports the change as valid.

## Workflow follow-up

- Before a borrower on another host relies on the relay, send one 200 KB match request through the lender's public address. A CDN can refuse it. See the first risk in design.md.
- Archive the change after review.
