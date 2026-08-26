# toll-road-extent Specification

## Purpose
Finds where the tolled road actually begins and ends at each priced booth, so that a tariff is divided by the distance the driver was charged for rather than by the distance between two barrier nodes.

## Requirements

### Requirement: The extent of the toll road is where routes stop agreeing

The tolled road at a booth SHALL be found by convergence. Every journey leaving an exit booth is on the same road until the network releases it, and only then do the journeys go to different places. So the last node they all share is the last node of the tolled road.

For an **exit** booth, the system SHALL route from the booth to each of its nearby places, take each route's node sequence from the booth node onward, and record the last node common to all of them as `last_toll_node_id`.

For an **enter** booth, the system SHALL route from each nearby place to the booth, take each route's node sequence up to the booth node, and record the first node common to all of them as `first_toll_node_id`.

Each recorded node SHALL be accompanied by its coordinates, as `first_toll_latlon` and `last_toll_latlon`. A node id alone cannot be routed to — the router takes coordinates — so an extent without them is an extent no consumer can measure between. They are taken from the same route's geometry, which carries one point per annotated node, so they cost no further request.

The sequence SHALL be taken from the booth node, not from the start of the annotation. The router snaps the query coordinate onto a lane and the returned sequence can begin a node before the booth, which belongs to no journey.

A booth whose routes share nothing beyond the booth node itself SHALL record that node. The tolled road ending at the barrier is an answer, not a failure.

A `gantry` booth SHALL NOT be measured, whether or not it carries `prices`. It charges for a section travelled rather than closing someone else's ticket, so the road at it is not the end of anything a tariff is divided by. The gantries carrying prices SHALL be reported as deliberately unmeasured, and their pairs fall back to the booth node.

A `passthrough` booth SHALL NOT be measured either. It carries a single amount for itself and no pair, so no distance divides it.

#### Scenario: An exit booth's extent is found

- **WHEN** AMBLAINVILLE, OSM node 288919803, is routed to its nearby places
- **THEN** the routes share a prefix of 64 nodes ending at node 240997497, 8.11 km beyond the barrier, and that node is recorded as `last_toll_node_id`

#### Scenario: An entrance booth's extent is found

- **WHEN** the nearby places of MERU, OSM node 288926127, are routed to it
- **THEN** the routes share a suffix beginning at node 5122294120, 0.41 km before the barrier, and that node is recorded as `first_toll_node_id`

#### Scenario: The extent carries its coordinates

- **WHEN** an extent node is recorded
- **THEN** its latitude and longitude are recorded beside it, taken from the geometry of the same route

#### Scenario: The extent ends at the barrier

- **WHEN** every route from an exit booth diverges at the booth node itself
- **THEN** the booth node is recorded as `last_toll_node_id`

#### Scenario: A gantry is not measured

- **WHEN** a `gantry` booth carrying `prices` is reached
- **THEN** no extent is recorded for it, and it is reported as deliberately unmeasured rather than as a gap

#### Scenario: The snapped node before the booth is not counted

- **WHEN** a route's node annotation begins one node before the booth node
- **THEN** that node is not part of the shared sequence, and the extent is measured from the booth node

### Requirement: Nearby places come from the route set

The places a booth is routed against SHALL be taken from the `places` list in `data/route_set.yaml`, which already carries 771 towns and villages with their node ids and coordinates. No new input SHALL be introduced.

The system SHALL use the nearest N by great-circle distance, N defaulting to 24 and settable. Twenty-four was measured to reach far enough in every direction that the routes genuinely diverge, while keeping the routing to about 30 000 queries over the whole inventory.

A `bidirectional` booth SHALL use a multiple of N, defaulting to four times. Its routes are split between its two sides and only one side serves the role being measured, so N places yield well under N usable routes — measured, 64 of its 90 roles fell below the floor at N=24. Four times rescues about half of them; the rest have few reachable places on that side whatever N is, and are left unmeasured.

A booth for which fewer than a configured minimum of those routes succeed SHALL be reported as a finding and left unmeasured, rather than having an extent derived from too few journeys to be a convergence at all.

#### Scenario: The nearest places are used

- **WHEN** a one-way booth is measured with the default N
- **THEN** the 24 nearest entries of the route set's `places` are routed against it

#### Scenario: A two-way booth is given more places

- **WHEN** a `bidirectional` booth is measured with the default N and multiplier
- **THEN** the 96 nearest places are routed against it, because the side filter discards those serving its other role

#### Scenario: Too few routes succeed

- **WHEN** fewer than the minimum number of a booth's place routes return a route
- **THEN** the booth is reported as a finding, no extent is recorded for it, and the step continues

### Requirement: The extent stops at the next booth

A shared sequence SHALL be truncated where it reaches another booth group, and the node before that booth SHALL be the extent.

Beyond another booth is another ticket. A corridor whose nearby places all lie past a second barrier would otherwise produce a shared prefix running into a section this tariff does not pay for, and the distance would be too long instead of too short.

Booth identity SHALL be decided the way the rest of the pipeline decides it: a node in `data/osm_toll_booths.yaml` under `toll_booths` or `aliases`, resolved through `parent_id`.

#### Scenario: A second barrier bounds the extent

- **WHEN** every route from an exit booth passes a second booth group before diverging
- **THEN** the extent is the node before that second booth, and the step says which booth bounded it

#### Scenario: An alias counts as its group

- **WHEN** a shared sequence reaches a lane recorded as an alias of another booth group
- **THEN** it is treated as that group and bounds the extent

### Requirement: A two-way booth is measured in both roles

A `bidirectional` booth that carries `prices` SHALL record both `first_toll_node_id` and `last_toll_node_id`, because it is an entrance to a journey driven one way and an exit to the same journey driven the other.

The two roles SHALL be told apart by the sides `data/bidirectional_booth_sides.yaml` already records. A route used for the exit role SHALL leave the booth by a node that is not in the booth's `inside_nodes`; a route used for the entrance role SHALL arrive at the booth from a node that is not in its `inside_nodes`. A route on the wrong side is measuring the other role's road and SHALL be discarded.

A `bidirectional` booth carrying no `prices` SHALL be skipped. It is a barrier: no journey has it as an end, so no tariff is divided by a distance from it.

#### Scenario: Both roles are recorded

- **WHEN** a `bidirectional` booth carrying `prices` is measured
- **THEN** its entry carries both `first_toll_node_id` and `last_toll_node_id`

#### Scenario: A route on the free side is discarded

- **WHEN** a route leaves a two-way booth by a node in its `inside_nodes` while the exit role is being measured
- **THEN** that route is not part of the convergence

#### Scenario: A barrier is skipped

- **WHEN** a `bidirectional` booth carries no `prices`
- **THEN** no extent is recorded for it and it is not reported as a gap

### Requirement: An overridden booth is not measured

A booth named in `data/osm_toll_booths_overrides.yaml` SHALL NOT have its extent derived by routing. Where the override states `first_toll_node_id` or `last_toll_node_id`, that value SHALL be recorded as given.

The override file is where a booth the road network describes wrongly is corrected by hand, and a derived value would overwrite the correction on the next run.

#### Scenario: A stated extent is published

- **WHEN** the override file states `last_toll_node_id` for a booth
- **THEN** that value appears in the price file and no routing is done for it

#### Scenario: An overridden booth with no stated extent

- **WHEN** a booth is named in the override file and states no extent
- **THEN** no extent is derived for it and it is not reported as a gap

### Requirement: A per-kilometre price is measured between the extent nodes

A priced pair's distance SHALL be measured from the entrance's `first_toll_node_id` to the exit's `last_toll_node_id` along the route between them, rather than from booth node to booth node.

This is the whole point of the capability. MERU to AMBLAINVILLE is priced at 1.90 EUR; booth to booth it is 1.5 km and reads 1.2422 EUR/km, and between the extent nodes it is 10.0 km and reads 0.19 EUR/km.

Where either end has no recorded extent, the booth node and its own coordinates SHALL be used for that end, so a partially measured inventory still prices every pair. Measured, 64 of 1 023 extents are unmeasured and all of them belong to two-way booths.

#### Scenario: The denominator is the tolled distance

- **WHEN** the pair MERU to AMBLAINVILLE is priced
- **THEN** its distance is measured from MERU's `first_toll_node_id` to AMBLAINVILLE's `last_toll_node_id`, about 10.0 km, and its rate is about 0.19 EUR/km

#### Scenario: An unmeasured end falls back to the booth

- **WHEN** a pair's exit booth carries no `last_toll_node_id`
- **THEN** the exit booth's own node is used as that end of the measurement

#### Scenario: The extent node is not on the route

- **WHEN** a pair's route does not traverse an end's recorded extent node
- **THEN** that end falls back to the booth node, and the step counts how often that happened

### Requirement: The step is resumable and always executes

The step SHALL always execute and SHALL read `data/vinci_price.yaml` to determine which booths it has already measured, measuring only the rest. Its unit of work is one booth, and it SHALL record a booth's extent before moving to the next, so an interrupted run repeats at most one booth.

A run against a complete file SHALL do no routing.

The step SHALL contact no external service and SHALL need no subscription key or tariff date. It asks only the router.

#### Scenario: The step resumes

- **WHEN** the step is interrupted partway through
- **THEN** the next run measures only the booths the price file does not already record

#### Scenario: A complete file is a no-op

- **WHEN** every priced booth already carries its extent
- **THEN** the step executes, finds nothing outstanding, and issues no route request

#### Scenario: No operator credentials are needed

- **WHEN** the step runs with no subscription key, no tariff date and no network
- **THEN** it completes normally

### Requirement: The extents are reported

The step SHALL report, for every booth it measured, the distance from the barrier to the extent node, and SHALL list the largest first. It SHALL report how many booths were bounded by a second barrier and how many were left unmeasured, with the reason.

An extent of many kilometres is either a real slip road or a convergence that ran too far, and the two are told apart by looking. A report that shows only a count hides which it was.

#### Scenario: The extents are listed

- **WHEN** the step completes
- **THEN** it prints the measured booths with their extent distance, largest first, each with its OSM node link

#### Scenario: The bounded and the unmeasured are counted

- **WHEN** the step completes
- **THEN** it reports how many extents were truncated at a second booth and how many booths went unmeasured, by reason
