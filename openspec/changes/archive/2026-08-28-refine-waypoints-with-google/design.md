## Context

See `proposal.md` — Why. What is already in place:

- `evaluation/prototype_reinsert.py` implements the drift-to-waypoint step and has been run against the bought Bayeux–Apt answer: 17 stretches outside a 50 m corridor, 258.6 km of drift, and two waypoints placed at 48.364290,0.566290 and 46.341340,3.381880. The algorithm is not speculative; it is prototyped and its output has been read.
- `evaluation/geometry.py` holds the corridor measure, the grid index, and the polyline codec. All three are needed by the application now.
- `evaluation/fetch_google_routes.py` holds a working Routes API client with the right request body.
- `french_tolls/service.py` builds the three links and caches answers as JSON files under `/cache/<fingerprint>/`.
- `french_tolls/autocomplete.py` opens `/cache/autocomplete.sqlite` per request, creating its table on the fly.
- `french_tolls/google_debug.py` and `GOOGLE_DIRECTIONS_DEBUG` exist and are removed by this change.
- `api.py` has never been modified by this project. It gains two routes here.

## Goals / Non-Goals

**Goals:**

- A link that sends a driver down the road we meant, where Google can be persuaded and afforded.
- At most two Google requests per journey, ever — one to correct the waypoints, one more only if someone looks at the result — and a hard monthly ceiling.
- A page control that shows what Google did, without an operator flag.

**Non-Goals:**

- Iterating. There is one correction pass: the second request draws the result, it does not correct it again. The stretches the waypoint budget could not cover stay uncorrected, and buying a further round is a separate decision with a separate bill.
- Changing the waypoint search. It keeps its contract — the fastest route on our own graph — and this adds a second stage after it rather than altering it.
- Refining for the bot at send time. The bot's links are refined when they are followed, not when they are written, so a link nobody clicks costs nothing.
- Migrating the existing file cache. Recomputing an answer takes under a second.

## Decisions

### Shared code moves to a package both sides import

`geometry.py` is needed by the application and by the evaluation, and the two run in different images. Copying it would let the corridor measure drift between the thing that refines and the thing that measures whether refining worked — the one place where an inconsistency would be invisible and fatal.

So it moves to `french_tolls/geometry.py`, and `evaluation/` imports it by mounting the package. The evaluation image already runs Python; it gains the package on its path rather than a copy of one file.

*Alternative rejected:* leaving a copy in each. Two corridors that disagree would make the report say the refinement worked when it did not.

### One database, four tables

`/cache/database.db`, opened by a small module both `autocomplete.py` and `service.py` use.

| table | key | holds |
| --- | --- | --- |
| `autocomplete` | `q` | the LocationIQ response, as today |
| `google_requests` | `year_month` | how many paid requests that month |
| `routes` | `fingerprint, from_lon, from_lat, to_lon, to_lat` | the answer |
| `refinements` | same | the refined waypoints, the set the drawn route was driven through, that route's geometry, faithfulness before and after |

`journal_mode=WAL` and a busy timeout, because the aiohttp application is single-threaded but the redirect and the API can both be in flight, and the evaluation may be reading at the same time.

SQLite calls are blocking and this is an async application. They are milliseconds against a route search of hundreds of them, so they run inline rather than in an executor; a note in the module says so, and says what would change if the service ever became busy enough to care.

The count is incremented in the same transaction that reserves the request, and committed **before** the HTTP call. A request that fails has still been made and may still have been billed, so the count must be able to overstate and never understate.

### The refinement, end to end

Two phases, because a link and a picture want different things and cost differently.

**First phase** — what a redirect needs:

1. Compute the answer as today: optimal route, waypoints, tolls.
2. If a stored refinement matches the journey and fingerprint, use it. Stop.
3. Waypoint budget = 9 − waypoints needed. If zero, stop, and say so.
4. Reserve a request against the month. If the month is spent, stop, and say so.
5. Ask Google to drive our waypoints.
6. Find drift stretches outside the 50 m corridor; rank by length; take the top *budget*.
7. For each, locate the bypassed portion of our route by its two ends and place a waypoint at that portion's midpoint.
8. Merge in driven order; store; return. **No geometry is kept**: the route just measured is the route through the *old* waypoints, and it is not the one the link now produces.

**Second phase** — only when a caller asks for something to draw:

9. Reserve another request; ask Google to drive the *refined* waypoints; store that geometry.

Step 9 cannot be folded into step 5. The route through the refined waypoints does not exist until it is asked for, and step 5's whole purpose is to find where that route will differ. Returning step 5's geometry alongside step 8's waypoints was the first implementation, and it put every added waypoint visibly off the drawn line — which is exactly where they were computed to go.

Where step 7 finds nothing to add, step 5's route *is* the route the link produces, so its geometry is kept and the second phase never happens.

Step 7 is the prototype, unchanged.

### Two endpoints

`POST /api/refine` — body `{"from": [lon, lat], "to": [lon, lat]}`, returns the refined link, the refined waypoints, Google's geometry through *those* waypoints, and which budgets applied. This is what the page's control calls, and the only caller that asks for geometry — so the only one that buys the second request.

`GET /go/{form}?from=lon,lat&to=lon,lat` — computes and 302s to Google Maps. `form` is one of `start`, `here`, `here-via-start`, matching the three link keys.

A redirect rather than a link built at send time, because the bot writes a link long before anyone follows it, and refining at send time would pay for every link nobody clicks. The cost is that a followed link waits for us: a cached journey redirects in milliseconds, an uncached one in about a second, and one that also asks Google in about two. A redirect never buys geometry, so following a link costs one request at most.

The three link keys become `{PUBLIC_SITE_URL}/go/{form}?...`. `PUBLIC_SITE_URL` already exists, used by the evaluation's report.

### The page's control

The `<i class="bi bi-sign-turn-right">` beside each link gains `cursor: pointer`, a title, and a click handler that calls `/api/refine` and draws the returned geometry. The overlay drawing, the orange, and the waypoint dots already exist from the debug work; what changes is what triggers them and where the data comes from.

`google_debug.py` and its flag go. The overlay is no longer "what the evaluation happened to have bought for this journey" but "what Google says about this journey", which is both more useful and available for every journey rather than 2 450 of them.

### What is not refined

`url_from_current_location` and `url_from_current_location_through_start` start from a place we do not know. The refinement is computed once for the route's own origin to its destination, and all three forms carry the same refined intermediate waypoints — which is exactly what the three links already do with the unrefined ones.

## Risks / Trade-offs

- **A link that used to reach Google now depends on us.** A dead service means dead links in every message the bot has ever sent. → The direct Google link is returned alongside for any consumer that prefers it, and the redirect falls back to the unrefined link rather than erroring. It does not mitigate the service being down, which is a real reduction in the durability of a sent link and is stated in the proposal as breaking.
- **Refinement makes the link worse.** Nothing guarantees the extra waypoints help; Google may route around them differently. → Measurable, and the corpus of 20 pre-refinement journeys is the baseline. The first thing to do after this lands is re-measure Bayeux–Apt and see whether 74.4% moved.
- **The monthly ceiling is a denial-of-service on refinement.** Anyone can spend it by asking for distinct journeys. → Bounded by construction: the ceiling is the ceiling. Beyond it the service answers unrefined, which is what it does today.
- **Blocking SQLite in the event loop.** → Milliseconds against a route search of hundreds; noted in the module, and an executor is the fix if it ever matters.
- **The count can overstate.** Deliberately: a request that failed may still have been billed.
- **Two spenders, one key.** The evaluation and the application share `GOOGLE_DIRECTIONS_API_KEY` and neither sees the other's spending. → Stated in `google-route-comparison`; the evaluation's guard is a per-run prompt and the application's is a monthly ceiling, and they bound different things.

## Migration Plan

1. Move `geometry.py` into `french_tolls/`, and put the package on the evaluation image's path. Confirm the report still produces the same numbers.
2. Add the database module; rename `autocomplete.sqlite` to `database.db` on first open where the old file exists.
3. Move route answers from files to the `routes` table. Delete `/cache/<fingerprint>/`.
4. Add the Google client, the refinement, and the two endpoints.
5. Change the three link keys; add the direct-link key.
6. Change the page's control; remove `google_debug.py` and the flag.
7. Verify with one real refinement of Bayeux–Apt, and compare its overlap against the 74.4% already measured.

Rollback is restoring the three link keys to direct Google addresses; everything else is additive or a cache.

## Open Questions

None. The corridor width, the nine-waypoint ceiling, and the placement rule are all settled by the prototype's measured output.
