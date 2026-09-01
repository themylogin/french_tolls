# bidirectional-booth-sides Specification

## Purpose
Defines how the two sides of a booth on a two-way road are told apart — the adjacent nodes the inventory records, how the router is probed to decide whether a side lies on the toll network or on free roads, what makes an observation admissible, the two states a booth may settle into, and the errors that stop the pipeline when it settles into neither.

## Requirements

### Requirement: The inventory records the adjacent nodes of a two-way booth and how they are reached

Step 3 SHALL write `adjacent_nodes` on every booth it types `bidirectional`: a mapping from each node adjacent to the booth along a way of a through road class, to whether the way reaching it is one-way — `true` for one-way, `false` for two-way.

A node reached by more than one way SHALL carry `false` when any of them is two-way. Onewayness SHALL be decided by the same function that decides the `bidirectional` type itself, so the two can never disagree.

A booth of any other type SHALL NOT carry the key. A one-way booth has one traffic sense, so it has no sides to tell apart.

#### Scenario: A two-way booth carries its neighbours and their onewayness

- **WHEN** the inventory is written
- **THEN** every `bidirectional` booth carries `adjacent_nodes` mapping each node beside it on a through-class way to `true` or `false`

#### Scenario: A one-way booth carries nothing

- **WHEN** a booth is typed `gantry` or carries no type
- **THEN** it carries no `adjacent_nodes`, `inside_nodes`, or `outside_nodes`

### Requirement: A side is inside when a vehicle there is holding a ticket

`inside_nodes` and `outside_nodes` SHALL partition a two-way booth's adjacent nodes.

A node is **inside** when a vehicle passing it is on the toll network, holding a ticket it will have to pay. A node is **outside** when a vehicle passing it circulates freely.

The distinction SHALL NOT be taken from OSM's `toll` tag, from direction of travel, or from any global topology of the network. Direction of travel in particular says nothing: an ordinary interchange ramp is driven both ways, and a booth on it is neither an entrance nor an exit by virtue of that.

#### Scenario: The sides partition the adjacency

- **WHEN** a booth settles
- **THEN** every node of its `adjacent_nodes` appears in exactly one of `inside_nodes` and `outside_nodes`

### Requirement: The sides are established by probing the router

The system SHALL route between each two-way booth and a set of targets, in both directions, and SHALL read each side from what the route reaches.

Targets SHALL be of two kinds, and both are required:

- every booth the price file records as `enter` or `exit`;
- places, spread over bearing sectors around the booth so that each side of it is offered a destination.

Booth targets alone cannot settle a booth. Booths sit on the motorway, so the router leaves by a ramp to reach any of them and the free side is never exercised. Place targets are what reach it.

#### Scenario: Both kinds of target are used

- **WHEN** the probe runs
- **THEN** it routes to enter/exit booths and to places, and in both directions

#### Scenario: Booth targets alone leave the free side unobserved

- **WHEN** a booth is probed with booth targets only
- **THEN** its free side receives no observation and the booth does not settle

### Requirement: What each target says about the side

An admitted observation SHALL settle the side as follows:

| the route | and the target is | the side is |
|---|---|---|
| arrives at the target | an `exit` booth | inside |
| arrives at the target | an `enter` booth | outside |
| departs from the target | an `enter` booth | inside |
| departs from the target | an `exit` booth | outside |
| arrives at a place | — | outside |

Arriving at an exit means you were holding a ticket to surrender there. Departing from an entrance means you had just taken one. The two directions are opposites and confusing them makes every side collect both labels, so neither can ever settle.

Reaching a place having passed no booth needs no role at all: a vehicle that got there was never ticketed.

#### Scenario: Reaching an exit booth marks the side inside

- **WHEN** a route leaves the booth by node D and arrives at an `exit` booth with nothing in between
- **THEN** D is inside

#### Scenario: Leaving an exit booth marks the side outside

- **WHEN** a route departs from an `exit` booth and reaches the booth by node A with nothing in between
- **THEN** A is outside

#### Scenario: Reaching a place marks the side outside

- **WHEN** a route leaves the booth by node D and reaches a place having crossed no booth
- **THEN** D is outside

### Requirement: A settled booth is an entrance/exit or a barrier

A booth whose every adjacent node is settled SHALL be in exactly one of two states:

- **entrance/exit** — at least one node inside and at least one outside. Driven one way it is an entrance, the other way an exit.
- **barrier** — every node agreeing. You pay passing it and your ticket state does not change: outside on every side is a barrier on free roads, inside on every side one within the network.

#### Scenario: An entrance/exit settles

- **WHEN** a booth has one inside node and one outside node
- **THEN** it is recorded as an entrance/exit

#### Scenario: A barrier settles

- **WHEN** every adjacent node of a booth is outside
- **THEN** it is recorded as a barrier

### Requirement: A contradicted side stops the step

A node with observations on both sides SHALL stop the step, naming the node, the count each way, and the routes behind the minority.

The minority is almost never noise. It is a route using a connection that does not exist, or a target whose recorded role is wrong, and naming it is how those are found. Outvoting it would bury the defect it reports.

#### Scenario: A node observed both ways stops the step

- **WHEN** a node collects both inside and outside observations
- **THEN** the step stops and names the node, both counts, and the minority routes

#### Scenario: The minority routes are identifiable

- **WHEN** the step stops on a contradicted node
- **THEN** each minority route is reported with its target, its direction, and its length

### Requirement: A side the sweep leaves unobserved is retried against the place catalogue

Where a side receives no admitted observation, the system SHALL retry it against places drawn from the inventory's place catalogue, and SHALL settle it by the rules already in place.

The sweep's places come from `data/route_set.yaml`, which lists the places the coverage search used as route endpoints — 745 of them. The catalogue in `data/filtered.osm.pbf` holds every `place=` node the extract carries. A side goes unobserved when no offered target is best reached that way, and a target too far off is beaten by the motorway however the roads lie.

Péage de Thèze, booth 986537073, is the case. Its free side is a slow local road against the A 65, and its nine route-set places are all reached past another barrier. Lalonquette — `place=village`, node 1825323182 — is 2.0 km up that local road and is not in the route set. Against it the sweep settles the side at once, in both directions, with one booth on the route.

The catalogue SHALL be consulted only for a side the sweep leaves unobserved. Every booth the sweep settles SHALL settle from the same targets it uses today, so this cannot move a side that is already established.

Catalogue targets SHALL be selected by the rule the sweep already uses for places — nearest per bearing sector, within the same distance bounds — so that a side is offered a destination in its own direction.

The verdict, the between-booth filter and the admission rules SHALL be unchanged. Only where the targets come from changes.

#### Scenario: A side no route-set place reaches is settled from the catalogue

- **WHEN** the sweep leaves node 10977821568 of booth 986537073 unobserved
- **THEN** the step retries that side against catalogue places and settles it `outside` from a village 2.0 km along it

#### Scenario: A settled booth is not revisited

- **WHEN** every side of a booth received an observation from the sweep
- **THEN** the catalogue is not consulted for it, and its sides are those the sweep established

#### Scenario: The verdict rules are unchanged

- **WHEN** a catalogue route reaches a place having crossed no booth
- **THEN** the side is outside, by the same rule that governs a route-set place

### Requirement: The report says which sides rest on the catalogue

A side settled from the catalogue SHALL be reported as such, apart from the sweep's counts.

A reader deciding whether to trust a side should not have to work out which pool produced it, and the count is what would say the sweep's own places have stopped being enough.

#### Scenario: A catalogue side is named

- **WHEN** the step settles a side from the catalogue
- **THEN** it reports that booth and that node, apart from the ordinary counts

### Requirement: A side with no evidence is reported, not fatal

A node no admitted observation reached, after both the sweep and the catalogue retry, SHALL be reported and SHALL NOT stop the step. The booth does not settle, and nothing downstream may treat it as settled.

That is a gap in what the probe reached, of the same kind as an uncovered coverage target, and this pipeline reports those rather than dying on them.

#### Scenario: An unobserved side is reported

- **WHEN** a booth ends the run with a node in neither set
- **THEN** the booth and that node are reported, and the step continues

#### Scenario: The catalogue is tried before the report

- **WHEN** the sweep leaves a side unobserved
- **THEN** the side is reported unobserved only after the catalogue retry has also failed to settle it

### Requirement: Output format

The system SHALL write `data/bidirectional_booth_sides.yaml`: a mapping from booth group id to `inside_nodes` and `outside_nodes`, each a list of node ids in ascending order, and each written only when not empty.

A booth that did not settle SHALL carry whatever was established and SHALL be distinguishable from a settled one by the absence of its remaining nodes from both lists, checked against the inventory's `adjacent_nodes`.

The file SHALL NOT be written by any other step, and no other step's output SHALL be written by this one.

#### Scenario: The file is written

- **WHEN** the step completes
- **THEN** `data/bidirectional_booth_sides.yaml` parses as YAML and holds one entry per `bidirectional` booth

#### Scenario: Rewriting is stable

- **WHEN** the step runs again against unchanged inputs
- **THEN** the result is byte-identical

### Requirement: An observation counts only when no booth lies between

An observation SHALL be admitted only when the route traverses the booth, and no other booth group lies between the booth and the target.

The side observed SHALL be the node immediately after the booth when routing away from it, and the node immediately before it when routing towards it.

The step SHALL NOT filter observations against a node blacklist. The routing profile makes a blacklisted node impassable, so a route over one is never returned, and a filter here would imply otherwise.

#### Scenario: A booth in between voids the observation

- **WHEN** a route from the booth to its target crosses a third booth
- **THEN** the observation is discarded

#### Scenario: No route can use a blacklisted node

- **WHEN** the probe runs
- **THEN** no returned route traverses a blacklisted node, and none is discarded for doing so

#### Scenario: The side is the node beside the booth

- **WHEN** a route leaves the booth by node D on its way to a target
- **THEN** the observation is about D
