# Spec Delta

## ADDED Requirements

### Requirement: Mainland is west of the meridian 8.4°E

A candidate SHALL be admitted only if its longitude is 8.4°E or less. The step SHALL report how many candidates the meridian excluded.

The meridian lies between Lauterbourg (8.23°E), the easternmost point of the mainland, and the Sanguinaires (8.53°E), the westernmost land of Corsica. The overseas departments need no rule: the France extract carries no city or town node there.

#### Scenario: Corsica is excluded

- **WHEN** the city set is built
- **THEN** no city on Corsica appears in it, and the step reports the number that the meridian excluded

#### Scenario: The easternmost mainland towns are kept

- **WHEN** the candidates include Wissembourg at 7.945°E
- **THEN** the meridian does not exclude it

#### Scenario: The router is not asked to exclude a class

- **WHEN** the step asks the router for reachability
- **THEN** the request carries no `exclude` parameter

### Requirement: A candidate the router cannot reach is excluded

A candidate west of the meridian SHALL be admitted only if the router can drive to it from a mainland reference point. The step SHALL report how many candidates the router could not reach.

#### Scenario: An unreachable candidate is excluded

- **WHEN** the router returns no duration from the reference point to a candidate
- **THEN** the candidate is not in the city set, and the count of unreachable candidates includes it

## REMOVED Requirements

### Requirement: Mainland is decided by the road network, not by a box

**Reason**: The routing profile declares no excludable class, so the router cannot answer a question that excludes ferries. Each excludable class costs 457 MB of memory in each graph.

**Migration**: The meridian 8.4°E decides what is mainland. The router still removes candidates that it cannot reach. An existing `data/test_cities.yaml` stays valid, because the old rule also excluded Corsica.
