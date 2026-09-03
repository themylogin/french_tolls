## MODIFIED Requirements

### Requirement: Eleven named build steps

The pipeline SHALL expose exactly twelve named steps — `download_pbf`, `setup_osrm`, `build_osm_toll_booths`, `build_route_set`, `build_vinci_toll_booths`, `build_vinci_prices`, `build_booth_sides`, `build_vinci_direct_prices`, `build_toll_extent`, `build_segment_weights`, `apply_segment_weights`, and `build_cost_cutting` — each individually invocable, and SHALL provide an `all` target that runs them in that order.

The seventh step SHALL run after the sixth, and the eighth after the seventh. The seventh reads the `enter`/`exit` roles the sixth records, and the eighth reads both the price file and the sides the seventh settles.

The ninth SHALL run after the eighth, the tenth after the ninth, and the eleventh after the tenth. The ninth reads the roles the eighth settles and writes the toll extents into the same price file; the tenth divides each tariff by the distance between those extents; the eleventh applies what the tenth wrote.

The twelfth SHALL run after the ninth, because it reads the price file only once the extents have been written into it. It needs neither the segment weights nor the toll-weighted graph, so it is ordered last for convenience rather than necessity, and it may be invoked on its own at any time after the ninth.

#### Scenario: Running the whole pipeline

- **WHEN** `make all` is run in a clean checkout
- **THEN** the twelve steps execute in the order `download_pbf`, `setup_osrm`, `build_osm_toll_booths`, `build_route_set`, `build_vinci_toll_booths`, `build_vinci_prices`, `build_booth_sides`, `build_vinci_direct_prices`, `build_toll_extent`, `build_segment_weights`, `apply_segment_weights`, `build_cost_cutting`

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

#### Scenario: Running the toll extent step alone

- **WHEN** `make build_toll_extent` is run
- **THEN** that step runs, along with any earlier step whose output is missing

#### Scenario: Running the segment weight step alone

- **WHEN** `make build_segment_weights` is run
- **THEN** that step runs, along with any earlier step whose output is missing

#### Scenario: Running the apply step alone

- **WHEN** `make apply_segment_weights` is run
- **THEN** that step runs, along with any earlier step whose output is missing

#### Scenario: Running the cost cutting step alone

- **WHEN** `make build_cost_cutting` is run
- **THEN** that step runs, along with any earlier step whose output is missing, and the toll-weighted graph is not built on its account

## ADDED Requirements

### Requirement: The cost cutting step needs the graph and no key

`build_cost_cutting` SHALL query the untouched routing graph and SHALL NOT contact the operator's rate service. Every duration it records is measured locally, so the step needs no subscription key, no tariff date, and no outbound network access.

It SHALL NOT require the toll-weighted graph. It reads how the road runs, not what the graph has been made to charge for it.

#### Scenario: The step runs without a key

- **WHEN** `build_cost_cutting` runs with no rate service key configured
- **THEN** it completes successfully

#### Scenario: The step runs without the toll-weighted graph

- **WHEN** `build_cost_cutting` runs before `apply_segment_weights` has ever been run
- **THEN** it completes successfully

### Requirement: The advice file is a published artefact

`data/cost-cutting.yaml` SHALL be carried in the repository, for the reason the booth sides and the segment weights are: it is derived from the routing graph, which is not in the repository, so a consumer who has only the checkout cannot rebuild it however cheap the step is.

#### Scenario: A fresh checkout can answer with advice

- **WHEN** the repository is checked out and the application is started without the pipeline having been run
- **THEN** `data/cost-cutting.yaml` is present and the service can offer splits
