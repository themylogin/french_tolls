## 1. Confirm the constant before relying on it

- [x] 1.1 Read `weight_name` and `weight_precision` out of `$(OSRM_TOLL_PATH)/profile/car.lua` and confirm that `weight_precision` is absent, so that OSRM's default of 1 applies and the multiplier is 10
- [x] 1.2 Confirm against the graph rather than the profile: over the `segments` array of `data/segment_weights_report.json`, verify that every annotated weight `w` is a multiple of 0.1, and record the count checked

## 2. Change the writer

- [x] 2.1 Add `WEIGHT_MULTIPLIER = 10` to the module constants in `builder/build_segment_weights.py`, with a comment carrying the evidence from tasks 1.1 and 1.2; verify the module still imports
- [x] 2.2 Change `write_csv` (`builder/build_segment_weights.py:1342`) to round the target weight to the multiplier's grid and to derive the rate from the rounded value; verify by hand on the two spec examples, that a 100 m segment at 2.77 s and 2.00 EUR/km writes a rate of 2.577319588, and that the 13.7 m arc leaving a 55.50 EUR barrier writes 0.001371056
- [x] 2.3 Rewrite the `write_csv` docstring so it states why the target is rounded before it is inverted, replacing the paragraph that justifies nine decimal places as a tolerance; verify the docstring no longer claims a 0.0001% bound that the change makes exact

## 3. Prove the graph is unchanged

- [x] 3.1 Write a throwaway script under the scratchpad that compares the stored integer weight between a file written the old way and one written by the new code, over the rows they share. Do not take lengths from `data/segment_weights_report.json`: it rounds them to three decimals, which is the size of the effect. Compare by the ratio `target_old / stored_new == rate_new / rate_old` instead, which needs no length — measured: 0 of 249 781 rows moved, and 0 speeds
- [x] 3.2 Verify the round trip is exact: for every row of the new file, `round(metres / rate * 10)` equals the integer the writer intended, with no row landing on a neighbouring grid point

## 4. Regenerate

- [x] 4.1 Rebuild the builder image and remove `data/segment_weights.csv`, then run `make build_segment_weights`; verify the step completes and writes both the file and the report
- [x] 4.2 Run `make apply_segment_weights`; verify `check_arcs` holds every flat-charge arc inside 0.01 EUR, `check_rows_present` finds every arc, and `check_graphs` puts the LE PERTHUS to BEZIERS-OUEST weight difference inside the 20% tolerance of 2 610 units
- [x] 4.3 Query a sample of at least 50 segments from `osrm-optimal` and verify each one's annotated weight equals the stored weight its row names, exactly

## 5. Confirm the diff shrank

- [x] 5.1 Diff the regenerated file against `HEAD`. The line-level diff is maximal, because every row is snapped for the first time; the measure that means anything is the stored weight. Verify by the length-free method of task 3.1 that the stored integer changed only on the rows the reroute moved, and that no speed changed — measured: 3 stored weights, 0 speeds, 13 rows dropped and 7 added by the reroute
- [x] 5.2 Rerun `make build_segment_weights` a second time from the same inputs and verify the file it writes is byte-identical to the first, with `git diff --stat` reporting no change

## 6. Land it

- [x] 6.1 Verify `openspec validate "snap-segment-rate-to-graph-granularity" --strict` passes. Do not hand-sync the delta into `openspec/specs/toll-weighted-graph/spec.md`: there is no `sync` command, and `openspec archive` is what updates the main specs, so syncing here would only collide with it
- [x] 6.2 Run `make test` and verify the suite passes
- [ ] 6.3 Commit `data/segment_weights.csv` on its own, with no other file in the commit, so the next regeneration's diff is readable — left to the user, who is reviewing the working tree first
