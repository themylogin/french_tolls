## ADDED Requirements

### Requirement: Hand-maintained booth overrides

The extraction step SHALL read `data/osm_toll_booths_overrides.yaml`, a hand-maintained input recording decisions about individual booths that no rule can derive from the extract. A missing file SHALL be treated as an empty set of overrides.

The file SHALL be a mapping with one top-level key, `toll_booths`, whose keys are OSM node ids. An entry SHALL carry at least one of `type`, `parent_id`, `vinci`, or `price`.

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
```

Different steps consume different keys. `type: ignore` and `parent_id` decide what the inventory contains and are applied by the extraction step; `vinci`, the `absent_*` types, and `price` are consumed by the gare mapping step. Editing one of the first kind therefore requires rebuilding the inventory before the effect is visible.

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

A booth whose override is `parent_id` SHALL be placed in the group of the named booth, without any topological test. The forced membership SHALL be applied after the grouping rules have run, and SHALL merge the overridden booth's whole group into the target's group, since a group cannot be split by fiat.

The target SHALL be a group representative after the grouping rules have run. A target that is itself an alias of some other group is not a group, and naming one SHALL stop the step.

The representative of the merged group SHALL follow the usual rule — the smallest node id among its members.

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

### Requirement: Every override is checked against the extract

The system SHALL validate every override against the booths found in the source extract, and SHALL stop and name the offending entry when one does not apply. An override that has gone stale — because the node was retagged, deleted, or renumbered upstream — otherwise produces a silently wrong inventory.

An overridden node SHALL be a booth in the source extract. A `parent_id` target SHALL be a booth that survived the through-road filter. A `type` value SHALL be one of `ignore`, `absent_enter`, `absent_exit`, `absent_passthrough`, `enter`, `exit`, or `passthrough`.

`enter`, `exit` and `passthrough` SHALL be accepted and SHALL have no effect on the inventory. They record how a booth relates to a border crossing, which nothing consumes yet; accepting them keeps the existing file valid, and enumerating them means a mistyped `ignore` fails instead of passing unnoticed.

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

#### Scenario: Border classifications are inert

- **WHEN** a booth carries `type: enter`, `type: exit`, or `type: passthrough`
- **THEN** the inventory is exactly as it would have been without that entry
