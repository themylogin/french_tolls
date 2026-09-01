## Why

The toll extent is found by convergence: route a booth against its 24 nearest places and keep the run of nodes every route shares. Convergence is not commitment, and at an interchange the two part company.

Every approach to a slip road merges onto the roundabout that feeds it. From there the routes share the ring itself, so the shared run does not stop where the slip meets the ring — it carries on around it, as far as the sample happens to agree. The extent lands on a ring node, which is a road every local driver uses and nobody pays for.

Measured over the 990 extents in `data/vinci_price.yaml`, against the point at which the driver loses the choice not to pay:

```
beyond the point of commitment          700   (71%)   of which on a roundabout 437
agrees with the commitment boundary     155   (16%)
short of it                             135   (13%)

extra road published beyond the commitment point
  p25 50 m   median 128 m   p75 267 m   p90 589 m   max 13 311 m
  over 100 m: 356     over 250 m: 169     over 1 km: 40
```

44% of all extents sit on a roundabout node. `builder/build_segment_weights.py` routes extent to extent and spreads the tariff over that route, so those ring segments carry a share of a toll in the toll-weighted graph. `osrm-optimal` then avoids a free roundabout, and in the worst 40 cases it avoids kilometres of free road.

The answer is also unstable, because it is a property of the sample rather than of the road. A rebuild against a fresh route set moved two of them:

```
booth 137232 exit   805521 -> 137224     both on ring way 4270765, different exits
booth 142268 enter  142274 -> 30841830   both on ring way 4805468, different feeding arms
```

Neither value is right, and neither is more right than the other. The road did not change; the sampled places did.

## What Changes

- The extent SHALL be derived from the road graph rather than from a sample of routes. For an **enter** booth the tolled road begins at the boundary of the region every path through which reaches the booth. For an **exit** booth it ends at the boundary of the region every path into which came from the booth. This is the commitment the driver makes, which is what a tariff is charged for.
- The published node SHALL be the region's own boundary — the first node the driver reaches already committed — rather than the free node beside it. The two are one segment apart and measure the same thing, but a consumer routes between the published coordinates and a router's snapping at a junction is ambiguous: publishing the free node makes `build_segment_weights` discard 3 912 of 23 410 priced pairs, and publishing the inside node 326. For booth 142268 that is node 3011249583, just past the fork the depot loop leaves by; for booth 137232 it is 8006502773, the last slip node before the ring.
- The region SHALL be computed over the **drive classes** — the set `booth_groups.DRIVE_CLASSES` already uses for what lies beyond a booth. Any road a car can drive counts as an escape, `service` and `unclassified` included. A section the driver can leave by is not a section the driver was committed to.
- A branch SHALL count as a way out only if it reaches the open network without crossing a toll point. One that leads nowhere, or that leads further into the toll network, ends a tolled road at its barrier when it should not — Péage de Gye by a two-node stub, ARGENTAN by a ramp fed by a booth the override ignores. A booth marked `type: ignore` SHALL count as a toll point for this question and no other.
- The graph SHALL reach at least 11 km beyond every booth, because the answers do. It SHALL be the one the router drives, not a wider one. It SHALL honour access tags by the profile's own hierarchy, SHALL treat a barrier the profile does not whitelist as impassable, SHALL close a gate that no allowed highway class carries, and SHALL make every node of `data/nodes_blacklist.yaml` impassable. Anything looser invents escapes that are not there: 29 294 ways in the carve are barred to a car and 9 031 nodes are impassable to it, and a region that walks through one stops at a fork the driver never sees. It changes 4 extents of 1 024, all in the direction of under-charging.
- **BREAKING for the artefact, not the format**: no field is added or removed. 850 of the 990 published extents move, 34 roles the old derivation could not measure gain one, and `data/segment_weights.csv` is rebuilt from them.
- The step SHALL stop routing to find extents. It needs no places, no convergence floor, and no `MIN_ROUTES`. About 36 500 local route requests and 14 minutes of the pipeline go away.
- A booth whose region has several boundary nodes — 292 of 1 024, where two roads meet the corridor at one point — SHALL publish the nearest of them to the booth, and SHALL report that it was ambiguous.
- The step SHALL remain resumable, SHALL keep its overrides, and SHALL keep reporting the extent distances largest first. A booth whose region is empty SHALL record the booth node, as it does now.
- The report SHALL name every extent whose road distance from the barrier exceeds a threshold, because a long committed region is either a real approach or a graph the class filter has made too generous.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `toll-road-extent`: the extent is defined by commitment rather than by convergence; the derivation is a graph computation rather than a routed sample; the place list, the place count and the minimum-route floor stop being inputs; the boundary convention and the class set are stated; an ambiguous boundary is resolved and reported; the step stops needing a routing service.

`toll-weighted-graph` is deliberately not listed. Its rule does not change: a priced pair is still measured from the entrance's `first_toll_node_id` to the exit's `last_toll_node_id`. Only the values those fields carry change.

## Impact

- **Modified**: `builder/build_toll_extent.py` (the derivation, the report, and the removal of the router and the place list), `data/vinci_price.yaml` (850 of 990 extent values move, 34 roles gain one, no field changes), `data/segment_weights.csv` (rebuilt), `Makefile` (step 9 stops starting `osrm-toll` and stops passing `--osrm` and `--route-set`), `openspec/specs/toll-road-extent/spec.md`.
- **Unchanged**: the price file's format, `builder/build_segment_weights.py`, `builder/build_vinci_prices.py`, `builder/overrides.py`, and the pipeline's ordering. The step still runs between `build_vinci_direct_prices` and `build_segment_weights`, because it still reads the roles the first settles and still writes what the second consumes.
- **New inputs**: the step reads `data/nodes_blacklist.yaml` and the pristine routing profile, which until now only `builder/patch_car_profile.py` read, and it carves its own extract of the road network. It stops reading `data/route_set.yaml`.
- **New artefacts**: `data/drive_ways.osm.pbf` (522 MB, the drive classes of the country), `data/extent_ways.osm.pbf` (248 MB, those cut to cells reaching at least 11 km beyond every booth), and `data/extent_wide_ways.osm.pbf` (71 MB, a second carve at 33 km around the 18 booths the first cannot bound). The first two are cut on first use and kept; the third is cut fresh each time, because which booths need it is a finding rather than an input. `make clean` removes all three. The grouping carve reaches 2 km, which ends inside AMBLAINVILLE's 8.11 km of tolled slip road, and 11 km ends inside RESTIGNE's 19.03 km.
- **No tariff is re-requested.** The operator is not contacted.
- **Runtime**: three passes over `plazas.osm.pbf` — barrier nodes, the gates an allowed class carries, then the graph — and a bounded fixed point per booth. Measured over the whole inventory at 20.0 minutes against about 14 minutes today, and 36 500 router requests become none. The derivation itself is 6.7 minutes of that; the other 13 are the price file being written after every role, which is what makes the step resumable and which it already did. The regions are small, median 6 nodes and 240 at the largest.
- **Known cost, recorded in `design.md`**: a public `service` or `unclassified` branch counts as an escape, so a rest area or an open access road joining a slip road ends the tolled section there. For 109 of the 1 024 extents the region reaches no further than the barrier's own neighbour, and those extents lose the length the old measurement claimed for them.
