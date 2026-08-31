## Context

See proposal.md — Why.

The facts the approach rests on, each measured rather than assumed:

- `osrm-customize` computes `segment_weight = round(length_in_metres / rate * weight_multiplier)` and stores that integer. Recorded in `openspec/changes/archive/2026-08-26-add-toll-weighted-osrm-graph/design.md:57`.
- The multiplier is 10. The image is `ghcr.io/project-osrm/osrm-backend:26.8-debian`, the profile is the stock `car.lua` patched by `builder/patch_car_profile.py`, and that patch touches nodes and gates only. The profile sets `weight_name = 'routability'` and no `weight_precision`, so OSRM's default of 1 applies and the multiplier is `10^1`. Confirmed against the graph: over 100 000 segments in `data/segment_weights_report.json`, every annotated weight is a multiple of 0.1 and none has a second decimal.
- The current diff is noise. Over the 249 441 rows shared between `HEAD` and the working copy that carry a length in the report, 3 change their stored weight. 38 306 rows differ in the file.
- The noise is amplified, not random. `fit_rates` couples every segment to every other through the journeys that cross them and runs 12 iterations. One journey rerouting at one junction — 13 segments dropped, 7 gained, all around nodes `4349032318`–`4349032325` and `8296363186`–`8296363209` — moved 38 306 rates. The median move is 3e-9 and the 99.9th percentile is 1e-4. Six rows moved by 1.8% to 2.1%; those six are the rerouted junction itself.

## Goals / Non-Goals

**Goals:**

- A rerun that produces the same graph produces the same file.
- The diff over `data/segment_weights.csv` names the segments whose cost changed, and nothing else.
- The graph is unchanged, bit for bit, by the change itself.

**Non-Goals:**

- Making `fit_rates` reproducible. It already is. The fit was fed a different route, and spreading that perturbation is the fit working correctly.
- Reducing the size of the file, or how git stores it.
- Snapping the speed column. Duration is stored as an integer too, and the same argument applies to it, but the speed column is not moving: it is byte-identical on all 249 774 shared rows. A fix wants a fault.
- Explaining why one journey rerouted. That is a separate question about the extract.

## Decisions

### Snap the target weight, not the rate

Round `target_weight` to the grid, then invert. Not: compute the rate and round the rate.

    stored = round(target * WEIGHT_MULTIPLIER) / WEIGHT_MULTIPLIER
    rate   = metres / stored

The grid is a grid in weight, not in rate. Rounding the rate to a fixed number of decimals snaps to a grid whose spacing in weight depends on the segment's length, which is why rounding the current file to six decimals still leaves 9 017 rows differing and to four leaves 845. Rounding the target reaches the fixed points directly.

It also makes the result exact rather than close. `osrm-customize` will compute `round(metres / (metres / stored) * multiplier)`, which is `round(stored * multiplier)`, which is the integer `stored` was built from. The row and the graph then name the same number by construction, for every row, at every magnitude.

Measured on the regenerated file, against a file the old code wrote from the same graph: the snap moves no stored weight at all, on any of 249 781 rows, and moves no speed.

That measurement has to be made without the lengths in the report, which are rounded to three decimals (`write_report`, `"m": round(segments.dist[i], 3)`). Three decimals is about 5e-4 of a weight unit once divided through by a rate near 10, which is the same size as the effect being looked for: a first attempt that took its lengths from the report reported 43 rows moved, all of them sitting within 4.6e-4 of a rounding boundary, which is to say all of them inside its own noise. The length cancels if the comparison is written as a ratio. For a row the two files share,

    target_old / stored_new  ==  rate_new / rate_old

so recovering the integer `stored_new * multiplier` once is enough to ask what the old rate would have stored, and no length enters.

Alternative considered: quantise the rate to N significant figures. Rejected — six significant figures still leaves 1 055 rows differing, and the bound it gives is relative to the rate rather than to the weight, so it says nothing about what the graph will store.

### Keep nine decimal places on the rate

The rate is still printed at nine places. Nine is not about the fit's precision now; it is about naming the snapped target without falling onto a neighbouring grid point. The smallest rate in the file is 0.001371056, where six places would name a weight 0.08% away.

### Name the multiplier as a constant, and do not derive it

Add `WEIGHT_MULTIPLIER = 10` next to the other module constants in `builder/build_segment_weights.py`, with the profile evidence in its comment. Do not read it out of the profile at run time.

The alternative — parse `weight_precision` out of `car.lua` — buys a correctness the pipeline does not need and costs a dependency `write_csv` does not have. The profile is stock, the patch does not touch weights, and if either changes the acceptance check catches it: a wrong multiplier snaps to a wrong grid, which moves every arc's weight, which is exactly what `check_arcs` measures. The constant is stated in the spec, so a future change to the profile has somewhere to look.

### Guard against a zero stored weight

`write_csv` already skips a row with `weight <= 0`. An annotated weight above zero is at least 0.1, being a multiple of it, and the toll term never subtracts, so `stored` is at least 0.1 and the division is safe. State this rather than adding a second guard that can never fire.

## Risks / Trade-offs

**The graph could change on a target sitting exactly on a rounding boundary.** → Measured at zero over 249 781 rows against the same graph, so no such target arises in the current inventory. It remains possible in principle: two roundings run in sequence, this step's and the one `osrm-customize` performs on a rate recovered through a nine-decimal print, and a target close enough to a boundary could fall either side. Where that happened both the old code and the new would be choosing arbitrarily between two adjacent integers, and one of them is 0.00028 EUR at the default wage. `check_arcs` holds every flat-charge arc to 0.01 EUR, so a flip on such an arc is caught.

**Nine decimal places could stop being enough to name a grid point.** → The worst row lands about 3.6e-2 units from the integer it means, against a boundary at 0.5. That is roughly 14x of headroom, not the 1e-7 an earlier draft of this design estimated.

The estimate was wrong because the error is not the print's relative error. It is that error amplified by `stored / rate`. The eight worst rows are all arcs leaving the 55.50 EUR barrier, where the weight is about 99 910 units and the rate about 0.001, so 5e-10 of print granularity becomes 4e-2 of weight. The headroom therefore scales with `rate / stored`, which is to say inversely with the largest tariff in the inventory: 55.50 EUR today, and of the order of a few hundred euro before nine places stop being enough. `check_arcs` is what would catch it, arc by arc, if a tariff ever came close.

In the graph itself the recovery is better than that bound. Asked for the 1 046 segments of the acceptance pair, `osrm-optimal` returns a weight equal to the one its row names to within 8.1e-10 units.

**The first regeneration produces a large diff.** → Unavoidable and one-off: nearly every row is snapped for the first time. It is the last large diff. Commit it as its own commit with nothing else in it, so the next one is readable.

**A future profile change to `weight_precision` silently invalidates the constant.** → `check_arcs` fails, because every arc's weight would be off by the ratio of the two grids. The spec records the dependency and the constant's comment records the evidence.

**The rate is no longer exactly what the fit asked for.** → It never was. `osrm-customize` discarded the difference before this change; the difference is now discarded one step earlier and is visible. The bound is half a grid step, 0.05 weight units, which is 0.00028 EUR at the default wage — three orders below the 0.01 EUR the arc check enforces and four below the cheapest tariff in the inventory, 0.40 EUR.

## Migration Plan

1. Change `write_csv`, add the constant.
2. Rerun step 10 and step 11. `data/segment_weights.csv` is checkpointed on itself, so remove it first to force the rebuild.
3. Confirm the acceptance checks pass: `check_arcs`, `check_rows_present`, and `check_graphs` on the fixed pair.
4. Confirm the intent directly: rebuild the graph from the new file, and verify that the annotated weight of a sample of segments equals the stored weight their row names.
5. Commit the regenerated file alone.

Rollback is `git checkout` on the two files. Nothing downstream reads the rate at more than the graph's own granularity, so no consumer needs migrating.
