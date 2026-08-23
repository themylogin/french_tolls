# toll-booth-inventory Specification

## Purpose
Defines which OpenStreetMap nodes count as French toll booths, which nodes are eligible as route endpoints, and the on-disk format of the resulting booth inventory that every downstream step is measured against.

## Requirements

### Requirement: Toll booth identification

The system SHALL treat an OSM node as a toll booth if and only if it carries the tag `barrier=toll_booth` or the tag `highway=toll_gantry`. Only nodes SHALL be considered; ways and relations carrying these tags SHALL be ignored.

#### Scenario: Node tagged as a toll booth

- **WHEN** the source extract contains a node tagged `barrier=toll_booth`
- **THEN** that node's id appears in the booth inventory

#### Scenario: Node tagged as a toll gantry

- **WHEN** the source extract contains a node tagged `highway=toll_gantry`
- **THEN** that node's id appears in the booth inventory

#### Scenario: Node carrying both tags

- **WHEN** a node is tagged both `barrier=toll_booth` and `highway=toll_gantry`
- **THEN** its id appears exactly once in the booth inventory

#### Scenario: Non-node element carrying a booth tag

- **WHEN** a way or relation is tagged `barrier=toll_booth`
- **THEN** it is excluded from the booth inventory

#### Scenario: Unrelated barrier

- **WHEN** a node is tagged `barrier=gate` or `barrier=lift_gate`
- **THEN** it is excluded from the booth inventory

### Requirement: Plaza lane grouping

A toll plaza is frequently mapped as one booth node per lane on parallel ways. A route can only ever traverse one of those lanes, so the system SHALL group such booths and treat the group as a single coverage target.

Two booths SHALL be treated as alternatives when they share a common predecessor node **and** a common successor node, where the path from that predecessor through the booth to that successor traverses no other toll booth. Reachability SHALL be evaluated over the drivable road graph, honouring one-way restrictions, bounded by distance travelled along the road.

That graph SHALL be built only from the road classes a route between two place nodes can traverse — the same classes the through-road rule uses to decide which booths enter the inventory. Service roads, tracks, and other classes outside that set SHALL NOT contribute connections. A toll plaza's internal access roads connect every lane to every other lane and to the adjoining slip roads, so admitting them manufactures a shared predecessor between booths that no car can drive between.

A booth lying on a through road the car profile can traverse in **both** directions SHALL NOT be grouped with any other booth. The rule above keeps opposite directions apart by way of one-way restrictions; on a bidirectional road there are none, so the two gares of one interchange would otherwise merge.

A group SHALL be the transitive closure of that relation, so the outer lanes of a wide plaza join through the lanes between them.

The bound SHALL be tight — on the order of a kilometre, comfortably longer than a plaza and comfortably shorter than an interchange loop. Given a generous bound any two booths eventually "reconverge" by looping around an interchange, which merges a mainline barrier with a slip-road barrier: booths that a single route drives through one after the other.

Grouping SHALL satisfy this invariant: **no single route may traverse two booths of the same group.** Booths a route can visit in succession are not alternatives, and merging them under-counts the network.

Grouping decisions SHALL NOT be made on geometric proximity. Distance MAY be used only to bound how much of the road network is loaded, never to decide whether two booths group.

#### Scenario: Parallel lanes are grouped

- **WHEN** several booths lie on parallel ways that diverge from one node and reconverge at another, with no other booth in between
- **THEN** they form a single group

#### Scenario: Booths in sequence are not grouped

- **WHEN** two booths lie one after another on the same carriageway, so travelling from the first reaches the second
- **THEN** they do not share a booth-free path and form separate groups

#### Scenario: A mainline barrier and a slip-road barrier are not grouped

- **WHEN** two booths at one interchange share nodes only by way of a path that loops around that interchange
- **THEN** they form separate groups, because that path is longer than the distance bound

#### Scenario: A plaza service road does not connect two booths

- **WHEN** a slip-road booth and a mainline booth share a predecessor only by way of the toll plaza's own service roads or tracks
- **THEN** they form separate groups, because those classes are absent from the graph grouping is evaluated over

#### Scenario: No route traverses two booths of one group

- **WHEN** every route in the generated route set is examined against the grouping
- **THEN** no route traverses more than one booth belonging to the same group

#### Scenario: A wide plaza joins through its middle lanes

- **WHEN** a plaza is wide enough that its outer lanes share no predecessor within the distance bound, but each neighbouring pair of lanes does
- **THEN** all its lanes form a single group by transitivity

#### Scenario: Opposite carriageways are not grouped

- **WHEN** two booths serve opposite directions of a one-way pair
- **THEN** the one-way restrictions give them no common predecessor and successor, and they form separate groups

#### Scenario: A booth on a two-way road is never grouped

- **WHEN** a booth lies on a through road the car profile can traverse in both directions, such as a slip road tagged `oneway=no`
- **THEN** it forms a group of its own, whatever predecessors and successors it shares

#### Scenario: Two gares of one bidirectional interchange

- **WHEN** two booths serve the entry and the exit of one interchange whose slip roads are bidirectional, so each is reachable from the other
- **THEN** they form separate groups

#### Scenario: A plaza of one-way lanes inside a turnaround loop

- **WHEN** every lane of a plaza is one-way and the lanes are mutually reachable only by way of a turnaround loop within the distance bound
- **THEN** they still form a single group, because they remain alternatives no single route traverses twice

#### Scenario: Distance does not decide grouping

- **WHEN** two booths are metres apart but share no booth-free predecessor and successor
- **THEN** they form separate groups regardless of their separation

#### Scenario: A long plaza is still one group

- **WHEN** the lanes of one plaza span a distance greater than any fixed proximity threshold
- **THEN** they still form a single group, because the (predecessor, successor) rule does not depend on separation

### Requirement: Only booths on through roads are counted

The inventory SHALL contain only booths lying on a road class a route between two place nodes can plausibly traverse: `motorway`, `trunk`, `primary`, `secondary`, `tertiary`, and their `_link` variants. Booths on any other class — including `service`, `unclassified`, `residential`, `footway`, `path`, `pedestrian`, `track`, `busway`, `construction`, `proposed` — and booths on no way at all SHALL be excluded.

Excluded booths SHALL be recorded in `data/excluded_booths.json`, each with the highway values that caused its exclusion, so the filter is auditable rather than silent.

A booth SHALL be retained when any way it belongs to is a through road, so a booth shared between a motorway and an adjoining service road is kept.

#### Scenario: Car park barrier is excluded

- **WHEN** a booth lies only on a `service` way
- **THEN** it is absent from the inventory and present in `data/excluded_booths.json` with `service` as its reason

#### Scenario: Non-drivable way is excluded

- **WHEN** a booth lies only on a `footway`, `path`, or `pedestrian` way
- **THEN** it is excluded, because no car route can traverse it

#### Scenario: Booth on no way is excluded

- **WHEN** a booth node belongs to no highway way
- **THEN** it is excluded, with a reason recording that it is on no way

#### Scenario: Motorway booth is retained

- **WHEN** a booth lies on a `motorway_link` way
- **THEN** it is present in the inventory

#### Scenario: Mixed membership retains the booth

- **WHEN** a booth lies on both a `motorway` way and a `service` way
- **THEN** it is retained, because one of its ways is a through road

#### Scenario: Exclusions are disjoint from the inventory

- **WHEN** the inventory and the exclusion report are compared
- **THEN** no booth appears in both, and together they account for every booth in the source extract

### Requirement: Booth inventory output format

The system SHALL write the booth inventory to `data/osm_toll_booths.yaml` as a mapping with two top-level keys.

`toll_booths` SHALL map one representative OSM node id per group to that node's details. The representative SHALL be the smallest node id in its group.

`aliases` SHALL map every non-representative booth id to that node's details together with `parent_id`, the id of its group's representative. Every *retained* booth SHALL appear exactly once, either in `toll_booths` or in `aliases`; booths excluded by the through-road rule appear in neither.

Every entry, representative and alias alike, SHALL carry `latlon`, a two-element list holding **that node's own** position in latitude, longitude order. An alias SHALL NOT repeat its representative's position: consumers match against individual lanes, and the members of one group are a median of 15 metres and up to several hundred metres apart.

An entry SHALL carry `bidirectional: true` when its booth lies on a through road the car profile can traverse in both directions. The key SHALL be absent otherwise. Such a booth is two tolls rather than one, and a consumer cannot tell that from position alone.

Keys under both `toll_booths` and `aliases` SHALL be written in ascending numeric order and without duplicates, so that regenerating an unchanged inventory produces an unchanged file.

```yaml
toll_booths:
  13380042:
    latlon: [48.3955158, 1.3849458]
  81055576:
    latlon: [49.0371990, 0.4416040]
    bidirectional: true
aliases:
  13380044:
    parent_id: 13380042
    latlon: [48.3955521, 1.3849902]
```

#### Scenario: Inventory is written

- **WHEN** the booth extraction step completes successfully
- **THEN** `data/osm_toll_booths.yaml` parses as YAML with `toll_booths` and `aliases` keys, each a mapping whose keys ascend numerically with no repeated id

#### Scenario: Every booth is accounted for

- **WHEN** the inventory is compared against the retained booths from the source extract
- **THEN** each retained booth appears exactly once, either under `toll_booths` or under `aliases`, and no id appears in both

#### Scenario: Representative is the smallest id

- **WHEN** any group of booths is inspected
- **THEN** its representative is the numerically smallest id among its members, and every other member carries that id as its `parent_id`

#### Scenario: Alias targets are representatives

- **WHEN** any `parent_id` in `aliases` is looked up
- **THEN** it is a key of `toll_booths`, and it is never itself a key of `aliases`

#### Scenario: Every booth carries its own position

- **WHEN** any entry under `toll_booths` or `aliases` is inspected
- **THEN** its `latlon` is that node's own position in the source extract, in latitude, longitude order

#### Scenario: An alias does not inherit its representative's position

- **WHEN** a group whose members lie metres apart is inspected
- **THEN** each alias carries its own distinct `latlon`, not a copy of the representative's

#### Scenario: A bidirectional booth is flagged

- **WHEN** a booth lies on a slip road tagged `oneway=no`
- **THEN** its entry carries `bidirectional: true`, and it is a representative with no aliases

#### Scenario: A one-way booth carries no flag

- **WHEN** a booth lies only on one-way ways
- **THEN** its entry has no `bidirectional` key

#### Scenario: Regenerating is stable

- **WHEN** the extraction step runs twice against the same extract
- **THEN** the two inventory files are byte-identical

### Requirement: Route endpoint candidates

The system SHALL treat an OSM node as an eligible route endpoint if and only if it carries a `place` tag whose value is `city`, `town`, `village`, `hamlet`, `isolated_dwelling`, or `locality`.

The smaller values are included because they are frequently the only settlements in an area a booth serves: mountain valleys and motorway interchange catchments often contain no city, town, or village at all, leaving such a booth with no endpoint to anchor a route on. This is a coverage requirement, not a preference — restricted to city, town, and village, some booths are provably unreachable by any endpoint pair. Endpoint candidates SHALL retain their node id, their coordinates, and their `name` tag — the coordinates because route requests are issued by coordinate while the route set records node ids, and the name because the route set resolves each endpoint it references.

#### Scenario: Eligible place node

- **WHEN** the source extract contains a node tagged `place=town`
- **THEN** that node is available as a candidate `from` or `to` endpoint, carrying its id, coordinates, and name

#### Scenario: Ineligible place value

- **WHEN** a node is tagged `place=suburb`, `place=neighbourhood`, or `place=quarter`
- **THEN** it is not available as a route endpoint

#### Scenario: Small settlements are eligible

- **WHEN** a node is tagged `place=hamlet`, `place=isolated_dwelling`, or `place=locality`
- **THEN** it is available as a route endpoint

#### Scenario: A booth whose only nearby settlements are small

- **WHEN** every settlement near a booth is a hamlet, isolated dwelling, or locality
- **THEN** those are still eligible endpoints, so the booth can be covered

#### Scenario: Place tagged on an area

- **WHEN** a city is mapped as a way or relation tagged `place=city`
- **THEN** it is not available as a route endpoint

### Requirement: Endpoint candidates are handed to route generation

The extraction step SHALL persist the endpoint candidates so the route generation step consumes the same parse rather than re-deriving them from the full extract. The candidate catalogue is an internal intermediate and is NOT part of the published output contract.

#### Scenario: Candidates survive the step boundary

- **WHEN** the route set step runs after the extraction step
- **THEN** it reads endpoint candidates produced by that extraction rather than re-parsing the full source extract

#### Scenario: Both steps see one parse

- **WHEN** the source extract is replaced between the two steps without re-running extraction
- **THEN** the route set step still uses the candidates from the earlier parse, keeping booths and endpoints consistent

### Requirement: Extraction is derived from the downloaded extract

The system SHALL derive both the booth inventory and the endpoint candidates from the downloaded France PBF extract, and SHALL NOT require network access at extraction time.

#### Scenario: Offline extraction

- **WHEN** the booth extraction step runs with the PBF already present and no network available
- **THEN** the step completes successfully and produces the inventory
