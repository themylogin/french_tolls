## Why

The refinement has a waypoint budget of nine less whatever the route already needs, and it spends that budget on the longest drift stretches. Bayeux to Apt finds seventeen stretches and can afford two. Length is the only thing that decides which two.

Length is not the only thing that matters. A driver follows the link from the beginning. A correction 900 km in is only worth what it is if the driver gets there, and a journey can be abandoned, interrupted, or re-requested from a new position long before that. A correction 50 km in is worth its full length, because every driver who follows the link at all drives through it.

The budget is therefore being spent as though every kilometre of the route were equally likely to be driven. Weighting each stretch by where it starts spends the same budget on the part of the route most likely to be used.

## What Changes

- The refinement ranks drift stretches by a weighted length rather than by raw length. The weight is `1.0 - (dist / total) / 2`, where `dist` is how far along the optimal route the bypassed portion starts and `total` is the optimal route's length. A stretch at the origin keeps its full length; a stretch at the destination counts for half.
- Both distances are measured along **our** route, not along Google's. The driver follows our route, and `at_m` already records position in that coordinate.
- `dist` is the near end of the bypassed portion on our route — the smaller of the two projected ends, which the code already normalises.
- Selection now happens after each stretch is located on our route, because the weight needs that position. Placement, merge order, and the stored record are unchanged.
- The score itself is not stored. `added` keeps `latlon`, `at_m`, `skipped_m`, and `google_detour_m`.

This changes which stretches are corrected. It never changes where a waypoint is placed, nor the order the waypoints appear in the link.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `google-route-refinement`: the requirement that a stretch becomes a waypoint currently ranks stretches by length and picks the longest. It now ranks by length weighted by position along the optimal route.

## Impact

- Modified: `french_tolls/refine.py` — `waypoints_for` only.
- Unchanged: `drift_sections`, both request phases, the stored schema, the two budgets, `french_tolls/api.py`, `french_tolls/service.py`, `www/index.js`.
- Unchanged: `evaluation/prototype_reinsert.py` keeps its own unweighted sort, so it stays a baseline the new scheme can be compared against.
- Money: none. The same number of Google requests buys the same number of waypoints.
- Data: stored refinements are keyed on the data fingerprint, which this change does not move. Refinements computed under the old ranking remain readable and are not recomputed. They are the previous ranking's answer, and they will only be replaced when the fingerprint changes.
