# route-set-generation Specification

## Purpose
Defines the contract for a small set of point-to-point driving routes whose union of traversed toll booths covers the booth inventory, including the format of `data/route_set.yaml`, what `covers` means, and how incomplete coverage must be reported.

## Requirements

### Requirement: Route set output format

The system SHALL write the route set to `data/route_set.yaml` as a mapping with two top-level keys, `places` and `routes`.

`routes` SHALL hold a list whose entries are mappings with exactly the keys `from`, `to`, and `covers`, where `from` and `to` are OSM node ids of eligible route endpoints.

`covers` SHALL hold a list whose entries are mappings carrying `node_id`, an OSM node id drawn from the booth inventory, and — when the inventory types that booth `bidirectional` — `prev_node_id`, the OSM node the route arrived from. `prev_node_id` SHALL be absent for a booth that is not bidirectional.

`covers` entries SHALL appear in the order the route traverses them. A consumer that charges for the journey has to know which booth came first, and the routing engine already reports the traversed nodes in order. Ordering by node id would discard that for no gain.

`places` SHALL hold a list whose entries are mappings with exactly the keys `name`, `node_id`, and `latlon`, resolving every endpoint referenced by `routes` so the file is self-describing without reference to any other artifact.

```yaml
places:
  - name: Paris
    node_id: 123
    latlon: [48.8566, 2.3522]
routes:
  - from: 123
    to: 456
    covers:
      - node_id: 249132733
      - node_id: 290864784
      - node_id: 81055576
        prev_node_id: 1042834510
```

#### Scenario: Route set is written

- **WHEN** the route set step completes
- **THEN** `data/route_set.yaml` parses as YAML with top-level `places` and `routes` keys, each holding a list, and every `routes` entry carries `from`, `to`, and `covers`

#### Scenario: Endpoints are eligible place nodes

- **WHEN** any route entry is inspected
- **THEN** its `from` and `to` values are node ids of eligible place nodes

#### Scenario: Covered ids are booths

- **WHEN** any route entry is inspected
- **THEN** every `node_id` in its `covers` list is a key of `toll_booths` in `data/osm_toll_booths.yaml`

#### Scenario: Endpoints differ

- **WHEN** any route entry is inspected
- **THEN** its `from` and `to` values are not equal

#### Scenario: A bidirectional booth records its approach

- **WHEN** a route traverses a booth the inventory types `bidirectional`
- **THEN** that `covers` entry carries `prev_node_id`, the node the route arrived from

#### Scenario: A one-way booth records no approach

- **WHEN** a route traverses a booth the inventory does not type `bidirectional`
- **THEN** that `covers` entry carries `node_id` alone

#### Scenario: Covers follows the driven order

- **WHEN** a route traverses booth X before booth Y
- **THEN** X appears before Y in that route's `covers` list, whatever their node ids

### Requirement: Place list resolves every referenced endpoint

The `places` list SHALL contain exactly one entry per distinct node id appearing as a `from` or `to` value in `routes` — no missing entries and no entries for endpoints that no route uses. Entries SHALL be ordered by `node_id` so that regenerating an unchanged route set produces an unchanged file.

#### Scenario: Every endpoint is resolvable

- **WHEN** any `from` or `to` value is looked up in `places`
- **THEN** exactly one entry has that `node_id`

#### Scenario: No unused places

- **WHEN** the `places` list is inspected
- **THEN** every `node_id` in it appears as a `from` or `to` value in at least one route

#### Scenario: Candidate catalogue is not dumped

- **WHEN** the route set is generated from a catalogue of tens of thousands of eligible place nodes
- **THEN** `places` lists only the endpoints the emitted routes use, not the whole catalogue

### Requirement: Place entry contents

Each `places` entry SHALL carry the place node's `name` tag, its OSM node id as `node_id`, and its position as `latlon`, a two-element list in **latitude, longitude** order. When the place node has no `name` tag the key SHALL still be present with a null value.

#### Scenario: Named place

- **WHEN** a route endpoint is a place node tagged `name=Lyon`
- **THEN** its `places` entry has `name: Lyon`, its `node_id`, and a `latlon` pair

#### Scenario: Unnamed place

- **WHEN** a route endpoint is a place node with no `name` tag
- **THEN** its `places` entry still carries a `name` key, with a null value

#### Scenario: Coordinate order

- **WHEN** a `latlon` value is read for a place in metropolitan France
- **THEN** its first element is the latitude (roughly 41–51) and its second the longitude (roughly −5–10), which is the reverse of the order OSRM route URLs take

### Requirement: Covers reflects every booth actually traversed

The `covers` list of a route SHALL contain every booth the routing engine reports for the driving route from `from` to `to`, not merely those booths for which the route was selected. A booth traversed by several routes SHALL appear in each of their `covers` lists.

Traversed booths SHALL be recorded as their group representative. Traversing any lane of a plaza therefore covers that plaza, and `covers` SHALL contain only ids listed under `toll_booths`, never alias ids.

A group traversed more than once by one route SHALL be recorded at its first traversal and not again, so `covers` holds one entry per group per approach.

For a bidirectional booth the recorded `prev_node_id` SHALL be the OSM node immediately preceding the booth on the route as the routing engine reports it. A booth traversed in both directions by different routes therefore appears with two different `prev_node_id` values.

#### Scenario: All traversed booths recorded

- **WHEN** a route from A to B passes through booths X, Y, and Z, and X was already covered by an earlier route
- **THEN** that route's `covers` list contains entries for X, Y, and Z

#### Scenario: A traversed lane covers its plaza

- **WHEN** a route passes through a booth that is an alias of representative R
- **THEN** its `covers` list contains an entry whose `node_id` is R rather than the alias id

#### Scenario: One entry per group

- **WHEN** a route passes through two booths belonging to the same group
- **THEN** that group's representative appears exactly once in its `covers` list

#### Scenario: Covers is reproducible

- **WHEN** a route's `from` and `to` are re-queried against the same routing instance
- **THEN** the sequence of booths on the returned route equals that route's recorded `covers` list, in the same order and with the same `prev_node_id` values

#### Scenario: Opposite directions record different approaches

- **WHEN** one route traverses a bidirectional booth in one direction and another route traverses it in the other
- **THEN** the two `covers` entries carry different `prev_node_id` values

### Requirement: Coverage of the booth inventory

The coverage target for a booth that is not bidirectional SHALL be the booth itself. A bidirectional booth SHALL contribute one target per direction a route can actually drive through it, identified by `prev_node_id`. Passing such a gare one way does not pay the toll charged the other way.

The union of the `covers` lists across all routes SHALL equal the full set of coverage targets, except for targets the routing engine cannot be made to traverse by any generated endpoint pair.

#### Scenario: Complete coverage

- **WHEN** every coverage target is traversed by at least one generated route
- **THEN** the union of all `covers` lists equals the target set and nothing is reported as uncovered

#### Scenario: A bidirectional booth needs both directions

- **WHEN** every route through a bidirectional booth arrives from the same predecessor
- **THEN** the other direction remains an uncovered target, even though the booth itself has been traversed

#### Scenario: Verification runs before the file is accepted

- **WHEN** the route set step finishes generating routes
- **THEN** it recomputes the union of `covers` and compares it against the target set before reporting success

### Requirement: Incomplete coverage is reported explicitly

When one or more coverage targets remain uncovered, the system SHALL write them to `data/uncovered_booths.json` and SHALL emit a summary on stdout stating the number covered, the number uncovered, and the total. A run that leaves targets uncovered SHALL NOT present itself as having covered the whole inventory.

Each uncovered entry SHALL identify the booth and, for a bidirectional booth, which direction is missing, so an uncovered direction is distinguishable from an uncovered booth.

#### Scenario: Some booths cannot be covered

- **WHEN** the route search ends with targets that no generated route traverses
- **THEN** `data/uncovered_booths.json` lists those targets and stdout reports the covered, uncovered, and total counts

#### Scenario: An uncovered direction is identifiable

- **WHEN** a bidirectional booth is traversed in one direction only
- **THEN** its entry in `data/uncovered_booths.json` names the booth and the direction that is missing

#### Scenario: Full coverage achieved

- **WHEN** the route search covers every target
- **THEN** stdout reports zero uncovered targets and `data/uncovered_booths.json` contains an empty list

#### Scenario: Stale report is not left behind

- **WHEN** a run achieves full coverage after an earlier run had reported uncovered targets
- **THEN** `data/uncovered_booths.json` is overwritten to reflect the current run rather than retaining the earlier list

### Requirement: Route set size

The system SHALL emit fewer routes than the number of coverage targets covered, by repeatedly selecting the candidate route that covers the greatest number of not-yet-covered targets. Minimality is NOT required, and no stronger ratio is guaranteed: covering the last few stubborn targets costs roughly one route each.

#### Scenario: Redundant route is not emitted

- **WHEN** a candidate route covers no target that is not already covered by routes already selected
- **THEN** that candidate is not added to the route set

#### Scenario: Fewer routes than groups covered

- **WHEN** the route set is generated over an inventory of more than a few hundred groups
- **THEN** the number of routes emitted is smaller than the number of coverage targets covered

### Requirement: Route set targets a single known routing configuration

The route set SHALL be generated against the project's own OSRM instance built from the same extract, the `car` profile, and the MLD algorithm, with no traffic or segment-speed data applied. The reproducibility guarantee for `covers` SHALL NOT be claimed for any other routing configuration.

#### Scenario: Consumer uses the project instance

- **WHEN** a downstream script replays `from`/`to` pairs against the project's OSRM instance
- **THEN** it obtains the same booths recorded in `covers`

### Requirement: Endpoints are solved, not only guessed

Candidate endpoints SHALL be derived from travel distance over the road network, not from straight-line geometry alone. A route from `u` to `v` crosses booth `b` exactly when `d(u,v)` equals `d(u,b) + d(b,v)`, and the routing engine's distance-table service supplies all three terms, so pairs can be identified rather than searched for blindly.

Straight-line bearings and radii SHALL NOT be the only basis for candidate selection: on a winding mountain road or a coastal motorway a compass bearing says nothing about which way the road runs, and booths reachable only by such roads are missed.

#### Scenario: A booth on a winding road

- **WHEN** a booth sits on a road whose direction of travel differs sharply from the straight line between candidate endpoints
- **THEN** candidate selection still finds endpoints whose route crosses it, because selection uses network distance

#### Scenario: Solved pairs are verified

- **WHEN** a pair is identified from the distance table
- **THEN** the route is still queried and its traversed booths recorded from the response, so `covers` reflects the route actually returned

### Requirement: Routing service readiness

The route set step SHALL tolerate a routing service that is still starting up, retrying its connection for a bounded period before failing, rather than aborting on the first refused connection.

#### Scenario: Router still loading

- **WHEN** the route set step starts while the routing service is still loading its graph
- **THEN** it retries the connection until the service answers or a bounded timeout elapses

#### Scenario: Router never becomes available

- **WHEN** the routing service does not answer within the retry period
- **THEN** the step fails with a clear message naming the unreachable service

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

### Requirement: A route through a blacklisted node is never selected

The override file MAY list OSM node ids under `nodes_blacklist`. A candidate route whose node sequence includes any of them SHALL be discarded: it SHALL NOT be selected, SHALL NOT count towards coverage, and an existing route that uses one SHALL be dropped when the route set is extended.

Each entry states that the map is wrong at that node — a connection that is not there on the ground. A route using it is not one a car can drive, so a route set that recorded it would send every later step chasing a journey that cannot happen. The list is a bridge until the extract carries the upstream fix, not a routing preference.

The system SHALL report how many candidate routes the blacklist discarded, and SHALL warn when it discarded none, since that means the entries are stale or wrong.

#### Scenario: A candidate through a blacklisted node is discarded

- **WHEN** a candidate route's node sequence includes a blacklisted node
- **THEN** it is not selected, and the booths it would have covered stay uncovered

#### Scenario: An existing route through a blacklisted node is dropped

- **WHEN** the route set is extended and a route already in it passes a node added to the blacklist since
- **THEN** that route is dropped from the route set

#### Scenario: The blacklist is reported

- **WHEN** the route set step completes with a non-empty blacklist
- **THEN** it reports how many candidate routes were discarded

#### Scenario: A blacklist that blocks nothing is called out

- **WHEN** the route set step completes and no candidate used any blacklisted node
- **THEN** it warns that the entries are stale or wrong
