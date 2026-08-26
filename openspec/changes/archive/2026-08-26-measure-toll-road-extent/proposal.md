## Why

A tariff is priced between two booths, and the pipeline measures the distance between those two booth *nodes*. That is not the distance the driver was charged for. A booth sits where the barrier is, and the tolled road runs on past it — through the plaza, down the slip road, to wherever the network actually ends.

The error is not small. MERU to AMBLAINVILLE on the A16 is priced at 1.90 EUR, and booth to booth it is 1.5 km, which reads as 1.2422 EUR/km — the highest sample in the whole segment table and the worst deviation in it, 815%. Measured to where the toll road really ends, the same journey is 10.0 km and 0.19 EUR/km, which is an ordinary rate. The 815% was the measurement, not the tariff.

The end of the toll road is discoverable by routing. Every journey leaving an exit booth is on the same road until the network releases it; only then do they go to different places. So the last node every route shares is the last node of the toll road. Routing AMBLAINVILLE to its 24 nearest places gives a common prefix of 64 nodes ending at node 240997497, 8.11 km beyond the barrier — the node a reader of the map picks out by eye.

The same holds in reverse for an entrance: route the places *to* the booth and the last node they converge on is where the tolled road begins. MERU's is node 5122294120, 0.41 km before the barrier.

## What Changes

- A new pipeline step, `build_toll_extent`, that finds where the tolled road begins and ends at every priced booth and records it in `data/vinci_price.yaml`.
- An `exit` booth gains `last_toll_node_id`: the final node shared by every route from the booth to its nearby places.
- An `enter` booth gains `first_toll_node_id`: the first node shared by every route from its nearby places to the booth.
- A `bidirectional` booth that carries `prices` gains both. Its two roles are told apart by the sides `data/bidirectional_booth_sides.yaml` already records: routes leaving by an `inside_nodes` node are the entrance's, routes arriving from one are the exit's. It is routed against four times as many places, because the side filter discards those serving its other role.
- Each node is recorded with its coordinates, as `first_toll_latlon` and `last_toll_latlon`. A node id alone cannot be routed to, and the coordinates come free from the geometry of the route that found it.
- Nearby places come from the 771 entries `data/route_set.yaml` already carries. No new input.
- A booth named in `data/osm_toll_booths_overrides.yaml` is skipped, and its stated value is used if it has one. The overrides are where a booth the road network describes wrongly is corrected by hand, and that has to stay possible here.
- The step is resumable: it reads the price file for the booths already measured and does only the rest, one booth at a time.
- **BREAKING for the consumer, not the format**: per-kilometre price calculations SHALL measure from the entrance's `first_toll_node_id` to the exit's `last_toll_node_id` rather than booth node to booth node. `builder/build_segment_weights.py` changes with it.

## Capabilities

### New Capabilities

- `toll-road-extent`: how the first and last node of the tolled road at a booth are found by convergence, which places are used, how a two-way booth's two roles are told apart, what stops the step, how it resumes, and what a per-kilometre price is measured between.

### Modified Capabilities

- `vinci-price-mapping`: the price file's `toll_booths` entries gain `first_toll_node_id` and `last_toll_node_id` with their coordinates, including on an `exit` entry, which until now carried `type` alone; and the file's temporary name becomes unique to the writing process.
- `toll-weighted-graph`: a priced pair is measured between the ends of its tolled road rather than between its two barriers.
- `build-pipeline`: the pipeline gains a further named step and its place in `all`; it is resumable, and it needs the graph and no key.

## Impact

- **New**: `builder/build_toll_extent.py`.
- **Modified**: `data/vinci_price.yaml` (up to four new optional fields per booth, 1 980 added lines and nothing else changed), `builder/build_vinci_prices.py` (its loader and writer carry the fields through, and its temporary name becomes per-process), `builder/build_segment_weights.py` (the per-kilometre denominator), `builder/overrides.py` (the two fields may be stated by hand), `Makefile`, `builder/Dockerfile`.
- **Ordering**: the new step runs after `build_vinci_direct_prices`, because it reads the roles that step settles, and before `build_segment_weights`, which consumes what it writes. `build_segment_weights` and `apply_segment_weights` shift one place later in `all`.
- **Depends on**: `add-toll-weighted-osrm-graph`, which introduces `builder/build_segment_weights.py` and the `toll-weighted-graph` capability. It must be archived first: this change carries a `toll-weighted-graph` delta that replaces its booth-to-booth measurement with extent-to-extent, and that delta has nothing to modify until the capability exists.
- **Unaffected**: the booth inventory, the route set, the gare mapping, the booth sides, and every step that produces them. No tariff is re-requested; the operator is not contacted.
- **Runtime**: measured at about 14 minutes for 978 booths and roughly 36 500 local routes, at 40 routes per second, peaking at 180 MB. 990 of 1 023 extents are measured; the 33 that are not all belong to two-way booths whose free side reaches too few places, and they fall back to the booth node.
