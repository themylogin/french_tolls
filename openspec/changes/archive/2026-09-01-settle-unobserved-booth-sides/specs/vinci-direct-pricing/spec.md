## MODIFIED Requirements

### Requirement: A barrier is never an endpoint

A two-way booth whose sides all agree — every adjacent node inside, or every one outside — SHALL be excluded from the grid as a source and as a target.

Such a booth is a barrier. You pay passing it and your ticket state does not change, so there is no journey for which it is the entrance or the exit, and any pair naming it is not a ticket however the roads read.

A booth SHALL be judged a barrier only when every node the inventory records as adjacent to it appears in one of its two lists. A booth with an adjacent node in neither list did not settle, and is not a barrier: `bidirectional-booth-sides` records the difference exactly that way, and testing only whether one list is empty cannot tell them apart. Péage de Thèze had one of its two adjacent nodes in neither list and was filed as a barrier, which discarded every pair naming it before any route was issued.

An unsettled booth SHALL be excluded from the grid as a barrier is, and SHALL be reported separately from the barriers, so that a gap in what step 7 reached is never read as a fact about the road.

The exclusion SHALL happen before routing, alongside self-pairs, same-gare pairs and prohibited pairs, and SHALL be recorded in neither output.

#### Scenario: A barrier is not a source

- **WHEN** the grid is enumerated and a `bidirectional` group has every side outside
- **THEN** no pair has it as a source

#### Scenario: A barrier is not a target

- **WHEN** the grid is enumerated and a `bidirectional` group has every side outside
- **THEN** no pair has it as a target

#### Scenario: A barrier costs no route

- **WHEN** a barrier is excluded
- **THEN** no route is requested for any pair naming it

#### Scenario: An unsettled booth is not filed as a barrier

- **WHEN** a `bidirectional` group has an adjacent node in neither of its lists
- **THEN** it is excluded from the grid and reported as unsettled, not counted among the barriers
