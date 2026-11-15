# Spec Delta

## MODIFIED Requirements

### Requirement: The planned route goes through the chosen stations

The service SHALL add the chosen stations to the planned route one at a time, in order. For each one, it SHALL place the station as the detour that listed it placed it, and route again. The route so far SHALL then be the detour route that was listed for that station. A station of a stop list SHALL be placed at the search point on the route so far. When the fuel lasts to the destination before such a station, the answer SHALL get the status 400. A station that the bot chose from a destination list or a cheaper list SHALL be placed at its route point, also when the fuel lasts.

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

#### Scenario: A chosen cheaper station

- **GIVEN** a split route with the stop A at 300 km, the search point at 450 km, and the cheaper station D with its route point at 200 km
- **WHEN** the driver chooses D in the bot
- **THEN** the planned route goes through D and then A, as the cheaper detour through D did

#### Scenario: A chosen destination station

- **GIVEN** the fuel lasts to the destination
- **WHEN** the driver chooses the station E of the destination list in the bot
- **THEN** the planned route goes through E and then to the destination, as the detour through E did, and the bot plan needs no other stop

## ADDED Requirements

### Requirement: The bot plan lists the stations at the destination

For the bot, when no stop is needed and no station is chosen, the plan SHALL take the destination as the search point. It SHALL find the candidates, route their detours, and list up to 10 stations, as for a stop. The answer of `POST /api/refuel` SHALL NOT change.

#### Scenario: The candidates are near the destination

- **GIVEN** the fuel lasts to the destination
- **WHEN** station A is 2 km from the destination and station B is 2 km from the origin, and both sell the fuel
- **THEN** the bot plan lists A and does not list B

#### Scenario: The cost decides the order

- **GIVEN** `EUR_PER_HOUR` is `20`, the stop at the destination buys 45 L, and no detour changes the tolls
- **WHEN** station A sells at `1.800` with the detour time 600 s, and station B sells at `1.750` with the detour time 1,800 s
- **THEN** A comes before B

#### Scenario: No station near the destination

- **WHEN** the fuel lasts, and no station within 50 km of the destination sells the fuel
- **THEN** the bot plan lists no station, and routes no detour

#### Scenario: The endpoint does not change

- **GIVEN** a route of 100 km at 130 km/h, `consume_130` is `6`, and the `reserve_km` is `50`
- **WHEN** the page sends the `fuel` `40`
- **THEN** the answer is `{"stop_needed": false, "fuel_left": 34.0}`, and the service routes no detour

### Requirement: The stop at the destination fills the tank

The stop at the destination SHALL buy `tank_volume` minus the fuel left at the destination. After a walk by the range, it SHALL buy `tank_volume` minus the reserve fuel at the destination, and at least 0.

#### Scenario: A stop after a walk by the fuel

- **GIVEN** the `tank_volume` is `50`
- **WHEN** 17 L are left at the destination
- **THEN** the cost of each station at the destination uses a stop of 33 L

#### Scenario: A stop after a walk by the range

- **GIVEN** the `tank_volume` is `50`, `consume_130` is `10`, and the `reserve_km` is `50`
- **WHEN** the range lasts to the destination
- **THEN** the cost of each station at the destination uses a stop of 45 L

### Requirement: The reference price is the lowest price of the list

For the bot, the reference price of a stop list or a destination list SHALL be the lowest price among its stations. A list without stations SHALL have no reference price and a share of 0.

#### Scenario: The cheapest station is not first

- **WHEN** the stop list has station A at `1.800` with a short detour, then station B at `1.750`
- **THEN** the reference price is `1.750`

#### Scenario: A destination list

- **WHEN** the fuel lasts, and the destination list has station A at `1.820`, then station B at `1.790`
- **THEN** the reference price is `1.790`

#### Scenario: An empty stop list

- **WHEN** no station within 50 km of the search point sells the fuel
- **THEN** the share is 0

### Requirement: The share counts the stored stations below the reference price

The share SHALL be the percentage of the stored stations with a price for the fuel of the car that are below the reference price. It SHALL be rounded up to a whole number. The price of a stored station SHALL be its lowest price among the station fuels of the car. The route SHALL have no effect on the share.

#### Scenario: A whole share

- **WHEN** 1,800 of 12,000 stored stations with the fuel are below the reference price
- **THEN** the share is 15

#### Scenario: A share rounded up

- **WHEN** 3 of 200 stored stations with the fuel are below the reference price
- **THEN** the share is 2

#### Scenario: A cheaper station far from the route

- **WHEN** a station 300 km from the route sells the fuel below the reference price
- **THEN** it counts in the share

#### Scenario: A station without the fuel

- **GIVEN** a diesel car
- **WHEN** a stored station sells only `SP95-E10 (E10)`
- **THEN** it counts in neither number of the share

### Requirement: The cheaper search waits for a request

The plan SHALL route no detour through a cheaper station. A separate cheaper search SHALL use the planned route, the start of the walk, the search point, the reference price, and the liters of a list. It SHALL route no planned route again.

#### Scenario: The stop list

- **WHEN** a station within 5 km of the route is below the reference price
- **THEN** the plan routes the planned route and the detours of its candidates, and no detour through that station

#### Scenario: The cheaper search

- **WHEN** the cheaper search keeps 3 stations
- **THEN** it sends 3 router requests, one detour through each station

### Requirement: The route stations lie near the route before the search point

A route station SHALL sell the fuel of the car and be 5 km or less, by great-circle distance, from a route point of the walk, up to the search point included. The points of the walk SHALL start at the origin, or after the point of the last chosen station. The route point of a route station SHALL be the nearest of these points.

#### Scenario: A station near the road

- **WHEN** a station that sells the fuel is 4 km from a route point before the search point
- **THEN** it is a route station

#### Scenario: A station far from the road

- **WHEN** a station that sells the fuel is 6 km from every route point
- **THEN** it is not a route station

#### Scenario: A station after the search point

- **WHEN** a station is 1 km from a route point after the search point, and more than 5 km from every point before it
- **THEN** it is not a route station

#### Scenario: A station on the route of a destination list

- **GIVEN** the fuel lasts to the destination
- **WHEN** a station that sells the fuel is 1 km from a route point halfway to the destination
- **THEN** it is a route station

#### Scenario: A station before the last chosen station

- **GIVEN** the chosen station C at 400 km from the origin
- **WHEN** a station is 1 km from the route point at 350 km, and more than 5 km from every point after C
- **THEN** it is not a route station

#### Scenario: A station at the last chosen station

- **GIVEN** the chosen station C
- **WHEN** a station is 1 km from the route point of C, and more than 5 km from every later point
- **THEN** it is not a route station

#### Scenario: A station without the fuel

- **GIVEN** a diesel car
- **WHEN** a station 1 km from the route sells only `SP95-E10 (E10)`
- **THEN** it is not a route station

### Requirement: The cheaper stations are the latest route stations below the reference price

The cheaper stations SHALL be the route stations with a price below the reference price. The search SHALL keep the 10 with the latest route point, then the lower price, then the lower station id. It SHALL list the kept stations that the router reaches by cost, with the liters of the list, and then by station id.

#### Scenario: The cost decides the order

- **GIVEN** `EUR_PER_HOUR` is `20`, the stop list buys 45 L, the reference price is `1.800`, and no detour changes the tolls
- **WHEN** station A sells at `1.700` with the detour time 60 s, and station B sells at `1.690` with the detour time 1,800 s
- **THEN** A comes before B, because A costs 76.83 € and B costs 86.05 €

#### Scenario: An equal price is not cheaper

- **GIVEN** the reference price is `1.800`
- **WHEN** a route station sells at `1.800`
- **THEN** it is not a cheaper station

#### Scenario: More than 10 cheaper stations

- **WHEN** 12 route stations are below the reference price
- **THEN** the search keeps the 10 with the latest route point

#### Scenario: An unreachable cheaper station

- **WHEN** the search keeps 3 stations, and the router finds no route through one of them
- **THEN** the search lists 2 stations, and no other station replaces it

### Requirement: A cheaper detour goes through the station at its route point

The cheaper detour SHALL go from the origin through the station to the destination, on the graph of the planned route. It SHALL also go through each split stop and chosen station, in route order. The station SHALL come after those before its route point and before those after it. No more than four detour requests SHALL be open at once.

#### Scenario: A split stop between the station and the search point

- **GIVEN** a split route with the stop A at 300 km and the stop B at 500 km, and the search point at 450 km
- **WHEN** the search routes the detour through a cheaper station with its route point at 200 km
- **THEN** the detour goes through the station, then A, then B

#### Scenario: Ten cheaper stations

- **WHEN** the search keeps 10 stations
- **THEN** it routes one detour through each, with no more than four requests open at once

### Requirement: Each cheaper station carries the keys of a listed station

Each cheaper station SHALL carry the keys of an entry of `stations`, from its own detour. Its `distance` and `distance_from_previous` SHALL run to the station through the split stops and chosen stations before it. Its cost SHALL use the liters of the list.

#### Scenario: The distance from the last chosen station

- **GIVEN** the chosen station C
- **WHEN** the cheaper detour drives 220 km to C, and then 80 km from C to the station
- **THEN** the `distance` of the station is `300000`, and its `distance_from_previous` is `80000`
