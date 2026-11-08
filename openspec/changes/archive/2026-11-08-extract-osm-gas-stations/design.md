# Design

## Context

See `proposal.md` for the reason. The current state that shapes the approach:

- **Image.** The root `Dockerfile` uses `debian:bookworm-slim` and Python 3.11. It has no OSM tool. The `builder` image has `osmium-tool` 1.15 and `python3-pyosmium`, but it holds only the build pipeline scripts.
- **Cache.** The Compose volume `cache` is mounted at `/cache` in `web`, `bot`, and `gas-stations`. It holds `database.db` and `errors/`.
- **Host.** The host has 5 GB of RAM and 4 cores.
- **Extract, observed on 2026-11-08.**
  - `france-latest.osm.pbf` of Geofabrik is 5.1 GB. It downloaded on this host in about 3 minutes.
  - `osmium tags-filter france-latest.osm.pbf nwr/amenity=fuel` took 1 min 38 s, and wrote 0.9 MB.
  - `osmium export -f geojsonseq` on that result writes each area as a `MultiPolygon`, also for a closed way.
  - The export keeps every tag of the 12,212 fuel objects, except the `type` tag of the 9 relations. `osmium-tool` 1.15 has no option to keep it.
  - 10,158 fuel objects carry `ref:FR:prix-carburants`: 6,514 nodes, 3,635 ways, and 9 multipolygon relations. Every way is closed. Six relations have two or three outer rings. No value holds a `;`.
  - The file in the format of the spec has 10,079 ids, 6,514 nodes, and 3,651 areas. It is 6.3 MB.

## Goals / Non-Goals

**Goals:**

- The run needs no more memory than the host has.
- No geometry code in the project. The OSM tool assembles the areas.
- A failed run leaves the cache as it was.
- A test runs the real tool on a small extract, and needs no network.

**Non-Goals:**

- Scheduling. The operator runs the command, or puts it in cron.
- A partial update. Each run writes the whole file again.
- A reader of the file in the application.

## Decisions

### D1. `osmium-tool` filters the extract, then exports the result

The run calls two commands:

```
osmium tags-filter <extract> nwr/amenity=fuel -o <tmp>/fuel.osm.pbf
osmium export <tmp>/fuel.osm.pbf -f geojsonseq --geometry-types=point,polygon -o <tmp>/fuel.geojsonseq
```

`tags-filter` reads the extract two times. The second pass adds the nodes of the fuel ways and the members of the fuel relations, so the small file is complete. `export` then makes a point for each tagged node, and a `MultiPolygon` for each closed way and multipolygon relation. `--geometry-types=point,polygon` drops the line strings. So a way that is not closed is not written.

Alternatives:

- **pyosmium in one pass with node locations.** A way needs the position of each of its nodes. For all of France, that index is larger than the 5 GB of the host.
- **pyosmium in three passes with id filters.** It finds the relations, then their ways, then the nodes. It needs more code, and its own multipolygon assembly.
- **`osmium export` on the full extract.** It assembles every area of France. That costs much more time and memory than the filter first.

### D2. Python converts the exported features

The module reads `fuel.geojsonseq` line by line. It removes the record separator `\x1e` at the start of each line, then parses the JSON. The properties of a feature are its tags.

For each feature with `amenity=fuel` and `ref:FR:prix-carburants`:

- a `Point` `[lon, lat]` gives `{"latitude": lat, "longitude": lon, "tags": tags}`;
- a `MultiPolygon` gives one `{"area": ..., "tags": tags}` for each polygon. The area is the first ring of the polygon, which is the outer ring, without its last point. Each `[lon, lat]` becomes `[lat, lon]`;
- another geometry is skipped.

An area from a relation has no `type` tag, because the export drops it. The run does not add it again. The value is not in the export, and `type` gives no fact about the station.

The ids are the parts of the tag value split at `;`, each without white space. Empty parts are skipped. The result is a `dict` of lists, and `json.dump` writes it with `ensure_ascii=False`, without indentation.

The positions are the numbers of the export, which has seven decimals. `json` writes the shortest form of each float, so `47.9120276` stays `47.9120276`.

### D3. The download goes to a temporary directory in the container

The run creates a `tempfile.TemporaryDirectory()`. It streams the response of `urllib.request.urlopen` into `france-latest.osm.pbf` there, with `shutil.copyfileobj`. The timeout is 60 s for each socket operation. The intermediate files of D1 are in the same directory. The directory is deleted when the run leaves it, also after an error.

The directory is in the writable layer of the container. When the container is killed, `docker compose run --rm` removes that layer, and the extract with it.

Alternatives:

- **The `cache` volume.** It keeps 5.1 GB after a killed run, and the volume is not for scratch data.
- **`aiohttp`.** The run makes one request and no other work at the same time. The standard library is simpler for one stream.
- **A stream into `osmium` without a file.** `tags-filter` must read the input two times (D1), so it needs a file.

### D4. The new file replaces the old file in one rename

The run writes the JSON to a temporary file in `/cache`, with `tempfile.NamedTemporaryFile(dir=..., delete=False)`. Then it calls `os.replace` to the final name. The rename is atomic because both names are on the same file system. When the write fails, the run deletes the temporary file.

### D5. One run, step by step

1. Configure logging from `config.log_level`, as `gas_stations.py` does.
2. Download the extract (D3).
3. Run the two commands of D1, with `subprocess.run(..., check=True)`.
4. Convert the features (D2), and write the file (D4).
5. Log the counts: ids, nodes, and areas. Exit with the status 0.

The run catches `urllib.error.URLError`, `OSError`, and `subprocess.CalledProcessError`. It logs the error and exits with the status 1. `HTTPError` is a `URLError`, so a 404 is caught too.

The extract URL and the output path are parameters of the run function. `main` gives `https://download.geofabrik.de/europe/france-latest.osm.pbf` and `/cache/osm_gas_stations.json`. The tests give the URL of a local HTTP server and a path in a temporary directory.

### D6. The application image gets `osmium-tool`

The `Dockerfile` adds `osmium-tool` to its `apt-get install` list. It installs three packages, about 5 MB.

Alternatives:

- **A service built from `builder/`.** That image has the tool. But the module then lives outside `french_tolls/`, and the `tests` service does not see it. The `builder` image is also for the build pipeline only.
- **The `osmium` package of PyPI.** It gives pyosmium only, not the command line tool. See D1 for why pyosmium alone does not fit.

### D7. The Compose service has no dependency

```yaml
osm-gas-stations:
  build: .
  entrypoint: ["python3", "-m", "french_tolls.osm_gas_stations"]
  volumes:
    - "cache:/cache"
  environment:
    LOG_LEVEL: "${LOG_LEVEL:-INFO}"
  profiles: ["osm-gas-stations"]
```

The run does not open the database, so it does not wait for `migrate`. It needs no key, so it has no `env_file`. The `entrypoint` has the same form as in `gas-stations`.

### D8. The test fixture is OSM XML

`french_tolls/tests/osm_gas_stations.osm` is a small OSM XML file. It holds one case for each scenario of the spec:

- a fuel node with an id;
- a fuel node without an id;
- a charging station with an id;
- a fuel node with two ids;
- a closed fuel way that shares its id with a fuel node;
- a fuel way that is not closed;
- a fuel multipolygon with two outer rings;
- a fuel multipolygon with one outer ring and one inner ring.

The test converts it to PBF with `osmium cat`, and serves the PBF from a local HTTP server. The run then uses the real download code and the real tool. The fixture stays readable in a diff.

## Risks / Trade-offs

- [Geofabrik is not available.] → The run exits with the status 1, and the old file stays. The operator runs it again later.
- [Each run downloads 5.1 GB.] → Geofabrik makes a new extract once a day. The README says to run the command once a day at most.
- [The disk of the Docker root has less than 5.2 GB free.] → The write fails with an `OSError`. The run exits with the status 1, and deletes the partial download.
- [A broken multipolygon in OSM.] → `osmium export` does not make an area for it, so the relation is not written. On 2026-11-08, all 9 fuel relations made areas.
- [A copied tag set.] → Some OSM objects carry the id and the `fuel:*` tags of another station. The file keeps the tags as they are. A caller must not trust them more than OSM does.
- [The application image grows.] → The tool and its libraries add about 5 MB to the image of `web` and `bot`.

## Migration Plan

1. Build the image. Run `docker compose run --rm osm-gas-stations`. The run creates `/cache/osm_gas_stations.json`.
2. To refresh each day, the operator adds the same command to cron.

Rollback: delete the service from `docker-compose.yml` and `osmium-tool` from the `Dockerfile`. Then run `docker compose run --rm --entrypoint rm web /cache/osm_gas_stations.json`. No other data changes.
