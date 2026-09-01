## Why

A booth the override file types `absent_enter` or `absent_exit` has no gare, and its passage cannot be sent to the rate service. `build_vinci_prices` therefore drops the whole route that crosses one: omitting only that passage would leave the neighbouring gare paired with a partner the vehicle never drove.

The route search does not know this. `builder/build_route_set.py` loads the override file at line 889 and never reads it. So the search treats such a booth as a coverage target, buys a route to reach it, and lets other routes cross it incidentally. Every priceable booth on those routes is then thrown away with them.

In the current route set, 7 of 786 routes are unaskable for this reason. They are the only cover of 7 booths that do have a gare, so those 7 booths carry no price. A rebuild of the route set moves which 7. Comparing the committed price file against a clean rebuild, 5 booths lost their entries and 4 gained one, entirely through this mechanism — including two entrances that between them carried 66 tariffs.

The route set spends routes on booths that can never be priced, and loses priceable booths to those same routes.

## What Changes

Three edits, all in `builder/build_route_set.py`, each closing one hole:

- **A blocking booth is not a coverage target.** The search stops buying routes to reach one. One of the seven routes exists only for this reason and disappears.
- **A route that traverses a blocking booth is not selectable.** Removing the target does not stop a route crossing the booth on its way elsewhere: `covers` is derived from the driven path, and `greedy_select` scores a candidate on marginal gain alone. One of the seven is exactly such an incidental crossing. This closes the other six.
- **A resumed route that traverses a blocking booth is discarded.** `load_existing` re-queries prior routes and keeps every one that covers anything, with no gain test. Without this the seven already on disk survive the change, and the targets they strand are never searched for again.

`covers` keeps recording every booth traversed, blocking booths included. The rejection is a selection rule, not an edit to the record. A route that reaches the output still describes the drive it made, and the existing guard in `build_vinci_prices` stays as the backstop that proves the two steps agree.

The blocking set is read from `data/osm_toll_booths_overrides.yaml`. No new override key, no data migration, no change to the price file format.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `route-set-generation`: a booth typed `absent_enter` or `absent_exit` is no longer a coverage target; a candidate or resumed route that traverses one is not selectable; the uncovered report no longer names such booths.
- `toll-booth-inventory`: "an `absent_*` booth remains a coverage target" narrows to `absent_passthrough`. The claim that nothing consumes the enter/exit/passthrough distinction is no longer true and is removed.

## Impact

- `builder/build_route_set.py` — `coverage_targets`, `cover_many`, `load_existing`, and `main`.
- `builder/overrides.py` — the blocking pair moves here from `build_vinci_prices.py` so both steps read one definition. The header comment stating that a route set keeps every `absent_*` booth, and that nothing consumes the suffix, becomes wrong and is corrected.
- `builder/build_vinci_prices.py` — `BLOCKING_ABSENT` becomes an import. No behaviour change; the guard stays.
- `data/route_set.yaml` and `data/uncovered_booths.json` are regenerated. `data/vinci_price.yaml`, `data/vinci_toll_booth.yaml` and the segment weights follow.

**Ulys request budget.** Run this with `make update_route_set`, not `make clean`. The update path keeps the routes already on disk, drops the seven, and searches only for the targets they freed. That costs a handful of new routes to map and price. A clean rebuild would cost roughly 24,000 requests and is not needed.

## Non-goals

- **Coverage redundancy.** 823 of 1256 booths that have a gare are covered by exactly one route, and 160 of those sit one position away from a passage the service will not price. That is a separate and larger question about what the route set optimises for.
- **Pruning the ratchet.** `load_existing` keeping every route that covers anything is left alone except for the blocking case. Trimming routes that have become redundant is out of scope.
- **The two blocked booths at the border.** Chanas, Bernay and Hochfelden stay in the inventory and in `covers`. Nothing here tries to find gares for them.
