## ADDED Requirements

### Requirement: A barrier is never an endpoint

A two-way booth whose sides all agree — every adjacent node inside, or every one outside — SHALL be excluded from the grid as a source and as a target.

Such a booth is a barrier. You pay passing it and your ticket state does not change, so there is no journey for which it is the entrance or the exit, and any pair naming it is not a ticket however the roads read.

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

### Requirement: A two-way end must be used on its inside side

A route SHALL additionally be rejected when a two-way booth at either end of the pair is not used on the side that gives it the role the pair requires.

- A two-way **source** SHALL be departed toward a node in its `inside_nodes`. Leaving by the free side means the vehicle was not entering the network there.
- A two-way **target** SHALL be arrived at from a node in its `inside_nodes`. Arriving from the free side means the vehicle was not leaving the network there.

Both tests use the node immediately beside the booth on the route, the same node the sides were established from.

A one-way booth SHALL NOT be tested. Its single traffic sense already fixes its role, and it carries no sides.

#### Scenario: A source departed by its free side is rejected

- **WHEN** the route leaves a two-way source by a node in its `outside_nodes`
- **THEN** the pair is rejected

#### Scenario: A source departed by its toll side is kept

- **WHEN** the route leaves a two-way source by a node in its `inside_nodes` and nothing lies between
- **THEN** the pair is priced

#### Scenario: A target arrived at from its free side is rejected

- **WHEN** the route reaches a two-way target from a node in its `outside_nodes`
- **THEN** the pair is rejected

#### Scenario: A one-way end is not tested

- **WHEN** either end of a pair is a one-way booth
- **THEN** no side test is applied to it

### Requirement: A rejection records why

A rejected pair SHALL record which of the two reasons applies: a booth lying between the two, or an end used on its free side.

Both mean "not a ticket", and they want different remedies — one is about a third booth, the other about the direction of travel at an endpoint. A record that conflates them cannot be read afterwards.

A rejection for a booth in the way SHALL name that booth. A rejection for a wrong side SHALL name none, because none is implicated.

#### Scenario: A blocked pair names its booth

- **WHEN** a route crosses a third booth
- **THEN** the record carries that booth and the reason distinguishing it

#### Scenario: A wrong-side pair names no booth

- **WHEN** a pair is rejected for using an end on its free side
- **THEN** the record carries no booth and the reason saying so

### Requirement: Prices recorded before the side rule are re-derived

Every price whose source or target is a two-way booth SHALL be discarded, so that it is asked again under the rule.

Those amounts were recorded when any `bidirectional` group could be either end. Some describe journeys the rule now rejects, and nothing in the file distinguishes them from the ones it keeps. Re-deriving is the only way to tell, and leaving them would publish tariffs for pairings the step would no longer make.

A price with a one-way booth at both ends SHALL be kept and SHALL NOT be asked again.

#### Scenario: A price touching a two-way booth is discarded

- **WHEN** a price has a `bidirectional` group as its source, or a target gare carried by one
- **THEN** it is removed from `data/vinci_price.yaml` and the pair becomes outstanding

#### Scenario: A price between one-way booths is kept

- **WHEN** a price has a one-way booth at both ends
- **THEN** it is unchanged and no request is issued for it
