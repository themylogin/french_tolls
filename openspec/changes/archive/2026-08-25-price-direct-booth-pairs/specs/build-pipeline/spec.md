## RENAMED Requirements

- FROM: `### Requirement: Six named build steps`
- TO: `### Requirement: Seven named build steps`

- FROM: `### Requirement: Two steps require network access at run time`
- TO: `### Requirement: Three steps require network access at run time`

## MODIFIED Requirements

### Requirement: Seven named build steps

The pipeline SHALL expose exactly seven named steps — `download_pbf`, `setup_osrm`, `build_osm_toll_booths`, `build_route_set`, `build_vinci_toll_booths`, `build_vinci_prices`, and `build_vinci_direct_prices` — each individually invocable, and SHALL provide an `all` target that runs them in that order.

The seventh step SHALL run after the sixth. It takes its source and target booths from the price file the sixth step produces, so a run against an empty or partial price file would enumerate an empty or partial grid.

#### Scenario: Running the whole pipeline

- **WHEN** `make all` is run in a clean checkout
- **THEN** the seven steps execute in the order `download_pbf`, `setup_osrm`, `build_osm_toll_booths`, `build_route_set`, `build_vinci_toll_booths`, `build_vinci_prices`, `build_vinci_direct_prices`

#### Scenario: Running a single step

- **WHEN** `make build_osm_toll_booths` is run
- **THEN** that step runs, along with any earlier step whose output is missing

#### Scenario: Running the gare mapping step alone

- **WHEN** `make build_vinci_toll_booths` is run
- **THEN** that step runs, along with any earlier step whose output is missing

#### Scenario: Running the pricing step alone

- **WHEN** `make build_vinci_prices` is run
- **THEN** that step runs, along with any earlier step whose output is missing

#### Scenario: Running the direct pricing step alone

- **WHEN** `make build_vinci_direct_prices` is run
- **THEN** that step runs, along with any earlier step whose output is missing

### Requirement: Steps do not repeat completed work

No step SHALL repeat work it has already completed. A step SHALL establish that in one of two ways.

A **checkpointed** step SHALL be skipped when its output is already in place. Skipping SHALL depend on the existence of the output, not on modification times, so that refreshing an earlier step's output does not silently invalidate a later step's expensive work. A checkpointed step that fails partway SHALL leave no completion marker, and the next run SHALL re-execute it from the beginning.

A **resumable** step SHALL always execute, and SHALL read its own output to determine what remains. Such a step SHALL record each unit of work only once that unit is complete, so an interrupted run repeats at most one unit. A resumable step SHALL perform no work and SHALL contact no external service when its output is already complete.

A step SHALL be resumable only when its work divides into units that are individually cheap to repeat and expensive to lose. `build_vinci_toll_booths`, `build_vinci_prices`, and `build_vinci_direct_prices` are resumable; every other step is checkpointed.

`build_vinci_direct_prices` SHALL read two outputs to determine what remains — the price file for the pairs it has priced, and the rejection database for the pairs it has ruled out. Its unit of work is one pair, and it repeats at most 25 of them.

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

#### Scenario: The direct pricing step resumes

- **WHEN** `build_vinci_direct_prices` fails partway through
- **THEN** the next run routes only the pairs its price file and its rejection database do not already record

### Requirement: Three steps require network access at run time

The gare mapping step, the pricing step, and the direct pricing step SHALL be the only steps other than `download_pbf` that require network access. Every other step SHALL continue to run offline once the extract is present.

The pricing step SHALL NOT require the routing service. It derives its input from `data/route_set.yaml` and `data/vinci_toll_booth.yaml`, so it runs with the OSRM graph absent.

The direct pricing step SHALL require the routing service as well as the network. It decides which pairs are askable by routing between booths, so it cannot proceed with the OSRM graph absent.

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

#### Scenario: Direct pricing without network

- **WHEN** `build_vinci_direct_prices` is run with outstanding pairs and no network available
- **THEN** it fails with a message naming the unreachable service, and leaves both its outputs valid for a later resume

#### Scenario: Direct pricing without the routing service

- **WHEN** `build_vinci_direct_prices` is run with outstanding pairs and the OSRM instance stopped
- **THEN** it fails with a message naming the unreachable routing service, before any rate request is issued

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

#### Scenario: Key is not configured for direct pricing

- **WHEN** `ULYS_SUBSCRIPTION_KEY` is unset or empty and `build_vinci_direct_prices` is run
- **THEN** the pipeline stops with a message naming the missing variable, before any pair is routed

#### Scenario: Key is not in version control

- **WHEN** the tracked files are inspected
- **THEN** no subscription key value appears in them, and `.env.example` names the variable with no value

### Requirement: The tariff date is configured via .env

The timestamp submitted with every toll passage SHALL be read from an `.env` file as `ULYS_PASSAGE_DATE` and SHALL be passed into the builder container through the Compose service's `environment` declaration.

`.env.example` SHALL name the variable with a value, since it is a configuration choice rather than a secret.

The pipeline SHALL fail with a clear message naming the missing variable when `ULYS_PASSAGE_DATE` is unset or empty, before the pricing step or the direct pricing step issues any request.

Both steps SHALL submit the same date, so every amount in `data/vinci_price.yaml` describes one tariff schedule whichever step recorded it.

#### Scenario: Configured date reaches the container

- **WHEN** `.env` sets `ULYS_PASSAGE_DATE` and the pricing step runs
- **THEN** the value is visible inside the builder container and appears on every submitted passage

#### Scenario: Date is not configured

- **WHEN** `ULYS_PASSAGE_DATE` is unset or empty and the pricing step is run
- **THEN** the pipeline stops with a message naming the missing variable, before any request is issued

#### Scenario: Date is not configured for direct pricing

- **WHEN** `ULYS_PASSAGE_DATE` is unset or empty and `build_vinci_direct_prices` is run
- **THEN** the pipeline stops with a message naming the missing variable, before any pair is routed
