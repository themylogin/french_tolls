## 1. Establish the geometry

- [x] 1.1 For the 12 bidirectional booths whose adjacent set is 3 nodes, inspect each in OSM and record whether the third node is real geometry or a tagging defect — all 12 are one shape: a one-way ramp in, a one-way ramp out, a two-way stub. Real geometry
- [x] 1.2 Verify onewayness is unambiguous per booth/neighbour edge — 110 edges, 0 conflicts, split (0 one-way, 2 two-way) x 35 and (2, 1) x 12

## 2. Step 3 emits the adjacency

- [x] 2.1 Collect each `bidirectional` booth's adjacent nodes and their onewayness during the pass `booth_groups` already makes over the carved plaza extract, deciding onewayness with `two_way()`; verify no additional extract is opened
- [x] 2.2 Write `adjacent_nodes` on every `bidirectional` booth, ascending by key, and on no other booth; verify all 47 carry it, 0 gantries and 0 untyped booths do, and the file is otherwise unchanged
- [x] 2.3 Verify a rewrite from the same extract is byte-identical
- [x] 2.4 Make the override file's bare `enter`/`exit`/`passthrough` types remove a booth from `two_way` before grouping; verify 2 of the 9 were tagged two-way in the extract, that both lose their type and adjacency, and that grouping is otherwise unchanged

## 3. Revert the direction-of-travel classification

- [x] 3.1 Remove `Sides`, `classify_sides`, and the end-of-run check from `builder/build_route_set.py`, and the `bidirectional_toll_booths` section from its output; verify step 4 still records `prev_node_id` on `covers` and that coverage is unchanged
- [x] 3.2 Delete `data/test_booth_sides.py`, whose subject no longer exists; verify no other check references it

## 4. The probe

- [x] 4.1 Create `builder/build_booth_sides.py` reading the inventory, the price file, the override file and the route set's places; verify it reports 47 two-way booths and 935 enter/exit targets without issuing a route request
- [x] 4.2 Build the target set: every `enter`/`exit` booth, plus places spread over 12 bearing sectors within 60 km; verify a booth-only target set leaves 16 booths unresolved with `outside` empty, and that adding places resolves all 16
- [x] 4.3 Admit an observation only when the route traverses the booth and no other booth group lies between it and the target; verify a route crossing a third booth is discarded
- [x] 4.4 Discard any route touching a node in `nodes_blacklist`; verify 105 of 88 636 routes are dropped and that dropping them takes the result from 42 entrance/exit and 3 contradicted to 45 and 0
- [x] 4.5 Apply the five verdict rules, with the two directions opposite; verify against a synthetic observation of each, and that using the arrival rule for both directions makes every node collect both labels
- [x] 4.6 Settle each booth as entrance/exit or barrier; verify 45 entrance/exit and 2 barrier against the current data

## 5. Errors and output

- [x] 5.1 Stop the step on a node with observations both ways, naming the node, both counts, and the minority routes with target, direction and length; verify the message identifies the offending route without further searching
- [x] 5.2 Report, without stopping, a node no admitted observation reached; verify the booth does not settle and the step exits successfully
- [x] 5.3 Write `data/bidirectional_booth_sides.yaml` with `inside_nodes` and `outside_nodes` ascending, each only when not empty; verify THOUARCE and LESTELLE ST MARTORY come out barriers with every node outside
- [x] 5.4 Verify a rerun against unchanged inputs is byte-identical

## 6. Pipeline integration

- [x] 6.1 Add the script to `builder/Dockerfile` and the builder image stamp; verify the image builds and the script is present
- [x] 6.2 Add a `build_booth_sides` target checkpointed on `data/bidirectional_booth_sides.yaml`, guarded by `guard-osrm-path`, bringing up `osrm-optimal`; verify it is skipped when the output exists
- [x] 6.3 Add it to `all` after `build_vinci_prices`; verify the order and that it issues no operator request
- [x] 6.4 Verify it fails naming the unreachable routing service when `osrm-optimal` is stopped
- [x] 6.5 Commit `data/bidirectional_booth_sides.yaml` alongside the other published booth files, and record why in `build-pipeline`'s project-layout requirement; verify it is not matched by any ignore rule

## 7. Cross-check

- [x] 7.1 Verify the two barriers are exactly the two-way booths carrying a flat `price` and no `prices` in `data/vinci_price.yaml`, which is data the probe does not use to classify
- [x] 7.2 Verify every settled entrance/exit booth has at least one inside and one outside node, and that the two sets partition its `adjacent_nodes`
