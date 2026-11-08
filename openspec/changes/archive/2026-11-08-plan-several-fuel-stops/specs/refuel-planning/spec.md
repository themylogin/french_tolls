# Spec Delta

## ADDED Requirements

### Requirement: The request carries the stations chosen so far

The request SHALL be allowed to carry `chosen`: the stations that the driver chose in this plan, in the order of choice. Each entry SHALL be an object with the numbers `latitude` and `longitude`. A request without `chosen` SHALL plan as with an empty list. A `chosen` that is not a list, has more than 20 entries, or has an entry without two finite numbers SHALL get the status 400 and SHALL cause no router request.

#### Scenario: A request without chosen stations

- **WHEN** the request has no `chosen` key
- **THEN** the service plans the first stop, as for `"chosen": []`

#### Scenario: Too many chosen stations

- **WHEN** the request has 21 entries in `chosen`
- **THEN** the service answers with the status 400, and sends no router request

#### Scenario: An entry without a position

- **WHEN** an entry of `chosen` is `{"latitude": 45.34}`
- **THEN** the service answers with the status 400

### Requirement: The planned route goes through the chosen stations

The service SHALL add the chosen stations to the planned route one at a time, in order. For each one, it SHALL find the search point on the route so far, place the station as a detour through that search point places it, and route again. The route so far SHALL then be the detour route that was listed for that station. When the fuel lasts to the destination before a chosen station, the answer SHALL get the status 400.

#### Scenario: One chosen station

- **GIVEN** the first answer listed the station A with its detour route
- **WHEN** the request has `"chosen": [A]`
- **THEN** the planned route is that detour route through A

#### Scenario: Two chosen stations

- **WHEN** the request has `"chosen": [A, B]`, and B was listed in the answer to `"chosen": [A]`
- **THEN** the planned route goes through A and then B, and a list in the answer is for the third stop

#### Scenario: A station that the plan does not need

- **WHEN** the route through A already reaches the destination with more than 5 L, and the request has `"chosen": [A, B]`
- **THEN** the service answers with the status 400

### Requirement: A finished plan carries its route

When `chosen` is not empty and the fuel lasts to the destination, the answer SHALL also carry `route`: an object with `nodes`, the `[longitude, latitude]` points of the planned route through the chosen stations, and `google_url`, a Google Maps link that drives it.

#### Scenario: The last stop is chosen

- **WHEN** the route through the chosen stations reaches the destination with 12.7 L
- **THEN** the answer has `stop_needed` false, `fuel_left` 12.7, and `route` with `nodes` and `google_url`

### Requirement: The link of a finished plan keeps every chosen station

The link SHALL go through each chosen station and each split stop. It SHALL also go through the waypoints of the route's own Google Maps link that lie on the planned route. All waypoints SHALL be in route order, at most 9. When they are more than 9, the service SHALL drop route waypoints, each time the one nearest along the route to another waypoint, until 9 remain. When the chosen stations and the split stops alone are more than 9, `google_url` SHALL be null.

#### Scenario: The waypoints fit

- **WHEN** the optimal route's link has 5 waypoints, and the plan has 2 chosen stations
- **THEN** the link has 7 waypoints, in route order

#### Scenario: Too many waypoints

- **WHEN** the optimal route's link has 8 waypoints, and the plan has 2 chosen stations
- **THEN** the link has 9 waypoints, both stations are among them, and the dropped waypoint is the route waypoint nearest along the route to another waypoint

#### Scenario: Too many stations

- **WHEN** the plan has 10 chosen stations
- **THEN** `google_url` is null

### Requirement: Each listed station carries its road distance from the previous stop

Each entry of `stations` SHALL also carry `distance_from_previous`: the distance in metres that the detour route drives from the last chosen station to the station, through the split stops between them. Without chosen stations, it SHALL be equal to `distance`.

#### Scenario: The distance from the last chosen station

- **GIVEN** the detour route drives 220 km to the chosen station C, and 310 km from C to the station
- **WHEN** the station is listed
- **THEN** its `distance_from_previous` is `310000`

#### Scenario: A split stop between

- **GIVEN** the detour route drives 150 km from the chosen station C to the split stop B, and 180 km from B to the station
- **WHEN** the station is listed
- **THEN** its `distance_from_previous` is `330000`

#### Scenario: No chosen station

- **WHEN** a station is listed in the answer to a request without chosen stations
- **THEN** its `distance_from_previous` is its `distance`

## MODIFIED Requirements

### Requirement: The search point is where the tank first holds 5 L or less

The service SHALL follow the route from the origin and subtract the fuel that each segment uses. The fuel that a segment uses SHALL be its distance in km multiplied by its consumption, divided by 100. The search point SHALL be the first route point where the fuel left is 5 L or less. When `fuel` is 5 L or less, the search point SHALL be the origin. With chosen stations, the walk SHALL start at the last chosen station with `tank_volume` liters.

#### Scenario: The tank reaches 5 L on the route

- **GIVEN** a route of 10 segments, each 10 km long at 130 km/h, and `consume_130` is `10`
- **WHEN** the request has the `fuel` `10`
- **THEN** the search point is the end of the fifth segment

#### Scenario: The tank holds 5 L or less at the origin

- **WHEN** the request has the `fuel` `4`
- **THEN** the search point is the origin

#### Scenario: Exactly 5 L at the origin

- **WHEN** the request has the `fuel` `5`
- **THEN** the search point is the origin

#### Scenario: The walk restarts at the last chosen station

- **GIVEN** the `tank_volume` is `50`, and the planned route uses 1 L per segment after the chosen station C
- **WHEN** the request has `"chosen": [C]`
- **THEN** the search point is 45 segments after C, whatever the tank held before C

### Requirement: No stop is planned when the fuel lasts to the destination

When the fuel left at the destination is more than 5 L, the answer SHALL have `stop_needed` false and `fuel_left`, the fuel left at the destination. Without chosen stations, these SHALL be its only keys. The service SHALL then read no station and send no detour request.

#### Scenario: A short route

- **GIVEN** a route of 100 km at 130 km/h, and `consume_130` is `6`
- **WHEN** the request has the `fuel` `40`
- **THEN** the answer is `{"stop_needed": false, "fuel_left": 34.0}`, and the service sends no detour request

#### Scenario: The fuel lasts after a chosen station

- **WHEN** the request has one chosen station, and the route through it reaches the destination with more than 5 L
- **THEN** the answer has `stop_needed` false, `fuel_left`, and `route`, and the service sends no detour request

### Requirement: The detour drives through the station on the same graph

The detour route SHALL go from the origin through the station to the destination, on the graph of the planned route. The detour SHALL also go through each split stop and each chosen station, in route order. The station SHALL come after those before the search point and before those after it.

#### Scenario: A detour on the split route

- **GIVEN** a split route with the stop A before the search point and the stop B after it
- **WHEN** the service routes the detour through a station
- **THEN** the detour goes through A, then the station, then B

#### Scenario: A detour after a chosen station

- **GIVEN** a split route with the stop B, and the chosen station C before the search point and before B
- **WHEN** the service routes the detour through a station
- **THEN** the detour goes through C, then the station, then B

### Requirement: Each listed station carries its road distance from the origin

Each entry of `stations` SHALL also carry `distance`: the distance in metres that the detour route drives from the origin to the station. This distance SHALL include the split stops and the chosen stations before the station.

#### Scenario: The distance on the optimal route

- **WHEN** the detour route drives 52 km from the origin to the station and 48 km from the station to the destination
- **THEN** the `distance` of the station is `52000`

#### Scenario: The distance on the split route

- **GIVEN** the detour route drives 30 km to the split stop A, 25 km from A to the station, and then on through the stop B
- **WHEN** the station is listed
- **THEN** its `distance` is `55000`

#### Scenario: The distance after a chosen station

- **GIVEN** the detour route drives 220 km to the chosen station C, and 310 km from C to the station
- **WHEN** the station is listed
- **THEN** its `distance` is `530000`
