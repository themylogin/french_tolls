## Context

See `proposal.md` — Why. The constraints that shape the approach:

- `service.get_route` has two callers: `api.calculate` and `bot.py`. The bot must not start buying Google requests, so anything that spends money cannot go into `get_route`.
- `www/index.js:286` already calls `showGoogleRoute` unconditionally after a successful calculation. The page has never known whether debug is on; the server answers `{"nodes": []}` when it is off and the page draws nothing. The signal already lives on the server side, which is what makes moving it onto the answer a small change.
- `Routers` is constructed in exactly three places in the application, all of the form `async with osrm.session() as session: ... Routers(session)`. **A fourth construction is in the tests and was missed when this was first written:** `test_equivalence.py`'s `Recorded(Routers)` calls `super().__init__(session=None)` — it never wanted a session, it passed a null one because the parameter existed. It drops the argument. `test_waypoints.py` uses its own `FakeRouters` and is unaffected.
- The recorded integration suite drives the bot end to end. It exercises `refine.refine` through the drive flow, not through `/api/refine`, so removing the endpoint does not touch it.

## Goals / Non-Goals

**Goals:**

- One HTTP request per journey from the page, and one local route search behind it.
- An answer whose shape says whether there is an overlay to draw, without the page reading configuration.
- A router client with no state between requests and no failure mode that exists to be retried.

**Non-Goals:**

- Changing how a refinement is computed, ranked, or paid for. `refine.refine` is untouched.
- Changing what a route answer's `fast` and `optimal` carry.
- Trimming `Refinement.as_dict`. Named as not addressed in the proposal.
- Any change to the bot, which reaches `refine.refine` directly.

## Decisions

### The refinement is added in `api.calculate`, not in `service.get_route`

`get_route` is what the bot calls for every journey a driver sends. Putting the refinement inside it would make the bot buy two Google requests per message, against a ceiling sized for deliberate use.

So the debug branch lives in the API handler, which is the layer that already knows it is serving the page:

```python
async def calculate(request):
    data = await request.json()
    answer = await get_route(data["from"], data["to"])

    if config.debug:
        refinement = await refine_module.refine(
            data["from"], data["to"], answer["optimal"], with_geometry=True)
        answer["google"] = {...}

    return web.json_response(answer)
```

*Alternative considered:* a `with_refinement=` flag on `get_route`. Rejected — it makes the function's cost depend on an argument, and the one place that would pass it is the one place that can just do the work.

### `refined_link` is deleted rather than reused

It exists to bundle `get_route`, `refine.refine` and a Google Maps link built from the refined waypoints. The handler above needs the first two and not the third: nothing reads `url`, and `google_url` on the answer already gives a consumer a direct address built from the route's own geometry.

Deleting it also removes the second `get_route` call, which is where the duplicated search came from.

### The key is `google`, absent when debug is off

Named for what it holds — Google's own route — rather than `refinement`, which describes the process rather than the content.

Absent rather than `{"nodes": []}`. An empty list conflates two facts the page renders differently: "the operator did not turn this on", which needs no explanation, and "there was nothing to draw", which carries a `reason` worth showing. Today the page cannot tell them apart and shows `data.reason || ""`, which silently works only because the off case has no reason. Presence-or-absence makes the distinction structural.

Beside `fast` and `optimal`, not inside `optimal`. `web-front-end` records the keys it reads *from each of the two routes*; a key that appears on one and not the other would break that reading.

Carried: `nodes`, `waypoints`, `added`, `reason` — exactly what the page draws from. Not carried: `url`, and the `ours` block whose `distance`, `duration` and `waypoints` are already on `optimal` in the same response.

### `Routers` opens a session per request

```python
async def _get(self, base, path, params):
    ...
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_S)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as resp:
            body = await resp.json(content_type=None)
```

The timeout moves from the shared session onto the per-request one, unchanged in value and meaning.

`CONNECTION_RETRIES`, the `for attempt in range(...)` loop and its comment go. `aiohttp.ClientConnectionError` is no longer special: it falls into the same `except aiohttp.ClientError` that already raises `RouterUnavailable`.

*Alternative considered:* keeping the shared session and setting `TCPConnector(force_close=True)`. It removes the pooling and therefore the retry, but keeps `osrm.session()`, the `session` parameter and the three `async with` blocks — the plumbing without the thing it was for.

*Alternative considered:* one module-level session for the process. That is more pooling, not less, and it would need a shutdown hook to close cleanly.

### `Routers.__init__` drops its first argument

`Routers(session, budget=...)` becomes `Routers(budget=...)`. The three call sites lose their `async with` wrapper:

| File | Before | After |
|---|---|---|
| `route.py:39` | `async with osrm.session() as s: Routers(s).distance_to_network(...)` | `await osrm.Routers().distance_to_network(...)` |
| `service.py:176` | `async with osrm.session() as s: routers = Routers(s)` | `routers = Routers()` |
| `service.py:229` | `async with osrm.session() as s: equivalence.booths_of(Routers(s), ...)` | `equivalence.booths_of(Routers(), ...)` |

`service.py:176` is inside the `try` that maps router failures onto `RouteError`; removing the `async with` must not change what that block covers.

## Risks / Trade-offs

**327 TCP connections on the dearest journey instead of a handful → more syscalls and more sockets in TIME_WAIT.** Measured, not assumed, and it did not show up: both arms interleaved in one process, a connection per request came out 17% faster on one run and 1% slower on the next. The routers answer in 2–11 ms on the same host, so the handshakes are lost in the routing.

**A first attempt at this measurement was wrong and is worth recording.** Comparing a warm long-running container over HTTP against a fresh `docker compose run` calling `get_route` directly showed 0.80 s against 1.15 s, and that gap was read as the cost of dropping the pool. It was the difference between the two harnesses. Pooling was restored on the strength of it and removed again once the arms were interleaved in one process. Measure both arms the same way, in the same process, or do not quote a number.

**A transient connection failure now fails the journey.** That is the point — it is one failure mode instead of two — but it is a real behaviour change: what used to be retried silently now reaches the user as `router_unavailable`. Without pooling there is no idle connection for the server to close, so the case the retry existed for should not arise.

**Debug mode now spends inside the calculate request.** The page's calculation takes as long as the two Google requests do, where the overlay used to arrive separately and the routes drew immediately. With debug off nothing changes. Worth knowing before turning the setting on for a session where responsiveness matters.

**`google` could collide with a future key on the answer.** The answer already carries `google_url` on each route; `google` at the top level is distinct and neither shadows the other.

## Migration Plan

No data migration and no deployment ordering. The page and the API ship in one image and are deployed together; a browser holding the old `index.js` against the new API would call `/api/refine` and get a 404, which its `.catch` already renders as "Could not reach Google for this route." A reload fixes it.

Rollback is the previous image.
