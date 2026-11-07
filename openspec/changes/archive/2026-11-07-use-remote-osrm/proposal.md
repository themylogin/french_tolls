# Proposal

## Why

The web application and the bot reach OSRM only at `osrm-toll` and `osrm-optimal` on the Compose network. So every deployment must hold both graphs, about 19 GB of disk, and the memory to serve them. A second deployment cannot use the routers of a deployment that already has them. Examples are a small host or a developer machine.

## What Changes

- Two new settings, `OSRM_TOLL_URL` and `OSRM_OPTIMAL_URL`. When one is set, the application sends that graph's requests to it, not to the internal server. The two settings are independent.
- When a URL is set, `make web`, `make bot`, `make app` and the evaluation targets do not start the matching internal server. They stop it if it runs.
  - The Makefile already reads `.env`, so it can skip the service. A `sleep infinity` fallback in the container is not necessary.
  - These targets no longer require the graph path of a server they do not start.
  - Compose loads the project when a graph path is unset. A deployment that uses remote routers holds no graphs.
- A new setting, `OSRM_ACCESS_TOKEN`. When it is set:
  - the web application serves `GET /api/osrm/toll/*` and `GET /api/osrm/optimal/*`;
  - each route forwards the path and the query unchanged to that graph's router, and returns the router's answer;
  - a request without `X-Auth: <token>` gets 401 and reaches no router;
  - the routing client sends `X-Auth: <token>` on every router request.
- When the token is unset, no route exists under `/api/osrm/`.
- nginx and the aiohttp server accept a request line up to 1 MiB. The bot matches a trace of about 2 000 points in one GET request, 40 to 120 KB of URL. Both servers refuse more than 8 KB by default.
- The routing client reports an answer that is not a JSON object as an unavailable router, with the HTTP status. An nginx error page is an example. Today the client raises a JSON decode error.
- `evaluation/build_test_cities.py` already reads `OSRM_TOLL_URL`. It sends `X-Auth` when the token is set.
- `.env.example` and `README.md` document the three settings and the two-deployment setup.

Assumptions:

- "The client for `OSRM_TOLL_URL` sends the token" applies to `OSRM_OPTIMAL_URL` too. The relay checks the token on both graphs.
- The relay forwards to the router that the deployment itself uses. Normally this is the internal server.

Not in this change:

- The build pipeline keeps the internal servers. Its steps name `http://osrm-toll:5000` directly.
- A plain `docker compose up` still starts both internal servers.
- Connection reuse for a remote router. Each request still opens its own connection.

## Capabilities

### New Capabilities

- `remote-routers`: how a deployment reaches a router at a configured address, and how a deployment lends its routers to another through a relay that checks a token.

### Modified Capabilities

- `route-service`: the router addresses and the access token become settings. `web` and `bot` reach a configured address instead of the service name. The API gains the relay routes when the token is set.
- `build-pipeline`: the web application and the bot address a router by its service name only when no URL is configured for it. The build steps always do.
- `drive-flow-integration-tests`: the suite reaches the routers that the configuration names.

## Impact

- Code: `french_tolls/config.py`, `french_tolls/osrm.py`, `french_tolls/route.py`, `french_tolls/api.py`, `french_tolls/web.py`, a new `french_tolls/relay.py`, and unit tests.
- Front end: `www/nginx.conf`.
- Operations: `Makefile` and `docker-compose.yml`.
- Evaluation: `evaluation/build_test_cities.py`.
- Documents: `.env.example` and `README.md`.
- Public surface: with the token set, `/api/osrm/*` is reachable on the public site. Only the token protects it.
- No new dependency.
