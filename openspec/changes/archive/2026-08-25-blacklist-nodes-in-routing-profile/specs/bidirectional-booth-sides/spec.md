## REMOVED Requirements

### Requirement: An observation counts only when nothing lies between

**Reason**: Replaced below. The routing profile now makes a blacklisted node impassable, so no returned route can traverse one and the clause discarding such routes has nothing to catch.

**Migration**: None. An observation admitted under the old rule is admitted under the new one.

## ADDED Requirements

### Requirement: An observation counts only when no booth lies between

An observation SHALL be admitted only when the route traverses the booth, and no other booth group lies between the booth and the target.

The side observed SHALL be the node immediately after the booth when routing away from it, and the node immediately before it when routing towards it.

The step SHALL NOT filter observations against a node blacklist. The routing profile makes a blacklisted node impassable, so a route over one is never returned, and a filter here would imply otherwise.

#### Scenario: A booth in between voids the observation

- **WHEN** a route from the booth to its target crosses a third booth
- **THEN** the observation is discarded

#### Scenario: No route can use a blacklisted node

- **WHEN** the probe runs
- **THEN** no returned route traverses a blacklisted node, and none is discarded for doing so

#### Scenario: The side is the node beside the booth

- **WHEN** a route leaves the booth by node D on its way to a target
- **THEN** the observation is about D
