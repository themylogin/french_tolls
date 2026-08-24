## ADDED Requirements

### Requirement: Every route begins and ends where a car can

Both endpoints of every emitted route SHALL be eligible route endpoints as the inventory defines them, which includes the reachability condition. A route SHALL NOT be emitted when the routing engine places its start or its end on a road that the endpoint has no access to.

An endpoint snapped onto a motorway carriageway makes the trip begin in traffic that no driver can join there. The route the engine then returns leaves at the next interchange and re-enters on the opposite carriageway, so it traverses both directions of the first plaza it meets. Its `covers` list is therefore not the set of tolls any real trip pays, and every consumer of the route set inherits that error.

#### Scenario: An endpoint on the motorway mainline

- **WHEN** a candidate place node snaps onto a motorway carriageway
- **THEN** no route is emitted with that node as `from` or `to`

#### Scenario: An endpoint far from any road

- **WHEN** a candidate place node lies further from the road network than the maximum snap distance
- **THEN** no route is emitted with that node as `from` or `to`

#### Scenario: Emitted endpoints are checked against the rule

- **WHEN** the `places` list of a generated route set is inspected
- **THEN** every entry in it satisfies the reachability condition

### Requirement: Resuming discards routes whose endpoints became ineligible

When an existing route set is loaded and extended, a route SHALL be discarded when either of its endpoints is no longer an eligible route endpoint. Retaining it because it still covers targets would preserve exactly the routes a tightened eligibility rule exists to remove, since the selection pass never revisits a route it has already accepted.

The targets such a discarded route covered SHALL return to the uncovered set and be searched for again.

#### Scenario: A resumed route with an ineligible endpoint

- **WHEN** an existing route set is loaded and one of a route's endpoints no longer satisfies the reachability condition
- **THEN** that route is dropped and the targets it covered are searched for again

#### Scenario: A resumed route with eligible endpoints

- **WHEN** both endpoints of an existing route are still eligible
- **THEN** the route is re-queried and kept if it still covers anything

#### Scenario: Tightening the rule changes the output

- **WHEN** the eligibility rule is tightened and the route set step is run against an existing route set
- **THEN** the emitted route set no longer contains any route that the tightened rule excludes

### Requirement: Reachability is measured from a real trip, not from proximity

The snap distance for a candidate SHALL be the distance from the candidate to the point at which the routing engine begins an actual trip from it, and the road class tested SHALL be the class of the segment that trip begins on.

A nearest-segment query SHALL NOT be used on its own for either. It reports the closest line on the map whether or not a car can drive out of it. A driveway stub in a disconnected component answers at 26 m while the router, asked for a real trip, starts 300 m away on the motorway carriageway — so a candidate can pass a distance test on a measurement that describes a segment no route will ever use.

The destination used to force a usable start SHALL be one the routing graph certainly connects to, so that the measurement reflects the main road network rather than whichever fragment the candidate sits on.

#### Scenario: A place beside an unreachable stub

- **WHEN** a candidate's closest segment is a driveway in its own disconnected component, and a real trip from that candidate starts on a motorway several hundred metres away
- **THEN** the recorded distance is the several hundred metres, and the candidate is rejected

#### Scenario: A place whose closest segment is usable

- **WHEN** a candidate's closest segment is one the router does start trips from
- **THEN** the two measurements agree and the candidate is judged on that distance

#### Scenario: Class follows the trip, not the map

- **WHEN** a real trip from a candidate begins on a motorway carriageway
- **THEN** the no-access class test is applied to that carriageway, whatever class the geometrically closest segment carries

#### Scenario: A candidate that reaches no destination

- **WHEN** no route can be found from a candidate to any of the destinations tried
- **THEN** it is recorded as unmeasured and is not an eligible endpoint

### Requirement: Endpoint reachability is measured once and reused

The reachability measurement for the candidate catalogue SHALL be persisted and reused across runs, rather than repeated on every invocation. The persisted record SHALL hold the measured snap distance rather than only the eligibility verdict, so that the maximum snap distance can be changed without repeating the measurement.

#### Scenario: The measurement is reused

- **WHEN** the route set step runs while a persisted reachability record is present
- **THEN** it reads that record instead of re-measuring the catalogue

#### Scenario: The threshold moves without a new measurement

- **WHEN** the maximum snap distance is changed and the step is run again
- **THEN** the new threshold is applied to the persisted distances, and no new measurement is made

#### Scenario: The measurement is made when absent

- **WHEN** the route set step runs with no persisted record present
- **THEN** it measures the catalogue and writes the record before searching
