# Proposal

## Why

The `gas_station` table has the prix-carburants position of each station. On 2026-11-08, 8.5% of these positions were more than 250 m from the station, and some were 5 to 15 km off. OpenStreetMap has 10,158 fuel stations that carry the prix-carburants id in `ref:FR:prix-carburants`, often with a better position. The application needs these stations in a form that it can look up by id.

## What Changes

- A new module, `french_tolls/osm_gas_stations.py`, does one run:
  - it downloads the most recent France extract from `https://download.geofabrik.de/europe/france-latest.osm.pbf` into a temporary directory;
  - it extracts each OSM object with `amenity=fuel` and `ref:FR:prix-carburants`;
  - it writes `/cache/osm_gas_stations.json`, which maps each id to the list of OSM stations with that id;
  - it removes the downloaded extract.
- A node is written as its `latitude` and `longitude`. An area is written as `area`, the list of `[latitude, longitude]` points of its outer ring. Both carry `tags`, all OSM tags of the object. Example:

  ```json
  {"45200007": [{"latitude": 47.9120276, "longitude": 2.7350978, "tags": {"amenity": "fuel", "name": "Total Access", "ref:FR:prix-carburants": "45200007"}}]}
  ```

- A new Compose service, `osm-gas-stations`, runs the module. The operator starts it with `docker compose run --rm osm-gas-stations`.
- The application image gets the Debian package `osmium-tool`.

## Capabilities

### New Capabilities

- `osm-gas-stations`: which OSM fuel stations the project extracts, the shape of the JSON file that holds them by prix-carburants id, how a run gets the extract and replaces the file, and how the operator starts a run.

### Modified Capabilities

None. The new file is not a table, so `runtime-store` does not change. The run does not read or write `gas_station`, so `gas-station-inventory` does not change.

## Impact

- New files: `french_tolls/osm_gas_stations.py`, `french_tolls/tests/test_osm_gas_stations.py`, and a small OSM XML fixture under `french_tolls/tests/`.
- Changed files: `Dockerfile`, `docker-compose.yml`, `README.md`.
- External load: one download of about 5.1 GB from Geofabrik for each run.
- Disk: the run needs about 5.2 GB of free space for the temporary extract. It keeps about 6.3 MB in the `cache` volume.
- Unchanged: the web service, the bot, the store, and the build pipeline. No current caller reads the new file.
- Not in scope:
  - matching OSM stations to the `gas_station` rows, or correcting their positions;
  - removing truck, CNG, or boat pumps. The tags are written, so a caller can filter them;
  - OSM fuel stations without `ref:FR:prix-carburants`;
  - reusing `data/france-latest.osm.pbf` of the build pipeline.
