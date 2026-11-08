# Spec Delta

## MODIFIED Requirements

### Requirement: The open station list defines the stations a run reads

A run SHALL read the open station list from `https://www.prix-carburants.gouv.fr/map/recupererOpenPdvs/`. Each entry gives a station id and a position. The station id SHALL be the key of the stored station. When no OpenStreetMap station gives the position, the stored latitude and longitude SHALL be the values of the list entry, as numbers.

#### Scenario: A listed station is stored under its id

- **WHEN** the list has the entry `{"id": 29520005, "coordLatitude": "48.209", "coordLongitude": "-3.818"}`, the OpenStreetMap file lists no station under `"29520005"`, and the run refreshes that station
- **THEN** the store has a station with id `29520005`, latitude `48.209`, and longitude `-3.818`

#### Scenario: The position comes from the list

- **WHEN** the list gives a new position for a stored station, the OpenStreetMap file lists no station under its id, and the run refreshes that station
- **THEN** the stored position is the new position from the list

## ADDED Requirements

### Requirement: A matched OpenStreetMap station gives the stored position

When the run refreshes a station, it SHALL read the candidates under the station id in `/cache/osm_gas_stations.json`, the file of `osm-gas-stations`. When the rules choose a candidate, the stored latitude and longitude SHALL be its position. The position of a node is its `latitude` and `longitude`. The position of an area is the centroid of its ring.

#### Scenario: A node gives the position

- **GIVEN** the list position `48.209`, `-3.818` for station `29520005`
- **WHEN** the file lists one node under `"29520005"`, at `48.2095`, `-3.8172`
- **THEN** the stored position is `48.2095`, `-3.8172`

#### Scenario: An area gives its centroid

- **GIVEN** the list position `48.209`, `-3.818` for station `29520005`
- **WHEN** the file lists one area under `"29520005"` with the points `[48.2, -3.82]`, `[48.2, -3.81]`, `[48.21, -3.81]`, `[48.21, -3.82]`
- **THEN** the stored position is `48.205`, `-3.815`

#### Scenario: The geographic index follows the OpenStreetMap position

- **WHEN** a refreshed station is stored at the position of its OpenStreetMap node
- **THEN** an area query around that node finds the station

### Requirement: A candidate far from the list position is not used

A candidate more than 20 km from the list position SHALL NOT be a candidate. When no candidate is left, the stored position SHALL be the list position.

#### Scenario: A candidate 15 km away is used

- **WHEN** the only candidate of a station is 15 km from its list position
- **THEN** the stored position is the position of that candidate

#### Scenario: A candidate 25 km away is not used

- **WHEN** the only candidate of a station is 25 km from its list position
- **THEN** the stored position is the list position

### Requirement: A candidate with the brand of the station is preferred

When several candidates are left, the run SHALL keep those whose `brand`, `name`, or `operator` tag contains the first word of the stored brand. The comparison SHALL ignore case and accents. When no candidate has that word, or the stored brand is null, the run SHALL keep every candidate.

#### Scenario: The station brand wins over a nearer station

- **GIVEN** the page of station `29520005` shows the brand `Leclerc`
- **WHEN** its candidates are a node named `PETRO-EST` 250 m from the list position, and an area named `Station Service E. Leclerc` 460 m from it
- **THEN** the stored position is the centroid of the `Station Service E. Leclerc` area

#### Scenario: Case and accents do not matter

- **GIVEN** the page of a station shows the brand `Intermarché Contact`
- **WHEN** its candidates are a node with `brand=INTERMARCHE` 300 m from the list position, and a node with `brand=Total` 100 m from it
- **THEN** the stored position is the position of the `INTERMARCHE` node

#### Scenario: No candidate has the brand

- **GIVEN** the page of a station shows the brand `Système U`
- **WHEN** its candidates are a node with `brand=Super U` and a node with `brand=Hyper U`
- **THEN** the run keeps both candidates, and the nearest rule chooses

### Requirement: The candidate nearest to the list position is chosen

Among the candidates that are left, the run SHALL choose the one nearest to the list position.

#### Scenario: Two candidates without the brand

- **WHEN** a station has two candidates without its brand word, one 100 m and one 300 m from the list position
- **THEN** the stored position is the position of the candidate 100 m away

### Requirement: A run without the OpenStreetMap file stores the list positions

When `/cache/osm_gas_stations.json` does not exist, is not JSON, or is not a JSON object, the run SHALL log a warning, and SHALL store the list position of each refreshed station. The file SHALL NOT change the exit status of the run.

#### Scenario: The file does not exist

- **WHEN** a run refreshes stations and `/cache/osm_gas_stations.json` does not exist
- **THEN** the run logs a warning, stores the list positions, and exits with the status 0 when no station failed

#### Scenario: The file is not JSON

- **WHEN** a run starts and the file holds `not json`
- **THEN** the run logs a warning, and stores the list positions

### Requirement: The run logs the source of the positions

At its end, the run SHALL log how many refreshed stations got an OpenStreetMap position, and how many got the list position.

#### Scenario: The counts are logged

- **WHEN** a run refreshes three stations, and two of them have a candidate
- **THEN** the log says that 2 stations got an OpenStreetMap position, and 1 got the list position
