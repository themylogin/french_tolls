## MODIFIED Requirements

### Requirement: Steps do not repeat completed work

No step SHALL repeat work it has already completed. A step SHALL establish that in one of two ways.

A **checkpointed** step SHALL be skipped when its output is already in place. Skipping SHALL depend on the existence of the output, not on modification times, so that refreshing an earlier step's output does not silently invalidate a later step's expensive work. A checkpointed step that fails partway SHALL leave no completion marker, and the next run SHALL re-execute it from the beginning.

A **resumable** step SHALL always execute, and SHALL read its own output to determine what remains. Such a step SHALL record each unit of work only once that unit is complete, so an interrupted run repeats at most one unit. A resumable step SHALL perform no work and SHALL contact no external service when its output is already complete.

A step SHALL be resumable only when its work divides into units that are individually cheap to repeat and expensive to lose. `build_vinci_toll_booths`, `build_vinci_prices`, `build_vinci_direct_prices`, and `build_toll_extent` are resumable; every other step is checkpointed.

`build_vinci_direct_prices` SHALL read two outputs to determine what remains — the price file for the pairs it has priced, and the rejection database for the pairs it has ruled out. Its unit of work is one pair, and it repeats at most 25 of them.

`build_toll_extent` SHALL read the price file for the booths whose extent it has recorded. Its unit of work is one booth, and it repeats at most one.

`build_segment_weights` and `apply_segment_weights` are checkpointed. The first divides into no unit worth keeping — its aggregation is over all pairs at once, and a partial file would be a wrong file rather than an incomplete one. The second is one copy and one customization, and half of either is not a graph.

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

#### Scenario: The toll extent step resumes

- **WHEN** `build_toll_extent` fails partway through
- **THEN** the next run measures only the booths its price file does not already record

#### Scenario: The segment weight step stops on deviation

- **WHEN** `build_segment_weights` stops because a segment exceeded the deviation limit
- **THEN** `data/segment_weights.csv` is not written or replaced, and the next run repeats the whole step

#### Scenario: The apply step fails midway

- **WHEN** `apply_segment_weights` fails during the copy or the customization
- **THEN** its completion marker is not written, and the next run copies the untouched graph again from the beginning

### Requirement: Eight named build steps

The pipeline SHALL expose exactly eleven named steps — `download_pbf`, `setup_osrm`, `build_osm_toll_booths`, `build_route_set`, `build_vinci_toll_booths`, `build_vinci_prices`, `build_booth_sides`, `build_vinci_direct_prices`, `build_toll_extent`, `build_segment_weights`, and `apply_segment_weights` — each individually invocable, and SHALL provide an `all` target that runs them in that order.

The seventh step SHALL run after the sixth, and the eighth after the seventh. The seventh reads the `enter`/`exit` roles the sixth records, and the eighth reads both the price file and the sides the seventh settles.

The ninth SHALL run after the eighth, the tenth after the ninth, and the eleventh after the tenth. The ninth reads the roles the eighth settles and writes the toll extents into the same price file; the tenth divides each tariff by the distance between those extents; the eleventh applies what the tenth wrote.

#### Scenario: Running the whole pipeline

- **WHEN** `make all` is run in a clean checkout
- **THEN** the eleven steps execute in the order `download_pbf`, `setup_osrm`, `build_osm_toll_booths`, `build_route_set`, `build_vinci_toll_booths`, `build_vinci_prices`, `build_booth_sides`, `build_vinci_direct_prices`, `build_toll_extent`, `build_segment_weights`, `apply_segment_weights`

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

## ADDED Requirements

### Requirement: The toll extent step needs the graph and no key

`build_toll_extent` SHALL require the `osrm-toll` service and nothing else. It reads `data/vinci_price.yaml`, `data/route_set.yaml`, `data/osm_toll_booths.yaml`, `data/bidirectional_booth_sides.yaml` and `data/osm_toll_booths_overrides.yaml`, all committed, and issues no request to the toll operator.

It SHALL NOT be blocked by a missing `ULYS_SUBSCRIPTION_KEY` or `ULYS_PASSAGE_DATE`.

#### Scenario: The step without network

- **WHEN** `build_toll_extent` runs with no network access and `osrm-toll` available
- **THEN** it completes normally

#### Scenario: The step without the routing service

- **WHEN** `build_toll_extent` is run with `osrm-toll` stopped
- **THEN** it fails with a message naming the unreachable routing service, before it routes any booth

#### Scenario: No operator credentials are needed

- **WHEN** `ULYS_SUBSCRIPTION_KEY` and `ULYS_PASSAGE_DATE` are both unset and the step is run
- **THEN** the step runs, and neither guard stops it
