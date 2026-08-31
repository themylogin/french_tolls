# route-algorithm-tests Specification

## Purpose
Defines the unit test suite for the two pieces of the route algorithm worth protecting — the waypoint search and the toll total — what a test may depend on, the hand-built graph and booth table it is driven from, and what each subject must demonstrate.

## Requirements

### Requirement: A test depends on the code and on nothing else

The suite SHALL run without a routing service, without the OSRM graphs, and without any file under `data/`.

It SHALL run inside a container built from the application's own image, so that what is tested is the code as it ships rather than a copy assembled by a test harness.

A checkout with no `.env`, no graphs, and no pipeline output SHALL be able to run it. The dependency the suite replaces put every assertion behind 30 GB of graph and two long-running services, so the two pieces of logic worth protecting could not be exercised at all without them.

No test SHALL import a module that reads an artefact at import time. `route` does, so a unit test SHALL reach `waypoints`, `tolls`, `osrm`, and `booths` directly rather than through it.

#### Scenario: The suite runs with nothing else running

- **WHEN** the suite is run with both routers stopped and `data/` unmounted
- **THEN** every test runs and passes

#### Scenario: The suite runs in the application image

- **WHEN** the test runner starts
- **THEN** it runs from the same image definition the web service and the bot are built from

#### Scenario: No test reaches the network

- **WHEN** the suite runs
- **THEN** no HTTP request is issued

### Requirement: The routing graph a test uses is built by hand

Where a test needs routing answers, they SHALL come from a stub standing in for `Routers`, over a graph written out in the test.

A hand-built graph is not a weaker substitute for France; for this purpose it is a stronger one. The cases that matter — a position that snaps onto a parallel carriageway, a stretch that lies on no fastest path, a leg that leaves the optimal route and rejoins it — can be written down, whereas in the real extract they have to be hunted for, and they move whenever the extract is rebuilt.

The stub SHALL answer the same questions the real client answers — snapping a coordinate, and a fast route between two snapped points — and SHALL count requests so the query budget can be reached deliberately.

The stub SHALL NOT reimplement the search. It answers routing questions; what the search does with the answers is what the tests are measuring.

#### Scenario: A stub answers routing questions

- **WHEN** the waypoint search is run in a test
- **THEN** every route and every snap it asks for is answered by the stub, from the graph the test wrote

#### Scenario: The stub counts what it was asked

- **WHEN** a test sets a query budget below what the search needs
- **THEN** the stub's count reaches that budget and the search stops

### Requirement: The waypoint search is tested by behaviour

The suite SHALL demonstrate each of the following, and SHALL assert the behaviour rather than a recorded value:

- a journey whose fast and optimal routes are the same road yields no waypoint;
- the search reaches the furthest position whose leg reproduces the optimal route, and not a midpoint short of it;
- every emitted waypoint has had its own leg from the preceding anchor verified;
- a position whose bare coordinate snaps onto a road the optimal route does not drive is not emitted, and an earlier position is used instead;
- a leg that leaves the optimal route and rejoins it before the far end does not count as reproducing it;
- a leg carrying one extra node equal to the neighbour of an endpoint *on the optimal route* does count, and one carrying any other extra node does not;
- the waypoint cap truncates the list, reports how many were needed, and marks the answer incomplete;
- the query budget stops the search, returns what was verified, marks the answer incomplete, and raises nothing;
- a stretch where no leg reproduces the route is recorded as a divergence, the search continues past it, and no leg is requested twice.

#### Scenario: Identical routes need no waypoint

- **WHEN** the stub's fast and optimal routes are the same node sequence
- **THEN** the search emits no waypoint and marks the answer complete

#### Scenario: The furthest reach is taken

- **WHEN** the furthest reproducing position lies at nine tenths of the route
- **THEN** the waypoint is emitted there, not at the midpoint

#### Scenario: A waypoint beside another road is rejected

- **WHEN** the furthest reproducing position snaps, unaided, onto a segment the optimal route does not drive
- **THEN** an earlier position is emitted instead, and its own leg was verified

#### Scenario: The cap truncates and says so

- **WHEN** a route needing four waypoints is searched with the cap set to two
- **THEN** two are returned, four is reported as the number needed, and the answer is marked incomplete

#### Scenario: The budget raises nothing

- **WHEN** the budget is set below what the search needs
- **THEN** the verified waypoints are returned, the answer is marked incomplete, and no exception reaches the caller

#### Scenario: A divergence does not fail the journey

- **WHEN** no leg from an anchor reproduces the optimal route
- **THEN** a divergence is recorded, the search continues to the destination, and no leg is requested a second time

### Requirement: The toll total is tested against booths written by hand

The suite SHALL build the booth table in the test — booths, lanes, types, gare codes, tariffs, and the two sides of a two-way barrier — and SHALL run the accounting over a node sequence it writes.

Hand-built booths are what make the states testable. A route that begins inside the toll network, an entrance never closed, a gare the entrance does not price, a booth absent from the price file: each of these is three lines to write and a hunt through 1 295 real booths to find.

The suite SHALL demonstrate:

- an entrance and a later exit produce one passage named `<entrance> → <exit>`, priced by the exit's gare code;
- a `passthrough` and a `gantry` are each charged their own flat amount, and neither opens nor closes a ticket;
- a `bidirectional` barrier reached from an outside node opens a ticket, and the same barrier reached from an inside node closes one, so the two directions produce different passages;
- a `bidirectional` barrier whose preceding node is neither side is resolved from the following node with the sense reversed, and one whose neighbours resolve to neither side is recorded unpriced;
- a node the inventory records as a lane is accounted against the booth it is a lane of;
- consecutive nodes resolving to one booth produce one passage, and the same booth reached again later produces another;
- the total is the sum of the priced passages.

#### Scenario: A ticketed section is priced by the exit's gare

- **WHEN** a route passes an entrance pricing gare `00002` at 13.70 EUR, and later the exit carrying that gare
- **THEN** one passage named `<entrance> → <exit>` costs 13.70 EUR

#### Scenario: The two directions of a two-way barrier differ

- **WHEN** a two-way barrier is crossed from an outside node, and then in a second journey from an inside node
- **THEN** the first opens a ticket and the second closes one, and the two passage lists differ

#### Scenario: A lane is charged as its plaza

- **WHEN** the route's node sequence carries a lane recorded as an alias
- **THEN** the passage is accounted against the booth that lane belongs to

#### Scenario: One plaza, one passage

- **WHEN** two consecutive nodes resolve to the same booth
- **THEN** one passage is recorded

### Requirement: Every unpriceable state is demonstrated

The suite SHALL demonstrate each state the accounting cannot price, and SHALL assert that the passage carries its own reason, carries no cost, and does not raise:

- an exit reached with no ticket open;
- an entrance reached while a ticket is already open;
- an exit whose gare the open entrance does not price;
- an exit carrying no gare code at all;
- a booth absent from the price file;
- a `passthrough` or `gantry` carrying no amount;
- a two-way booth whose neighbours resolve to neither side;
- a route ending with a ticket still open.

A cost of zero SHALL NOT be accepted for any of them. Zero says the crossing was free, which is a different claim from not knowing what it cost.

The count of unpriced passages SHALL be asserted alongside them.

#### Scenario: An unpriceable passage carries a reason and no cost

- **WHEN** any of the listed states is reached
- **THEN** the passage carries that state's own reason, its cost is absent rather than zero, and nothing is raised

#### Scenario: Each state has its own reason

- **WHEN** the reasons of the listed states are compared
- **THEN** no two of them are the same string

### Requirement: A test names one behaviour

Each test SHALL exercise one behaviour, and its name SHALL say which. A failure SHALL identify the behaviour that broke without the reader having to open the file.

The suite SHALL NOT parameterise one assertion across a list of journeys. That is what produced 96 cases carrying about a dozen distinct claims, where a single change failed a dozen of them and none of the names said what was wrong.

#### Scenario: A broken pricing rule fails a named test

- **WHEN** the tariff lookup is changed to take the wrong gare
- **THEN** the failing test's name identifies entrance-to-exit pricing
