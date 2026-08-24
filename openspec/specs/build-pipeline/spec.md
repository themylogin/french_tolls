# build-pipeline Specification

## Purpose
Defines the six-step build pipeline that turns a Geofabrik extract into a toll booth inventory, a covering route set, and a priced inventory, including how the steps are invoked, when they are skipped or resumed, and how the project is laid out and configured.

## Requirements

### Requirement: All work runs in containers

Every step SHALL perform its work inside Docker containers, so that the pipeline requires no OSM, routing, or language toolchain installed on the host beyond Docker and Compose.

#### Scenario: Host has no OSM tooling

- **WHEN** the pipeline runs on a host with Docker and Compose but without osmium, pyosmium, or OSRM installed
- **THEN** every step completes successfully

### Requirement: Project layout

The repository root SHALL hold only the pipeline's entry points — `Makefile` and `docker-compose.yml` — together with configuration dotfiles such as `.gitignore` and `.env.example`. No source file SHALL sit at the root.

The container image definition and all pipeline scripts SHALL live under `builder/`. Generated artifacts SHALL live under `data/`.

The artifacts the pipeline is asked to produce — the booth inventory, the route set, and the gare mapping — SHALL be committed, so a consumer can read them without running the pipeline. Regenerable intermediates, OSM extracts, and the per-run diagnostic reports SHALL NOT be committed.

The exclusion report and the uncovered report SHALL still be produced on every run: they describe what one run of the pipeline decided, and the gare mapping step reads the exclusion report to name the nearest excluded booth when a placemark matches nothing. They are diagnostics about a run rather than published outputs, so they are not carried in the repository.

#### Scenario: Scripts are located together

- **WHEN** the repository is inspected
- **THEN** the Dockerfile and the pipeline scripts are under `builder/`, and no pipeline script sits at the repository root

#### Scenario: Root holds only entry points and configuration

- **WHEN** the tracked files at the repository root are listed
- **THEN** they are `Makefile`, `docker-compose.yml`, and configuration dotfiles, and nothing else

#### Scenario: Deliverables are committed

- **WHEN** the repository is checked out without running the pipeline
- **THEN** the booth inventory, the route set, and the gare mapping are present under `data/`

#### Scenario: Reports are produced but not committed

- **WHEN** the pipeline has run
- **THEN** the exclusion report and the uncovered report exist under `data/` and are untracked

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

### Requirement: Six named build steps

The pipeline SHALL expose exactly six named steps — `download_pbf`, `setup_osrm`, `build_osm_toll_booths`, `build_route_set`, `build_vinci_toll_booths`, and `build_vinci_prices` — each individually invocable, and SHALL provide an `all` target that runs them in that order.

#### Scenario: Running the whole pipeline

- **WHEN** `make all` is run in a clean checkout
- **THEN** the six steps execute in the order `download_pbf`, `setup_osrm`, `build_osm_toll_booths`, `build_route_set`, `build_vinci_toll_booths`, `build_vinci_prices`

#### Scenario: Running a single step

- **WHEN** `make build_osm_toll_booths` is run
- **THEN** that step runs, along with any earlier step whose output is missing

#### Scenario: Running the gare mapping step alone

- **WHEN** `make build_vinci_toll_booths` is run
- **THEN** that step runs, along with any earlier step whose output is missing

#### Scenario: Running the pricing step alone

- **WHEN** `make build_vinci_prices` is run
- **THEN** that step runs, along with any earlier step whose output is missing

### Requirement: Steps do not repeat completed work

No step SHALL repeat work it has already completed. A step SHALL establish that in one of two ways.

A **checkpointed** step SHALL be skipped when its output is already in place. Skipping SHALL depend on the existence of the output, not on modification times, so that refreshing an earlier step's output does not silently invalidate a later step's expensive work. A checkpointed step that fails partway SHALL leave no completion marker, and the next run SHALL re-execute it from the beginning.

A **resumable** step SHALL always execute, and SHALL read its own output to determine what remains. Such a step SHALL record each unit of work only once that unit is complete, so an interrupted run repeats at most one unit. A resumable step SHALL perform no work and SHALL contact no external service when its output is already complete.

A step SHALL be resumable only when its work divides into units that are individually cheap to repeat and expensive to lose. `build_vinci_toll_booths` and `build_vinci_prices` are resumable; every other step is checkpointed.

#### Scenario: Re-running a completed pipeline

- **WHEN** `make all` is run a second time with every output already present and complete
- **THEN** no step performs work again, and no request is issued to any external service

#### Scenario: Earlier output is touched

- **WHEN** the downloaded extract's modification time becomes newer than the OSRM graph
- **THEN** the OSRM preprocessing step is still skipped

#### Scenario: A single output is deleted

- **WHEN** `data/route_set.yaml` is deleted and `make all` is run
- **THEN** the route set step re-executes, and no earlier step does

#### Scenario: A step fails midway

- **WHEN** a checkpointed step fails partway through
- **THEN** its completion marker is not written, and the next run re-executes that step from the beginning

#### Scenario: A resumable step fails midway

- **WHEN** `build_vinci_toll_booths` fails partway through
- **THEN** the next run continues from the work its output already records, rather than starting over

#### Scenario: A resumable step with a complete output

- **WHEN** `make all` is run and `data/vinci_toll_booth.yaml` already covers every route
- **THEN** the step executes, finds nothing outstanding, and finishes without issuing a request

#### Scenario: The pricing step resumes

- **WHEN** `build_vinci_prices` fails partway through
- **THEN** the next run submits only the routes its output does not already record

### Requirement: The gare service subscription key is configured via .env

The subscription key for the toll operator's placemark service SHALL be read from an `.env` file as `ULYS_SUBSCRIPTION_KEY` and SHALL be passed into the builder container through the Compose service's `environment` declaration. Exporting the variable on the host is not sufficient on its own: a container receives only the variables Compose declares for it.

The key SHALL NOT be committed. `.env.example` SHALL name the variable without a value.

The pipeline SHALL fail with a clear message naming the missing variable when `ULYS_SUBSCRIPTION_KEY` is unset, before the step issues any request and before it does any routing work.

#### Scenario: Configured key reaches the container

- **WHEN** `.env` sets `ULYS_SUBSCRIPTION_KEY` and the gare mapping step runs
- **THEN** the value is visible inside the builder container and authenticates its requests

#### Scenario: Key is not configured

- **WHEN** `ULYS_SUBSCRIPTION_KEY` is unset or empty and the gare mapping step is run
- **THEN** the pipeline stops with a message naming the missing variable, before any request is issued

#### Scenario: Key is not in version control

- **WHEN** the tracked files are inspected
- **THEN** no subscription key value appears in them, and `.env.example` names the variable with no value

### Requirement: Two steps require network access at run time

The gare mapping step and the pricing step SHALL be the only steps other than `download_pbf` that require network access. Every other step SHALL continue to run offline once the extract is present.

The pricing step SHALL NOT require the routing service. It derives its input from `data/route_set.yaml` and `data/vinci_toll_booth.yaml`, so it runs with the OSRM graph absent.

#### Scenario: Offline run of the derivation steps

- **WHEN** `build_osm_toll_booths` and `build_route_set` are run with the extract and the graph present and no network available
- **THEN** both complete successfully

#### Scenario: Gare mapping without network

- **WHEN** `build_vinci_toll_booths` is run with outstanding routes and no network available
- **THEN** it fails with a message naming the unreachable service, and leaves its output valid for a later resume

#### Scenario: Pricing without network

- **WHEN** `build_vinci_prices` is run with outstanding routes and no network available
- **THEN** it fails with a message naming the unreachable service, and leaves its output valid for a later resume

#### Scenario: Pricing without the routing service

- **WHEN** `build_vinci_prices` is run with outstanding routes and the OSRM instance stopped
- **THEN** it completes normally

### Requirement: The tariff date is configured via .env

The timestamp submitted with every toll passage SHALL be read from an `.env` file as `ULYS_PASSAGE_DATE` and SHALL be passed into the builder container through the Compose service's `environment` declaration.

`.env.example` SHALL name the variable with a value, since it is a configuration choice rather than a secret.

The pipeline SHALL fail with a clear message naming the missing variable when `ULYS_PASSAGE_DATE` is unset or empty, before the pricing step issues any request.

#### Scenario: Configured date reaches the container

- **WHEN** `.env` sets `ULYS_PASSAGE_DATE` and the pricing step runs
- **THEN** the value is visible inside the builder container and appears on every submitted passage

#### Scenario: Date is not configured

- **WHEN** `ULYS_PASSAGE_DATE` is unset or empty and the pricing step is run
- **THEN** the pipeline stops with a message naming the missing variable, before any request is issued
