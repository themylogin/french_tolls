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

An entry SHALL carry `type` when its booth charges differently from a plain one-way lane, and SHALL NOT carry it otherwise. Two values exist:

- **`bidirectional`** — the booth lies on a through road the car profile can traverse in both directions. Such a booth is two tolls rather than one, and it is an entrance to a journey driven one way and an exit to the same journey driven the other.
- **`gantry`** — the booth is tagged `highway=toll_gantry`, a portal over the carriageway rather than a lane a car stops in. A free-flow point charges per section travelled, so it starts a section when another gantry follows on the same journey and is a charge of its own when none does.

Both say the same thing: the role this booth plays belongs to the journey, not to the booth. A consumer cannot infer either from position or from a charge, and both change how the booth is priced.

A booth SHALL NOT be both. `type` holds one value, so a booth that qualified as both would silently lose one, and the step SHALL stop rather than write it.

Keys under both `toll_booths` and `aliases` SHALL be written in ascending numeric order and without duplicates, so that regenerating an unchanged inventory produces an unchanged file.

```yaml
toll_booths:
  13380042:
    latlon: [48.3955158, 1.3849458]
  81055576:
    latlon: [49.0371990, 0.4416040]
    type: bidirectional
  11578487423:
    latlon: [46.5164141, 3.4689468]
    type: gantry
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
- **THEN** its entry carries `type: bidirectional`, and it is a representative with no aliases

#### Scenario: A gantry is typed

- **WHEN** a booth is tagged `highway=toll_gantry`
- **THEN** its entry carries `type: gantry`

#### Scenario: A one-way booth carries no flag

- **WHEN** a booth lies only on one-way ways and is not a gantry
- **THEN** its entry has no `type` key

#### Scenario: A booth cannot hold two types

- **WHEN** a booth is tagged `highway=toll_gantry` and also lies on a two-way through road
- **THEN** the step stops and names it, rather than writing one type and dropping the other

#### Scenario: Regenerating is stable

- **WHEN** the extraction step runs twice against the same extract
- **THEN** the two inventory files are byte-identical

### Requirement: Route endpoint candidates

The system SHALL treat an OSM node as an eligible route endpoint if and only if it carries a `place` tag whose value is `city`, `town`, `village`, `hamlet`, `isolated_dwelling`, or `locality`, AND a car can start and finish a trip there.

A node satisfies the second condition when the routing engine snaps it to a position no further than a stated maximum distance away, and the road segment it snaps to is not of a class that carries no local access. The classes that carry no local access are `motorway`, `motorway_link`, and `trunk_link`. `trunk` is not among them: in France it covers ordinary roads with property access as well as motorway-grade routes.

The maximum snap distance SHALL be a single stated value, so that it can be raised when a booth proves uncoverable without it. It SHALL NOT vary by `place` value.

The smaller `place` values are included because they are frequently the only settlements in an area a booth serves: mountain valleys and motorway interchange catchments often contain no city, town, or village at all, leaving such a booth with no endpoint to anchor a route on. This is a coverage requirement, not a preference — restricted to city, town, and village, some booths are provably unreachable by any endpoint pair. The reachability condition narrows this pool without contradicting it: a locality remains eligible by tag, and is disqualified only by where it sits relative to the road network.

Endpoint candidates SHALL retain their node id, their coordinates, and their `name` tag — the coordinates because route requests are issued by coordinate while the route set records node ids, and the name because the route set resolves each endpoint it references.

#### Scenario: Eligible place node

- **WHEN** the source extract contains a node tagged `place=town` that snaps within the maximum distance to a road carrying local access
- **THEN** that node is available as a candidate `from` or `to` endpoint, carrying its id, coordinates, and name

#### Scenario: Ineligible place value

- **WHEN** a node is tagged `place=suburb`, `place=neighbourhood`, or `place=quarter`
- **THEN** it is not available as a route endpoint

#### Scenario: Small settlements are eligible

- **WHEN** a node is tagged `place=hamlet`, `place=isolated_dwelling`, or `place=locality` and satisfies the reachability condition
- **THEN** it is available as a route endpoint

#### Scenario: A booth whose only nearby settlements are small

- **WHEN** every settlement near a booth is a hamlet, isolated dwelling, or locality that satisfies the reachability condition
- **THEN** those are still eligible endpoints, so the booth can be covered

#### Scenario: Place tagged on an area

- **WHEN** a city is mapped as a way or relation tagged `place=city`
- **THEN** it is not available as a route endpoint

#### Scenario: A place too far from any road

- **WHEN** a node tagged `place=locality` names a field whose nearest routable segment is further away than the maximum snap distance
- **THEN** it is not an eligible route endpoint

#### Scenario: A place whose nearest road is a motorway

- **WHEN** a node tagged `place=locality` sits beside a motorway and the routing engine snaps it onto the motorway carriageway
- **THEN** it is not an eligible route endpoint, whatever the snap distance

#### Scenario: A place inside a toll plaza

- **WHEN** a place node sits within a toll plaza and snaps onto a `motorway_link` between the barriers
- **THEN** it is not an eligible route endpoint, even though the snap distance is a few metres

#### Scenario: A trunk road is not excluded

- **WHEN** a place node snaps to a segment tagged `highway=trunk` within the maximum snap distance
- **THEN** it remains an eligible route endpoint

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

### Requirement: An ignored booth is treated as absent

A booth whose override is `type: ignore` SHALL be removed from the pipeline entirely. It SHALL NOT be grouped, SHALL NOT appear in the inventory as a representative or an alias, and SHALL NOT become a coverage target.

It SHALL be recorded in `data/excluded_booths.json` with a reason naming the override, so the inventory and the exclusion report together still account for every booth in the source extract, and so the removal is auditable rather than invisible.

#### Scenario: Ignored booth leaves the inventory

- **WHEN** a booth carries `type: ignore`
- **THEN** it is absent from both `toll_booths` and `aliases` in `data/osm_toll_booths.yaml`

#### Scenario: Ignored booth is recorded as excluded

- **WHEN** a booth carries `type: ignore`
- **THEN** it appears in `data/excluded_booths.json` with a reason identifying it as ignored by override

#### Scenario: Ignored booth does not group

- **WHEN** an ignored booth would otherwise have been an alias of a plaza group
- **THEN** that group is formed without it, and its remaining members are unaffected

#### Scenario: Accounting still holds

- **WHEN** the inventory and the exclusion report are compared against the source extract
- **THEN** every booth in the extract appears in exactly one of them

### Requirement: A booth the operator does not carry

A booth whose override is one of the `absent_*` types SHALL stay in the inventory and remain a coverage target: it is a real booth on a real road that a route drives through. Only the requirement that the gare mapping find a gare for it SHALL be waived, because the operator's placemark layer does not carry it and there is no gare to find.

The accepted values SHALL be `absent_enter`, `absent_exit`, and `absent_passthrough`, recording how a route meets the booth. Nothing consumes that distinction yet.

An `absent_*` override SHALL NOT be combined with a `vinci` entry: stating that the operator does not carry the booth and then naming its gare is a contradiction.

`price` SHALL state what such a booth charges, and SHALL be accepted only with `absent_passthrough`. An enter or an exit is one half of a journey whose charge depends on where the other half was, so there is no single price to state. `price` SHALL be a number.

#### Scenario: An absent booth stays in the inventory

- **WHEN** a booth carries `type: absent_passthrough`
- **THEN** it appears in the inventory and remains a coverage target, unlike an ignored booth

#### Scenario: An absent booth needs no gare

- **WHEN** the gare mapping runs over a route that drives through an absent booth
- **THEN** that booth is not required to have a gare

#### Scenario: Absent and vinci together

- **WHEN** an entry carries both an `absent_*` type and a `vinci` entry
- **THEN** the step stops and names that entry

#### Scenario: Price on the wrong type

- **WHEN** `price` appears on any entry whose type is not `absent_passthrough`
- **THEN** the step stops and names the entry

#### Scenario: Price is not a number

- **WHEN** `price` carries a value that is not a number
- **THEN** the step stops and names the entry and the value

### Requirement: A gare stated by hand

A booth whose override carries `vinci` SHALL be recorded as belonging to that operator gare, whatever the placemark positions say. The entry SHALL carry `id`, the operator number, and `name`, and SHALL carry nothing else.

The operator number SHALL be compared as a string throughout. Operator numbers are digit strings with leading zeros, which YAML would otherwise read as integers.

The named booth SHALL be a group representative in the inventory. A booth that the grouping rules made an alias is not a group, and attaching a gare to one SHALL stop the step.

#### Scenario: A displaced gare is stated by hand

- **WHEN** the operator places a gare too far from any lane a route drives for a positional match to succeed
- **THEN** a `vinci` entry naming that booth records the gare regardless

#### Scenario: Operator numbers keep their leading zeros

- **WHEN** a `vinci` entry states `id: 04801`
- **THEN** it is recorded and compared as the string `04801`, not as a number

#### Scenario: vinci names a non-representative

- **WHEN** a `vinci` entry names a booth that the grouping rules made an alias of another group
- **THEN** the step stops and names the entry

#### Scenario: vinci is incomplete

- **WHEN** a `vinci` entry is missing `id` or `name`, or carries any other key
- **THEN** the step stops and names the entry

### Requirement: Re-running extraction reuses its carved extracts

The extraction step SHALL reuse the filtered extract and the carved plaza extract when they are already present, rather than deriving them from the source extract again. Both depend only on the source extract and the tag rules, and no override can change either.

The override file SHALL NOT be declared a prerequisite of the inventory. Doing so would key an expensive step to a modification time, which the pipeline avoids everywhere else; editing overrides means deleting the inventory and running the step again.

#### Scenario: Re-running after an override edit

- **WHEN** the inventory is deleted and the extraction step is run again with both carved extracts present
- **THEN** it reuses them and completes in about a minute, rather than repeating the passes over the source extract

#### Scenario: Touching the override file does not rebuild anything

- **WHEN** `data/osm_toll_booths_overrides.yaml` is edited and the pipeline is run
- **THEN** no step re-executes on account of the modification time alone

### Requirement: Forced group membership

A booth whose override is `parent_id` naming another booth SHALL be placed in the group of the named booth, without any topological test. The forced membership SHALL be applied after the grouping rules have run, and SHALL merge the overridden booth's whole group into the target's group.

A booth whose override is `parent_id` with a null value SHALL be kept in a group of its own, whatever the topology says. This is the only way a group is split by hand, and it splits in one direction only: the named booth is held out and the rest of its group stays together. It exists because the topological rule can be correct that two lanes are alternatives and still reach a wrong result — the operator sometimes charges two lanes of one plaza as different gares, and one group can carry only one gare.

An isolated booth SHALL take no part in the pairing relation, in either position, rather than being detached after the rules have run. Grouping is a transitive closure, so a booth left in the relation still chains its neighbours to each other even when it is removed from the result.

A booth SHALL NOT both state a null `parent_id` and be named as another booth's `parent_id` target. Either spelling of that combination SHALL stop the step.

The target of a non-null `parent_id` SHALL be a group representative after the grouping rules have run. A target that is itself an alias of some other group is not a group, and naming one SHALL stop the step.

The representative of any group SHALL follow the usual rule — the smallest node id among its members.

#### Scenario: Booth is forced into a group

- **WHEN** a booth carries `parent_id` naming a group representative
- **THEN** it belongs to that group in the inventory, whatever the topology says

#### Scenario: The forced booth brings its group

- **WHEN** a booth carrying `parent_id` is itself grouped with other booths
- **THEN** all of them join the target's group

#### Scenario: Target is not a representative

- **WHEN** a `parent_id` names a booth that the grouping rules made an alias of another group
- **THEN** the step stops and names the entry, because the group it points at does not exist

#### Scenario: A two-way booth may still be forced

- **WHEN** a booth that the two-way rule would leave ungrouped carries `parent_id`
- **THEN** the override wins and it joins the named group

#### Scenario: A booth is held out of every group

- **WHEN** a booth carries `parent_id` with a null value and the topological rule would otherwise group it with another lane
- **THEN** it appears in the inventory as its own group representative, not as an alias

#### Scenario: The rest of the group stays together

- **WHEN** a booth carrying a null `parent_id` belongs to a plaza of several lanes
- **THEN** the other lanes remain one group and only the named booth is separated

#### Scenario: An isolated booth does not chain its neighbours

- **WHEN** two lanes are related to each other only through a booth carrying a null `parent_id`
- **THEN** those two lanes are not grouped, because the isolated booth never enters the relation

#### Scenario: Isolation and forced membership conflict

- **WHEN** one booth states a null `parent_id` and another names it as its `parent_id` target
- **THEN** the step stops and names the entry

#### Scenario: Two lanes the operator charges separately

- **WHEN** two lanes of one plaza are topologically alternatives but the operator reports a different gare for each
- **THEN** holding one out with a null `parent_id` makes them two coverage targets, so each can carry its own gare

### Requirement: Every override is checked against the extract

The system SHALL validate every override against the booths found in the source extract, and SHALL stop and name the offending entry when one does not apply. An override that has gone stale — because the node was retagged, deleted, or renumbered upstream — otherwise produces a silently wrong inventory.

An overridden node SHALL be a booth in the source extract, whether it is named by `type`, `parent_id`, `vinci`, or a null `parent_id`. A non-null `parent_id` target SHALL be a booth that survived the through-road filter. A `type` value SHALL be one of `ignore`, `absent_enter`, `absent_exit`, `absent_passthrough`, `enter`, `exit`, or `passthrough`.

`enter`, `exit`, and `passthrough` state that a booth is a plain one-way lane of that role, whatever the extract's tags say, and they have two effects on the inventory.

First, the booth SHALL NOT be typed `bidirectional` and SHALL NOT carry `adjacent_nodes`, even where it lies on a way tagged `oneway=no`. Such a tag makes the booth two coverage targets instead of one, keeps it out of every plaza group, and leaves the reverse direction permanently uncovered because no car can drive it. A booth already one-way in the extract is unaffected, because the statement and the tags agree.

Second, the booth SHALL carry `passage`, the two nodes either side of it in driven order. What that field is for is settled in `vinci-gare-mapping`.

#### Scenario: Override names a node that is not a booth

- **WHEN** an override names a node the extract does not carry as a toll booth
- **THEN** the step stops and names that node

#### Scenario: Override names a deleted node

- **WHEN** a node named by an override has been deleted upstream and is absent from a refreshed extract
- **THEN** the step stops rather than applying an override to nothing

#### Scenario: parent_id names a booth that is not in the inventory

- **WHEN** a `parent_id` names a booth the through-road filter excluded, or that is itself ignored
- **THEN** the step stops and names the entry

#### Scenario: Unknown type

- **WHEN** an entry carries a `type` that is not one of the accepted values
- **THEN** the step stops and names the entry and the value

#### Scenario: A border classification overrides a two-way tag

- **WHEN** a booth on a way tagged `oneway=no` carries `type: enter`, `type: exit`, or `type: passthrough`
- **THEN** its entry carries neither `type: bidirectional` nor `adjacent_nodes`, and it is eligible to join a plaza group

#### Scenario: Border classifications are inert

- **WHEN** a booth that the extract already reads as one-way carries `type: enter`, `type: exit`, or `type: passthrough`
- **THEN** its typing, its grouping, and its aliases are exactly as they would have been without that entry, because the statement and the tags agree

#### Scenario: A border classification produces a passage

- **WHEN** a booth carries `type: enter`, `type: exit`, or `type: passthrough`
- **THEN** its entry carries `passage`

#### Scenario: An isolated node is checked too

- **WHEN** an override carries a null `parent_id` for a node the extract does not carry as a toll booth
- **THEN** the step stops and names that node

### Requirement: The no-access road classes are available to route generation

The extraction step SHALL persist the ways of the classes that carry no local access, covering the whole source extract, so that the route generation step can decide whether a candidate's snapped segment belongs to one of them.

This is required because the routing engine reports the snapped segment's node ids and its name, but not its road class, and a large share of the segments involved carry no name at all.

The persisted set is an internal intermediate and is NOT part of the published output contract.

#### Scenario: No-access ways are persisted

- **WHEN** the extraction step completes
- **THEN** an artefact holding every `motorway`, `motorway_link`, and `trunk_link` way in the source extract is available to the route generation step

#### Scenario: Class is decided without the way's name

- **WHEN** a candidate snaps onto an unnamed segment
- **THEN** its class is still determined, from the persisted ways rather than from the name the routing engine reports

#### Scenario: Re-running extraction reuses the persisted ways

- **WHEN** the extraction step runs again while the artefact is already present
- **THEN** it is reused rather than rebuilt, in the same way the filtered and carved extracts are

### Requirement: Gare pairs the operator does not sell

The override file SHALL accept a `prohibited_gare_pairs` section: a list of two-element lists of operator numbers, each an ordered pair the pipeline must never ask the rate service about.

Operator numbers SHALL be normalised to strings, as every other operator number in the file is, so a leading zero survives YAML reading them as integers.

Direction SHALL be part of the statement. Prohibiting A to B says nothing about B to A, and both SHALL be listed when both are meant.

A pair naming one gare twice SHALL be refused. Such a pair is already excluded by the rule that drops same-gare pairs, so stating it can only mean something else was intended.

The section exists for pairs that are not a journey however the road network reads — two ramps of one interchange under two codes, where a router asked to drive between them produces a loop out and back that crosses no booth and so resembles a ticket.

#### Scenario: A prohibited pair is loaded

- **WHEN** the file lists `["04355", "04354"]`
- **THEN** the overrides carry the ordered pair `04355` to `04354`

#### Scenario: Leading zeros survive

- **WHEN** the file lists `[04355, 04354]` unquoted
- **THEN** the overrides carry `"04355"` and `"04354"` as five-character strings

#### Scenario: A malformed entry is refused

- **WHEN** the section holds something other than a list, or an entry that is not a two-element list
- **THEN** the step stops and names the offending value

#### Scenario: A pair of a gare with itself is refused

- **WHEN** the file lists `["04355", "04355"]`
- **THEN** the step stops and says the pair names one gare twice

### Requirement: A two-way booth carries its adjacent nodes and their onewayness

The system SHALL write `adjacent_nodes` on every booth it types `bidirectional`: a mapping from each node id adjacent to the booth node along a way whose class is one of the through road classes, to whether the way reaching it is one-way, in ascending numeric key order.

Adjacency SHALL be taken from the carved plaza extract the grouping already reads, so the field costs no further pass over the source.

A booth typed `gantry`, and a booth carrying no `type` at all, SHALL NOT carry the field. Both have one traffic sense, so they have no sides to tell apart.

The field is a work list for step 4 and carries no meaning of its own. What the two sides mean is settled in `bidirectional-booth-sides`.

#### Scenario: A two-way booth carries its neighbours and their onewayness

- **WHEN** the inventory is written
- **THEN** every `bidirectional` booth carries `adjacent_nodes` mapping each node id beside it on a through-class way to `true` or `false`, ascending by key

#### Scenario: A one-way booth does not

- **WHEN** a booth is typed `gantry` or carries no `type`
- **THEN** it carries no `adjacent_nodes`

#### Scenario: Adjacency comes from the carved extract

- **WHEN** the step runs
- **THEN** it reads no extract it did not already read to group the booths

### Requirement: Hand-maintained booth decisions

The extraction step SHALL read `data/osm_toll_booths_overrides.yaml`, a hand-maintained input recording decisions that no rule can derive from the extract. A missing file SHALL be treated as an empty set of overrides.

The file SHALL be a mapping with two permitted top-level keys. `toll_booths` holds decisions about individual booths, keyed by OSM node id; an entry SHALL carry at least one of `type`, `parent_id`, `vinci`, or `price`. `duplicate_gares` holds operator numbers of gares that one route may legitimately pay twice.

A top-level key that is neither of the two SHALL stop the step. A mistyped section name would otherwise read as an absent section, and every entry beneath it would be dropped without a word.

Operator numbers in `duplicate_gares` SHALL be compared as strings. They carry leading zeros, which YAML reads away when the value is unquoted, so `04210` and `"04210"` SHALL name the same gare.

Blacklisted nodes are not booth overrides and SHALL NOT appear here. They describe the road graph rather than any booth, they are enforced by the routing profile, and `build-pipeline` gives them a file of their own.

#### Scenario: Overrides are read

- **WHEN** the extraction step runs with the override file present
- **THEN** it applies the entries in that file before writing the inventory

#### Scenario: No override file

- **WHEN** `data/osm_toll_booths_overrides.yaml` does not exist
- **THEN** the step runs as though it were empty, rather than failing

#### Scenario: An entry carries no key at all

- **WHEN** an entry is empty
- **THEN** the step stops and names that entry

#### Scenario: An unknown key

- **WHEN** an entry carries a key other than `type`, `parent_id`, `vinci`, or `price`
- **THEN** the step stops and names the entry and the key

#### Scenario: An unknown top-level section

- **WHEN** the file carries a top-level key other than `toll_booths` or `duplicate_gares`
- **THEN** the step stops and names it, rather than silently ignoring everything under it

#### Scenario: A leftover nodes_blacklist section stops the step

- **WHEN** the file still carries a `nodes_blacklist` key
- **THEN** the step stops and names it, as it would any unknown section

#### Scenario: A gare number written without quotes

- **WHEN** `duplicate_gares` lists `04210` unquoted, which YAML reads as an integer
- **THEN** it still names gare `04210`, with the leading zero intact

#### Scenario: duplicate_gares is not a list

- **WHEN** `duplicate_gares` carries something other than a list
- **THEN** the step stops and names what it found

### Requirement: A border-typed booth carries the passage through it

The system SHALL write `passage` on every booth the override file types `enter`, `exit`, or `passthrough`: a two-element list holding the position of the node reached immediately before the booth and the position of the node reached immediately after it, each as `[latitude, longitude]`, in the order a vehicle drives them.

The two nodes SHALL be taken from the directed adjacency over the through road classes that the grouping already builds from the carved plaza extract. A predecessor is a node from which the booth is reachable in one step; a successor is a node reachable from the booth in one step. The field SHALL therefore cost no further pass over the source.

The booth's own position SHALL NOT be repeated in `passage`. The entry already carries it as `latlon`, and a consumer that needs the whole leg forms `passage[0]`, `latlon`, `passage[1]`.

A booth carrying no border type SHALL NOT carry the field. The field exists for booths that no route reaches, and a booth a route reaches is resolved by that route.

Where a booth has more than one predecessor or more than one successor, the system SHALL choose one of each deterministically, so that regenerating an unchanged inventory produces an unchanged file. Any one of them describes a lawful passage through the booth.

The step SHALL stop and name the booth when a border-typed booth has no predecessor or no successor. A booth with no way through it cannot be resolved by a leg, and writing a partial `passage` would defer the failure to a step that cannot explain it.

```yaml
toll_booths:
  1987610456:
    latlon: [42.5236532, 2.8177941]
    passage: [[42.5235734, 2.8177759], [42.5236972, 2.8178054]]
```

#### Scenario: A border-typed booth carries its passage

- **WHEN** the inventory is written
- **THEN** every booth typed `enter`, `exit`, or `passthrough` in the override file carries `passage` as two `[latitude, longitude]` pairs

#### Scenario: The passage is in driven order

- **WHEN** a border-typed booth lies on a one-way way
- **THEN** `passage[0]` is the node upstream of it and `passage[1]` is the node downstream of it

#### Scenario: The booth's own position is not repeated

- **WHEN** a `passage` is inspected
- **THEN** it holds two positions, neither of which is the booth's own `latlon`

#### Scenario: An ordinary booth carries no passage

- **WHEN** a booth carries no border type in the override file
- **THEN** its entry has no `passage` key, whatever its `type`

#### Scenario: Passage comes from the carved extract

- **WHEN** the step runs
- **THEN** it reads no extract it did not already read to group the booths

#### Scenario: Regenerating is stable

- **WHEN** the extraction step runs twice against the same extract and the same override file
- **THEN** both inventories carry the same `passage` for every border-typed booth

#### Scenario: A border-typed booth with no way through it

- **WHEN** a border-typed booth has no predecessor or no successor on a through-class way
- **THEN** the step stops and names that booth
