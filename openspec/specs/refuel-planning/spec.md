# refuel-planning Specification

## Purpose

Defines how the service finds the point on a route where the driver must refuel, which stations it considers, how it prices a stop at each one, and what `POST /api/refuel` accepts and returns.

## Requirements

### Requirement: The endpoint takes a journey, a route, a car, and the fuel in the tank

`POST /api/refuel` SHALL take a JSON object with these keys: `from` and `to`, each a `[longitude, latitude]` pair; `route`, either `optimal` or `super_optimal`; `car`, an object with `fuel_type`, `tank_volume`, `consume_80`, and `consume_130`; and `fuel`, the liters in the tank at the origin.

#### Scenario: A complete request

- **WHEN** the page sends `{"from": [2.35, 48.86], "to": [5.37, 43.30], "route": "optimal", "car": {"fuel_type": "diesel", "tank_volume": 50, "consume_80": 5.5, "consume_130": 7.2}, "fuel": 20}`
- **THEN** the service answers with the status 200 and a JSON object

### Requirement: The endpoint refuses invalid values before it routes

The service SHALL refuse a request with a missing key or a value outside its limits. The limits SHALL be the limits of `car-parameters`: a whole `tank_volume` of 30 or more, a `fuel_type` of `diesel`, `95`, or `98`, and each consumption more than 0 and less than 30, with `consume_130` not less than `consume_80`. `fuel` SHALL be a number from 0 to `tank_volume`. A refused request SHALL get the status 400 and SHALL cause no router request.

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

#### Scenario: An unknown route

- **WHEN** the request has the `route` `fast`
- **THEN** the service answers with the status 400

#### Scenario: A missing key

- **WHEN** the request has no `fuel` key
- **THEN** the service answers with the status 400

### Requirement: The service plans along the route that the page shows

The service SHALL route the journey again from `from` to `to`. For `optimal`, it SHALL use the optimal route of `route-service`. For `super_optimal`, it SHALL use the split route of `route-service`, through the same stops. When the journey has no split route, a `super_optimal` request SHALL get the status 404.

#### Scenario: The optimal route

- **WHEN** a request names `optimal`
- **THEN** the service plans along the route that `/api/calculate` returns as `optimal` for the same `from` and `to`

#### Scenario: The split route

- **WHEN** a request names `super_optimal`, and the journey has a split route with two stops
- **THEN** the service plans along the route through these two stops

#### Scenario: No split route

- **WHEN** a request names `super_optimal`, and `/api/calculate` returns no `super_optimal` for that journey
- **THEN** the service answers with the status 404

### Requirement: A failed route gives an error status

When the service cannot route the journey, it SHALL answer with the status 502 and a JSON object whose `error` key names the cause. The causes SHALL be the causes of `route-service`: `out_of_reach`, `no_route`, and `router_unavailable`.

#### Scenario: The router does not answer

- **WHEN** the routing service does not answer while the service rebuilds the route
- **THEN** the service answers with the status 502 and `{"error": "router_unavailable"}`

### Requirement: The speed of a segment uses the corrected travel time

The speed of a route segment SHALL be its distance divided by its router duration multiplied by `TIME_MULTIPLIER`.

#### Scenario: The correction makes a segment faster

- **GIVEN** `TIME_MULTIPLIER` is `0.9`
- **WHEN** a segment is 1,000 m long and the router gives it 40 s
- **THEN** the speed of the segment is 100 km/h

### Requirement: The consumption at a speed comes from the two car consumptions

Below 80 km/h, the consumption SHALL be `consume_80`. At 80 km/h and above, it SHALL be on the curve `a + b × v²` through `(80, consume_80)` and `(130, consume_130)`, where `v` is the speed in km/h. The curve SHALL also apply above 130 km/h.

#### Scenario: A speed between the two

- **GIVEN** `consume_80` is `6` and `consume_130` is `8`
- **WHEN** the speed is 105 km/h
- **THEN** the consumption is 6.881 L/100 km, rounded to three decimals

#### Scenario: The curve meets the two car values

- **GIVEN** `consume_80` is `6` and `consume_130` is `8`
- **WHEN** the speed is 80 km/h, and then 130 km/h
- **THEN** the consumption is 6 L/100 km, and then 8 L/100 km

#### Scenario: A slow speed

- **GIVEN** `consume_80` is `6`
- **WHEN** the speed is 50 km/h
- **THEN** the consumption is 6 L/100 km

#### Scenario: A fast speed

- **GIVEN** `consume_80` is `6` and `consume_130` is `8`
- **WHEN** the speed is 150 km/h
- **THEN** the consumption is 9.067 L/100 km, rounded to three decimals

### Requirement: The search point is where the tank first holds 5 L or less

The service SHALL follow the route from the origin and subtract the fuel that each segment uses. The fuel that a segment uses SHALL be its distance in km multiplied by its consumption, divided by 100. The search point SHALL be the first route point where the fuel left is 5 L or less. When `fuel` is 5 L or less, the search point SHALL be the origin.

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

### Requirement: No stop is planned when the fuel lasts to the destination

When the fuel left at the destination is more than 5 L, the answer SHALL be `{"stop_needed": false, "fuel_left": <liters>}`, where `<liters>` is the fuel left at the destination. The service SHALL then read no station and send no detour request.

#### Scenario: A short route

- **GIVEN** a route of 100 km at 130 km/h, and `consume_130` is `6`
- **WHEN** the request has the `fuel` `40`
- **THEN** the answer is `{"stop_needed": false, "fuel_left": 34.0}`, and the service sends no detour request

### Requirement: The candidates are the 30 nearest stations that sell the fuel of the car

A candidate SHALL be a station within 50 km of the search point, measured on the surface of the earth. It SHALL have a stored price for one of the station fuels that `car-parameters` gives for the fuel type of the car. The service SHALL take the 30 candidates nearest to the search point.

#### Scenario: A far station is not a candidate

- **WHEN** a station that sells diesel is 60 km from the search point of a diesel car
- **THEN** that station is not a candidate

#### Scenario: A station without the fuel is not a candidate

- **WHEN** a station 2 km from the search point sells only `E85 (E85)`
- **THEN** that station is not a candidate for a diesel, 95, or 98 car

#### Scenario: Many stations near the search point

- **WHEN** 40 stations within 50 km sell the fuel of the car
- **THEN** the service sends a detour request for the 30 nearest only

### Requirement: The price of a station is its lowest price for the fuel of the car

The price of a candidate SHALL be the lowest stored price among the station fuels of the car fuel type. The answer SHALL name the station fuel that has this price.

#### Scenario: A 95 car at a station with two 95 fuels

- **WHEN** a station has the prices `SP95-E10 (E10)` at `1.799` and `SP95 (E5)` at `1.859`, and the car uses `95`
- **THEN** the price of the station is `1.799`, and its fuel is `SP95-E10 (E10)`

### Requirement: The detour drives through the station on the same graph

The detour route SHALL go from the origin through the station to the destination, on the graph of the planned route. On the split route, the detour SHALL also go through each split stop, in route order. The station SHALL come after the stops before the search point and before the stops after it.

#### Scenario: A detour on the split route

- **GIVEN** a split route with the stop A before the search point and the stop B after it
- **WHEN** the service routes the detour through a station
- **THEN** the detour goes through A, then the station, then B

### Requirement: The stop fills the tank

The liters bought SHALL be `tank_volume` minus the fuel left at the search point. The answer SHALL give this value as `liters`.

#### Scenario: A stop at 5 L

- **GIVEN** the `tank_volume` is `50`
- **WHEN** the fuel left at the search point is 5 L
- **THEN** `liters` is `45`

### Requirement: The cost of a stop is the fuel, the toll change, and the time

The cost of a candidate SHALL be the sum of three parts. The first is `liters` multiplied by the price. The second is the toll cost of the detour route minus the toll cost of the planned route. The third is the detour time in hours multiplied by `EUR_PER_HOUR`. The detour time SHALL be the duration of the detour route minus the duration of the planned route, both multiplied by `TIME_MULTIPLIER`.

#### Scenario: The three parts

- **GIVEN** `EUR_PER_HOUR` is `20`, and `liters` is `45`
- **WHEN** a station has the price `1.800`, the detour tolls are 2.10 € more, and the detour time is 600 s
- **THEN** the cost of that station is 86.43 €

#### Scenario: A detour that avoids a toll

- **WHEN** the detour route costs 3.00 € less in tolls than the planned route
- **THEN** the toll part of the cost is -3.00 €

### Requirement: A candidate without a detour route is left out

When the router finds no detour route through a candidate, the service SHALL leave out that candidate and SHALL continue with the others.

#### Scenario: A station that the router cannot reach

- **WHEN** the router reports no route through one candidate
- **THEN** the answer does not list that candidate, and lists the others

### Requirement: The answer lists the 10 cheapest stops

When the route has a search point, the answer SHALL be `{"stop_needed": true, "liters": <liters>, "stations": [...]}`. `stations` SHALL hold the 10 candidates with the lowest cost, from the lowest cost. Each entry SHALL carry `name`, `address`, `latitude`, `longitude`, `google_url`, `fuel`, `price`, `detour_duration` in seconds, `toll_difference`, `fuel_cost`, and `cost`. `google_url` SHALL open the position of the station in Google Maps.

#### Scenario: The cost decides the order, not the price

- **GIVEN** `EUR_PER_HOUR` is `20`, `liters` is `45`, and no detour changes the tolls
- **WHEN** station A has the price `1.800` and the detour time 600 s, and station B has the price `1.750` and the detour time 1,800 s
- **THEN** A comes before B, because A costs 84.33 € and B costs 88.75 €

#### Scenario: More than 10 candidates

- **WHEN** 30 candidates have a detour route
- **THEN** `stations` holds 10 entries

#### Scenario: The station position link

- **WHEN** a listed station is at latitude `48.209` and longitude `-3.818`
- **THEN** its `google_url` is `https://www.google.com/maps/search/?api=1&query=48.209000%2C-3.818000`

### Requirement: Each listed station carries its road distance from the origin

Each entry of `stations` SHALL also carry `distance`: the distance in metres that the detour route drives from the origin to the station. On the split route, this distance SHALL include the split stops before the station.

#### Scenario: The distance on the optimal route

- **WHEN** the detour route drives 52 km from the origin to the station and 48 km from the station to the destination
- **THEN** the `distance` of the station is `52000`

#### Scenario: The distance on the split route

- **GIVEN** the detour route drives 30 km to the split stop A, 25 km from A to the station, and then on through the stop B
- **WHEN** the station is listed
- **THEN** its `distance` is `55000`

### Requirement: Each listed station carries one badge or none

Each entry of `stations` SHALL also carry `badge`. It SHALL be `"24"` when the services of the station contain `Automate CB 24/24`. Else, it SHALL be `"Autoroute"` when an address line contains `autoroute` in any letter case. Else, it SHALL be `"Aire"` when an address line contains `aire`, not after a letter, then white space, then `de`, `des`, `du`, `d'`, or `d’`, in any letter case. Else, it SHALL be `null`.

#### Scenario: A station that sells at any hour

- **WHEN** the services of a station are `["Automate CB 24/24", "Lavage automatique"]`
- **THEN** its `badge` is `"24"`

#### Scenario: The 24 badge comes first

- **WHEN** a station has the service `Automate CB 24/24` and the address line `Autoroute A7`
- **THEN** its `badge` is `"24"`

#### Scenario: A motorway address in any letter case

- **WHEN** a station without `Automate CB 24/24` has the address line `Autoroute A7`, or the address line `aire de l'autoroute`
- **THEN** its `badge` is `"Autoroute"`

#### Scenario: A service area

- **WHEN** a station without `Automate CB 24/24` and without `autoroute` has one of the address lines `Aire de Beaune`, `aire des Volcans`, `aire du Poitou`, `aire d'Orange`, or `aire d’Orange`
- **THEN** its `badge` is `"Aire"`

#### Scenario: A service area glued to its motorway number

- **WHEN** a station without the two other badges has the address line `A71aire de ste thorette`
- **THEN** its `badge` is `"Aire"`

#### Scenario: A word that ends in aire

- **WHEN** a station without the two other badges has the address line `38460 Saint hilaire de brens` or `Zi portuaire des mielles`
- **THEN** its `badge` is `null`

#### Scenario: No rule matches

- **WHEN** a station has no services and the address lines `Rue de quimper` and `29520 Chateauneuf du faou`
- **THEN** its `badge` is `null`

### Requirement: An empty list says that no station is near

When the search point has no candidate, or no candidate has a detour route, the answer SHALL be `{"stop_needed": true, "liters": <liters>, "stations": []}`.

#### Scenario: No station near the search point

- **WHEN** no station within 50 km of the search point sells the fuel of the car
- **THEN** the answer has `stop_needed` true and an empty `stations` list
