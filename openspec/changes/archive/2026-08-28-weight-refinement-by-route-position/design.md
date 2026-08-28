## Context

See proposal.md — Why.

The whole change lives in one function, `waypoints_for` in `french_tolls/refine.py`. It receives the drift stretches, the optimal route's points, and the waypoint budget, and it returns the waypoints to add.

Today it sorts by raw length, takes `budget` stretches, and only then locates each chosen stretch on the optimal route:

```python
along = _cumulative(ours)
for section in sorted(sections, key=lambda s: -s["length"])[:budget]:
    start = along[_nearest_index(ours, section["from"])]
    end = along[_nearest_index(ours, section["to"])]
    if end < start:
        start, end = end, start
    middle = (start + end) / 2
    ...
```

The constraint that shapes the whole design: a stretch is a run of Google's own points, and the new weight is expressed in distance along **our** route. The two are connected only by `_nearest_index`, a linear scan over every point of the optimal route. So the ordering of "locate" and "select" has to invert, and that inversion is the only structural consequence.

## Goals / Non-Goals

**Goals:**

- Rank stretches by length weighted by position along the optimal route.
- Keep the weight and its anchor expressed in one coordinate — distance along the optimal route — so the ranking, `at_m`, and the merge order all agree.
- Leave the observable output identical for any stretch that would have been chosen either way.

**Non-Goals:**

- Changing where a waypoint is placed inside its stretch. The midpoint of the bypassed portion stands.
- Changing the merge order, the two budgets, the two request phases, or the stored schema.
- Modelling abandonment properly. The weight is a stated linear discount, not a survival curve fitted to anything.
- Invalidating refinements already stored under the old ranking.

## Decisions

### The weight is anchored on our route, not on Google's

`section["from"]` is a vertex of Google's route, so its distance along Google's route is free: `drift_sections` already walks those points in order, and `_measure` already sums the total. Anchoring there would cost nothing.

Anchoring on our route costs one `_nearest_index` per stretch instead of two per chosen stretch, and it is still the right anchor.

The rationale for the whole change is that a driver may not reach the far end of the route. The driver follows *our* route. Distance along Google's route answers a question about a journey the driver does not take.

It also matters that the two scales diverge. On Bayeux to Apt, Google spends 134 km where our route spends 86. Every stretch after that detour sits further along Google's route than along ours, by an amount that has nothing to do with how far the driver has driven. Anchoring on our route keeps the weight in the same coordinate as `at_m` and as the merge, so all three describe the same position.

### `dist` is the near end of the bypassed portion

The stretch is located on our route by two projected ends, and the code already swaps them when the projection inverts. `dist` is the smaller of the pair after that swap.

The alternative is the midpoint of the bypassed portion, which is where the waypoint lands. On a 1 000 km route with an 86 km bypass, start and midpoint differ by about 4% of the weight. The near end is chosen because it is the first point at which the correction starts to matter to the driver, and because the swap that produces it is already there.

### Selection moves after location

The weight needs the position, so every stretch is located before any is chosen:

```
locate every stretch on our route  ->  score  ->  sort by score  ->  take budget  ->  place
```

`start` and `end` are computed once per stretch and reused by the placement, rather than recomputed for the chosen ones.

The cost is that `_nearest_index` runs `2 × len(sections)` times instead of `2 × budget`. Bayeux to Apt has seventeen stretches and a budget of two, so thirty-four scans replace four. Each scan is a linear pass over the optimal route, which can be tens of thousands of points.

`geometry.SegmentIndex` already exists and would turn each scan into a lookup over one grid cell and its eight neighbours. It is deliberately not used here. The cost has to be measured before it is optimised, and a refinement already spends two network round trips to Google; a change measured in tenths of a second on a path that is bought at most twice per journey does not justify a second index in this module. If the measurement says otherwise, `SegmentIndex.distance_m` is the ready answer.

### The score is not stored

`added` keeps `latlon`, `at_m`, `skipped_m`, and `google_detour_m`. The score is derivable from `at_m`, `google_detour_m`, and the route's length, so storing it would record a number that can be recomputed and would have to be kept honest across a formula change.

## Risks / Trade-offs

**A journey that is always driven whole gets a slightly worse link.** → Accepted, and it is the trade the change is making. Where the tail is genuinely reached, deprioritising it costs real correction. The `/2` divisor is the hedge: the weight bottoms out at 0.5 rather than 0, so a late stretch is discounted rather than discarded, and a late stretch more than twice the length of an early one still wins.

**The tail's correction is not free, only deferred.** → Unmitigated, and worth stating plainly. The re-request from a mid-route position is a new journey with a new fingerprint, and it spends its own requests against `GOOGLE_DIRECTIONS_MAX_REQUEST_PER_MONTH`. This change makes each request buy more of what is likely to be used; it does not reduce the number of requests.

**Location cost rises with the number of stretches, which is unbounded.** → Measure it on the worst journey in the evaluation corpus before accepting it. A pathological route with hundreds of stretches turns a linear scan per stretch into something noticeable. If the measurement is bad, index the lookup rather than capping the stretch count — a cap would silently drop candidates the ranking is meant to consider.

**Stored refinements keep the old ranking.** → Accepted. A refinement is invalidated by the data fingerprint, and this change does not move it. Existing refinements were bought and are correct answers to the previous question; recomputing them would spend Google requests to improve links that already work. New journeys, and every journey after the next pipeline rebuild, get the new ranking.

**The change is invisible unless it is measured.** → The two rankings agree whenever the budget covers every stretch, and disagree only on which of several stretches is corrected. `evaluation/prototype_reinsert.py` keeps its own unweighted sort, so the two can be run against the same stored corpus and compared.

## Migration Plan

No migration. No schema change, no configuration change, no data to move. Deploying the change is deploying the code; rolling back is reverting it. Refinements stored under either ranking remain readable by both.
