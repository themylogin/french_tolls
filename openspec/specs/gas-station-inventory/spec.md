# gas-station-inventory Specification

## Purpose
Defines which fuel stations the project stores from `prix-carburants.gouv.fr`, what it stores for each station, how a run refreshes the stale stations, and how a caller finds the stations in an area.

## Requirements

### Requirement: The open station list defines the stations a run reads

A run SHALL read the open station list from `https://www.prix-carburants.gouv.fr/map/recupererOpenPdvs/`. Each entry gives a station id and a position. The station id SHALL be the key of the stored station. When no OpenStreetMap station gives the position, the stored latitude and longitude SHALL be the values of the list entry, as numbers.

#### Scenario: A listed station is stored under its id

- **WHEN** the list has the entry `{"id": 29520005, "coordLatitude": "48.209", "coordLongitude": "-3.818"}`, the OpenStreetMap file lists no station under `"29520005"`, and the run refreshes that station
- **THEN** the store has a station with id `29520005`, latitude `48.209`, and longitude `-3.818`

#### Scenario: The position comes from the list

- **WHEN** the list gives a new position for a stored station, the OpenStreetMap file lists no station under its id, and the run refreshes that station
- **THEN** the stored position is the new position from the list

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

At the end of a run that stores its stations, the run SHALL log how many refreshed stations got an OpenStreetMap position, and how many got the list position.

#### Scenario: The counts are logged

- **WHEN** a run refreshes three stations, and two of them have a candidate
- **THEN** the log says that 2 stations got an OpenStreetMap position, and 1 got the list position

#### Scenario: A refused run does not log the counts

- **WHEN** a run is refused
- **THEN** the log has no line with the count of refreshed stations

### Requirement: The stored name is the brand without its label

The station page shows the brand as `Marque : <brand>`. The stored name SHALL be `<brand>`, without the label, the colon, and the white space around them. When the page has no brand line, the stored name SHALL be empty (null).

#### Scenario: The label is removed

- **WHEN** the page shows `Marque : Leclerc`
- **THEN** the stored name is `Leclerc`

#### Scenario: An independent station keeps the text of the page

- **WHEN** the page shows `Marque : Indépendant sans enseigne`
- **THEN** the stored name is `Indépendant sans enseigne`

#### Scenario: A page without a brand line

- **WHEN** the station block of the page has no `Marque` line
- **THEN** the stored name is null, and every line of the block is an address line

### Requirement: The address is stored as its lines

The stored address SHALL be a JSON list of the address lines of the station page, in page order. In each line, each run of white space SHALL become one space, and the line SHALL have no white space at its start or end.

#### Scenario: A two-line address

- **WHEN** the page shows `Rue de quimper`, then a line break, then `29520` and `Chateauneuf du faou` on separate source lines
- **THEN** the stored address is `["Rue de quimper", "29520 Chateauneuf du faou"]`

### Requirement: The services are stored as a list of names

The stored services SHALL be a JSON list of the service names of the station page, in page order. When the page shows no service, the stored services SHALL be an empty list.

#### Scenario: A station with one service

- **WHEN** the page lists the service `Lavage automatique`
- **THEN** the stored services are `["Lavage automatique"]`

#### Scenario: A station with no service

- **WHEN** the services section of the page is empty
- **THEN** the stored services are `[]`

### Requirement: Each sold fuel is stored as a fuel, a date, and a price

The stored prices SHALL be a JSON list with one `[fuel, date, price]` entry for each fuel row that shows a price, in page order. The date SHALL be the page date `DD/MM/YY` in the ISO 8601 form `YYYY-MM-DD`. The price SHALL be the text of the page, unchanged, as a string. A fuel row without a price SHALL NOT be stored.

#### Scenario: A sold fuel

- **WHEN** the page shows the fuel `SP95-E10 (E10)` with the date `06/11/26` and the price `1.999`
- **THEN** the stored prices contain `["SP95-E10 (E10)", "2026-11-06", "1.999"]`

#### Scenario: The price text is kept exactly

- **WHEN** the page shows the price `2.100`
- **THEN** the stored price is the string `"2.100"`, not the number `2.1`

#### Scenario: A fuel that the station does not sell

- **WHEN** the row `SP98 (E5)` shows no date and no price
- **THEN** the stored prices contain no entry for `SP98 (E5)`

### Requirement: The update time records the last successful page read

The stored `last_updated_at` SHALL be the UTC time at which the run read the station page. It SHALL change only when the run stores a parsed page for that station.

#### Scenario: A stored station gets the time of its read

- **WHEN** a run stores a station
- **THEN** its `last_updated_at` is in UTC, and is between the start and the end of that run

### Requirement: A run refreshes only the stations older than the maximum age

A run SHALL take a maximum age as an ISO 8601 duration, for example `PT23H`. The run SHALL read the page of each listed station that has no stored row. It SHALL also read the page of each listed station whose `last_updated_at` is earlier than the run start minus the maximum age. It SHALL NOT read any other station page.

#### Scenario: A fresh station is skipped

- **GIVEN** a listed station with a `last_updated_at` of two hours ago
- **WHEN** a run starts with the maximum age `PT23H`
- **THEN** the run does not request the page of that station, and its row does not change

#### Scenario: A stale station is refreshed

- **GIVEN** a listed station with a `last_updated_at` of 30 hours ago
- **WHEN** a run starts with the maximum age `PT23H`
- **THEN** the run requests the page of that station and replaces its row

#### Scenario: A new station is read

- **WHEN** a listed station has no stored row
- **THEN** the run requests its page and creates its row

#### Scenario: A zero age refreshes every listed station

- **WHEN** a run starts with the maximum age `PT0S`
- **THEN** the run requests the page of every listed station

### Requirement: A run with an invalid age sends no request

A run SHALL refuse a maximum age that is missing or that is not an ISO 8601 duration. It SHALL then exit with a non-zero status, and SHALL NOT send a request.

#### Scenario: An age that is not ISO 8601

- **WHEN** a run starts with the maximum age `23h`
- **THEN** the run exits with a non-zero status, and sends no request

#### Scenario: No age

- **WHEN** a run starts without a maximum age
- **THEN** the run shows its usage, exits with a non-zero status, and sends no request

### Requirement: A failed station does not stop the run

A station fails when its page request fails, when the response status is not 200, or when the page has no price table or no station block. The row of a failed station SHALL stay unchanged. The run SHALL log the id and the reason of each failure. It SHALL continue with the other stations, and SHALL exit with a non-zero status after the last one.

#### Scenario: A station page that is not found

- **WHEN** the page of one selected station returns the status 404
- **THEN** the row of that station does not change, the run refreshes the other selected stations, and the run exits with a non-zero status

#### Scenario: A page with an unknown layout

- **WHEN** the page of a selected station has no price table
- **THEN** the run stores nothing for that station, and logs its id with the reason

#### Scenario: Every station succeeds

- **WHEN** the run refreshes every selected station without a failure
- **THEN** the run exits with the status 0

### Requirement: A run that cannot read the list changes nothing

When the list request fails, or the response is not a JSON list of entries with an id and a position, the run SHALL exit with a non-zero status. It SHALL NOT request a station page, and SHALL NOT change the store.

#### Scenario: The list is not available

- **WHEN** the list request returns the status 503
- **THEN** the run exits with a non-zero status, requests no station page, and leaves every stored row unchanged

### Requirement: A run stores its stations in one transaction

The run SHALL read the page of each selected station before it writes any station. It SHALL then write all the read stations in one transaction. When a run stops before that commit, every stored row SHALL stay unchanged.

#### Scenario: An interrupted run stores nothing

- **GIVEN** five listed stations without a stored row
- **WHEN** a run reads four of their pages and then stops
- **THEN** the store has no station, and the next run requests the five pages

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

### Requirement: A station that leaves the open list stays stored

A run SHALL NOT delete or change the row of a station that the open list does not contain.

#### Scenario: A station is no longer listed

- **GIVEN** a stored station whose id is not in the open list
- **WHEN** a run completes
- **THEN** the row of that station is unchanged

### Requirement: The run limits its load on the source

The run SHALL have no more than four station page requests open at the same time.

#### Scenario: Many stale stations

- **WHEN** a run refreshes 100 stations
- **THEN** no more than four station page requests are open at any time

### Requirement: A caller finds the stations in an area through a geographic index

The store SHALL keep a geographic index of the station positions. A caller SHALL be able to ask for the stations in a box, given by its south, west, north, and east bounds. The answer SHALL contain each station whose stored position is in the box or on its edge, and no other station. The query SHALL use the index, and SHALL NOT read every station row.

#### Scenario: Only the stations in the box

- **GIVEN** a station at latitude `48.209`, longitude `-3.818`, and a station at latitude `44.928`, longitude `2.443`
- **WHEN** a caller asks for the box with south `47.0`, west `-5.0`, north `49.0`, and east `-1.0`
- **THEN** the answer contains the first station only

#### Scenario: A station on the edge

- **GIVEN** a station at latitude `48.0`, longitude `-3.0`
- **WHEN** a caller asks for the box with south `48.0`, west `-4.0`, north `49.0`, and east `-3.0`
- **THEN** the answer contains that station

#### Scenario: The query uses the index

- **WHEN** the query plan of an area query is inspected
- **THEN** it reads the geographic index, and does not scan the whole station table

### Requirement: The index always agrees with the station table

The index SHALL hold exactly one entry for each stored station, at the stored position of that station. This SHALL be true after each insert, update, and delete of a station row, whichever code makes the change.

#### Scenario: A new station is indexed

- **WHEN** a station row is inserted
- **THEN** the index has one entry for it, at its position

#### Scenario: A moved station is indexed at its new position

- **WHEN** the position of a stored station changes
- **THEN** its index entry is at the new position, and the old position finds it no more

#### Scenario: A deleted station leaves the index

- **WHEN** a station row is deleted
- **THEN** the index has no entry for it

### Requirement: The update is a one-shot Compose service

`docker-compose.yml` SHALL define the service `gas-stations`, built from the application image. `docker compose run --rm gas-stations <maximum age>` SHALL start one run with that maximum age. The service SHALL use the store of the application, and SHALL start only after `migrate` completes successfully. A plain `docker compose up` SHALL NOT start it. It SHALL publish no port.

#### Scenario: The operator starts a run

- **WHEN** the operator runs `docker compose run --rm gas-stations PT23H`
- **THEN** `migrate` completes, then one run starts with the maximum age of 23 hours, and the command exits with the status of that run

#### Scenario: The schema is applied first

- **GIVEN** a store without the station table
- **WHEN** the operator starts the service
- **THEN** `migrate` creates the station table before the run starts

#### Scenario: The web service sees the stored stations

- **WHEN** a run completes
- **THEN** its rows are in the same database that `web` and `bot` open

#### Scenario: Plain compose up does not start it

- **WHEN** `docker compose up` is run
- **THEN** the `gas-stations` service does not start
