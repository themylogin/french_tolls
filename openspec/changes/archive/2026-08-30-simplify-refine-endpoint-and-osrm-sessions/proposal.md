## Why

Two pieces of machinery that no longer earn what they cost.

**`/api/refine` is a second endpoint for one page load.** The page calculates a journey, then immediately asks a second time for the same journey's refinement — `www/index.js:286` calls `showGoogleRoute` right after `/api/calculate` returns, unconditionally. The second request re-routes the journey from nothing to get back to the same optimal route, because `refined_link` calls `get_route` again. Two POSTs, two full local searches, for one thing a visitor asked for once.

It also sends fields nobody reads. The page reads `nodes`, `reason`, `added` and `waypoints`. The endpoint additionally returns `url` and an `ours` block of `distance`, `duration` and `waypoints` — dead on arrival since the page stopped showing a directions link of its own.

**The routers' session is threaded through everything to be pooled, and the pooling then needs a retry loop.** `osrm.session()` makes one `aiohttp.ClientSession` per journey; it is passed to `Routers(...)` and threaded through three call sites. Keep-alive is what that buys, and keep-alive is also what makes the server drop a connection mid-search — so `_get` carries `CONNECTION_RETRIES`, a three-attempt loop, and six lines of comment explaining that a dropped pooled connection is not a real failure. The complication exists to serve the optimisation, and the optimisation is for a container on the same Compose network answering in 2–11 ms.

## What Changes

### The refinement rides along with the answer

- **BREAKING** `POST /api/refine` is removed. `www/index.js` stops calling it and `showGoogleRoute` goes with it.
- In debug mode, `POST /api/calculate` SHALL carry a `google` key alongside `fast` and `optimal`, holding what the page draws: `nodes`, `waypoints`, `added`, `reason`.
- Out of debug mode the key SHALL be absent. The page draws the overlay when it is there and does not when it is not, which is the same rule it follows today against an empty `nodes` list.
- `url` and `ours` are not carried over. Nothing reads them.
- **The spend is unchanged.** Today the page buys a refinement on every calculation with debug on; it will buy one on every calculation with debug on. One local route search per journey is saved, not one Google request.
- `service.refined_link` loses its only caller and is removed. The Google Maps link it built from the refined waypoints is not read by anything.

### A router request opens its own connection

- **BREAKING (internal)** `osrm.session()` is removed, along with the `session` argument to `Routers.__init__` and the three `async with osrm.session()` blocks in `service.py` and `route.py`.
- `Routers._get` opens its own `aiohttp.ClientSession` per request. Nothing is pooled between requests, so nothing has to survive a pooled connection being closed.
- `CONNECTION_RETRIES`, the retry loop and its comment go with it. A connection error becomes `RouterUnavailable` on the first failure, which is what every other client error already does.
- The request timeout stays. It moves from the shared session onto each request.
- **The pooling bought nothing measurable here, and that was measured rather than assumed.** Strasbourg to Nantes, 327 requests, both arms interleaved in one process so machine load hits each equally: a connection per request came out **17% faster** on one run and **1% slower** on the next. The routers are on the same host and answer in 2–11 ms, so 327 local handshakes disappear into the noise of the routing itself.

## Capabilities

### Modified Capabilities

- `google-route-refinement`: the refinement stops being reachable at its own endpoint and becomes part of the route answer.
- `web-front-end`: the page makes one request per journey rather than two, and draws the overlay from a key on the answer rather than from a second reply.
- `route-service`: the answer gains a debug-only `google` key, and the API loses a route.

## Impact

- Removed: `api.refine` and the `/api/refine` route, `service.refined_link`, `service.maps_link_with` (a pass-through wrapper with no callers, dead before this change), `osrm.session`, `osrm.CONNECTION_RETRIES` and the retry loop, `www/index.js`'s `showGoogleRoute`.
- Modified: `french_tolls/api.py` (`calculate` gains the debug branch), `french_tolls/osrm.py` (a connection per request, no retry), `french_tolls/service.py` (`refined_link` and `maps_link_with` gone, two call sites drop the session block), `french_tolls/route.py` (one call site), `www/index.js` (draw from `data.google`).
- Unchanged: `refine.refine` and everything about how a refinement is computed and paid for; `get_route`; the bot, which never called `/api/refine` and does its own refining through `refine.refine`.
- **One fewer local route search per debug page load.** A few hundred router requests, about a second, per calculation.
- **A transient connection failure now fails the journey** rather than being retried silently. Without the retry there is one failure mode instead of two.
- Not addressed: whether `Refinement.as_dict` should shrink to the four fields the page reads. It is also returned by nothing else now, but trimming it is a separate change and `preference` in particular is checked by the integration cassettes.
