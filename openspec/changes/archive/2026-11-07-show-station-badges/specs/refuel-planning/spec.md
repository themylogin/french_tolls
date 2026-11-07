# Spec Delta

## ADDED Requirements

### Requirement: Each listed station carries one badge or none

Each entry of `stations` SHALL also carry `badge`. It SHALL be `"24"` when the services of the station contain `Automate CB 24/24`. Else, it SHALL be `"Autoroute"` when an address line contains `autoroute` in any letter case. Else, it SHALL be `"Aire"` when an address line contains `aire`, not after a letter, then white space, then `de`, `des`, `du`, `d'`, or `d’`, in any letter case. Else, it SHALL be `null`.

#### Scenario: A station that sells at any hour

- **WHEN** the services of a station are `["Automate CB 24/24", "Lavage automatique"]`
- **THEN** its `badge` is `"24"`

#### Scenario: The 24 badge comes first

- **WHEN** a station has the service `Automate CB 24/24` and the address line `Autoroute A7`
- **THEN** its `badge` is `"24"`

#### Scenario: A motorway address in any letter case

- **WHEN** a station without `Automate CB 24/24` has the address line `Autoroute A7`, or the address line `aire de l'autoroute`
- **THEN** its `badge` is `"Autoroute"`

#### Scenario: A service area

- **WHEN** a station without `Automate CB 24/24` and without `autoroute` has one of the address lines `Aire de Beaune`, `aire des Volcans`, `aire du Poitou`, `aire d'Orange`, or `aire d’Orange`
- **THEN** its `badge` is `"Aire"`

#### Scenario: A service area glued to its motorway number

- **WHEN** a station without the two other badges has the address line `A71aire de ste thorette`
- **THEN** its `badge` is `"Aire"`

#### Scenario: A word that ends in aire

- **WHEN** a station without the two other badges has the address line `38460 Saint hilaire de brens` or `Zi portuaire des mielles`
- **THEN** its `badge` is `null`

#### Scenario: No rule matches

- **WHEN** a station has no services and the address lines `Rue de quimper` and `29520 Chateauneuf du faou`
- **THEN** its `badge` is `null`
