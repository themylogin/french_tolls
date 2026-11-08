# Tasks

## 1. Image

- [x] 1.1 Add `osmium-tool` to the `apt-get install` list of the root `Dockerfile` (design D6). Build the image. Verify that `docker compose --profile test run --rm --no-TTY --entrypoint osmium tests --version` prints `osmium version 1.15.0`.

## 2. Extraction

- [x] 2.1 Write `french_tolls/tests/osm_gas_stations.osm`, the OSM XML fixture of design D8, with fixed ids and positions. Verify that `osmium cat` converts it to PBF in the test image without an error.
- [x] 2.2 In `french_tolls/osm_gas_stations.py`, write the conversion of design D2. It takes the lines of a GeoJSON sequence and returns the dict of lists. Add tests on feature literals:
  - a `Point` gives `latitude`, `longitude`, and `tags`;
  - a `MultiPolygon` with two polygons gives two areas, without the closing point and without the inner ring;
  - a `LineString` is skipped;
  - a feature without `amenity=fuel`, or without the id tag, is skipped;
  - the value `45200007; 45200008` lists the station under both keys;
  - the `tags` value has every property, unchanged;
  - a line that starts with `\x1e` is read.

  The tests assert literal values. Verify with `make test`.
- [x] 2.3 Write the extraction of design D1. It runs `osmium tags-filter` and `osmium export` on a PBF file in a given directory, and returns the dict of 2.2. Add a test that converts the fixture with `osmium cat`, extracts it, and compares the whole result with a literal dict. Verify with `make test`.

## 3. Run

- [x] 3.1 Write `run(url, output_path)`, steps 2 to 5 of design D5: the download of D3, the extraction, the write of D4, and the log of the counts. Add a test with a `http.server.ThreadingHTTPServer` in a thread that serves the fixture PBF. It checks that the run returns 0, the file holds the literal dict of 2.3, and the output directory holds only that file. Verify with `make test`.
- [x] 3.2 Add the failure tests. A 404 returns 1, leaves an earlier file byte for byte, and leaves no temporary file next to it. A body that is not PBF makes `osmium` fail. That run returns 1, keeps the earlier file, and leaves the scratch directory empty. Point `tempfile.tempdir` at a test directory to check this. Verify with `make test`.
- [x] 3.3 Write `main()` and the module guard. It configures logging as `gas_stations.py` does, calls `run` with the URL and path of design D5, and exits with its status. Add a test that replaces `run` and asserts the literal URL `https://download.geofabrik.de/europe/france-latest.osm.pbf` and the literal path `/cache/osm_gas_stations.json`. Verify with `make test`.

## 4. Compose service and documentation

- [x] 4.1 Add the service `osm-gas-stations` of design D7 to `docker-compose.yml`. Verify that `docker compose config --services` does not list it. Verify that `docker compose --profile osm-gas-stations config --services` lists it without `migrate`. Verify that it has no `ports`.
- [x] 4.2 Add a section "OSM gas stations" to `README.md`. Give the command `docker compose run --rm osm-gas-stations`, the path and format of the file, and the exit status. Also give the free disk space it needs, the duration, and the limit of one run each day. Verify that the command is the one that task 5.2 runs.

## 5. Integration checks

- [x] 5.1 Run `make test`. Verify that both suites pass.
- [x] 5.2 With the agreement of the operator, run `docker compose run --rm osm-gas-stations` against Geofabrik. Verify that it exits with the status 0. Verify that the counts are near 10,079 ids, 6,514 nodes, and 3,651 areas.
- [x] 5.3 Read `/cache/osm_gas_stations.json` from the `web` container. Verify that the key `"45200007"` lists a node at about `47.912`, `2.735`. Verify that `/cache` holds no temporary file from the run.
- [x] 5.4 Run `openspec validate extract-osm-gas-stations --strict`. Verify that the change is valid.

## Workflow follow-up

- Archive the change after review, with `/opsx:archive`.
