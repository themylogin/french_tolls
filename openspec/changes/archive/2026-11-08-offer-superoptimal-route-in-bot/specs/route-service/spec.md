## MODIFIED Requirements

### Requirement: The answer may carry a route that splits a ticket

A route query MAY return a third route under the key `super_optimal`, beside `fast` and `optimal`. It SHALL be present only when splitting a ticket somewhere on the optimal route beats the configured threshold, and absent otherwise.

`super_optimal` SHALL carry every key a route carries, with the same meanings, so that a consumer reading `distance`, `duration`, `nodes`, `peages` and `cost` needs no new handling. It SHALL additionally carry:

- `stops` — the junctions at which the driver leaves and immediately re-enters the tolled road, in driven order, each with the gare name and its position. Each stop SHALL also carry `booths`, the exit booth and the entrance booth crossed there, named as the route's `booths` names them, and `index`, the position in `nodes` where the route reaches the exit booth;
- `extra_duration` — seconds, the driving time it adds over `optimal`, including booth time;
- `saving` — euros, `optimal.cost` minus `super_optimal.cost`;
- `drive_waypoints` — the waypoints that drive the route with every stop kept, as `[longitude, latitude]` pairs in driven order. They are a waypoint at each stop, and as many of the optimal route's waypoints that lie on the route as fit beside the stops in one directions link. It SHALL be null where the stops alone do not fit.

`drive_waypoints` SHALL NOT change `google_url`. The page offers `google_url` without a check against Google, so it keeps every waypoint or is withheld. The bot checks the route against Google and corrects it, so it can drop a waypoint of the optimal route to keep a stop.

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

#### Scenario: A stop names its booths and its place

- **WHEN** `super_optimal` is present
- **THEN** each stop carries `booths` with the exit booth and the entrance booth, each one in the route's `booths`, and an `index` whose node in `nodes` is the exit booth

#### Scenario: The drive waypoints keep every stop

- **WHEN** a split route with 2 stops is returned, and the optimal route needed 8 waypoints that all lie on the split route
- **THEN** `drive_waypoints` holds 9 waypoints in driven order with both stops among them, and `google_url` is null

#### Scenario: The drive waypoints and the link agree where everything fits

- **WHEN** a split route with 1 stop is returned, and the optimal route needed 4 waypoints that all lie on the split route
- **THEN** `drive_waypoints` holds the 5 waypoints that `google_url` carries, in the same order

#### Scenario: Stops that do not fit

- **WHEN** the stops of a split route alone are more than one directions link carries
- **THEN** `drive_waypoints` is null
