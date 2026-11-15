# Spec Delta

## ADDED Requirements

### Requirement: The patched profile declares no excludable class

The setup step SHALL patch the profile so that it declares no excludable class. Each graph SHALL then carry one metric set.

The stock profile declares `toll`, `motorway` and `ferry`. For each excludable class, the customize step stores one more metric set. In the France graph, each metric set is 457 MB, on disk and in the memory of each router.

#### Scenario: The graph carries one metric set

- **WHEN** the setup step builds the untouched graph
- **THEN** its `cell_metrics` file holds the metric set with no exclusion and no other

#### Scenario: The toll-weighted graph carries one metric set

- **WHEN** the apply step customizes the toll-weighted graph
- **THEN** its `cell_metrics` file holds one metric set

#### Scenario: An exclusion is refused

- **WHEN** a request to either router carries `exclude=ferry`
- **THEN** the router answers with an error and returns no route

#### Scenario: A profile without the declaration stops the step

- **WHEN** the profile from the routing image declares no `excludable` sequence
- **THEN** the setup step stops before `osrm-extract` and names the missing declaration

### Requirement: The routers do not load turn-by-turn data

`osrm-toll` and `osrm-optimal` SHALL start with the turn-by-turn dataset disabled. They SHALL NOT load the intersection bearings.

No consumer in this repository asks for steps. On the France graph, the skipped data is 219 MB of resident memory in each router.

#### Scenario: The application's requests are answered

- **WHEN** the application snaps a point, asks for a route with `annotations=nodes,distance,duration`, matches a trace, or the pipeline asks for a table
- **THEN** the router returns the same body it returned before the change, waypoint names included

#### Scenario: A request for steps is refused

- **WHEN** a request to either router carries `steps=true`
- **THEN** the router answers with the code `DisabledDataset` and returns no route

#### Scenario: The graph is not rebuilt for this

- **WHEN** an existing graph is served with the turn-by-turn dataset disabled
- **THEN** the router starts without a new extract, partition or customize
