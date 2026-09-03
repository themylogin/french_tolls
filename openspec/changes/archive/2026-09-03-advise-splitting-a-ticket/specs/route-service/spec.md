## ADDED Requirements

### Requirement: The answer may carry a route that splits a ticket

A route query MAY return a third route under the key `super_optimal`, beside `fast` and `optimal`. It SHALL be present only when splitting a ticket somewhere on the optimal route beats the configured threshold, and absent otherwise.

`super_optimal` SHALL carry every key a route carries, with the same meanings, so that a consumer reading `distance`, `duration`, `nodes`, `peages` and `cost` needs no new handling. It SHALL additionally carry:

- `stops` — the junctions at which the driver leaves and immediately re-enters the tolled road, in driven order, each with the gare name and its position;
- `extra_duration` — seconds, the driving time it adds over `optimal`, including booth time;
- `saving` — euros, `optimal.cost` minus `super_optimal.cost`.

Its absence SHALL NOT be an error and SHALL NOT be explained. A route with nothing to save is the ordinary case.

#### Scenario: A route with nothing to save

- **WHEN** no section of the optimal route has a split above the threshold
- **THEN** the answer carries `fast` and `optimal` and no `super_optimal`

#### Scenario: A route with something to save

- **WHEN** some section has a split above the threshold
- **THEN** the answer carries `super_optimal`, whose `cost` is lower than `optimal`'s and whose `duration` is higher

#### Scenario: The third route reads like the others

- **WHEN** `super_optimal` is present
- **THEN** it carries `distance`, `duration`, `duration_osrm`, `nodes`, `peages`, `cost` and `google_url`, with the meanings those keys have on `optimal`

### Requirement: The split route is routed and priced, not asserted

`super_optimal` SHALL be produced by routing the journey through the stored booth nodes and pricing the geometry that comes back, using the same accounting that prices every other route.

The advice file names OSM booth nodes. The service SHALL resolve them to positions through the booth inventory it already loads, and SHALL route the journey through them on the toll-weighted graph, so that the road between two stops is chosen exactly as it is for `optimal`.

The price SHALL come from walking the returned geometry and pairing each entrance with the exit that follows it. It SHALL NOT be computed by subtracting the advice file's figures from the direct fare: the file says where stopping is worthwhile, and the route that comes back is what the driver would actually pay.

When the routed geometry does not cross the stops it was built from, the split SHALL NOT be offered. A route that missed a stop was not the journey the saving was computed for.

#### Scenario: The offered route is priced from its own geometry

- **WHEN** `super_optimal` is returned
- **THEN** its `cost` is the sum of its own `peages`, each of which came from pairing an entrance with the following exit on its geometry

#### Scenario: The re-route missed a stop

- **WHEN** routing through the stops returns a geometry that does not cross one of them
- **THEN** no `super_optimal` is returned

### Requirement: A split is offered at the rate the graph was weighted with

The threshold above which a split is offered SHALL be what a driver's hour is worth, read from the one setting that also weights the toll-weighted graph.

That graph carries `weight = osm_weight + price / wage * 3600`, which is what makes the router accept a detour whose toll saving beats the minutes it costs. Offering a stop asks the identical question about a different kind of detour. Two separate values would offer a driver a trade the router had already rejected as bad, or withhold one it would have taken, and nothing in the answer would show why.

It SHALL be applied per closed section of the optimal route, so a journey crossing several sections takes the splits that are worth it and leaves the ones that are not.

#### Scenario: The rate is the one the graph was built with

- **WHEN** a split is judged
- **THEN** the euros-per-hour it must clear is the same value step 10 passed as the wage

#### Scenario: Raising the rate withdraws the marginal offers

- **WHEN** the setting is raised above what a section's best split earns per hour
- **THEN** that section is no longer offered a split

#### Scenario: Sections are judged separately

- **WHEN** a route crosses two closed sections and only one has a split above the threshold
- **THEN** `super_optimal` stops only in that section

### Requirement: A split route's directions link carries its stops, or is withheld

`super_optimal` SHALL carry a `google_url` that drives the split journey, built from the optimal route's own waypoints together with a waypoint at each stop, in driven order. Where those do not fit the waypoint allowance a Maps URL takes, `google_url` SHALL be null.

Both sets are needed and neither is optional. The optimal route's waypoints are what make a fastest-path router follow the same road; a waypoint at each stop is what makes it leave the motorway and rejoin, which no shortest path does on its own. A link carrying only the first would drive the road without the manoeuvre — the ordinary route, at the ordinary price, presented as the cheap one.

Null is the honest answer when they do not fit. A consumer SHALL treat it as "no link", not as an error.

#### Scenario: The link drives the stops

- **WHEN** a split route with one stop is returned and the optimal route needed four waypoints
- **THEN** its `google_url` carries five waypoints, the stop among them

#### Scenario: The allowance is already spent

- **WHEN** the optimal route's waypoints plus the stops exceed what a Maps URL takes
- **THEN** `google_url` is null and no other key of the route changes

### Requirement: The advice file is one of the artefacts the service requires

`data/cost-cutting.yaml` SHALL be read at start-up and its absence SHALL stop the service, naming the file, exactly as a missing price file does.

It is not a mode. Step 12 runs in every build and the file is carried in the repository, so a tree without it has lost an artefact rather than opted out. Treating the absence as "no split is available anywhere" would answer every journey as though the tariff were additive, and nothing in the answer would distinguish that from a road where splitting genuinely saves nothing.

#### Scenario: A missing advice file

- **WHEN** `data/cost-cutting.yaml` is not mounted
- **THEN** the service exits at start-up naming that file, rather than serving

#### Scenario: An unparseable advice file

- **WHEN** `data/cost-cutting.yaml` is present but not valid YAML
- **THEN** the service exits at start-up naming that file
