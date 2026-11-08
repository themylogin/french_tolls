# Spec Delta

## RENAMED Requirements

- FROM: `### Requirement: The search point is where the tank first holds 5 L or less`
- TO: `### Requirement: The search point is where the tank first holds the reserve or less`

## MODIFIED Requirements

### Requirement: The endpoint takes a journey, a route, a car, and the fuel in the tank

`POST /api/refuel` SHALL take a JSON object with these keys: `from` and `to`, each a `[longitude, latitude]` pair; `route`, either `optimal` or `super_optimal`; `car`, an object with `fuel_type`, `tank_volume`, `consume_80`, `consume_130`, and `reserve`, the liters at which the driver wants to refuel; and `fuel`, the liters in the tank at the origin.

#### Scenario: A complete request

- **WHEN** the page sends `{"from": [2.35, 48.86], "to": [5.37, 43.30], "route": "optimal", "car": {"fuel_type": "diesel", "tank_volume": 50, "consume_80": 5.5, "consume_130": 7.2, "reserve": 5}, "fuel": 20}`
- **THEN** the service answers with the status 200 and a JSON object

### Requirement: The endpoint refuses invalid values before it routes

The service SHALL refuse a request with a missing key or a value outside its limits. The limits SHALL be the limits of `car-parameters`: a whole `tank_volume` of 30 or more, a `fuel_type` of `diesel`, `95`, or `98`, each consumption more than 0 and less than 30, with `consume_130` not less than `consume_80`, and a `reserve` of 0 or more and less than `tank_volume`. `fuel` SHALL be a number from 0 to `tank_volume`. A refused request SHALL get the status 400 and SHALL cause no router request.

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

#### Scenario: An unknown route

- **WHEN** the request has the `route` `fast`
- **THEN** the service answers with the status 400

#### Scenario: A missing key

- **WHEN** the request has no `fuel` key, or its `car` has no `reserve` key
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

- **WHEN** the route through A already reaches the destination with more than the reserve, and the request has `"chosen": [A, B]`
- **THEN** the service answers with the status 400

### Requirement: The search point is where the tank first holds the reserve or less

The service SHALL follow the route from the origin and subtract the fuel that each segment uses. The fuel that a segment uses SHALL be its distance in km multiplied by its consumption, divided by 100. The search point SHALL be the first route point where the fuel left is the `reserve` of the car or less. When `fuel` is the reserve or less, the search point SHALL be the origin. With chosen stations, the walk SHALL start at the last chosen station with `tank_volume` liters.

#### Scenario: The tank reaches 5 L on the route

- **GIVEN** a route of 10 segments, each 10 km long at 130 km/h, `consume_130` is `10`, and the `reserve` is `5`
- **WHEN** the request has the `fuel` `10`
- **THEN** the search point is the end of the fifth segment

#### Scenario: A larger reserve

- **GIVEN** the same route and car, with the `reserve` `8`
- **WHEN** the request has the `fuel` `10`
- **THEN** the search point is the end of the second segment

#### Scenario: The tank holds 5 L or less at the origin

- **GIVEN** the `reserve` is `5`
- **WHEN** the request has the `fuel` `4`
- **THEN** the search point is the origin

#### Scenario: Exactly 5 L at the origin

- **GIVEN** the `reserve` is `5`
- **WHEN** the request has the `fuel` `5`
- **THEN** the search point is the origin

#### Scenario: The walk restarts at the last chosen station

- **GIVEN** the `tank_volume` is `50`, the `reserve` is `5`, and the planned route uses 1 L per segment after the chosen station C
- **WHEN** the request has `"chosen": [C]`
- **THEN** the search point is 45 segments after C, whatever the tank held before C

### Requirement: No stop is planned when the fuel lasts to the destination

When the fuel left at the destination is more than the `reserve` of the car, the answer SHALL have `stop_needed` false and `fuel_left`, the fuel left at the destination. Without chosen stations, these SHALL be its only keys. The service SHALL then read no station and send no detour request.

#### Scenario: A short route

- **GIVEN** a route of 100 km at 130 km/h, `consume_130` is `6`, and the `reserve` is `5`
- **WHEN** the request has the `fuel` `40`
- **THEN** the answer is `{"stop_needed": false, "fuel_left": 34.0}`, and the service sends no detour request

#### Scenario: A reserve above the fuel left

- **GIVEN** a route of 100 km at 130 km/h, `consume_130` is `6`, and the `reserve` is `35`
- **WHEN** the request has the `fuel` `40`
- **THEN** the answer has `stop_needed` true

#### Scenario: The fuel lasts after a chosen station

- **WHEN** the request has one chosen station, and the route through it reaches the destination with more than the reserve
- **THEN** the answer has `stop_needed` false, `fuel_left`, and `route`, and the service sends no detour request
