## MODIFIED Requirements

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

#### Scenario: An isolated node is checked too

- **WHEN** an override carries a null `parent_id` for a node the extract does not carry as a toll booth
- **THEN** the step stops and names that node
