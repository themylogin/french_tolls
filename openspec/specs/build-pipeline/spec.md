# build-pipeline Specification

## Purpose
Defines the four-step build pipeline that turns a Geofabrik extract into a toll booth inventory and a covering route set, including how the steps are invoked, when they are skipped, and how the project is laid out and configured.

## Requirements

### Requirement: Four named build steps

The pipeline SHALL expose exactly four named steps — `download_pbf`, `setup_osrm`, `build_osm_toll_booths`, and `build_route_set` — each individually invocable, and SHALL provide an `all` target that runs them in that order.

#### Scenario: Running the whole pipeline

- **WHEN** `make all` is run in a clean checkout
- **THEN** the four steps execute in the order `download_pbf`, `setup_osrm`, `build_osm_toll_booths`, `build_route_set`

#### Scenario: Running a single step

- **WHEN** `make build_osm_toll_booths` is run
- **THEN** that step runs, along with any earlier step whose output is missing

### Requirement: Steps are skipped once their output exists

Each step SHALL be skipped when its output is already in place. Skipping SHALL depend on the existence of the output, not on modification times, so that refreshing an earlier step's output does not silently invalidate a later step's expensive work.

#### Scenario: Re-running a completed pipeline

- **WHEN** `make all` is run a second time with every output already present
- **THEN** no step re-executes its work

#### Scenario: Earlier output is touched

- **WHEN** the downloaded extract's modification time becomes newer than the OSRM graph
- **THEN** the OSRM preprocessing step is still skipped

#### Scenario: A single output is deleted

- **WHEN** `data/route_set.yaml` is deleted and `make all` is run
- **THEN** only the route set step re-executes

#### Scenario: A step fails midway

- **WHEN** a step fails partway through
- **THEN** its completion marker is not written, and the next run re-executes that step from the beginning

### Requirement: All work runs in containers

Every step SHALL perform its work inside Docker containers, so that the pipeline requires no OSM, routing, or language toolchain installed on the host beyond Docker and Compose.

#### Scenario: Host has no OSM tooling

- **WHEN** the pipeline runs on a host with Docker and Compose but without osmium, pyosmium, or OSRM installed
- **THEN** every step completes successfully

### Requirement: Project layout

The repository root SHALL hold only the pipeline's entry points — `Makefile` and `docker-compose.yml` — together with configuration dotfiles such as `.gitignore` and `.env.example`. No source file SHALL sit at the root.

The container image definition and all pipeline scripts SHALL live under `builder/`. Generated artifacts SHALL live under `data/`.

The artifacts the pipeline is asked to produce SHALL be committed, so a consumer can read them without running the pipeline. Regenerable intermediates and OSM extracts SHALL NOT be committed.

#### Scenario: Scripts are located together

- **WHEN** the repository is inspected
- **THEN** the Dockerfile and the pipeline scripts are under `builder/`, and no pipeline script sits at the repository root

#### Scenario: Root holds only entry points and configuration

- **WHEN** the tracked files at the repository root are listed
- **THEN** they are `Makefile`, `docker-compose.yml`, and configuration dotfiles, and nothing else

#### Scenario: Deliverables are committed

- **WHEN** the repository is checked out without running the pipeline
- **THEN** the booth inventory, the route set, and the coverage reports are present under `data/`

#### Scenario: Extracts and intermediates are not committed

- **WHEN** the pipeline has run
- **THEN** the OSM extracts and the regenerable intermediates it produced are untracked

### Requirement: OSRM data location is configured via .env

The location of the OSRM graph SHALL be read from an `.env` file as `OSRM_OPTIMAL_PATH` and SHALL be mounted into the OSRM containers. `./data` SHALL be mounted alongside it. The pipeline SHALL fail with a clear message when `OSRM_OPTIMAL_PATH` is unset rather than operating on an unintended path.

Where that directory lives is deliberately unconstrained: it is local configuration, and the graph is excluded from version control wherever it sits.

#### Scenario: Configured path is used

- **WHEN** `.env` sets `OSRM_OPTIMAL_PATH` to a directory
- **THEN** the OSRM graph files are produced in that directory

#### Scenario: Path is not configured

- **WHEN** `OSRM_OPTIMAL_PATH` is unset or empty and any step needing it is run
- **THEN** the pipeline stops with a message naming the missing variable

### Requirement: The extract is not duplicated permanently

The downloaded extract SHALL be retained under `data/`. The copy placed alongside the OSRM graph for preprocessing SHALL be removed once preprocessing is complete, so the extract is duplicated only for the duration of that step.

#### Scenario: Copy is released after preprocessing

- **WHEN** the OSRM preprocessing step completes successfully
- **THEN** no `.osm.pbf` file remains under `OSRM_OPTIMAL_PATH`, while `data/france-latest.osm.pbf` is still present

#### Scenario: Stale copy from a failed run

- **WHEN** a previous preprocessing run failed and left a partial extract copy behind
- **THEN** the next run replaces that copy rather than treating it as usable input

### Requirement: Named routing service

The pipeline SHALL define a long-running OSRM query service named `osrm-optimal`, addressable under that name both as a container and on the Compose network, serving the graph from `OSRM_OPTIMAL_PATH`. One-shot preprocessing containers SHALL NOT be started by a plain `docker compose up`.

#### Scenario: Service is addressable by name

- **WHEN** the route set step issues routing requests
- **THEN** it reaches the query service at the host name `osrm-optimal`

#### Scenario: Plain compose up

- **WHEN** `docker compose up` is run
- **THEN** the query service starts and the one-shot preprocessing containers do not
