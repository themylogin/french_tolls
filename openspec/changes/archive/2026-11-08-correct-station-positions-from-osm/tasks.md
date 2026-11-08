# Tasks

## 1. Choice of the position

- [x] 1.1 Write `osm_position(candidates, brand, listed)` in `french_tolls/gas_stations.py`, with the steps of design D2. Add tests that call it without a server, and assert literal values:
  - a node gives its position;
  - the area `[48.2, -3.82]`, `[48.2, -3.81]`, `[48.21, -3.81]`, `[48.21, -3.82]` gives `48.205`, `-3.815` (use `pytest.approx`);
  - no candidate gives `None`;
  - a single candidate 25 km away gives `None`, and one 15 km away gives its position;
  - with the brand `Leclerc`, a `PETRO-EST` node 250 m away loses to a `Station Service E. Leclerc` area 460 m away;
  - with the brand `Intermarché Contact`, a node with `brand=INTERMARCHE` 300 m away wins over a node with `brand=Total` 100 m away;
  - with the brand `Système U`, nodes with `brand=Super U` and `brand=Hyper U` give the nearest one;
  - with a null brand, two candidates 100 m and 300 m away give the one 100 m away.

  Verify with `make test`.

## 2. Run

- [x] 2.1 Add the parameter `osm_path="/cache/osm_gas_stations.json"` to `update`, and load the file as design D1 says. Change `LocalSource` in `french_tolls/tests/test_gas_stations.py` so that it takes the OSM stations as a dict, writes them to a file in a temporary directory, and gives that path. Without OSM stations, it gives a path that does not exist. Add tests: a missing file, the content `not json`, and the content `[]` each log a warning (use `caplog`), store the list positions, and return 0. Verify with `make test`, and that every existing test still passes.
- [x] 2.2 Make `_refresh` store the result of `osm_position`, or the list position on `None`. It gets the station name from the parsed page. Add the counts of design D6 to the final log line. Add tests through `LocalSource`:
  - station `29520005` with an OSM node at `48.2095`, `-3.8172` is stored there, and `stations_in_area` around the node finds it;
  - a station without OSM stations under its id gets its list position;
  - a run of three stations, two of them with a candidate, logs `2` OSM positions and `1` list position.

  Verify with `make test`.

## 3. Documentation

- [x] 3.1 Change the section "Gas stations" of `README.md`. Say that the run takes the position of the matched OSM station from `/cache/osm_gas_stations.json` when it exists, and the list position otherwise. Give the order of the two commands for cron: `osm-gas-stations`, then `gas-stations PT23H`. Verify that the commands are the ones that task 4.2 runs.

## 4. Integration checks

- [x] 4.1 Run `make test`. Verify that both suites pass.
- [x] 4.2 With the agreement of the operator, run `docker compose run --rm gas-stations PT23H` after `osm-gas-stations` has written the file. Verify that the final log line gives about 9,300 OSM positions, and fewer than 100 list positions.
- [x] 4.3 Read the store. Verify these stations:
  - `78680002` (Épône) is near `48.9566`, `1.8241`, not at the list position `48.979`, `1.955`;
  - `45200007` is at `47.9120276`, `2.7350978`;
  - `51500002` is at the centroid of the Leclerc area, not at the PETRO-EST node;
  - `26700001` is at the Carrefour Market node.
- [x] 4.4 Run `openspec validate correct-station-positions-from-osm --strict`. Verify that the change is valid.

## Workflow follow-up

- Archive the change after review, with `/opsx:archive`.
