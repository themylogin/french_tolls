## 1. The refinement rides with the answer

- [x] 1.1 Add the debug branch to `api.calculate`: call `refine_module.refine` with `answer["optimal"]` and `with_geometry=True`, and set `answer["google"]` to `nodes`, `waypoints`, `added` and `reason`; verify a calculation with `DEBUG=1` returns the key and one with `DEBUG=` does not return it at all
- [x] 1.2 Verify the refinement is built in the API layer and not in `service.get_route`: call `get_route` directly with `DEBUG=1` set and assert it makes no Google request and returns no `google` key, which is what keeps the bot from spending
- [x] 1.3 Verify the key sits beside `fast` and `optimal` rather than inside either, and that `fast` and `optimal` carry exactly the keys `web-front-end` records today
- [x] 1.4 Verify `google` carries no `url` and no `ours` block, and that the four fields it does carry hold what `/api/refine` returned for the same journey before this change

## 2. Removing the endpoint

- [x] 2.1 Delete `api.refine` and the `web.post("/api/refine", refine)` route; verify the API's routes are exactly `GET /api/autocomplete` and `POST /api/calculate`
- [x] 2.2 Verify a POST to `/api/refine` is no longer served
- [x] 2.3 Delete `service.refined_link` and drop `RouteError` and `refined_link` from `api.py`'s import where they are no longer used; verify `grep -rn "refined_link" french_tolls/` returns nothing and the package imports
- [x] 2.4 Verify the second `get_route` per debug page load is gone: with `DEBUG=1`, count the router requests for one calculation and confirm it is one search rather than two

## 3. The page

- [x] 3.1 Remove `showGoogleRoute` and its `fetch('/api/refine', ...)` from `www/index.js`, and the call to it at the end of `calculate`; verify `grep -n "api/refine" www/index.js` returns nothing
- [x] 3.2 Draw the overlay from `data.google` inside the existing `/api/calculate` handler, keeping the orange colour, the double width, the stacking order beneath the optimal route, and the two waypoint dot colours; verify the drawing code is unchanged in what it produces
- [x] 3.3 Treat an absent `data.google` as nothing to draw and not as an error; verify the page renders both routes normally with `DEBUG=` unset
- [x] 3.4 Keep the note behaviour: show `reason` when the key is present with no `nodes`, and clear it when a route is drawn; verify an exhausted budget still explains itself rather than silently drawing nothing
- [x] 3.5 Verify the overlay and its waypoint markers are still cleared when a new journey is calculated

## 4. A router request opens its own connection

- [x] 4.1 Open an `aiohttp.ClientSession` inside `Routers._get` with the existing `REQUEST_TIMEOUT_S`, and issue the request through it; verify a route query still answers
- [x] 4.2 Delete `osrm.session`, drop `session` from `Routers.__init__`, and remove it from `__all__` if listed; verify `grep -rn "osrm.session()" french_tolls/` returns nothing
- [x] 4.3 Update the three call sites — `route.py:39`, `service.py:176`, `service.py:229` — to construct `Routers()` with no session and no `async with`; verify `service.py:176`'s construction stays inside the `try` that maps router failures onto `RouteError`
- [x] 4.4 Delete `CONNECTION_RETRIES`, the `for attempt in range(...)` loop and its comment, letting `aiohttp.ClientConnectionError` fall into the existing `except aiohttp.ClientError`; verify a router that is not running fails as `router_unavailable` on the first attempt
- [x] 4.5 Verify a timeout still reports the router unavailable and still names the timeout in its message
- [x] 4.6 Verify `QUERY_BUDGET` is unchanged in value and still stops a search, and that the request count for a known journey is what it was before this change

## 5. Verification

- [x] 5.1 Unit suite passes, 117 tests. `FakeRouters` needed no change as expected, but `design.md`'s claim that no test depends on the session parameter was wrong: `test_equivalence.py`'s `Recorded(Routers)` called `super().__init__(session=None)` and failed 9 tests until it became `super().__init__()`.
- [x] 5.2 Run the recorded drive-flow suite; verify it passes, which exercises `refine.refine` through the bot rather than through the removed endpoint
- [x] 5.3 MEASURED, and the first measurement was wrong. Strasbourg to Nantes is 327 router requests, not 325. The first attempt compared a warm long-running container over HTTP (0.80 s) against a fresh `docker compose run` calling `get_route` directly (median 1.15 s) and reported +44% as the cost of dropping the pool; that was the difference between the two harnesses, not between the two arms. Re-measured with both arms interleaved in one process: **a connection per request was 17% faster on one run and 1% slower on the next.** It is noise at this size, so the pool is not worth its retry loop.
- [x] 5.4 With `DEBUG=1`, calculate a journey through the front end and verify one request is made, the orange route and both waypoint dot colours are drawn, and the month's count rises by exactly two
- [x] 5.5 With `DEBUG=` unset, calculate the same journey and verify no `google` key, no overlay, and no rise in the month's count
- [x] 5.6 Retire the documentation this makes false: `www/index.js`'s comment about the service storing the answer, and any comment or spec prose describing a second request for the refinement; verify by grep that nothing still describes `/api/refine`
