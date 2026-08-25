## RENAMED Requirements

- FROM: `### Requirement: Seven named build steps`
- TO: `### Requirement: Eight named build steps`

## MODIFIED Requirements

### Requirement: Eight named build steps

The pipeline SHALL expose exactly eight named steps — `download_pbf`, `setup_osrm`, `build_osm_toll_booths`, `build_route_set`, `build_vinci_toll_booths`, `build_vinci_prices`, `build_booth_sides`, and `build_vinci_direct_prices` — each individually invocable, and SHALL provide an `all` target that runs them in that order.

The seventh step SHALL run after the sixth, and the eighth after the seventh. The seventh reads the `enter`/`exit` roles the sixth records, and the eighth reads both the price file and the sides the seventh settles.

#### Scenario: Running the whole pipeline

- **WHEN** `make all` is run in a clean checkout
- **THEN** the eight steps execute in the order `download_pbf`, `setup_osrm`, `build_osm_toll_booths`, `build_route_set`, `build_vinci_toll_booths`, `build_vinci_prices`, `build_booth_sides`, `build_vinci_direct_prices`

#### Scenario: Running a single step

- **WHEN** `make build_osm_toll_booths` is run
- **THEN** that step runs, along with any earlier step whose output is missing

#### Scenario: Running the gare mapping step alone

- **WHEN** `make build_vinci_toll_booths` is run
- **THEN** that step runs, along with any earlier step whose output is missing

#### Scenario: Running the pricing step alone

- **WHEN** `make build_vinci_prices` is run
- **THEN** that step runs, along with any earlier step whose output is missing

#### Scenario: Running the booth sides step alone

- **WHEN** `make build_booth_sides` is run
- **THEN** that step runs, along with any earlier step whose output is missing

#### Scenario: Running the direct pricing step alone

- **WHEN** `make build_vinci_direct_prices` is run
- **THEN** that step runs, along with any earlier step whose output is missing

## ADDED Requirements

### Requirement: The booth sides step needs the graph and not the key

Its position in the order is forced rather than chosen. The step reads the `enter` and `exit` roles from `data/vinci_price.yaml`, which the pricing step produces, so it cannot run before it. It issues no request to the operator, only to the routing service, so it needs the graph and not the subscription key.

The step SHALL be checkpointed on `data/bidirectional_booth_sides.yaml`: its work divides into no resumable units, and a complete run costs about two minutes of local routing.

#### Scenario: The step needs the routing service

- **WHEN** `build_booth_sides` is run with the OSRM instance stopped
- **THEN** it fails with a message naming the unreachable routing service

#### Scenario: The step contacts no operator service

- **WHEN** `build_booth_sides` runs with no network access and the routing service available
- **THEN** it completes normally

#### Scenario: A complete output is skipped

- **WHEN** `data/bidirectional_booth_sides.yaml` is already present
- **THEN** the step is skipped

### Requirement: The booth sides are a published artefact

`data/bidirectional_booth_sides.yaml` SHALL be committed, alongside the booth inventory, the route set, the gare mapping and the price file.

It is derived from the routing graph, which is not in the repository, so a consumer who has only the checkout cannot rebuild it however cheap the step is. That is the same reason the inventory and the route set are carried rather than regenerated, and the opposite of the rejection database, which any consumer with the graph rebuilds in minutes and which no consumer outside the pipeline reads.

#### Scenario: The file is present in a fresh checkout

- **WHEN** the repository is checked out without running the pipeline
- **THEN** `data/bidirectional_booth_sides.yaml` is present under `data/`

#### Scenario: No ignore rule matches it

- **WHEN** the ignore rules are inspected
- **THEN** none of them matches `data/bidirectional_booth_sides.yaml`
