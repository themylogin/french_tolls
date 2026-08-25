## Why

The direct pricing step constructs entrance/exit pairings rather than observing them, and it has no way to check that a two-way booth is acting as the end it is being used as. It treats any `bidirectional` group as both a source and a target, whichever way a route happens to leave it.

That is why 15 of its 17 `unexpected answer` findings are pairs of two-way booths: the operator answered with two standalone barrier charges because the pairing it was asked about is not a journey anyone drives.

`data/bidirectional_booth_sides.yaml` now says which side of each two-way booth is the toll network. Applying it turns "is this booth two-way" into the question that matters — "does this route leave it on the side that makes it an entrance".

## What Changes

- The step reads `data/bidirectional_booth_sides.yaml`.
- A **barrier** — a two-way booth whose every side agrees — is never a source and never a target. You pay passing it and your ticket state does not change, so it cannot be one end of a ticket. Two booths leave the grid on each side.
- For a two-way **source**, the route must depart the booth toward a node in `inside_nodes`. Leaving by the free side means the booth was not an entrance on that journey.
- For a two-way **target**, the route must arrive at the booth from a node in `inside_nodes`. Arriving from the free side means it was not an exit.
- A pair failing either test is recorded in the rejection database with a reason distinguishing it from a pair with a booth in the way. Both are "not a ticket"; only one is about a third booth.
- **BREAKING** the rejection database gains a `reason` column and `blocker` becomes nullable. A wrong-side rejection names no booth.
- The 4 027 prices already recorded with a two-way booth at either end are discarded and re-derived under the rule.

## Capabilities

### Modified Capabilities

- `vinci-direct-pricing`: the grid excludes barriers; a clean route is additionally required to use the inside side at each two-way end; the rejection record gains a reason.

## Impact

- **Modified**: `builder/build_vinci_direct_prices.py`, `data/vinci_routes_rejected.sqlite3` schema, `data/vinci_price.yaml`.
- **Depends on**: `label-bidirectional-booth-sides`, which produces the sides and must be applied first.
- **Unaffected**: steps 1 to 7. The sides are read, not written.
- **Cost**: about 4 027 rate requests to re-derive the discarded prices, roughly 67 minutes, plus the routing of whatever the rule newly rejects. Pairs untouched by a two-way booth keep their prices and are not re-asked.
- **Expected**: the 15 two-way `unexpected answer` findings become ordinary rejections rather than stops.
