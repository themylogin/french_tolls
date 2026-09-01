## 1. The extract

- [x] 1.0 Cut a second carve at 0.3 deg around the booths the first cannot bound, uncached, and verify it is 84 cells and 71 MB and bounds RESTIGNE at 19.05 km

- [x] 1.1 Cut `data/drive_ways.osm.pbf` from the source extract with `osmium tags-filter` over `booth_groups.DRIVE_CLASSES`, and verify it is 522 MB with 40.8 M nodes and 4.2 M ways
- [x] 1.2 Cut `data/extent_ways.osm.pbf` from it with `booth_groups.carve_neighbourhoods` at 0.1 deg, and verify it is 248 MB with 18.2 M nodes over 2 576 cells
- [x] 1.3 Reuse both when present, and verify `make clean` removes them with the pipeline's other extracts

## 2. The road graph

- [x] 2.1 Read `data/extent_ways.osm.pbf` into a directed adjacency over `booth_groups.DRIVE_CLASSES`, deciding direction with `booth_groups.two_way`, and verify the step reports 34 114 614 edges
- [x] 2.2 Bar a way whose access the profile bars, resolving `motorcar`, `motor_vehicle`, `vehicle`, `access` in order, and verify 29 294 ways are dropped from the carve
- [x] 2.3 Make impassable every node whose `barrier` the profile does not whitelist, and every `gate` or `lift_gate` that no allowed highway class carries, and verify 27 163 barrier nodes and 15 735 gates are seen with 15 729 open
- [x] 2.4 Make impassable every node of `data/nodes_blacklist.yaml`, and verify all 3 are counted into the impassable set
- [x] 2.5 Verify the four rules together leave 9 031 nodes impassable in the carve
- [x] 2.6 Carry each edge's length in metres from the node locations of the same pass, and verify a known slip road measures the same length as the router reports for it
- [x] 2.7 Keep no coordinate in the graph, and verify the step reads back only the positions it publishes
- [x] 2.8 Seed each booth's node set from `data/osm_toll_booths.yaml`, resolving `aliases` through `parent_id`, and verify a plaza with alias lanes seeds every lane

## 3. The region

- [x] 3.0 Count a branch as a way out only when its closure reaches the open network without crossing a toll point, bounded at 500 nodes, and verify booth 1482474156 moves from the barrier to 2.50 km and booth 268212668 to 9.13 km
- [x] 3.0a Count a booth the override marks `type: ignore` as a toll point for this rule and nowhere else, and verify ARGENTAN's merging ramp is no longer read as free road
- [x] 3.0b Send a region that absorbed a dead end more than 8 km from the barrier to the wider carve, and verify 18 roles need it rather than a quarter of all of them

- [x] 3.1 Grow the entrance region backwards by the rule "keep a predecessor when every road leaving it is already inside", and verify booth 142268's free node is 1320680243 and no node of ring way 4805468 lies inside its region
- [x] 3.2 Grow the exit region forwards by the mirror rule, and verify booth 137232's region stops at 805520 rather than running around ring way 4270765
- [x] 3.3 Stop a region at any node belonging to another booth group, and verify the step names the bounding booth
- [x] 3.4 Restrict a two-way booth's region to the free side using `data/bidirectional_booth_sides.yaml`, and verify no node of `inside_nodes` is used to leave the booth
- [x] 3.5 Cap the region at a stated size and report a booth that reaches it, and verify the cap is never reached
- [x] 3.6 Assert over the whole inventory that no node inside any region lies on a `junction=roundabout` way, and verify the count is 0 of 1 024

## 4. The published extent

- [x] 4.1 Publish the region's own boundary node with its coordinates, and verify booth 137232 records 8006502773 and booth 142268 records 3011249583
- [x] 4.2 Where the free side has several nodes, publish the nearest by road distance and count the booth as ambiguous, and verify the count is 292 of 1 024
- [x] 4.3 Leave a booth whose region finds no free side unmeasured and report it rather than publishing the barrier, and verify only 2 remain on the wide extract
- [x] 4.4 Report every region that reaches a node the graph stops at, and verify the count is 28
- [x] 4.5 Keep `gantry`, `passthrough` and unpriced `bidirectional` booths unmeasured, and verify their counts match the previous run's 52, 229 and 2
- [x] 4.6 Keep the override path: a booth named in `data/osm_toll_booths_overrides.yaml` derives nothing, and a stated `first_toll_node_id` or `last_toll_node_id` is published as given, verified by the existing 14 overridden booths
- [x] 4.7 Verify AMBLAINVILLE records a junction rather than its own barrier node, the failure the plaza carve produced

## 5. Removing the sample

- [x] 5.1 Delete the router, the place loading, `PLACES`, `BIDIRECTIONAL_PLACES` and `MIN_ROUTES` from `builder/build_toll_extent.py`, and verify the step runs with `osrm-toll` stopped
- [x] 5.2 Drop `$(COMPOSE) up -d osrm-toll`, `--osrm` and `--route-set` from the step's Makefile recipe, and verify `make build_toll_extent` completes with no routing service running
- [x] 5.3 Verify the whole step over the inventory completes in about 28 minutes, of which 3 are the graph pass and 13 the per-role checkpoint writes, against the 14 minutes it takes now

## 6. The report

- [x] 6.1 List measured booths with their road distance from the barrier, largest first, each with its OSM node link, and verify the table renders for the current inventory
- [x] 6.2 Report the counts of regions bounded by a second booth, ending at the barrier, ambiguous, truncated, and unmeasured with no free side, and verify each against sections 3 and 4
- [x] 6.3 Name every extent beyond the reporting threshold rather than counting it, and verify no extent past the threshold is only counted
- [x] 6.4 Report the booths whose region ends at the barrier as a group, and verify the count is 109 of 1 024

## 7. Republishing the artefacts

- [x] 7.1 Clear the extent fields from `data/vinci_price.yaml` and re-run the step, and verify no field is added or removed and no non-extent field changes
- [x] 7.2 Re-run `build_segment_weights` and `apply_segment_weights`, and verify `build_segment_weights.py --verify` passes its acceptance check
- [x] 7.3 Compare the EUR/km distribution before and after, and verify the median and p99 hold; a rising maximum is the change working, so verify instead that each pair whose rate rose by more than half did so because free road stopped being credited
- [x] 7.4 Run the step twice against one extract and verify the two price files are byte-identical
- [x] 7.5 Verify `build_segment_weights` does not report more "extent node not on the route" fallbacks than the 3 100 it reported before the change, and verify the count is 824

## 8. Correcting the record

- [x] 8.1 Re-measure the class set and the profile rules on the wide extract, and verify both change far less than the 2 km carve suggested: 16 extents of 1 024 for the class set, 4 for the profile rules, and 112 barrier-endings either way
- [x] 8.2 Update `proposal.md`, `design.md` and the spec with the wide-extract figures throughout, and record that the earlier figures were the carve's truncation rather than the rules

## 9. Inspection before archiving

- [x] 9.1 Inspect the remaining 109 extents whose region ends at the barrier, largest claimed length first: the two largest were checked by hand and cleared, and below 300 m they are ramp-mouth barriers where nothing is committed before the barrier
- [ ] 9.2 Decide from that inspection whether barring `access=destination` outright still matches what a driver can do, and record the finding in `design.md` under Open Questions
- [x] 9.3 Establish whether the regions sent to the wider carve are long tolled stretches or a carve still too tight: 16 of the 18 return the same answer at 33 km as at 11 km, and only RESTIGNE needed the reach, so the carve is not too tight
- [x] 9.4 Decide whether a permanently unmeasurable role should be recorded so the step stops re-deriving it: moot, nothing is unmeasurable now
