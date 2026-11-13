# Spec Delta

## ADDED Requirements

### Requirement: A valid station sells diesel and 95

A stored station SHALL be valid when its stored prices contain an entry for a fuel of the type `diesel`, and an entry for a fuel of the type `95`. The fuels of each type SHALL be those that `car-parameters` gives it. The date of an entry SHALL NOT matter.

#### Scenario: Diesel and E10

- **WHEN** the stored prices are `[["SP95-E10 (E10)", "2026-11-06", "1.999"], ["Gazole (B7)", "2026-11-06", "2.149"]]`
- **THEN** the station is valid

#### Scenario: Diesel and E5

- **WHEN** the stored prices are `[["SP95 (E5)", "2026-11-06", "2.019"], ["Gazole (B7)", "2026-11-06", "2.149"]]`
- **THEN** the station is valid

#### Scenario: Diesel without 95

- **WHEN** the stored prices are `[["SP98 (E5)", "2026-11-06", "2.089"], ["Gazole (B7)", "2026-11-06", "2.149"]]`
- **THEN** the station is not valid

#### Scenario: 95 without diesel

- **WHEN** the stored prices are `[["SP95-E10 (E10)", "2026-11-06", "1.999"], ["E85 (E85)", "2026-11-06", "0.877"]]`
- **THEN** the station is not valid

#### Scenario: The fuel types decide

- **GIVEN** the fuel type `95` covers `SP95-E10 (E10)`, `SP95 (E5)`, and a new fuel `SP95-E15 (E15)`
- **WHEN** the stored prices are `[["SP95-E15 (E15)", "2026-11-06", "1.949"], ["Gazole (B7)", "2026-11-06", "2.149"]]`
- **THEN** the station is valid

#### Scenario: An old price still counts

- **WHEN** the stored prices are `[["SP95-E10 (E10)", "2026-04-08", "1.899"], ["Gazole (B7)", "2026-11-06", "2.149"]]`
- **THEN** the station is valid

### Requirement: A run stores its stations in one transaction

The run SHALL read the page of each selected station before it writes any station. It SHALL then write all the read stations in one transaction. When a run stops before that commit, every stored row SHALL stay unchanged.

#### Scenario: An interrupted run stores nothing

- **GIVEN** five listed stations without a stored row
- **WHEN** a run reads four of their pages and then stops
- **THEN** the store has no station, and the next run requests the five pages

### Requirement: A run that loses too many valid stations is refused

The run SHALL count the valid stations of the store before it writes the read stations, and after it writes them. When the first count is above 0, and the second count is 80% or less of the first, the run SHALL leave every stored row unchanged. It SHALL then log both counts, and SHALL exit with the status 1.

#### Scenario: A drop to 80% is refused

- **GIVEN** five stored stations that are valid and stale
- **WHEN** a run refreshes them, and the page of one of them shows a price for `E85 (E85)` only
- **THEN** every stored row is unchanged, the log has the line `The update is refused: 4 valid stations after it, 5 before it`, and the run exits with the status 1

#### Scenario: A drop to 90% is stored

- **GIVEN** ten stored stations that are valid and stale
- **WHEN** a run refreshes them, and the page of one of them shows a price for `E85 (E85)` only
- **THEN** the run stores the ten read stations, and exits with the status 0

#### Scenario: A store without a valid station accepts any run

- **GIVEN** a store with no valid station
- **WHEN** a run refreshes a station whose page shows a price for `E85 (E85)` only
- **THEN** the run stores that station, and exits with the status 0

#### Scenario: A refused run with a failed station

- **GIVEN** five stored stations that are valid and stale
- **WHEN** a run refreshes them, the page of one of them returns the status 404, and the page of another one shows a price for `E85 (E85)` only
- **THEN** every stored row is unchanged, the log has the line `The update is refused: 4 valid stations after it, 5 before it`, and the run exits with the status 1

## MODIFIED Requirements

### Requirement: The run logs the source of the positions

At the end of a run that stores its stations, the run SHALL log how many refreshed stations got an OpenStreetMap position, and how many got the list position.

#### Scenario: The counts are logged

- **WHEN** a run refreshes three stations, and two of them have a candidate
- **THEN** the log says that 2 stations got an OpenStreetMap position, and 1 got the list position

#### Scenario: A refused run does not log the counts

- **WHEN** a run is refused
- **THEN** the log has no line with the count of refreshed stations

## REMOVED Requirements

### Requirement: Each station is stored in its own transaction

**Reason**: A refused run must leave the store unchanged. So the run cannot commit a station before it checks the count of valid stations.

**Migration**: No operator action. A run that stops early stores nothing, and the next run reads all its selected pages again.
