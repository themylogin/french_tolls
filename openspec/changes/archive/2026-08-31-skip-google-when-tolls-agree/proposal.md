## Why

When the optimal route and the fastest route cross the same toll booths, there is nothing for a waypoint to correct and nothing for Google to tell us. The journey costs what it costs by either road, so the plain directions link between the two points is already the right answer.

The flow pays for that answer anyway. Today any part with a non-zero cost goes straight to rule 3 and buys at least one Google request, and may buy a second and then split into as many as four links. Perpignan → Béziers is the case: measured against the running service on 2026-08-31, the fast and the optimal routes both cost 9.10 EUR, both cross booths `1676618837` and `2398039585`, and the optimal route needs no waypoints at all. The driver is asked to press through parts of a journey that has one road.

## What Changes

- The drive decision gains a rule between "pays no tolls" and "budget exhausted": **the fastest route crosses exactly the booths the optimal route crosses**. The part is answered with a directions link from the driver's current location straight to its destination, carrying no waypoints, and **no Google request is made**.
- The rule tests booth sets for equality, not cost. Two routes that cross the same booths cost the same, and the booth set is the finer fact.
- The decision's `Part` gains the fastest route's booth set, so the rule has both sides to compare. The bot reads it from the `booths` key the service answer already carries on the fast route; nothing new is computed and no new request is issued.
- A link accepted this way is recorded under its own basis, so an operator reading the log can tell it from a link accepted on tolls Google was actually asked about. One cost a request and the other did not.
- The unit suite gains tests for the new rule: that it fires, that it sends no waypoints, that it makes no request, that toll-free still wins when both would match, and that a difference of one booth falls through to the existing rules.
- The integration suite gains a pinned journey, Perpignan → Béziers, pinned at zero paid requests and one part.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `telegram-drive-flow`: the ordered decision gains a rule, and the ordering against the toll-free rule is stated.
- `drive-flow-integration-tests`: the pinned journeys gain one for the new outcome.

## Impact

- `french_tolls/drive.py` — `Part` gains a field, `_part` gains the rule, a basis constant is added.
- `french_tolls/bot.py` — `part_of` reads the fast route's booths; `send_outcome` names the new basis in its log line.
- `french_tolls/tests/test_drive.py` — tests for the rule and its ordering.
- `french_tolls/integration/journeys.py`, `french_tolls/integration/test_drive_flow.py` — the pinned journey.
- `french_tolls/integration/cassettes/` — a recording holding no answers for the new journey, as `toll-free.json` already does. No Google request is made and none is replayed.
- `french_tolls/route.py` is unchanged: the answer already carries `booths` for both routes.
- Not addressed: the evaluation. `evaluation/` measures how faithfully Google follows our road and does not run this decision.
