## Why

`www/` now holds the page this project has always been the back end for: `index.html`, `index.js`, `style.css`, 28 KB in three files. Nothing serves it. The aiohttp application answers `/api/calculate` and `/api/autocomplete` and returns 404 for everything else, so the deployed site is served from somewhere outside this repository, by something nothing here describes.

The page cannot be served from just anywhere. It fetches `/api/calculate` and `/api/autocomplete` as relative paths, so whatever serves it has to be the same origin as the API. That is one arrangement, not a choice each deployment makes for itself, and it belongs in the repository beside the service it depends on.

Reading the page against the API also turned up a defect. `index.js` formats every passage cost through `Intl.NumberFormat`, and `format(null)` renders `0,00 €`. Since the accounting rewrite, a passage that cannot be priced carries `cost: null` — so the page now tells a driver that a toll they will be charged for is free. That is the exact claim `journey-toll-accounting` forbids the API from making, defeated at the last step.

## What Changes

### An nginx service serves the page and fronts the API

- A new `nginx` Compose service becomes the public entry point. It serves the three files from `www/` and proxies `/api/` to the aiohttp application over the Compose network, so the page's relative fetches resolve without CORS and without the page knowing where the API lives.
- **BREAKING** `web` stops publishing a host port. It is reached at `web:8080` over the Compose network and nowhere else. Two public ports serving overlapping things is a deployment waiting to disagree with itself; the front door is now one door. `FRENCH_TOLLS_PORT` moves to `nginx`, so the address a browser uses does not change.
- `www/` is copied into the nginx image at build time. What ships is what was built, and a deployment carries one image rather than an image plus a directory that has to arrive with it.
- The new service sits behind the same `app` profile as `web` and `bot`, so a plain `docker compose up` still starts the two routers and nothing else.

### The page stops saying a toll was free when it does not know

- **BREAKING** A passage carrying `cost: null` renders as a marker rather than `0,00 €`, with the `reason` the API already sends shown on hover. Only a passage with a real amount is formatted as currency.
- No other change to the page. The map, the autocomplete, the deep-link hash, the route panel and the Google Maps links behave as they do today.

### The page's contract with the API is written down

The page reads `nodes`, `duration`, `cost`, `distance`, `peages[].name`, `peages[].cost`, and the three Google Maps URL keys. Those keys were kept compatible through the algorithm rewrite on the strength of an argument about a consumer nobody in this repository could see. The consumer is here now, and what it reads becomes a requirement rather than an assumption.

## Capabilities

### New Capabilities

- `web-front-end`: what `www/` holds, how it is built into an image and served, why the page and the API must share an origin, the proxy that makes that true, and the two rules the page itself must follow — currency only for a real amount, and the deep link it accepts.

### Modified Capabilities

- `route-service`: the requirement listing the Compose services names three built from one image, with `web` publishing a host port. There are now four, one of them built from a different image, and `web` publishes nothing.
- `build-pipeline`: the project layout requirement places the pipeline under `builder/`, its artefacts under `data/`, and the application under `french_tolls/`. It does not account for `www/`.

## Impact

- New: `www/Dockerfile`, `www/nginx.conf`.
- Modified: `www/index.js` — the passage cost formatting only.
- Modified: `docker-compose.yml` (an `nginx` service; `web` loses its `ports`), `Makefile` (`web` brings up the front end too), `.env.example` (`FRENCH_TOLLS_PORT` now describes the nginx port).
- Unchanged: every Python module. `api.py` keeps its two routes and gains no static handler — nginx serves the files, so the application does not have to know they exist.
- Unchanged: `www/index.html` and `www/style.css`.
- Deployment: the browser-facing address stays `127.0.0.1:${FRENCH_TOLLS_PORT}`, but it is answered by `nginx` rather than by `web`. Anything pointing at the aiohttp port directly must be repointed.
- Not addressed: `index.html` embeds a Google Maps API key and a Swetrix site id. Both are client-side identifiers that a browser receives anyway, and restricting them is a matter for those services' own consoles rather than for this repository. Serving the page from here does not expose anything a visitor could not already read.
