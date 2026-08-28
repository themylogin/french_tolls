## 1. The front end image

- [x] 1.1 Write `www/nginx.conf` serving the page from the image and proxying `/api/` to `web:8080`, with `try_files ... =404` rather than a single-page fallback and a proxy read timeout of 60 s; verify `nginx -t` accepts it
- [x] 1.2 Write `www/Dockerfile` on an nginx image, copying the page in at build time and installing the config; verify the built image holds `index.html`, `index.js`, and `style.css` under the served root and nothing else
- [x] 1.3 Write `www/.dockerignore` excluding the Dockerfile, the nginx config, and any editor droppings; verify neither the Dockerfile nor the config is reachable as a URL from the running container
- [x] 1.4 Set cache headers — `no-cache` for `index.html`, a long `max-age` for `.js` and `.css`; verify with a request for each that the headers differ as intended

## 2. Wiring it up

- [x] 2.1 Add the `nginx` service to `docker-compose.yml` under the `app` profile, building from `./www`, publishing `127.0.0.1:${FRENCH_TOLLS_PORT:-8080}:80`, and depending on nothing it cannot start without; verify `docker compose config` parses and places it in the `app` profile
- [x] 2.2 Remove the `ports` mapping from the `web` service; verify `docker compose --profile app config` shows a published port for `nginx` and none for `web`, `bot`, or `tests`
- [x] 2.3 Update the `FRENCH_TOLLS_PORT` comment in `.env.example` to say it is the front end's port and that the API is no longer published; verify every variable the four services interpolate is still documented
- [x] 2.4 Make `make web` bring up the front end alongside the application, and confirm `make bot` and `make test` are unaffected; verify `make -n web` prints the expected invocations
- [x] 2.5 Confirm a plain `docker compose up` still starts only `osrm-toll` and `osrm-optimal`; verify with `docker compose config --services`

## 3. The cost cell

- [x] 3.1 Change the passage cost in `www/index.js` to render an em dash carrying the API's `reason` when `cost` is null or undefined, and currency otherwise, checking against null and undefined rather than falsiness; verify a cost of `0` still renders `0,00 €`
- [x] 3.2 Confirm nothing else in the page was touched; verify `index.html` and `style.css` are byte-identical to what was there before, and that the only edit to `index.js` is the cost cell

## 4. Verification

- [x] 4.1 Bring the stack up and fetch the page over the published port; verify `index.html`, `index.js`, and `style.css` all return 200 with the right content types
- [x] 4.2 Calculate Lyon → Paris through the proxy; verify `/api/calculate` returns both routes through nginx and that the response is the same one the application returns directly
- [x] 4.3 Load the page in a browser and calculate that route; verified: the user loaded the page from the published port and confirmed it works. Checked here without a browser by running the page's own `showRoute` over a live API answer — the summary shows 5h 54min / 16,90 € / 505 km and 4h 56min / 41,30 € / 465 km, the passage table lists all five optimal passages with the two unpriced gantries as dashes, and the three Google Maps links carry the right origin, destination and waypoints
- [x] 4.4 Confirm an unpriced passage renders as a dash and not as `0,00 €`; verify on the Lyon → Paris optimal route, which carries two unpriced gantries, and confirm the reason is readable on the row
- [x] 4.5 Confirm `/api/autocomplete` is reachable through the proxy; verify a query returns predictions, or a clear failure if no LocationIQ key is configured
- [x] 4.6 Open a deep link of the shape the bot produces; verify the page fills both fields and calculates that route unaided
- [x] 4.7 Confirm the aiohttp port is no longer published and the page is served only by nginx; verify with `docker compose ps` and a request to the old port
- [x] 4.8 Run the unit suite and confirm it is unaffected; verify 47 tests still pass
