## MODIFIED Requirements

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

### Requirement: Hand-maintained booth overrides

The extraction step SHALL read `data/osm_toll_booths_overrides.yaml`, a hand-maintained input recording decisions that no rule can derive from the extract. A missing file SHALL be treated as an empty set of overrides.

The file SHALL be a mapping with three permitted top-level keys. `toll_booths` holds decisions about individual booths, keyed by OSM node id; an entry SHALL carry at least one of `type`, `parent_id`, `vinci`, or `price`. `duplicate_gares` holds operator numbers of gares that one route may legitimately pay twice. `nodes_blacklist` holds OSM node ids a route may not pass through.

A top-level key that is none of the three SHALL stop the step. A mistyped section name would otherwise read as an absent section, and every entry beneath it would be dropped without a word.

Operator numbers in `duplicate_gares` SHALL be compared as strings. They carry leading zeros, which YAML reads away when the value is unquoted, so `04210` and `"04210"` SHALL name the same gare.

`nodes_blacklist` SHALL be a list of integer node ids. Each entry states that the map is wrong at that node — a connection that is not there on the ground — so a route the router builds through it is not one a car can drive. It is a bridge until the extract carries the upstream fix, not a routing preference, and each entry SHALL record what is wrong and be removed once the fix lands.

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

nodes_blacklist:
  # the D28 is joined to the A71 through the L'Arverne service area
  - 13461343964
```

Different steps consume different keys. `type: ignore` and `parent_id` decide what the inventory contains and are applied by the extraction step; `nodes_blacklist` is consumed by the route search; `vinci`, the `absent_*` types, `price`, and `duplicate_gares` are consumed by the gare mapping step, and `price` again by the pricing step. Editing one of the first kind therefore requires rebuilding the inventory before the effect is visible.

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

- **WHEN** the file carries a top-level key other than `toll_booths`, `duplicate_gares`, or `nodes_blacklist`
- **THEN** the step stops and names it, rather than silently ignoring everything under it

#### Scenario: A gare number written without quotes

- **WHEN** `duplicate_gares` lists `04210` unquoted, which YAML reads as an integer
- **THEN** it still names gare `04210`, with the leading zero intact

#### Scenario: duplicate_gares is not a list

- **WHEN** `duplicate_gares` carries something other than a list
- **THEN** the step stops and names what it found

#### Scenario: nodes_blacklist is not a list

- **WHEN** `nodes_blacklist` carries something other than a list
- **THEN** the step stops and names what it found

#### Scenario: A blacklisted node id is not an integer

- **WHEN** `nodes_blacklist` lists a value that is not an integer node id
- **THEN** the step stops and names it
