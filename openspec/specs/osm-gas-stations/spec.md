# osm-gas-stations Specification

## Purpose
Defines which OpenStreetMap fuel stations the project extracts, the shape of the JSON file that gives them by prix-carburants id, how a run gets the extract and replaces the file, and how the operator starts a run.

## Requirements

### Requirement: A run reads the most recent France extract

Each run SHALL download the France extract from `https://download.geofabrik.de/europe/france-latest.osm.pbf`. It SHALL NOT read an extract from an earlier run, and SHALL NOT read `data/france-latest.osm.pbf` of the build pipeline.

#### Scenario: Two runs download two times

- **WHEN** the operator starts two runs, one after the other
- **THEN** each run requests `https://download.geofabrik.de/europe/france-latest.osm.pbf`

### Requirement: The file holds the fuel objects that carry a prix-carburants id

The file SHALL hold each OSM node and area that has the tag `amenity=fuel` and the tag `ref:FR:prix-carburants`. It SHALL hold no other OSM object.

#### Scenario: A fuel station with an id

- **WHEN** the extract has a node with `amenity=fuel` and `ref:FR:prix-carburants=45200007`
- **THEN** the file holds that node

#### Scenario: A fuel station without an id

- **WHEN** the extract has a node with `amenity=fuel` and no `ref:FR:prix-carburants` tag
- **THEN** the file does not hold that node

#### Scenario: An id on an object that is not a fuel station

- **WHEN** the extract has a node with `amenity=charging_station` and `ref:FR:prix-carburants=45200007`
- **THEN** the file does not hold that node

### Requirement: The file gives the stations by id

The file SHALL be one JSON object. Each key SHALL be a prix-carburants id, as a string. Its value SHALL be a list of every written station that carries that id, in no fixed order. An id that no station carries SHALL NOT be a key.

#### Scenario: Two stations with the same id

- **WHEN** a node and an area both have `ref:FR:prix-carburants=33560002`
- **THEN** the value of the key `"33560002"` is a list of two stations: the node and the area

#### Scenario: A look-up by id

- **WHEN** a caller reads the key `"45200007"`
- **THEN** it gets every written station with the id `45200007`, and no other station

### Requirement: A station with several ids is listed under each id

A `ref:FR:prix-carburants` value can hold several ids, separated by `;`. The run SHALL split the value at each `;`, and SHALL remove the white space around each part. It SHALL list the station under each part that is not empty.

#### Scenario: Two ids in one tag

- **WHEN** a fuel node has `ref:FR:prix-carburants=45200007; 45200008`
- **THEN** the node is in the list of the key `"45200007"` and in the list of the key `"45200008"`

### Requirement: A node is written as its position and its tags

A node SHALL be written as an object with exactly three keys: `latitude` and `longitude`, as JSON numbers, and `tags`. The position SHALL be the position of the node in the extract.

#### Scenario: A fuel node

- **WHEN** the extract has the fuel node at latitude `47.9120276` and longitude `2.7350978`, with the tags `amenity=fuel` and `ref:FR:prix-carburants=45200007`
- **THEN** the key `"45200007"` lists `{"latitude": 47.9120276, "longitude": 2.7350978, "tags": {"amenity": "fuel", "ref:FR:prix-carburants": "45200007"}}`

### Requirement: An area is written as the points of its outer ring and its tags

An area SHALL be written as an object with exactly two keys: `area` and `tags`. The `area` value SHALL be the list of the points of one outer ring, in ring order. Each point SHALL be a list `[latitude, longitude]` of two JSON numbers. The first point SHALL NOT be repeated at the end.

#### Scenario: A closed way

- **WHEN** a closed way with `amenity=fuel` and `ref:FR:prix-carburants=33560002` goes through the points `(44.9, -0.5)`, `(44.9, -0.4)`, `(45.0, -0.4)`, and back to `(44.9, -0.5)`
- **THEN** the key `"33560002"` lists `{"area": [[44.9, -0.5], [44.9, -0.4], [45.0, -0.4]], "tags": {"amenity": "fuel", "ref:FR:prix-carburants": "33560002"}}`

### Requirement: A multipolygon gives one area for each outer ring

A multipolygon relation with `amenity=fuel` and `ref:FR:prix-carburants` SHALL be written as one area for each of its outer rings. Each of these areas SHALL have all the tags of the relation, except `type`. The inner rings SHALL NOT be written.

#### Scenario: A relation with two outer rings

- **WHEN** a fuel multipolygon with `ref:FR:prix-carburants=21490003` has two outer rings
- **THEN** the key `"21490003"` lists two areas, one for each outer ring, and both have the tags of the relation except `type`

#### Scenario: A relation with an inner ring

- **WHEN** a fuel multipolygon has one outer ring and one inner ring
- **THEN** the file lists one area, and its points are the points of the outer ring

### Requirement: An object that is not a node or an area is not written

A fuel way that does not make an area, for example a way that is not closed, SHALL NOT be written.

#### Scenario: A way that is not closed

- **WHEN** a way that is not closed has `amenity=fuel` and `ref:FR:prix-carburants=45200007`
- **THEN** the file does not hold that way

### Requirement: The tags are written as in the extract

The `tags` value SHALL be a JSON object with every tag of the OSM object, and no other key. Each key and each value SHALL be the text of the extract, as a JSON string. One tag is not written: the `type` tag of a multipolygon relation, which the OSM tool drops when it makes the area.

#### Scenario: Every tag is kept

- **WHEN** a fuel node has the tags `amenity=fuel`, `brand=Total Access`, `hgv=only`, and `ref:FR:prix-carburants=45200007`
- **THEN** its `tags` value is `{"amenity": "fuel", "brand": "Total Access", "hgv": "only", "ref:FR:prix-carburants": "45200007"}`

#### Scenario: The type of a multipolygon is not kept

- **WHEN** a multipolygon relation has the tags `type=multipolygon`, `amenity=fuel`, and `ref:FR:prix-carburants=13200006`
- **THEN** the `tags` value of its area is `{"amenity": "fuel", "ref:FR:prix-carburants": "13200006"}`

### Requirement: The file is in the application cache

The run SHALL write the file to `/cache/osm_gas_stations.json`, in the `cache` volume of the application.

#### Scenario: The web service can read the file

- **WHEN** a run completes
- **THEN** the `web` and `bot` containers can read the new file at `/cache/osm_gas_stations.json`

### Requirement: Only a successful run replaces the file

A run SHALL replace the file in one step, after it has written the complete new content. When the download or the extraction fails, the run SHALL exit with a non-zero status, and the file SHALL stay unchanged. A successful run SHALL exit with the status 0.

#### Scenario: The download fails

- **GIVEN** a file from an earlier run
- **WHEN** the extract request returns the status 404
- **THEN** the run exits with a non-zero status, and the file is unchanged

#### Scenario: A reader during a run

- **WHEN** a caller reads the file while a run writes the new content
- **THEN** the caller gets the complete old file or the complete new file

#### Scenario: A successful run

- **WHEN** the download and the extraction succeed
- **THEN** the file holds the stations of the new extract, and the run exits with the status 0

### Requirement: The run removes the downloaded extract

The run SHALL delete the downloaded extract and each intermediate file before it exits. This SHALL be true when the run succeeds and when it fails.

#### Scenario: A successful run

- **WHEN** a run completes
- **THEN** the only file that the run leaves is `/cache/osm_gas_stations.json`

#### Scenario: A failed run

- **WHEN** the extraction fails after the download
- **THEN** the downloaded extract is deleted

### Requirement: The run is a one-shot Compose service

`docker-compose.yml` SHALL define the service `osm-gas-stations`, built from the application image. `docker compose run --rm osm-gas-stations` SHALL start one run, without arguments. A plain `docker compose up` SHALL NOT start it. It SHALL publish no port.

#### Scenario: The operator starts a run

- **WHEN** the operator runs `docker compose run --rm osm-gas-stations`
- **THEN** one run starts, and the command exits with the status of that run

#### Scenario: Plain compose up does not start it

- **WHEN** `docker compose up` is run
- **THEN** the `osm-gas-stations` service does not start
