# Spec Delta

## ADDED Requirements

### Requirement: Use asks for the next stop

A click on `Use` SHALL add its station to the chosen stations of the plan. The page SHALL then send one request with the same values as `Calculate` and with all chosen stations, in order. While the request is open, the old list SHALL keep its place but be invisible, with the busy sign at its center. When the answer has `stop_needed` true, the dialog SHALL show its list in place of the old one.

#### Scenario: The first Use

- **WHEN** the visitor clicks `Use` on the station A
- **THEN** the page sends one request with `"chosen": [A]`, and until the answer comes the list is invisible in its place, with the busy sign at its center

#### Scenario: More fuel is needed

- **WHEN** the answer to `"chosen": [A]` has `stop_needed` true and stations
- **THEN** the dialog shows the new list, and a click on `Use` on its station B sends `"chosen": [A, B]`

### Requirement: A finished plan closes the dialog and is drawn

When the answer to a `Use` has `stop_needed` false, the dialog SHALL close. The map SHALL draw the `route` of the answer in black, with the width of the split route, beneath the optimal and the split routes. It SHALL mark each chosen station with a black dot. The Google Maps link of the planned route SHALL become the `google_url` of the answer. A null `google_url` SHALL hide that link.

#### Scenario: The plan is finished

- **WHEN** the answer to `"chosen": [A, B]` has `stop_needed` false
- **THEN** the dialog closes, the black route is drawn beneath the other routes, and A and B have black dots

#### Scenario: The link drives the plan

- **WHEN** a plan on the optimal route is finished
- **THEN** the Google Maps link beside "Optimal route" is the `google_url` of the answer

#### Scenario: A plan without a link

- **WHEN** the answer of a finished plan has a null `google_url`
- **THEN** the planned route shows no Google Maps link

### Requirement: A new route calculation clears the plan

A new route calculation SHALL remove the black route and the black dots. The new routes SHALL show their gas station icons as before any plan.

#### Scenario: The visitor calculates another route

- **GIVEN** a finished plan is drawn
- **WHEN** the visitor calculates a route
- **THEN** no black route or black dot remains, and the optimal route has a gas station icon that opens the dialog

### Requirement: The distance column counts from the previous stop

The distance column of the list SHALL show `distance_from_previous` in whole km. So the first list shows the distance from the origin, and each later list shows the distance from the last chosen station.

#### Scenario: A later list

- **WHEN** the visitor has chosen a station, and the next list has a station with `distance` 530,000 m and `distance_from_previous` 310,000 m
- **THEN** its distance column shows `310 km`

### Requirement: The toll column shows how a detour changes the tolls

The toll column SHALL show `toll_difference` as euros with two decimals and its sign, for example `+1,15 €` or `-1,25 €`. When `toll_difference` rounds to 0, the cell SHALL be empty.

#### Scenario: A detour that pays more tolls

- **WHEN** a listed station has the `toll_difference` 1.15
- **THEN** its toll column shows `+1,15 €`

#### Scenario: A detour that pays less tolls

- **WHEN** a listed station has the `toll_difference` -1.25
- **THEN** its toll column shows `-1,25 €`

#### Scenario: A detour that does not change the tolls

- **WHEN** a listed station has the `toll_difference` 0
- **THEN** its toll column is empty

## MODIFIED Requirements

### Requirement: The optimal route and the split route offer a gas station icon

Beside the title of the optimal route and of the split route, the page SHALL show a gas station icon with the hover text `Find a gas station`. The icon SHALL come after the Google Maps link when the page shows that link. When the route has no link, the icon SHALL still be shown. The fastest route SHALL show no icon. After a finished plan, only the planned route SHALL show the icon, and a click on it SHALL do nothing.

#### Scenario: The optimal route

- **WHEN** the optimal route is listed with a Google Maps link
- **THEN** the gas station icon is shown after that link

#### Scenario: A split route without a link

- **WHEN** `super_optimal` carries a null `google_url`
- **THEN** its title shows the gas station icon and no Google Maps link

#### Scenario: The fastest route

- **WHEN** the fastest route is listed
- **THEN** its title shows no gas station icon

#### Scenario: After a finished plan

- **GIVEN** a plan on the optimal route is finished, and the journey has a split route
- **WHEN** the visitor clicks the gas station icon of the optimal route
- **THEN** no dialog opens, and the split route shows no gas station icon

### Requirement: Calculate stores the car values and sends one request

When every field is valid, `Calculate` SHALL store the four car values. It SHALL then send one request to `/api/refuel` with the origin, the destination, the route of the clicked icon, the car values, and the fuel. The request SHALL carry no chosen station. While the request is open, the dialog SHALL show that it is busy, and `Calculate` SHALL not send a second request.

#### Scenario: A valid form

- **WHEN** the visitor clicks `Calculate` on the icon of the split route with valid fields
- **THEN** the storage holds the four car values, and the page sends one request with the `route` `super_optimal`

#### Scenario: Calculate after a Use

- **GIVEN** the visitor clicked `Use` once, and the answer asked for another stop
- **WHEN** the visitor clicks `Calculate`
- **THEN** the request carries no chosen station

### Requirement: Cancel closes the dialog and changes nothing

`Cancel` SHALL close the dialog. It SHALL send no request and SHALL NOT change the storage. It SHALL drop the stations chosen in an unfinished plan, and the map SHALL show none of them.

#### Scenario: The visitor cancels

- **GIVEN** the storage holds the tank volume `50`
- **WHEN** the visitor changes the tank volume to `60` and clicks `Cancel`
- **THEN** the dialog closes, no request is sent, and the storage still holds `50`

#### Scenario: The visitor cancels an unfinished plan

- **GIVEN** the visitor clicked `Use` once, and the answer asked for another stop
- **WHEN** the visitor clicks `Cancel`, and then opens the dialog again
- **THEN** no black route or black dot is drawn, and the next `Calculate` carries no chosen station

### Requirement: The dialog lists the stations of the answer

When the answer has `stop_needed` true and stations, the dialog SHALL list the stations in the order of the answer, below the fields. Each row SHALL have six columns: the name as a link to `google_url` that opens in a new tab, the distance in whole km, the price per liter, the detour time in whole minutes with its sign, the toll change, and a green `Use` button. A null name SHALL be shown as `Unnamed station`. A `badge` SHALL be shown in bold after the name link.

#### Scenario: A listed station

- **WHEN** the answer lists the station `Leclerc` with the distance 235,400 m, the price `1.799`, and the detour time 420 s
- **THEN** the row shows `Leclerc` as a Google Maps link, `235 km`, `1,799 €/L`, `+7 min`, an empty toll cell, and a green `Use` button

#### Scenario: A station with a badge

- **WHEN** the answer lists the station `Leclerc` with the `badge` `"24"`
- **THEN** the first column shows the link `Leclerc`, then `24` in bold

#### Scenario: A station without a badge

- **WHEN** a listed station has the `badge` `null`
- **THEN** the first column shows only the name link

#### Scenario: A detour that saves time

- **WHEN** a listed station has the detour time -120 s
- **THEN** its detour column shows `-2 min`

#### Scenario: The fields stay

- **WHEN** the dialog lists the stations
- **THEN** the five fields stay in the dialog, and the visitor can change the fuel and click `Calculate` again

### Requirement: The dialog says when no stop is needed

When the answer has `stop_needed` false and the plan has no chosen station, the dialog SHALL show `No need to refuel: you'll arrive with <n> L.`, where `<n>` is `fuel_left` rounded down to a whole number.

#### Scenario: Enough fuel

- **WHEN** the answer is `{"stop_needed": false, "fuel_left": 12.7}`
- **THEN** the dialog shows `No need to refuel: you'll arrive with 12 L.`
