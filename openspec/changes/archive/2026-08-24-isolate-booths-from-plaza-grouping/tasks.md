## 1. Parse the null parent

- [x] 1.1 Add an `isolated` set to `Overrides` and route `parent_id: null` into it instead of `forced`; verify `overrides.load` on the project file reports 1 booth kept out of every group and no null value in `forced`.
- [x] 1.2 Reject a booth that states a null `parent_id` while another names it as a `parent_id` target, in `overrides.load`; verify a hand-built pair raises `OverrideError`.
- [x] 1.3 Include isolated nodes in `check_against_extract`; verify an isolated node absent from the extract stops the step.

## 2. Apply isolation in the grouping

- [x] 2.1 Give `group_booths` an `isolated` parameter and skip those booths in both positions of the pairing loop; verify the step prints the count held out.
- [x] 2.2 Raise from `group_booths` when a booth is both isolated and forced, for callers that pass the two directly; verify the message names both booths.
- [x] 2.3 Pass `ov.isolated` from `build_osm_toll_booths`; verify step 3 completes and prints the override summary including the new count.

## 3. Verify the split

- [x] 3.1 Re-run step 3 and confirm `25315120` and `26024647` are both keys of `toll_booths`, neither an alias of the other; verify group and alias counts move from 1294/262 to 1295/261.
- [x] 3.2 Confirm no other group changed, by diffing the new inventory against the previous one and checking that `26024647` is the only booth that moved between `toll_booths` and `aliases`.

## 4. Propagate to the route set and the gare mapping

- [x] 4.1 Run `make update_route_set`; verify every existing route is re-queried so `covers` reflects the new grouping, and that the run reports the new target `26024647` as covered or lists it as uncovered.
- [x] 4.2 Remove only the `25315120` entry from `data/vinci_toll_booth.yaml`, leaving `routes` and every other booth record intact; verify the file still parses and the entry count drops by exactly one.
- [x] 4.3 Run step 5 to completion; verify it exits zero, records a gare for both `25315120` and `26024647`, and that the two differ.
