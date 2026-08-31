## Why

`data/segment_weights.csv` is committed, and a rerun of step 10 rewrites it far more widely than the graph it produces changes. Measured over the current working copy against `HEAD`: 38 306 rows moved, but only 3 of them change the integer weight `osrm-customize` stores. The other 38 303 rows describe no difference in the graph at all.

The file prints the rate to nine decimal places. The graph keeps the weight as an integer at a granularity of 0.1 weight units. Nine places therefore name distinctions the graph cannot hold, and the fit that produces the rate is globally coupled — one journey rerouting at one junction moves 38 306 rates by a median of 3e-9. Every one of those becomes a diff line, and the real change is unreadable inside them.

## What Changes

- `write_csv` snaps the target weight to the granularity `osrm-customize` stores before it inverts the target into a rate. The row then names the weight the graph will actually hold, rather than a weight the graph will round.
- The rate keeps nine decimal places. Nine places are what it takes to name a snapped target exactly at the small end of the range; the change is to what is being named, not to how precisely it is named.
- The spec's precision rule changes from a tolerance ("within 0.01% of the target weight") to an identity ("the weight the graph derives is the weight the row names"). The tolerance was a bound on an error that no longer exists.
- The regenerated `data/segment_weights.csv` is committed.

Not a breaking change. The graph built from the new file is identical to the graph built from a file written the old way, because `osrm-customize` already performs this rounding. Measured over 249 781 rows against the same graph: no stored weight moved, and no speed moved. The change moves the rounding upstream so that it is visible in the file, and so that a rerun whose result is the same graph produces the same bytes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `toll-weighted-graph`: the requirement "The segment speed file preserves duration and moves only weight" changes how the rate is derived from the target weight, and replaces the precision tolerance with the snapping rule.

## Impact

- `builder/build_segment_weights.py`: `write_csv`, and a new module constant for the weight multiplier.
- `data/segment_weights.csv`: regenerated. The rewrite touches nearly every row once, and then stops moving on reruns that do not change the graph.
- `openspec/specs/toll-weighted-graph/spec.md`: one requirement.
- No change to the Makefile, to the profile, to the OSRM version, or to any other step.
- The acceptance checks (`--verify`, `check_arcs`, `check_graphs`) are unaffected in principle and SHALL be run to confirm it.
