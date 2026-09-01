## ADDED Requirements

### Requirement: The extent of the toll road is where the driver commits

The tolled road at a booth SHALL be found by commitment. The extent is the point at which the driver loses the choice not to pay, and that is a property of the road network rather than of any set of journeys over it.

For an **enter** booth, the system SHALL find the region of nodes from which every continuation reaches the booth, and record its free-side boundary as `first_toll_node_id`. A node belongs to the region when every road leaving it leads into the region; the booth's own lane nodes seed it.

For an **exit** booth, the system SHALL find the region of nodes into which every arrival came from the booth, and record its free-side boundary as `last_toll_node_id`. A node belongs to the region when every road entering it comes from inside the region.

A branch SHALL count as a way out only if it reaches the open network without crossing a toll point. Two kinds fail that test, and both ended a tolled road at its barrier:

- **A branch that leads nowhere.** Péage de Gye on the A 31 was ended by a two-node `motorway_link` stub off the junction before it; a driver taking it reaches the end of the road and can only turn round and pay. Its tolled road in fact begins 2.50 km back.
- **A branch that leads further into the toll network.** ARGENTAN's exit has an on-ramp merging fifty metres past the barrier, and that ramp is fed seven metres back by a booth of its own, so its traffic has paid too. Its tolled road runs 9.13 km, not nothing.

A booth the override file marks `type: ignore` SHALL still count as a toll point here. `ignore` states that no route passes that lane, which settles pricing and grouping and does not settle what stands on the ground: traffic that came past one has paid, and the road it merges onto is still tolled. ARGENTAN's ramp is fed by exactly such a booth.

The closure that decides this SHALL be bounded. A toll pocket — a plaza's own roads, the ramp between two adjacent barriers — is a handful of nodes; a tolled carriageway is tens of kilometres, and admitting one as a pocket makes an exit's region run until the network releases it, past the edge of the extract for a quarter of all roles. Measured, a bound of 500 nodes separates the two.

Whether a branch that leads nowhere is a mapping artefact or the edge of the extract cannot be told from inside the graph. A region that absorbed one more than 8 km from the barrier SHALL be re-derived over the wider carve; nearer than that, the extract reaches at least 11 km, so the road stops because the map says so.

The published node SHALL be the region's own boundary: the node one segment inside it, which is the first node the driver reaches already committed. Where several roads meet the corridor at one point, the one nearest the booth by road distance SHALL be published.

The free node just outside — the last node at which a choice still existed — names the same junction and sits a median of 19 m away, so neither is the better measurement. The inside node is published because a consumer routes between the published coordinates, and a junction is where a router's snapping is ambiguous: asked to start from one, the router may take a different arm and never traverse the node it was given. `builder/build_segment_weights.py` discards such a pair and falls back to barrier-to-barrier. Measured over the 23 410 priced pairs, publishing the free node discards 3 912 of them and publishing the inside node discards 326, against 3 100 before this change.

A roundabout node SHALL never lie inside a region, because it always carries a road leaving it that does not reach the booth, and a road entering it that did not come from the booth. Where a slip road meets a roundabout the ring node is therefore the free node and the published extent is the slip road node beside it, so the tolled section stops at the junction instead of running around the ring. Measured over the 1 024 extents, 0 inside-region nodes lie on a roundabout.

The region SHALL be computed over the drive classes — the through classes plus `unclassified`, `residential`, `living_street`, `service`, `winter_road` and `ice_road` — the set `builder/booth_groups.py` already uses to decide what lies beyond a booth. Any road a car profile can drive SHALL count as an escape.

The test is what the driver can do, not what class the escape carries. A section a driver can leave by is a section the driver was not committed to, and charging a tariff over it would spread that tariff onto road the driver need not have paid for. Where a public rest area or access road joins a slip road, the region therefore stops at that junction. Measured, 109 of the 1 024 extents reach no further than the barrier's own neighbour for this reason.

Direction SHALL be decided by `booth_groups.two_way`, so the graph an extent is derived from and the graph the booths were grouped on can never disagree.

Each recorded node SHALL be accompanied by its coordinates, as `first_toll_latlon` and `last_toll_latlon`. A node id alone cannot be routed to — the consumer takes coordinates — so an extent without them is an extent no consumer can measure between.

A booth whose region is bounded one segment from the barrier SHALL record that boundary. The tolled road ending at the barrier is an answer, not a failure, and 109 of the 1 024 extents are that answer.

A `gantry` booth SHALL NOT be measured, whether or not it carries `prices`. It charges for a section travelled rather than closing someone else's ticket, so the road at it is not the end of anything a tariff is divided by. The gantries carrying prices SHALL be reported as deliberately unmeasured, and their pairs fall back to the booth node.

A `passthrough` booth SHALL NOT be measured either. It carries a single amount for itself and no pair, so no distance divides it.

#### Scenario: An entrance booth's extent is the head of its slip road

- **WHEN** the region of booth 142268 is computed
- **THEN** its free node is 1320680243, the head of the slip road where the depot loop branches away, and the node inside beside it, 3011249583, is recorded as `first_toll_node_id` in place of ring node 142274

#### Scenario: An exit booth's extent is where the slip meets the ring

- **WHEN** the region of booth 137232 is computed
- **THEN** its free node is 805520, the roundabout node its slip joins, and the node inside beside it, 8006502773, is recorded as `last_toll_node_id` in place of 805521 further around ring way 4270765

#### Scenario: The extent never runs around a roundabout

- **WHEN** any booth's extent is recorded
- **THEN** no node inside its region lies on a way tagged `junction=roundabout`

#### Scenario: A stub is not a way out

- **WHEN** the junction before booth 1482474156 carries a `motorway_link` that stops after one node
- **THEN** the region grows past that junction, and the extent is recorded 2.50 km from the barrier rather than at it

#### Scenario: A branch into the toll network is not a way out

- **WHEN** an on-ramp merges past booth 268212668's barrier and is itself fed by a booth the override marks `type: ignore`
- **THEN** the region grows past the merge, and the extent is recorded 9.13 km from the barrier rather than at it

#### Scenario: An open service branch ends the tolled road

- **WHEN** a service road a car may drive, behind no gate and barred by no access tag, leaves a slip road inside a booth's region
- **THEN** the region stops at that junction, because a driver reaching it can leave without paying

#### Scenario: The extent carries its coordinates

- **WHEN** an extent node is recorded
- **THEN** its latitude and longitude are recorded beside it

#### Scenario: The extent ends at the barrier

- **WHEN** a booth's region reaches a junction one segment from the barrier
- **THEN** that junction is recorded as the extent, and the tolled road ending at the barrier is the answer

#### Scenario: A gantry is not measured

- **WHEN** a `gantry` booth carrying `prices` is reached
- **THEN** no extent is recorded for it, and it is reported as deliberately unmeasured rather than as a gap

### Requirement: The graph is the one the router drives

The graph a region is grown over SHALL admit exactly what the routing profile admits. A road the router cannot take is not an escape, and treating it as one ends a tolled section at a fork the driver never sees.

The system SHALL bar a way whose access the profile bars, resolving `motorcar`, `motor_vehicle`, `vehicle` and `access` in that order and taking the first that is present. Measured, 29 294 ways in the carved extract are barred to a car.

The system SHALL treat a node carrying a `barrier` value the profile does not whitelist as impassable, and SHALL treat a `gate` or `lift_gate` as impassable unless an allowed highway class carries it — the rule `builder/patch_car_profile.py` compiles into the profile. Measured, the extract holds 27 163 barrier nodes and 15 735 gates, of which 15 729 are carried by an allowed class.

The system SHALL treat every node of `data/nodes_blacklist.yaml` as impassable, for the same reason the profile does: the map is wrong about that connection, and a region that walks through one stops at a fork that is not there on the ground.

Honouring all four leaves 9 031 nodes impassable in the carved extract. It changes 4 of the 1 024 extents, and where it does the looser graph is shorter by a median of 245 m, having found an escape the router does not have. The reason the rule is stated rather than left to chance is the coupling it protects: `builder/build_segment_weights.py` falls back to barrier-to-barrier whenever a pair's route does not traverse a recorded extent node, so an extent placed behind a locked gate would be discarded without any error being raised.

#### Scenario: A way the profile bars is not an escape

- **WHEN** a service road tagged `access=private` leaves a slip road inside a booth's region
- **THEN** the region continues past it, because a car may not take that road

#### Scenario: A closed gate is not an escape

- **WHEN** a branch leaving a booth's region passes a `barrier=gate` node that no allowed highway class carries
- **THEN** the region continues past that branch, because the profile treats the gate as shut

#### Scenario: A blacklisted node is not an escape

- **WHEN** a branch leaving a booth's region passes a node listed in `data/nodes_blacklist.yaml`
- **THEN** the region continues past that branch, because the router cannot cross that node either

#### Scenario: The extent node is reachable by the router

- **WHEN** the pairs of a rebuilt price file are routed extent to extent
- **THEN** no pair falls back for "extent node not on the route" that did not fall back before

### Requirement: The graph reaches further than the answer

The system SHALL derive every region from an extract that reaches at least 11 km beyond every booth, and from a second, wider one where that is not enough. It SHALL read no route set and SHALL issue no routing request.

The distance is what the answers demand: a tolled slip road runs 8.11 km past AMBLAINVILLE, and the 2 km cells `builder/booth_groups.py` carves for grouping end inside it. A region that runs out of data does not stop at a junction — it stops at nothing, which reads as "the tolled road ends here" and is a fabrication. Reusing the grouping carve produced exactly that for 15 extents, AMBLAINVILLE among them, and drove its pair from 0.19 to 1.03 EUR/km.

The extract SHALL be cut from the source extract in two cached stages, as the pipeline's other extracts are: the drive classes of the whole country, then cells around the booths. The second stage is what makes the graph fit in memory — the country's drive network is 40.8 million nodes and the carve is 18.2 million.

A region that reaches a node the graph stops at, or that finds no free side at all, SHALL NOT be published from that extract. A cul-de-sac and the edge of the carve are indistinguishable from inside the graph, and the second means the answer was not established by the road.

Such a booth SHALL be re-derived over a second carve, cut around those booths alone and reaching at least three times as far. Cutting it around the whole inventory would cost the memory of a country to answer for a handful of booths: measured, 18 roles over 18 booths needed it, and the carve was 84 cells and 71 MB. RESTIGNE's tolled road is 19.05 km, the longest in the inventory and genuine — the A 85 has no junction for that distance — and the first carve cannot see the end of it.

The second carve SHALL NOT be cached. Its booth set is the first pass's finding rather than an input, and a file kept from an earlier set would answer for the wrong booths.

A region the second carve cannot bound either SHALL be reported and left unmeasured. The consumer already falls back to the booth node for an absent extent, and recording that node here would state as a measurement what is in fact a gap. Measured, none remains.

The system SHALL bound each region at a stated maximum size and SHALL report a booth that reaches it, so a defect in the class filter cannot produce an unbounded walk.

#### Scenario: No route set is read

- **WHEN** the step runs
- **THEN** it opens no route set and issues no routing request

#### Scenario: The same road gives the same answer

- **WHEN** the step is run twice against one extract
- **THEN** every extent is identical, including booths whose extents differed between two published route sets

#### Scenario: A region that cannot be bounded is reported

- **WHEN** a region reaches the stated maximum size
- **THEN** the booth is reported and no extent is derived for it

#### Scenario: A region that runs out of data is given a wider carve

- **WHEN** a region reaches a node the graph stops at, or finds no free side
- **THEN** the booth is re-derived over a carve cut around it alone and reaching three times as far, and only a region that carve cannot bound either is left unmeasured

#### Scenario: The wider carve bounds the longest extent

- **WHEN** RESTIGNE's region, which runs 17.5 km past the first carve's edge, is re-derived
- **THEN** it is bounded at 19.05 km by a junction on the A 85

#### Scenario: The extract reaches past the longest extent

- **WHEN** AMBLAINVILLE's exit region is derived
- **THEN** the extract still carries road beyond its 8.11 km of tolled slip road, and the region is bounded by a junction rather than by the edge of the data

### Requirement: A two-way booth is measured in both roles from its free side

A `bidirectional` booth that carries `prices` SHALL record both `first_toll_node_id` and `last_toll_node_id`, because it is an entrance to a journey driven one way and an exit to the same journey driven the other.

The two roles SHALL be told apart by the sides `data/bidirectional_booth_sides.yaml` already records. A region SHALL leave the booth only by a node that is not in the booth's `inside_nodes`: the entrance's region grows back from the free side, and the exit's region forward onto it. A region grown through the inside nodes is the other role's road.

A `bidirectional` booth carrying no `prices` SHALL be skipped. It is a barrier: no journey has it as an end, so no tariff is divided by a distance from it.

A two-way booth SHALL NOT be given a larger sample than a one-way one, because no sample is taken. The 64 roles that fell below the convergence floor at N=24, and the 33 that stayed unmeasured at four times that, SHALL be measured like any other.

#### Scenario: Both roles are recorded

- **WHEN** a `bidirectional` booth carrying `prices` is measured
- **THEN** its entry carries both `first_toll_node_id` and `last_toll_node_id`, each on the free side

#### Scenario: The toll side is not entered

- **WHEN** a two-way booth's region is grown for its exit role
- **THEN** no node of its `inside_nodes` is used to leave the booth

#### Scenario: A barrier is skipped

- **WHEN** a `bidirectional` booth carries no `prices`
- **THEN** no extent is recorded for it and it is not reported as a gap

#### Scenario: A booth with few reachable places is still measured

- **WHEN** a two-way booth whose free side reaches few places is measured
- **THEN** its extent is derived from its region like any other booth's

## MODIFIED Requirements

### Requirement: The extent stops at the next booth

A region SHALL NOT grow through another booth group. Where the region reaches a node belonging to another group, that node SHALL bound it, and the extent SHALL be the free node on that side.

Beyond another booth is another ticket. A corridor that ran on through a second barrier would carry a section this tariff does not pay for, and the distance would be too long instead of too short.

Booth identity SHALL be decided the way the rest of the pipeline decides it: a node in `data/osm_toll_booths.yaml` under `toll_booths` or `aliases`, resolved through `parent_id`. A booth's own lanes and aliases SHALL seed its region rather than bound it, so a plaza's parallel lanes do not read as a choice.

#### Scenario: A second barrier bounds the extent

- **WHEN** a booth's region reaches a node belonging to another booth group
- **THEN** the region stops there, and the step says which booth bounded it

#### Scenario: An alias counts as its group

- **WHEN** a region reaches a lane recorded as an alias of another booth group
- **THEN** it is treated as that group and bounds the region

#### Scenario: A plaza's own lanes do not bound it

- **WHEN** a booth group's lanes fork upstream of the barrier
- **THEN** the fork node lies inside the region, because every road leaving it reaches a lane of the same group

### Requirement: The step is resumable and always executes

The step SHALL always execute and SHALL read `data/vinci_price.yaml` to determine which booths it has already measured, measuring only the rest. Its unit of work is one booth, and it SHALL record a booth's extent before moving to the next, so an interrupted run repeats at most one booth.

A run against a complete file SHALL do no work beyond reading the extract.

The step SHALL contact no external service and SHALL need no subscription key, no tariff date, and no routing service. It reads an extract and the artefacts the pipeline has already published.

#### Scenario: The step resumes

- **WHEN** the step is interrupted partway through
- **THEN** the next run measures only the booths the price file does not already record

#### Scenario: A complete file is a no-op

- **WHEN** every priced booth already carries its extent
- **THEN** the step executes and derives no region

#### Scenario: No operator credentials are needed

- **WHEN** the step runs with no subscription key, no tariff date and no network
- **THEN** it completes normally

#### Scenario: No router is needed

- **WHEN** the step runs with no routing service reachable
- **THEN** it completes normally

### Requirement: The extents are reported

The step SHALL report, for every booth it measured, the road distance from the barrier to the extent node, and SHALL list the largest first. It SHALL report how many regions were bounded by a second barrier, how many booths recorded the booth node for want of a boundary, and how many had an ambiguous boundary.

A region with several boundary nodes — two roads meeting the corridor at one point — SHALL publish the one nearest the booth by road distance, and SHALL be counted as ambiguous. Measured, 292 of 1 024 extents have more than one.

An extent of many kilometres is either a real approach road or a region the class filter has made too generous, and the two are told apart by looking. The step SHALL name every extent beyond a stated distance rather than only counting it.

#### Scenario: The extents are listed

- **WHEN** the step completes
- **THEN** it prints the measured booths with their extent distance, largest first, each with its OSM node link

#### Scenario: The bounded and the unmeasured are counted

- **WHEN** the step completes
- **THEN** it reports how many regions were truncated at a second booth and how many booths went unmeasured, by reason

#### Scenario: An ambiguous boundary is resolved and reported

- **WHEN** a booth's region has two free-side boundary nodes
- **THEN** the nearer by road distance is published, and the booth is counted as ambiguous

#### Scenario: A long extent is named

- **WHEN** a booth's extent lies further from the barrier than the reporting threshold
- **THEN** the step names that booth and its distance rather than only counting it

## REMOVED Requirements

### Requirement: The extent of the toll road is where routes stop agreeing

**Reason**: Convergence over a sample of journeys answers "where do these routes stop agreeing", which equals "where does the driver commit" only when the corridor has a single approach. Where approaches merge before the corridor — an interchange roundabout, most often — the sample agrees along the merged road too, and the extent runs past the junction by however far the sample happens to agree. Measured over the 990 published extents, 753 lie beyond the commitment point and 436 sit on a roundabout node, by a median of 162 m and by more than 1 km on 56 of them. `builder/build_segment_weights.py` spreads each tariff over the route between the extents, so those ring segments carry a share of a toll that nobody pays to drive them. The result is also unstable: rebuilding the route set moved 500 of the 990 extents with no change to the road.

**Migration**: Replaced by "The extent of the toll road is where the driver commits". The fields, their names and their coordinates are unchanged, so no consumer changes. 500 of the 990 recorded values move, and `data/segment_weights.csv` is rebuilt from them.

### Requirement: Nearby places come from the route set

**Reason**: The place list, the place count N, the four-times multiplier for two-way booths and the minimum-route floor are all parameters of the sampling this change removes. With no sample there is nothing to draw places for, nothing for N to size, and no floor below which a convergence is not a convergence.

**Migration**: Replaced by "The graph reaches further than the answer". `data/route_set.yaml` remains an input to the steps that already read it and stops being one here.

### Requirement: A two-way booth is measured in both roles

**Reason**: Its side test is stated in terms of the routes the convergence used — a route leaving by an `inside_nodes` node was discarded from the sample. With no sample there are no routes to discard. The same fact about sides now governs which way a region may grow out of the booth, which is a different mechanism and reads as one.

**Migration**: Replaced by "A two-way booth is measured in both roles from its free side". Both fields, both roles and the sides file are unchanged. The 33 roles left unmeasured for want of usable routes gain an extent.
