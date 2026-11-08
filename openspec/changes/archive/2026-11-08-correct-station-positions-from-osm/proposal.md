# Proposal

## Why

`gas-stations` stores the position of the prix-carburants list. That position is often coarse: 6,395 of 9,357 stations have three decimals or fewer. It is sometimes wrong: 1,459 stations are more than 250 m from their OpenStreetMap object, and 372 are more than 1 km away, up to 14.6 km. `refuel-planning` sends drivers to these positions. `osm-gas-stations` now writes the OpenStreetMap stations by prix-carburants id, so the run can take a better position from it.

## What Changes

- When `gas-stations` refreshes a station, it looks up the station id in `/cache/osm_gas_stations.json`. It stores the position of the matched OSM station in place of the list position.
- The matching rules, from a study of the data of 2026-11-08:
  1. The candidates are the OSM stations listed under the station id.
  2. The position of a node is its position. The position of an area is the centroid of its ring.
  3. A candidate more than 20 km from the list position is dropped.
  4. When several candidates are left, the run prefers those whose `brand`, `name`, or `operator` contains the first word of the station brand. The comparison ignores case and accents.
  5. The run takes the candidate nearest to the list position.
  6. When no candidate is left, the run stores the list position, as now.
- When the OSM file is missing or cannot be read, the run logs a warning and stores the list positions. The price refresh does not fail.
- The run logs how many refreshed stations got an OSM position.
- `README.md` says to run `osm-gas-stations` before `gas-stations`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `gas-station-inventory`: the requirement "The open station list defines the stations a run reads" says that the stored position is the list position. It changes so that a matched OSM station gives the position. New requirements state the matching rules and the fallback without the OSM file.

## Impact

- Changed files: `french_tolls/gas_stations.py`, `french_tolls/tests/test_gas_stations.py`, `README.md`.
- Data: on the data of 2026-11-08, 9,334 of 9,357 stations get an OSM position. The median move is 53 m, and 4% of the stations move more than 1 km.
- Dependencies: none new. The centroid uses `shapely`, and the distance uses `pyproj`. Both are already dependencies.
- Unchanged: the schema, the list read, the page parser, the selection of stale stations, and `osm-gas-stations`.
- Not in scope:
  - matching an OSM station that has no `ref:FR:prix-carburants`, for example by distance. 23 stations have no OSM object with their id;
  - a new position for a fresh station that the run does not refresh;
  - storing the list position or the source of the position;
  - correcting OSM. The study lists the OSM objects with a copied id, but this change does not edit OSM.
