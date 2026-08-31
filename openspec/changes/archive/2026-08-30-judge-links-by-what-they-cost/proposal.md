## Why

A link is judged by whether Google drove the same road. The driver cares whether they pay the same tolls. Those are not the same question, and the gap is large.

Measured over 205 journeys: **72 of the 100 that fall below the 0.98 overlap line cross an identical set of toll booths.** Every one is refined today, and under the drive flow may be split into two, three or four links a driver has to open in sequence — for a difference that costs them nothing.

Portes-lès-Valence to Saint-Gaudens is the plain case. 530 km, a quarter of it on different roads, the same four booths, the same €5.60.

The rule is also wrong the other way: **5 journeys at or above 0.98 cross different booths**, three of them costing the driver €4.40 more than we told them.

## What Changes

### A link is judged by the tolls it pays

- **BREAKING** The drive flow SHALL accept Google's route when it crosses no toll booth the optimal route does not. Overlap stops being the test and becomes a diagnostic the report still prints.
- The test SHALL be **containment, not equality**. A Google route crossing strictly fewer of our booths costs the driver less and is not a reason to spend a request correcting it; a route crossing one of ours *plus another* costs them money they did not agree to and is.
- Where the tolls cannot be established — the route could not be matched, or the trace broke — the system SHALL fall back to the overlap test rather than accept. Not knowing is not the same as agreeing.

### Google's route is priced by map-matching it

- Google returns geometry, not node ids, and this project prices a route from node ids. The route SHALL be matched onto the untouched graph to recover them, and priced by the accounting `journey-toll-accounting` already defines, aliases and all.
- **The whole trace SHALL be matched in one request.** Matching it in windows was the single cause of every wrong answer found while investigating this: a window is matched with no knowledge of what came before it, so at a boundary the matcher is free to start on a slip road. Near LEZIGNAN it produced a 400 m out-and-back that skipped the plaza and lost €13.70.
- **Each leg's repeated head node SHALL be dropped.** An OSRM leg re-announces the node before its own start, because the tracepoint snapped partway along a segment — the same behaviour `waypoint-route-search` already forgives when it verifies a leg. Kept, it turns one plaza crossing into two tickets. It cost three phantom crossings and €3.00 on a journey whose geometry was identical to ours.
- **Consequence:** `osrm-toll` needs its matching size raised. The default admits 100 coordinates and a long route's trace is tens of thousands.

### The parts of a split journey stop calling themselves the first half

- **BREAKING** The message announcing a part SHALL describe it as the next part, not as the first half.
- A journey can be halved twice. Embrun to Ancenis-Saint-Géréon resolves into three links, and each said "here is the first half of the route" — about the first half, then about a quarter of it, then about the far half, the last two to a driver who had already driven a part.
- It cannot be fixed by numbering. Splitting is lazy, so when the message is written the system does not yet know how many parts there will be.
- *Already applied*, with a test. Recorded here because it is a defect in `telegram-drive-flow` as archived, against a requirement that each message carry the link for the part it describes.

## Capabilities

### New Capabilities

- `toll-equivalence`: what it means for two routes to cost a driver the same, how Google's geometry is turned into the booths it crosses, and what happens when that cannot be established.

### Modified Capabilities

- `telegram-drive-flow`: what the drive flow accepts, and how a part of a split journey describes itself.
- `google-route-refinement`: the fit share stops being the sole criterion and becomes one of two.
- `route-service`: `osrm-toll` is started with a matching size a real trace fits in.

## Impact

- Modified: `french_tolls/drive.py` (the acceptance test, the wording), `french_tolls/refine.py` or a new module (matching and pricing Google's route), `french_tolls/osrm.py` (a match request), `docker-compose.yml` (`--max-matching-size`).
- Unchanged: the waypoint search, the pipeline, toll accounting, and how a route is priced. This asks the existing accounting a new question; it does not change the answer.
- **Fewer paid Google requests.** A journey accepted on tolls is one that buys no correction and no split. On the sample that is 72 of every 100 below the line.
- **More local work.** Matching a trace costs about 1.6 s against `osrm-toll`, once per part, on top of the routing already there. It buys no Google request, so it trades latency for money.
- **`osrm-toll` accepts a much larger match request.** Nothing else changes about the service, but the ceiling exists to bound what one call can cost the router.
- Not addressed: whether the *evaluation* should report toll equivalence beside overlap. It would make the report describe what the bot decides on, and it is a separate change.
