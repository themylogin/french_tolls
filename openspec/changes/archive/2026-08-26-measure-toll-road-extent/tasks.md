## 1. Inputs and enumeration

- [x] 1.1 Create `builder/build_toll_extent.py` reading `data/vinci_price.yaml`, `data/route_set.yaml`, `data/osm_toll_booths.yaml`, `data/bidirectional_booth_sides.yaml` and `data/osm_toll_booths_overrides.yaml`, reusing `bp.load_state` and `bd.load_inventory`/`load_sides`; verify a dry run reports 771 places and the booth counts by role without issuing a route
- [x] 1.2 Build the work list: every `exit` booth wants a last node, every `enter` booth with `prices` wants a first node, every `bidirectional` booth with `prices` wants both; verify the counts against the price file's 467 exit, 470 enter and 47 bidirectional entries, and that 45 of the bidirectional ones qualify
- [x] 1.3 Exclude `gantry` and `passthrough` booths and report the 7 gantries carrying prices as deliberately unmeasured; verify none of the 52 gantries or 239 passthroughs appears in the work list
- [x] 1.4 Exclude every booth named in `data/osm_toll_booths_overrides.yaml` from routing, and publish `first_toll_node_id`/`last_toll_node_id` where the override states one; verify all 33 override booths are skipped and that a hand-added `last_toll_node_id` reaches the price file unrouted
- [x] 1.5 Add `first_toll_node_id` and `last_toll_node_id` to the override schema in `builder/overrides.py` as optional integer node ids; verify a non-integer and an unknown key are each refused

## 2. Convergence

- [x] 2.1 Select the N nearest places by great-circle distance with `--places` defaulting to 24; verify AMBLAINVILLE's 24 span 10.9 to 73.0 km
- [x] 2.2 Route booth-to-place for an exit and place-to-booth for an entrance with `annotations=nodes`, `overview=false`, `steps=false`, 16 workers; verify 24 of 24 route for AMBLAINVILLE and for MERU
- [x] 2.3 Take each route's node sequence from the booth node onward (exit) or up to it (entrance), discarding a route whose annotation does not contain the booth node; verify AMBLAINVILLE's sequences start at index 1, and that node 2587186119 at index 0 is excluded
- [x] 2.4 Reduce to the longest common prefix and take its last node; verify AMBLAINVILLE gives a 64-node prefix ending at 240997497, and MERU a 28-node one beginning at 5122294120
- [x] 2.5 Verify the measured distances: 8.11 km from AMBLAINVILLE to its last node, 0.41 km from MERU's first node to the barrier
- [x] 2.6 Record the booth's own node when the routes diverge immediately, and verify that is written rather than treated as a failure
- [x] 2.7 Add `--min-routes` defaulting to 8; leave a booth unmeasured and report it as a finding when fewer routes succeed, and verify the step continues

## 3. Bounds and sides

- [x] 3.1 Truncate a shared sequence at the first node belonging to another booth group, resolving aliases through `parent_id` as `bd.load_inventory` returns them; verify a synthetic sequence containing a known alias truncates at the node before it and names the bounding booth
- [x] 3.2 Report how many extents were truncated by a second barrier; verify the count over the whole inventory and read the list to check it is as rare as design D4 expects
- [x] 3.3 For a `bidirectional` booth measuring its exit role, discard routes leaving by an `inside_nodes` node; for the entrance role, discard routes arriving from one; verify with one two-way booth that each role keeps a different subset of the 24 routes
- [x] 3.4 Verify a `bidirectional` booth carrying `prices` ends with both fields, and one carrying none is skipped and not reported as a gap — of the 45 with prices, 26 carry both, 5 carry one and 14 carry neither; the 33 missing roles are exactly those the `--min-routes` floor left unmeasured, which the spec's fallback covers. Both booths without prices carry no extent. Every node id in the file is paired with its coordinates

## 4. Recording and resume

- [x] 4.1 Extend `bp.load_state` and `bp.write_state` to carry `first_toll_node_id` and `last_toll_node_id`, written in the order `type`, `price`, `first_toll_node_id`, `last_toll_node_id`, `prices`; verify a file with extents round-trips byte-identically
- [x] 4.2 Verify `build_vinci_prices` and `build_vinci_direct_prices` both preserve extents they did not produce — run each against a file carrying extents and confirm every one survives
- [x] 4.3 Write the price file after each booth is measured, so an interrupted run repeats at most one booth; verify killing the step mid-run leaves the booths already done recorded
- [x] 4.4 Derive the outstanding work from the price file alone, with no cursor of the step's own; verify a run against a complete file issues no route request and exits successfully
- [x] 4.5 Verify the written file still satisfies the `vinci-price-mapping` format rules — ascending group ids, ascending gare codes, and a byte-identical rewrite from the same state

## 4b. Writing the file safely

- [x] 4b.1 Give `bp.write_state` a temporary name unique to the writing process and remove it on failure; verify the name carries the pid and that a failed write leaves no `.part` file. Found by hitting it: two runs of this step raced on a shared `data/vinci_price.yaml.part`, one renamed it, and the other's rename failed with `FileNotFoundError` — the price file was gone
- [x] 4b.2 Verify the four steps that write the price file all go through that one function, so the fix reaches every writer; verify a byte-identical rewrite still holds afterwards

## 5. Report

- [x] 5.1 Print every measured booth with its extent distance, largest first, each with its gare code, name and OSM node link, in the bordered `table` helper; verify the borders render and the ordering is by distance
- [x] 5.2 Print the booths left unmeasured grouped by reason — too few routes, bounded, overridden, gantry — with counts; verify the counts sum to the work list size
- [x] 5.3 Read the extent distances over the whole inventory and check the large ones by eye against the map, per design D3's open question on whether 24 places is enough everywhere

## 6. Using the extents

- [x] 6.1 In `builder/build_segment_weights.py`, measure a priced pair's distance from the entrance's `first_toll_node_id` to the exit's `last_toll_node_id` along the route, falling back to the booth node at either end that has none; verify MERU to AMBLAINVILLE measures about 10.0 km and rates about 0.19 EUR/km
- [x] 6.2 Count and report how often an end fell back — because it had no extent, or because the route did not traverse the extent node; verify the counts appear in the summary
- [x] 6.3 Verify the first/last dropped segments rule still holds against the new endpoints, and that the sampled segment range is the one between the extent nodes
- [x] 6.4 Re-run the full survey and record the corrected deviation and reconstruction distributions against the previous 63.9% median deviation and 9.0% median price error — 23 376 of 23 376 pairs placed, 0 unusable, 248 054 segments. Deviation median 63.9% -> 59.9%, p90 122.6% -> 101.7%, max 815.2% -> 675.9%. Price error median 9.0% -> 8.6%, p90 24.4% -> 23.3%. Ends taken back to the booth: 961 exits and 25 entrances with no extent, 5 882 whose extent node was not on the route, 3 401 whose route missed a booth
- [x] 6.5 Take the corrected numbers to the maintainer and settle the `--max-deviation` default of `add-toll-weighted-osrm-graph`, which design D5 defers to here — settled: the gate is removed entirely. The corrections left the sample spread at 59.4% median with 97.9% over 10%, which is French tariff structure rather than a defect; the fitted rates are what keep it off the driver, and the run now reports the journey error instead of gating on the spread

## 7. Pipeline integration

- [x] 7.1 Add `build_toll_extent.py` to the `COPY` line in `builder/Dockerfile` and to `$(BUILDER_STAMP)`'s prerequisites; verify `docker compose build builder` succeeds and the script is in the image
- [x] 7.2 Add a phony, always-executing `build_toll_extent` target guarded by `guard-osrm-path` alone, bringing up `osrm-toll` first; verify it runs with `ULYS_SUBSCRIPTION_KEY` and `ULYS_PASSAGE_DATE` unset and with no network
- [x] 7.3 Verify it fails with a message naming the unreachable routing service when `osrm-toll` is stopped, before any booth is routed
- [x] 7.4 Insert the step into `all` between `build_vinci_direct_prices` and `build_segment_weights`, and make `$(SEGMENTS)` depend on it; verify `make -n all` runs the eleven steps in the specified order
- [x] 7.5 Verify a second `make all` performs no work, including the new step

## 8. Full run

- [x] 8.1 Run the step to completion over the whole inventory; verify it measures every eligible booth, report the routing time against the ~30 000 queries design D3 predicts, and record the peak memory
- [x] 8.2 Verify `data/vinci_price.yaml` reloads under `bp.load_state` without an `Abort`, with the same booth, type and price counts as before the step ran
- [x] 8.3 Verify the committed price file's diff contains only added extent fields — no tariff, type or route line changes
- [x] 8.4 Run `make all` end to end and verify steps 1 to 8 do no work, step 9 measures, step 10 rebuilds the segment weights against the new denominators, and step 11 produces the graph — 27.5 s total; steps 1-8 idle, step 9 re-attempts only the 33 booths it cannot measure (12 s of routing) and steps 10 and 11 skip on their outputs. The file is never `complete` while those 33 exist, so the no-routing path is reachable in code but not with this data
- [x] 8.5 Re-run the acceptance check of `add-toll-weighted-osrm-graph` and record how the Le Perthus to Béziers weight difference moved from the 36.2 minutes measured against booth-to-booth distances — 36.1 minutes, essentially unchanged, and the durations still agree exactly. The pair is 105.5 km, so its two extents are a small fraction of the denominator; the correction is felt by short journeys, not long ones
