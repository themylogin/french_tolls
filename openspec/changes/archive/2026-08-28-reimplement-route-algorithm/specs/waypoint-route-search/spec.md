## Purpose

Defines how a journey across France is turned into two routes — the fastest and the cheapest in money and time — and how the cheapest one is reduced to the shortest list of intermediate waypoints that makes a general-purpose fastest-path router drive it.

## ADDED Requirements

### Requirement: Two graphs answer two different questions

The system SHALL obtain the **fast route** from the untouched graph, served as `osrm-toll`, and the **optimal route** from the toll-weighted graph, served as `osrm-optimal`.

The fast route is the fastest by time, because the untouched graph carries no tariff. It is also the system's model of what a general-purpose navigation application computes when it is given two points and nothing else.

The optimal route is the cheapest in money and time together, because `toll-weighted-graph` adds to each tolled segment the time a driver works to pay for it. Its weight is therefore not a duration, and the system SHALL NOT present it as one. The duration and distance it reports SHALL be the route's own `duration` and `distance`, which both graphs measure the same way.

The system SHALL NOT query any routing service other than these two. In particular it SHALL NOT query a public routing endpoint.

#### Scenario: The two graphs disagree

- **WHEN** a route from Lyon to Paris is requested
- **THEN** the fast route is about 465 km and about 4 h 57, the optimal route is about 505 km and about 5 h 54, and the two are reported separately

#### Scenario: The optimal route's weight is not its duration

- **WHEN** the optimal route is reported
- **THEN** its duration is the value the router reports as `duration`, and the larger `weight` that carries the tariff appears nowhere in the answer

### Requirement: A location is snapped once and the snap serves both graphs

A query coordinate SHALL be snapped by asking the untouched graph for its nearest candidates. The snapped location and the router hint that comes with it SHALL then be used against both graphs.

One snap serves both because the toll-weighted graph is a copy of the untouched one with different edge weights. The node ids, the geometry, and the data checksum are the same, so a hint issued by one is accepted by the other. Snapping separately on each graph would allow the two routes to start on different lanes, and the two would then not be comparable.

The system SHALL NOT snap a location by routing it to a fixed third point. A location that cannot reach that point is not thereby off the road network, and a location that is that point has no route to it.

A location whose nearest candidate lies further from the road network than the configured reach SHALL be rejected with an error naming the measured distance. The reach SHALL default to 1 000 m.

#### Scenario: One snap, two graphs

- **WHEN** an origin is snapped on the untouched graph and both routes are requested with the resulting hint
- **THEN** the toll-weighted graph accepts the hint and both routes begin at the same location

#### Scenario: A location off the network is rejected

- **WHEN** a coordinate 4 km from the nearest road is submitted
- **THEN** the request fails with an error naming 4 km, and no route is requested

#### Scenario: No fixed third point is involved

- **WHEN** the origin is the centre of Paris
- **THEN** it snaps normally, because snapping asks only about the coordinate itself

### Requirement: A route is read as a node sequence with one coordinate per node

A route SHALL be read as the node id annotation of its single leg, together with a coordinate for each of those nodes and the distance, duration, and weight of each segment between consecutive nodes.

Coordinates SHALL be taken from the full-overview geometry, which carries exactly one point per annotated node. A route of 669 nodes returns 669 points. Stitching the geometry from per-step polylines SHALL NOT be used: it costs a decoding step, it rounds every coordinate to five decimal places, and the rounding is of the same order as the tolerances the snapping then has to meet.

A route of *n* nodes has *n* − 1 segments. The annotation reports *n* node ids and *n* − 1 distances, so the two sequences SHALL NOT be paired element by element. A Lyon–Paris route returns 8 642 node ids and 8 641 distances; pairing them discards the last node id, and a barrier standing on it is then never charged.

The route's total distance and duration SHALL be the values the router reports for the route, not a sum of the annotation.

#### Scenario: Every node is kept

- **WHEN** a route returns 8 642 node ids and 8 641 segment distances
- **THEN** the route is read as 8 642 nodes, and its last node id takes part in toll accounting

#### Scenario: Coordinates come from the geometry

- **WHEN** a route of 669 annotated nodes is read
- **THEN** it carries 669 coordinates, taken from the full-overview geometry rather than decoded from step geometries

### Requirement: A leg reproduces the optimal route when its node sequence is equal

For two positions *a* < *b* on the optimal route, the leg from *a* to *b* **reproduces** the optimal route when the fast route between the coordinates of those two nodes visits exactly the node ids the optimal route visits from *a* to *b*, in that order.

Equality SHALL be of the whole node sequence, except for one node at each end. A leg that rejoins the optimal route after leaving it drives a road the optimal route does not, and the driver pays for that road.

The endpoint tolerance is bookkeeping rather than road, and it is bounded exactly. A coordinate taken from the optimal route's geometry snaps onto a *segment*, and the router's annotation then carries that segment's other end as well: measured on the France graph, the leg from position *i* comes back as `optimal[i - 1]` followed by `optimal[i..b]`. A leading node equal to `optimal[a - 1]`, and a trailing node equal to `optimal[b + 1]`, SHALL therefore be stripped before the sequences are compared.

No other node SHALL be forgiven. The tolerance admits only the endpoints' immediate neighbours *on the optimal route itself*, so a leg that drove any other road differs in its interior and still fails. Without it, every leg whose ends are not the route's own endpoints is reported as a divergence — measured before it was applied, a Nice–Marseille journey recorded 20 divergences and exhausted its budget creeping forward one node at a time, where afterwards it needs one waypoint and 49 requests.

Each leg SHALL be requested with the hints of its two endpoints, so the query is pinned to the carriageway the optimal route uses rather than to whichever lane is nearest.

#### Scenario: An equal sequence reproduces the route

- **WHEN** the fast route between two positions of the optimal route visits the same node ids in the same order
- **THEN** the leg reproduces the optimal route

#### Scenario: A snapped endpoint carries its segment's other end

- **WHEN** a leg from position *i* comes back as `optimal[i - 1]` followed by `optimal[i..b]`
- **THEN** that leading node is stripped and the leg reproduces the optimal route

#### Scenario: Any other extra node fails

- **WHEN** a leg carries a leading node that is not `optimal[a - 1]`
- **THEN** the leg does not reproduce the optimal route

#### Scenario: A rejoining leg does not

- **WHEN** the fast route between two positions leaves the optimal route and returns to it before the second position
- **THEN** the leg does not reproduce the optimal route, whatever its endpoints

### Requirement: The search reaches as far as each leg allows

The waypoint list SHALL be built greedily from the origin. From the current anchor the system SHALL find the furthest position on the optimal route whose leg from that anchor reproduces the optimal route, emit that position as a waypoint, and take it as the next anchor. It SHALL stop when the anchor reaches the destination.

The destination SHALL be tested first. Where the whole remainder reproduces the optimal route, no waypoint is needed and one request settles it — which is the common case for a journey whose two routes are already the same road.

Where it does not, the furthest position SHALL be found by testing positions at growing offsets from the anchor — one node, two, four, and so on doubling — until a leg fails to reproduce the route, and then bisecting the interval between the last position that succeeded and the first that failed. Growing before bisecting costs a number of queries proportional to the logarithm of the step actually taken, rather than of the length of the whole route.

Growth SHALL stop at the first failure that follows a success, not at the first failure outright.

The search SHALL rely on the fact that a prefix of a fastest path is a fastest path, so that a leg reproducing the route implies every shorter leg from the same anchor does. Where the router breaks a tie in favour of an equally fast alternative this can end the growth early. That costs an extra waypoint and never costs correctness, because the emitted waypoint is always one whose own leg was verified.

The system SHALL NOT emit a waypoint whose leg from the anchor it did not verify. Verifying a leg between two interior positions and then emitting its far end as the first waypoint proves nothing about the leg the driver drives, because two fastest paths laid end to end are not a fastest path.

#### Scenario: A route needing no waypoint

- **WHEN** the optimal route and the fast route between the same two points are the same route
- **THEN** the first growth step reaches the destination and no waypoint is emitted

#### Scenario: Every emitted waypoint was verified from its anchor

- **WHEN** the search emits a waypoint
- **THEN** a leg from the preceding anchor to that waypoint was requested and reproduced the optimal route

#### Scenario: The search does not stop at the midpoint

- **WHEN** the furthest reproducing leg from the anchor ends at 90% of the remaining route
- **THEN** the waypoint is emitted at that position, not at the midpoint

### Requirement: A waypoint must snap back onto the optimal route unaided

Before a position is emitted as a waypoint, its coordinate SHALL be snapped on the untouched graph **without a hint**, and the nearest candidate SHALL lie on a segment of the optimal route. Where it does not, the position SHALL be rejected and the search SHALL fall back to the nearest earlier position that passes.

Whether a position is emittable SHALL NOT take part in finding the furthest reach. They are two different questions, and letting the first end the search makes it emit a waypoint a few metres into a journey whose two routes are the same road. A snap taken to route a leg from SHALL NOT be handed out as an emittable waypoint without being checked; caching the snap for both purposes is what makes that possible.

Where a position is emitted that is not the furthest reach, its own leg from the anchor SHALL be verified before it is emitted.

A waypoint is handed to a router that has only the coordinate. Where the optimal route runs beside another road within the snapping distance — the opposite carriageway of a dual carriageway, a parallel service road, a slip road — a bare coordinate can snap to the wrong one, and the router then drives somewhere else entirely. Pinning the leg with a hint hides that, because the hint names the carriageway the coordinate alone does not.

Waypoint coordinates SHALL be reported to six decimal places, the precision the geometry carries.

#### Scenario: A waypoint beside the opposite carriageway is rejected

- **WHEN** the chosen position's coordinate snaps, unaided, to a segment that is not part of the optimal route
- **THEN** that position is not emitted, and an earlier position is used instead

#### Scenario: A waypoint is reported at full precision

- **WHEN** a waypoint is emitted
- **THEN** its latitude and longitude carry six decimal places

### Requirement: The waypoint list is bounded and an overflow is reported

A Google Maps directions URL carries at most nine intermediate waypoints. The system SHALL emit at most nine, and SHALL report the number the optimal route actually needed alongside them.

Where more than nine were needed, the answer SHALL carry an explicit marker saying the link does not reproduce the optimal route in full. The system SHALL NOT emit a link carrying more waypoints than the URL admits, and SHALL NOT silently drop the surplus.

The waypoints kept SHALL be the first nine. A later waypoint governs a part of the journey a driver reaches only after the link has already failed them.

#### Scenario: A route needing eleven waypoints

- **WHEN** the search emits eleven waypoints
- **THEN** the answer carries the first nine, reports eleven as the number needed, and marks the link as incomplete

#### Scenario: A route needing nine or fewer

- **WHEN** the search emits four waypoints
- **THEN** the answer carries four, reports four as the number needed, and does not mark the link

### Requirement: A stretch that admits no progress is a divergence

Where no position beyond the anchor yields a leg that reproduces the optimal route — not even the next node — the system SHALL advance the anchor by one position without emitting a waypoint, and SHALL record a **divergence** naming the two positions.

This happens where the optimal route uses a segment that is not on any fastest path between its own endpoints, which the toll weighting can make it do. It is a fact about the two graphs, not an error. Raising on it fails a whole journey over one segment, and retrying on it does not terminate.

The answer SHALL carry the divergences it recorded. The system SHALL NOT retry a search by restarting it from the origin with an adjusted parameter: a restart re-issues every request the search already made, and the budget is spent on work whose answer is known.

#### Scenario: A divergent segment does not fail the journey

- **WHEN** the optimal route uses a segment no fastest path between its endpoints uses
- **THEN** the search advances past it, records a divergence, and continues to the destination

#### Scenario: No search is restarted from the origin

- **WHEN** a leg fails to reproduce the optimal route
- **THEN** the search bisects or advances, and never re-requests a leg it has already requested

### Requirement: The search runs to a query budget

The search SHALL count the routing requests it issues and SHALL stop when it reaches its budget, which SHALL default to 500 requests and SHALL be settable.

The default is measured rather than chosen. Across France the dearest journey found is Strasbourg to Nantes: 11 127 nodes on the optimal route, 8 waypoints, 325 requests. A budget of 200 truncates that journey to 4 of its 8 waypoints, so 200 is below what an ordinary French journey costs.

On reaching the budget the system SHALL return the waypoints it has verified so far, together with the count it needed and the incompleteness marker, rather than raising. A partial list of verified waypoints is worth more to a driver than an error.

The budget is on requests rather than on elapsed time. A routing request against these graphs takes between 2 and 11 ms measured on the France extract, so the request count is what the search's cost is made of, and a time limit measures the machine's load instead.

#### Scenario: The budget is reached

- **WHEN** the search has issued its budget of requests without reaching the destination
- **THEN** it returns the waypoints verified up to that point and marks the answer incomplete

#### Scenario: An ordinary journey stays well inside the budget

- **WHEN** a Lyon to Paris route is searched
- **THEN** it completes within the budget — measured at 2 waypoints and 99 requests

#### Scenario: The longest measured journey fits

- **WHEN** a Strasbourg to Nantes route is searched
- **THEN** it completes within the budget — measured at 8 waypoints and 325 requests
