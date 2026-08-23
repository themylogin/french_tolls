# route-set-generation Specification

## Purpose
Defines the contract for a small set of point-to-point driving routes whose union of traversed toll booths covers the booth inventory, including the format of `data/route_set.yaml`, what `covers` means, and how incomplete coverage must be reported.

## Requirements

### Requirement: Route set output format

The system SHALL write the route set to `data/route_set.yaml` as a mapping with two top-level keys, `places` and `routes`.

`routes` SHALL hold a list whose entries are mappings with exactly the keys `from`, `to`, and `covers`, where `from` and `to` are OSM node ids of eligible route endpoints and `covers` is a list of OSM node ids drawn from the booth inventory.

`places` SHALL hold a list whose entries are mappings with exactly the keys `name`, `node_id`, and `latlon`, resolving every endpoint referenced by `routes` so the file is self-describing without reference to any other artifact.

```yaml
places:
  - name: Paris
    node_id: 123
    latlon: [48.8566, 2.3522]
routes:
  - from: 123
    to: 456
    covers: [9, 10, 11]
```

#### Scenario: Route set is written

- **WHEN** the route set step completes
- **THEN** `data/route_set.yaml` parses as YAML with top-level `places` and `routes` keys, each holding a list, and every `routes` entry carries `from`, `to`, and `covers`

#### Scenario: Endpoints are eligible place nodes

- **WHEN** any route entry is inspected
- **THEN** its `from` and `to` values are node ids of eligible place nodes

#### Scenario: Covered ids are booths

- **WHEN** any route entry is inspected
- **THEN** every id in its `covers` list is listed under `toll_booths` in `data/osm_toll_booths.yaml`

#### Scenario: Endpoints differ

- **WHEN** any route entry is inspected
- **THEN** its `from` and `to` values are not equal

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

#### Scenario: All traversed booths recorded

- **WHEN** a route from A to B passes through booths X, Y, and Z, and X was already covered by an earlier route
- **THEN** that route's `covers` list contains X, Y, and Z

#### Scenario: A traversed lane covers its plaza

- **WHEN** a route passes through a booth that is an alias of representative R
- **THEN** its `covers` list contains R rather than the alias id

#### Scenario: One entry per group

- **WHEN** a route passes through two booths belonging to the same group
- **THEN** that group's representative appears exactly once in its `covers` list

#### Scenario: Covers is reproducible

- **WHEN** a route's `from` and `to` are re-queried against the same routing instance
- **THEN** the set of booths on the returned route equals that route's recorded `covers` list

### Requirement: Coverage of the booth inventory

The union of the `covers` lists across all routes SHALL equal the set of group representatives listed under `toll_booths` in `data/osm_toll_booths.yaml`, except for groups the routing engine cannot be made to traverse by any generated endpoint pair.

#### Scenario: Complete coverage

- **WHEN** every group in the inventory is traversed by at least one generated route
- **THEN** the union of all `covers` lists equals the representative set and nothing is reported as uncovered

#### Scenario: Verification runs before the file is accepted

- **WHEN** the route set step finishes generating routes
- **THEN** it recomputes the union of `covers` and compares it against the inventory before reporting success

### Requirement: Incomplete coverage is reported explicitly

When one or more groups remain uncovered, the system SHALL write their representatives to `data/uncovered_booths.json` and SHALL emit a summary on stdout stating the number covered, the number uncovered, and the total. A run that leaves groups uncovered SHALL NOT present itself as having covered the whole inventory.

#### Scenario: Some booths cannot be covered

- **WHEN** the route search ends with groups that no generated route traverses
- **THEN** `data/uncovered_booths.json` lists those representatives and stdout reports the covered, uncovered, and total counts

#### Scenario: Full coverage achieved

- **WHEN** the route search covers every group in the inventory
- **THEN** stdout reports zero uncovered booths and `data/uncovered_booths.json` contains an empty list

#### Scenario: Stale report is not left behind

- **WHEN** a run achieves full coverage after an earlier run had reported uncovered groups
- **THEN** `data/uncovered_booths.json` is overwritten to reflect the current run rather than retaining the earlier list

### Requirement: Route set size

The system SHALL emit fewer routes than the number of groups covered, by repeatedly selecting the candidate route that covers the greatest number of not-yet-covered groups. Minimality is NOT required, and no stronger ratio is guaranteed: covering the last few stubborn groups costs roughly one route each.

#### Scenario: Redundant route is not emitted

- **WHEN** a candidate route covers no group that is not already covered by routes already selected
- **THEN** that candidate is not added to the route set

#### Scenario: Fewer routes than groups covered

- **WHEN** the route set is generated over an inventory of more than a few hundred groups
- **THEN** the number of routes emitted is smaller than the number of groups covered

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
