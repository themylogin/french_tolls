## MODIFIED Requirements

### Requirement: Booth inventory output format

The system SHALL write the booth inventory to `data/osm_toll_booths.yaml` as a mapping with two top-level keys.

`toll_booths` SHALL map one representative OSM node id per group to that node's details. The representative SHALL be the smallest node id in its group.

`aliases` SHALL map every non-representative booth id to that node's details together with `parent_id`, the id of its group's representative. Every *retained* booth SHALL appear exactly once, either in `toll_booths` or in `aliases`; booths excluded by the through-road rule appear in neither.

Every entry, representative and alias alike, SHALL carry `latlon`, a two-element list holding **that node's own** position in latitude, longitude order. An alias SHALL NOT repeat its representative's position: consumers match against individual lanes, and the members of one group are a median of 15 metres and up to several hundred metres apart.

An entry SHALL carry `name` when its node carries an OSM `name` tag, and SHALL NOT carry it otherwise. The value SHALL be the tag as the extract states it, unaltered.

The name is recorded because it is the only name some booths have. Twelve booths map to no operator gare and so have no operator name; every one of them is named in OSM — Chanas, Bernay, Hochfelden, Péage de Vienne — and discarding the tag left a consumer with nothing to print but a node id. Recording it costs one string per booth and is what the extract already holds.

The pipeline SHALL NOT correct, translate, or normalise the tag. What OSM calls a place is a fact about OSM; deciding it should be called something else is a different job, and doing it here would put an opinion in an inventory.

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
    name: Ablis
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
    name: Ablis
```

#### Scenario: A named node carries its name

- **WHEN** a booth's node carries an OSM `name` tag
- **THEN** its entry carries `name` holding that tag unaltered, whether it is a representative or an alias

#### Scenario: An unnamed node carries nothing

- **WHEN** a booth's node has no `name` tag
- **THEN** its entry carries no `name` key

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
