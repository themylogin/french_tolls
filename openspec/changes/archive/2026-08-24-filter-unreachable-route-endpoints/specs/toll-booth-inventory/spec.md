## MODIFIED Requirements

### Requirement: Hand-maintained booth overrides

The extraction step SHALL read `data/osm_toll_booths_overrides.yaml`, a hand-maintained input recording decisions that no rule can derive from the extract. A missing file SHALL be treated as an empty set of overrides.

The file SHALL be a mapping with two permitted top-level keys. `toll_booths` holds decisions about individual booths, keyed by OSM node id; an entry SHALL carry at least one of `type`, `parent_id`, `vinci`, or `price`. `duplicate_gares` holds operator numbers of gares that one route may legitimately pay twice.

A top-level key that is neither SHALL stop the step. A mistyped section name would otherwise read as an absent section, and every entry beneath it would be dropped without a word.

Operator numbers in `duplicate_gares` SHALL be compared as strings. They carry leading zeros, which YAML reads away when the value is unquoted, so `04210` and `"04210"` SHALL name the same gare.

```yaml
toll_booths:
  # weird layout. a real route will never go through this booth
  14061571393:
    type: ignore
  # exit through the service roads, not currently supported by scripts
  13719126553:
    parent_id: 635884768
  # toll booth in vinci is displaced
  14061571392:
    vinci:
      id: 12010
      name: SEES
  # not carried by the operator at all
  1391610490:
    type: absent_passthrough
    price: 1.4

duplicate_gares:
  # the road that would let a driver carry on is not built yet
  - "04210"
```

Different steps consume different keys. `type: ignore` and `parent_id` decide what the inventory contains and are applied by the extraction step; `vinci`, the `absent_*` types, `price`, and `duplicate_gares` are consumed by the gare mapping step. Editing one of the first kind therefore requires rebuilding the inventory before the effect is visible.

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

#### Scenario: A gare number written without quotes

- **WHEN** `duplicate_gares` lists `04210` unquoted, which YAML reads as an integer
- **THEN** it still names gare `04210`, with the leading zero intact

#### Scenario: duplicate_gares is not a list

- **WHEN** `duplicate_gares` carries something other than a list
- **THEN** the step stops and names what it found

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

## ADDED Requirements

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
