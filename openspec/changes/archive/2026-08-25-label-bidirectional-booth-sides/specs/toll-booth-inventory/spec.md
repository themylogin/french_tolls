## ADDED Requirements

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
