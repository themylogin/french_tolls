## MODIFIED Requirements

### Requirement: Route set output format

The system SHALL write the route set to `data/route_set.yaml` as a mapping with two top-level keys, `places` and `routes`.

`routes` SHALL hold a list whose entries are mappings with exactly the keys `from`, `to`, and `covers`, where `from` and `to` are OSM node ids of eligible route endpoints.

`covers` SHALL hold a list whose entries are mappings carrying `node_id`, an OSM node id drawn from the booth inventory, and — when that booth is marked `bidirectional` in the inventory — `prev_node_id`, the OSM node the route arrived from. `prev_node_id` SHALL be absent for a booth that is not bidirectional.

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

- **WHEN** a route traverses a booth marked `bidirectional` in the inventory
- **THEN** that `covers` entry carries `prev_node_id`, the node the route arrived from

#### Scenario: A one-way booth records no approach

- **WHEN** a route traverses a booth not marked `bidirectional`
- **THEN** that `covers` entry carries `node_id` alone

### Requirement: Covers reflects every booth actually traversed

The `covers` list of a route SHALL contain every booth the routing engine reports for the driving route from `from` to `to`, not merely those booths for which the route was selected. A booth traversed by several routes SHALL appear in each of their `covers` lists.

Traversed booths SHALL be recorded as their group representative. Traversing any lane of a plaza therefore covers that plaza, and `covers` SHALL contain only ids listed under `toll_booths`, never alias ids.

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
- **THEN** the set of booths on the returned route equals that route's recorded `covers` list, `prev_node_id` values included

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
