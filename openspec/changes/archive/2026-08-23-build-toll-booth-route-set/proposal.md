## Why

We need to know, for every toll booth in France, a concrete drivable trip that passes through it — so that downstream tooling can exercise real toll-charging behaviour against the whole national network rather than a hand-picked sample. Today nothing in this repository produces either the booth inventory or such a trip set.

The natural formulation is a set-cover problem: find a small collection of point-to-point routes whose union of traversed toll booths equals the full booth inventory. "Small" matters because every downstream consumer pays per route; "complete" matters because an uncovered booth is a silent blind spot.

## What Changes

- Add a four-step, `make`-driven build pipeline that runs entirely in Docker, with each step skipped when its output is already in place:
  - `download_pbf` — fetch `france-latest.osm.pbf` from Geofabrik into `./data`.
  - `setup_osrm` — copy the PBF into `$OSRM_OPTIMAL_PATH`, run `osrm-extract` / `osrm-partition` / `osrm-customize` (MLD) there, then unlink the copy.
  - `build_osm_toll_booths` — produce `data/osm_toll_booths.yaml`: every node tagged `barrier=toll_booth` or `highway=toll_gantry`, with the parallel lanes of a single plaza grouped under one representative id and the rest recorded as aliases.
  - `build_route_set` — produce `data/route_set.yaml`: a list of `{from, to, covers}` routes between eligible `place` nodes whose union of traversed booths covers the inventory, alongside a `places` list resolving every referenced endpoint to its name and coordinates so the file stands on its own.
- `make all` runs the four steps in sequence.
- Add a `builder/` image (Dockerfile plus the extraction and route-set scripts) and a root `docker-compose.yml` defining an `osrm-optimal` MLD query server plus a one-shot `osrm-tools` container, with volume paths read from `.env` (`OSRM_OPTIMAL_PATH`) and `./data` mounted alongside.
- Report incomplete coverage explicitly: any booth that no generated route traverses is written to `data/uncovered_booths.json` and summarised on stdout, so a partial result can never be mistaken for a complete one.

## Capabilities

### New Capabilities

- `toll-booth-inventory`: extracting the set of French toll booths and the candidate place nodes from an OSM PBF extract, and the on-disk format of the booth inventory.
- `route-set-generation`: producing a small set of point-to-point routes that collectively traverse every toll booth, the coverage semantics of `route_set.yaml`, and the reporting contract when coverage is incomplete.
- `build-pipeline`: the four-step Makefile pipeline, its Docker/Compose topology, and its skip-when-already-built semantics.

### Modified Capabilities

None — this is the repository's first change.

## Impact

- **New files**: `Makefile`, `docker-compose.yml`, `.env` (git-ignored) and its example, `builder/Dockerfile`, `builder/build_osm_toll_booths.py`, `builder/build_route_set.py`, `builder/booth_groups.py`.
- **New outputs**: `data/france-latest.osm.pbf`, `data/osm_toll_booths.yaml`, `data/route_set.yaml`, `data/uncovered_booths.json`, plus a retained filtered PBF and a carved plaza-neighbourhood extract as internal hand-offs.
- **External dependencies**: Docker and Compose; `ghcr.io/project-osrm/osrm-backend:26.8-debian`; Geofabrik downloads; `osmium-tool` and `pyosmium` inside the builder image.
- **Resources**: roughly 30 GB peak under `$OSRM_OPTIMAL_PATH` (settling to ~25 GB) plus ~4.7 GB in `./data`; OSRM preprocessing dominates wall-clock at roughly 30–60 minutes, while the route search itself is minutes.
- **Consumers**: `route_set.yaml` is only reproducible against an OSRM instance built the same way — same extract, same `car` profile, same MLD algorithm, no traffic file. Future scripts must query the `osrm-optimal` instance.
