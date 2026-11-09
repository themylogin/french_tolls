# Spec Delta

## REMOVED Requirements

### Requirement: The endpoint refuses invalid values before it routes

**Reason**: The car has no reserve in liters any more, and the checks are clearer in three parts.

**Migration**: "The endpoint refuses a car outside its limits", "The endpoint refuses a fuel or a range outside its limits", and "The endpoint refuses an unknown route" keep every other check.

### Requirement: The search point is where the tank first holds the reserve or less

**Reason**: The reserve is in km. A walk in liters reads it along the road ahead.

**Migration**: "A walk by the fuel subtracts what each segment uses" and "The search point is where the fuel left lasts only the reserve km" replace it.

## MODIFIED Requirements

### Requirement: The endpoint takes a journey, a route, a car, and the fuel or the range

`POST /api/refuel` SHALL take a JSON object with these keys: `from` and `to`, each a `[longitude, latitude]` pair; `route`, either `optimal` or `super_optimal`; `car`, an object with `fuel_type`, `tank_volume`, `consume_80`, `consume_130`, and `reserve_km`, the km of range at which the driver wants to refuel; and either `fuel`, the liters in the tank at the origin, or `range`, the km of range at the origin. A `reserve` key in `car` SHALL be ignored.

#### Scenario: A complete request

- **WHEN** the page sends `{"from": [2.35, 48.86], "to": [5.37, 43.30], "route": "optimal", "car": {"fuel_type": "diesel", "tank_volume": 50, "consume_80": 5.5, "consume_130": 7.2, "reserve_km": 50}, "fuel": 20}`
- **THEN** the service answers with the status 200 and a JSON object

#### Scenario: A complete request with the range

- **WHEN** the page sends the same request with `"range": 300` in place of `"fuel": 20`
- **THEN** the service answers with the status 200 and a JSON object

#### Scenario: A request from a page with a reserve in liters

- **WHEN** the `car` of the request also has `"reserve": 5`
- **THEN** the service answers as for the same request without it

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

- **WHEN** the route through A already reaches the destination with more than its reserve fuel, and the request has `"chosen": [A, B]`
- **THEN** the service answers with the status 400

### Requirement: No stop is planned when the fuel lasts to the destination

When the fuel left at the destination is more than the reserve fuel there, the answer SHALL have `stop_needed` false and `fuel_left`, the fuel left at the destination. The reserve fuel at the destination SHALL be `reserve_km` at `consume_130`. Without chosen stations, these SHALL be its only keys. The service SHALL then read no station and send no detour request.

#### Scenario: A short route

- **GIVEN** a route of 100 km at 130 km/h, `consume_130` is `6`, and the `reserve_km` is `50`
- **WHEN** the request has the `fuel` `40`
- **THEN** the answer is `{"stop_needed": false, "fuel_left": 34.0}`, and the service sends no detour request

#### Scenario: A reserve above the fuel left

- **GIVEN** a route of 100 km at 130 km/h, `consume_130` is `6`, and the `reserve_km` is `100`
- **WHEN** the request has the `fuel` `10`
- **THEN** the answer has `stop_needed` true, because the 4 L left at the destination are less than the 6 L of the reserve

#### Scenario: The fuel lasts after a chosen station

- **WHEN** the request has one chosen station, and the route through it reaches the destination with more than its reserve fuel
- **THEN** the answer has `stop_needed` false, `fuel_left`, and `route`, and the service sends no detour request

### Requirement: The stop fills the tank

The liters bought SHALL be `tank_volume` minus the fuel left at the search point. After a walk by the range, the fuel left at the search point is not known, so the liters bought SHALL be `tank_volume` minus the reserve fuel at the search point, and at least 0. The answer SHALL give this value as `liters`.

#### Scenario: A stop at 5 L

- **GIVEN** the `tank_volume` is `50`
- **WHEN** the fuel left at the search point is 5 L
- **THEN** `liters` is `45`

#### Scenario: A stop after a walk by the range

- **GIVEN** the `tank_volume` is `50`, `consume_130` is `10`, the `reserve_km` is `80`, and the route after the search point runs at 130 km/h
- **WHEN** the request has a `range`, and the range reaches `reserve_km` on the route
- **THEN** `liters` is `42`

#### Scenario: A reserve longer than a full tank

- **GIVEN** the `tank_volume` is `50`, `consume_130` is `12`, the `reserve_km` is `500`, and the route after the search point runs at 130 km/h
- **WHEN** the request has a `range`, and the range reaches `reserve_km` on the route
- **THEN** `liters` is `0`

### Requirement: After a chosen station, a range plan walks by the fuel

With `range` and chosen stations, the walk by the range SHALL apply only up to the first chosen station. From each chosen station on, the walk SHALL be the walk by the fuel, with `tank_volume` liters.

#### Scenario: The walk after a chosen station

- **GIVEN** the `tank_volume` is `50`, the `reserve_km` is `50`, and the planned route uses 1 L per 10 km segment at 130 km/h after the chosen station C, with `consume_130` `10`
- **WHEN** the request has a `range` and `"chosen": [C]`
- **THEN** the search point is 45 segments after C, whatever the range was at the origin

## ADDED Requirements

### Requirement: The endpoint refuses a car outside its limits

The service SHALL refuse a `car` with a missing key or a value outside the limits of `car-parameters`: a whole `tank_volume` of 30 or more, a `fuel_type` of `diesel`, `95`, or `98`, each consumption more than 0 and less than 30, with `consume_130` not less than `consume_80`, and a `reserve_km` from 0 to 500. A refused request SHALL get the status 400 and SHALL cause no router request.

#### Scenario: A tank below the limit

- **WHEN** the request has the `tank_volume` `29`
- **THEN** the service answers with the status 400, and sends no router request

#### Scenario: A lower consumption at 130 km/h

- **WHEN** the request has the `consume_80` `7.2` and the `consume_130` `5.5`
- **THEN** the service answers with the status 400

#### Scenario: A reserve above the limit

- **WHEN** the request has the `reserve_km` `501`
- **THEN** the service answers with the status 400, and sends no router request

#### Scenario: A reserve of 0 is valid

- **WHEN** the request has the `reserve_km` `0` and valid other values
- **THEN** the service accepts the request

#### Scenario: A car without a reserve

- **WHEN** the `car` of the request has no `reserve_km` key, even with a `reserve` key
- **THEN** the service answers with the status 400

### Requirement: The endpoint refuses a fuel or a range outside its limits

The request SHALL have exactly one of `fuel` and `range`. `fuel` SHALL be a number from 0 to `tank_volume`. `range` SHALL be a number from 0 to 3000. Any other request SHALL get the status 400 and SHALL cause no router request.

#### Scenario: More fuel than the tank holds

- **WHEN** the request has the `tank_volume` `50` and the `fuel` `51`
- **THEN** the service answers with the status 400

#### Scenario: An empty tank is valid

- **WHEN** the request has the `fuel` `0` and valid other values
- **THEN** the service accepts the request

#### Scenario: A range above the limit

- **WHEN** the request has the `range` `3001` and no `fuel`
- **THEN** the service answers with the status 400

#### Scenario: Both the fuel and the range

- **WHEN** the request has the `fuel` `20` and the `range` `300`
- **THEN** the service answers with the status 400

#### Scenario: Neither the fuel nor the range

- **WHEN** the request has neither `fuel` nor `range`
- **THEN** the service answers with the status 400

### Requirement: The endpoint refuses an unknown route

The `route` of the request SHALL be `optimal` or `super_optimal`. Any other value SHALL get the status 400 and SHALL cause no router request.

#### Scenario: An unknown route

- **WHEN** the request has the `route` `fast`
- **THEN** the service answers with the status 400

### Requirement: A walk by the fuel subtracts what each segment uses

A walk by the fuel SHALL follow the route from its start and subtract the fuel that each segment uses. The fuel that a segment uses SHALL be its distance in km multiplied by its consumption, divided by 100. The walk SHALL start at the origin with `fuel` liters, or at the last chosen station with `tank_volume` liters.

#### Scenario: One segment

- **GIVEN** a segment of 10 km at 130 km/h, and `consume_130` is `10`
- **WHEN** the walk passes it with 10 L
- **THEN** 9 L are left after it

### Requirement: The search point is where the fuel left lasts only the reserve km

The reserve fuel at a route point SHALL be the fuel that the next `reserve_km` of the route use from that point, by the consumption of each segment. A segment that these km cover only in part SHALL count for that part. Each km past the destination SHALL use `consume_130`. The search point of a walk by the fuel SHALL be its first route point where the fuel left is the reserve fuel there or less.

#### Scenario: The tank reaches the reserve on the route

- **GIVEN** a route of 10 segments, each 10 km long at 130 km/h, `consume_130` is `10`, and the `reserve_km` is `50`
- **WHEN** the request has the `fuel` `10`
- **THEN** the search point is the end of the fifth segment, where 5 L are left

#### Scenario: A larger reserve

- **GIVEN** the same route and car, with the `reserve_km` `80`
- **WHEN** the request has the `fuel` `10`
- **THEN** the search point is the end of the second segment

#### Scenario: A slow road ahead

- **GIVEN** `consume_80` is `6`, `consume_130` is `10`, the `reserve_km` is `50`, and the route runs 60 km at 50 km/h after the point P
- **WHEN** the walk reaches P with 3 L
- **THEN** the reserve fuel at P is 3 L, and P is the search point

#### Scenario: The reserve runs past the destination

- **GIVEN** `consume_130` is `10`, the `reserve_km` is `50`, and the destination is 20 km at 130 km/h after the point P
- **WHEN** the walk reaches P
- **THEN** the reserve fuel at P is 5 L: 2 L for the 20 km of the route and 3 L for the 30 km past the destination

#### Scenario: The reserve or less at the origin

- **GIVEN** the reserve fuel at the origin is 5 L
- **WHEN** the request has the `fuel` `4` or `5`
- **THEN** the search point is the origin

#### Scenario: The walk restarts at the last chosen station

- **GIVEN** the `tank_volume` is `50`, the `reserve_km` is `50`, and the planned route uses 1 L per 10 km segment at 130 km/h after the chosen station C, with `consume_130` `10`
- **WHEN** the request has `"chosen": [C]`
- **THEN** the search point is 45 segments after C, whatever the tank held before C
