## MODIFIED Requirements

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

## ADDED Requirements

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
