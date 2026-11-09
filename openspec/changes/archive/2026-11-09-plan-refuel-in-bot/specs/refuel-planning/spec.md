# Spec Delta

## RENAMED Requirements

- FROM: `### Requirement: The endpoint takes a journey, a route, a car, and the fuel in the tank`
- TO: `### Requirement: The endpoint takes a journey, a route, a car, and the fuel or the range`

## MODIFIED Requirements

### Requirement: The endpoint takes a journey, a route, a car, and the fuel or the range

`POST /api/refuel` SHALL take a JSON object with these keys: `from` and `to`, each a `[longitude, latitude]` pair; `route`, either `optimal` or `super_optimal`; `car`, an object with `fuel_type`, `tank_volume`, `consume_80`, `consume_130`, `reserve`, the liters at which the driver wants to refuel, and `reserve_km`, the km of range at which the driver wants to refuel; and either `fuel`, the liters in the tank at the origin, or `range`, the km of range at the origin.

#### Scenario: A complete request

- **WHEN** the page sends `{"from": [2.35, 48.86], "to": [5.37, 43.30], "route": "optimal", "car": {"fuel_type": "diesel", "tank_volume": 50, "consume_80": 5.5, "consume_130": 7.2, "reserve": 5, "reserve_km": 50}, "fuel": 20}`
- **THEN** the service answers with the status 200 and a JSON object

#### Scenario: A complete request with the range

- **WHEN** the page sends the same request with `"range": 300` in place of `"fuel": 20`
- **THEN** the service answers with the status 200 and a JSON object

### Requirement: The endpoint refuses invalid values before it routes

The service SHALL refuse a request with a missing key or a value outside its limits. The limits SHALL be the limits of `car-parameters`: a whole `tank_volume` of 30 or more, a `fuel_type` of `diesel`, `95`, or `98`, each consumption more than 0 and less than 30, with `consume_130` not less than `consume_80`, a `reserve` of 0 or more and less than `tank_volume`, and a `reserve_km` from 0 to 500. The request SHALL have exactly one of `fuel` and `range`. `fuel` SHALL be a number from 0 to `tank_volume`. `range` SHALL be a number from 0 to 3000. A refused request SHALL get the status 400 and SHALL cause no router request.

#### Scenario: A tank below the limit

- **WHEN** the request has the `tank_volume` `29`
- **THEN** the service answers with the status 400, and sends no router request

#### Scenario: A lower consumption at 130 km/h

- **WHEN** the request has the `consume_80` `7.2` and the `consume_130` `5.5`
- **THEN** the service answers with the status 400

#### Scenario: More fuel than the tank holds

- **WHEN** the request has the `tank_volume` `50` and the `fuel` `51`
- **THEN** the service answers with the status 400

#### Scenario: An empty tank is valid

- **WHEN** the request has the `fuel` `0` and valid other values
- **THEN** the service accepts the request

#### Scenario: A reserve equal to the tank volume

- **WHEN** the request has the `tank_volume` `50` and the `reserve` `50`
- **THEN** the service answers with the status 400, and sends no router request

#### Scenario: A reserve of 0 is valid

- **WHEN** the request has the `reserve` `0` and valid other values
- **THEN** the service accepts the request

#### Scenario: A range reserve above the limit

- **WHEN** the request has the `reserve_km` `501`
- **THEN** the service answers with the status 400, and sends no router request

#### Scenario: A range above the limit

- **WHEN** the request has the `range` `3001` and no `fuel`
- **THEN** the service answers with the status 400

#### Scenario: Both the fuel and the range

- **WHEN** the request has the `fuel` `20` and the `range` `300`
- **THEN** the service answers with the status 400

#### Scenario: An unknown route

- **WHEN** the request has the `route` `fast`
- **THEN** the service answers with the status 400

#### Scenario: A missing key

- **WHEN** the request has neither `fuel` nor `range`, or its `car` has no `reserve` key or no `reserve_km` key
- **THEN** the service answers with the status 400

### Requirement: The stop fills the tank

The liters bought SHALL be `tank_volume` minus the fuel left at the search point. After a walk by the range, the fuel left at the search point is not known, so the liters bought SHALL be `tank_volume` minus `reserve`. The answer SHALL give this value as `liters`.

#### Scenario: A stop at 5 L

- **GIVEN** the `tank_volume` is `50`
- **WHEN** the fuel left at the search point is 5 L
- **THEN** `liters` is `45`

#### Scenario: A stop after a walk by the range

- **GIVEN** the `tank_volume` is `50`, and the `reserve` is `8`
- **WHEN** the request has a `range`, and the range reaches `reserve_km` on the route
- **THEN** `liters` is `42`

## ADDED Requirements

### Requirement: With a range, the search point is where the range first reaches the range reserve

With `range`, the service SHALL follow the route from the origin and subtract the distance of each segment, in km, from the range. It SHALL use no consumption. The search point SHALL be the first route point where the range left is `reserve_km` or less. When `range` is `reserve_km` or less, the search point SHALL be the origin.

#### Scenario: The range reaches the range reserve on the route

- **GIVEN** a route of 10 segments of 10 km, and the `reserve_km` is `50`
- **WHEN** the request has the `range` `80`
- **THEN** the search point is the end of the third segment

#### Scenario: A range at or below the range reserve

- **GIVEN** the `reserve_km` is `50`
- **WHEN** the request has the `range` `50` or `40`
- **THEN** the search point is the origin

### Requirement: After a chosen station, a range plan walks by the fuel

With `range` and chosen stations, the walk by the range SHALL apply only up to the first chosen station. From each chosen station on, the walk SHALL be the walk by the fuel, with `tank_volume` liters and the `reserve`.

#### Scenario: The walk after a chosen station

- **GIVEN** the `tank_volume` is `50`, the `reserve` is `5`, and the planned route uses 1 L per segment after the chosen station C
- **WHEN** the request has a `range` and `"chosen": [C]`
- **THEN** the search point is 45 segments after C, whatever the range was at the origin

### Requirement: A range plan refuses a station that it does not need

With `range`, when the range left at the destination is more than `reserve_km` and `chosen` is not empty, the answer SHALL get the status 400.

#### Scenario: A station after a lasting range

- **GIVEN** a route of 100 km, and the `reserve_km` is `50`
- **WHEN** the request has the `range` `300` and one chosen station
- **THEN** the service answers with the status 400

### Requirement: No stop is planned when the range lasts to the destination

With `range` and no chosen station, when the range left at the destination is more than `reserve_km`, the answer SHALL be `{"stop_needed": false, "range_left": <km>}`, with the km rounded to two decimals. The service SHALL then read no station and send no detour request.

#### Scenario: A short route

- **GIVEN** a route of 100 km, and the `reserve_km` is `50`
- **WHEN** the request has the `range` `183.4`
- **THEN** the answer is `{"stop_needed": false, "range_left": 83.4}`, and the service sends no detour request

#### Scenario: A range reserve above the range left

- **GIVEN** a route of 100 km, and the `reserve_km` is `90`
- **WHEN** the request has the `range` `183.4`
- **THEN** the answer has `stop_needed` true
