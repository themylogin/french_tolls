## ADDED Requirements

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

## MODIFIED Requirements

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
