# Spec Delta

## RENAMED Requirements

- FROM: `### Requirement: The icon opens a dialog with five required fields`
- TO: `### Requirement: The icon opens a dialog with six required fields`

## MODIFIED Requirements

### Requirement: The icon opens a dialog with six required fields

A click on the icon SHALL open a modal dialog with six fields in this order: `Tank volume`, `Fuel type`, `Consumption at 80 km/h`, `Consumption at 130 km/h`, `Reserve`, and `Fuel in the tank now`. Each label SHALL be on the same line as its field. `Fuel type` SHALL be a group of three radio buttons: `Diesel`, `95`, and `98`. The dialog SHALL have the buttons `Cancel` and `Calculate`.

#### Scenario: The dialog opens

- **WHEN** the visitor clicks the gas station icon of the optimal route
- **THEN** a modal dialog opens with the six fields and the buttons `Cancel` and `Calculate`, each label is on the line of its field, and `Reserve` is directly above `Fuel in the tank now`

#### Scenario: The fuel type is a radio group

- **WHEN** the dialog opens
- **THEN** `Fuel type` shows the radio buttons `Diesel`, `95`, and `98`, and exactly one of them is selected

### Requirement: Each number field shows its unit inside the field

The tank volume, the two consumptions, the reserve, and the fuel in the tank SHALL each show their unit in grey inside the field, on the right: `L`, `L/100 km`, `L/100 km`, `L`, and `L`. A typed value SHALL NOT run under the unit. A marked field SHALL keep its unit visible.

#### Scenario: The units of the fields

- **WHEN** the dialog opens
- **THEN** `L` is inside the tank volume field, the reserve field, and the fuel field, and `L/100 km` is inside both consumption fields, on the right, in grey

#### Scenario: A marked field

- **WHEN** the tank volume field is marked as invalid
- **THEN** its unit `L` is still visible

### Requirement: The browser keeps the car values and not the fuel in the tank

The page SHALL keep the tank volume, the fuel type, the two consumptions, and the reserve in the local storage of the browser. When the dialog opens, it SHALL fill these five fields from the storage. When the storage holds no fuel type, `95` SHALL be selected. When the storage holds no reserve, the reserve field SHALL show `5`. The fuel in the tank SHALL NOT be stored, and its field SHALL be empty each time the dialog opens.

#### Scenario: A second visit

- **GIVEN** the visitor calculated a fuel stop with the tank volume `50`, `Diesel`, `5.5`, `7.2`, the reserve `8`, and the fuel `20`
- **WHEN** the visitor reloads the page, calculates a route, and opens the dialog
- **THEN** the five car fields hold `50`, `Diesel`, `5.5`, `7.2`, and `8`, and the fuel field is empty

#### Scenario: A first visit

- **GIVEN** the storage holds no car values
- **WHEN** the visitor opens the dialog
- **THEN** the tank volume, the two consumptions, and the fuel in the tank are empty, `95` is selected, and the reserve field shows `5`

#### Scenario: A storage from before the reserve

- **GIVEN** the storage holds the tank volume `50`, `Diesel`, `5.5`, and `7.2`, and no reserve
- **WHEN** the visitor opens the dialog
- **THEN** the four fields hold these values, and the reserve field shows `5`

### Requirement: Calculate refuses a field that is empty or out of its limits

`Calculate` SHALL check each field against the limits of `refuel-planning`. A field that is empty or out of its limits SHALL be marked and SHALL show its message. The page SHALL then send no request and SHALL NOT change the storage. The messages SHALL be:

- `The tank volume must be a whole number of 30 or more.`
- `The consumption must be a number more than 0 and less than 30, for example 6.5.`
- `The reserve must be a number of 0 or more and less than the tank volume.`
- `The fuel in the tank must be a number from 0 to the tank volume.`

#### Scenario: An empty fuel field

- **WHEN** the visitor fills the five car fields and clicks `Calculate` with an empty fuel field
- **THEN** the fuel field shows `The fuel in the tank must be a number from 0 to the tank volume.`, and the page sends no request

#### Scenario: A tank below the limit

- **WHEN** the visitor enters the tank volume `29` and clicks `Calculate`
- **THEN** the tank volume field shows `The tank volume must be a whole number of 30 or more.`

#### Scenario: A reserve equal to the tank volume

- **WHEN** the visitor enters the tank volume `50` and the reserve `50`, and clicks `Calculate`
- **THEN** the reserve field shows `The reserve must be a number of 0 or more and less than the tank volume.`, and the page sends no request

#### Scenario: An empty reserve field

- **WHEN** the visitor clears the reserve field and clicks `Calculate`
- **THEN** the reserve field shows `The reserve must be a number of 0 or more and less than the tank volume.`

#### Scenario: Invalid values are not stored

- **GIVEN** the storage holds the consumption at 80 km/h `5.5`
- **WHEN** the visitor changes it to `0` and clicks `Calculate`
- **THEN** the storage still holds `5.5`

### Requirement: Calculate stores the car values and sends one request

When every field is valid, `Calculate` SHALL store the five car values. It SHALL then send one request to `/api/refuel` with the origin, the destination, the route of the clicked icon, the car values with the reserve, and the fuel. The request SHALL carry no chosen station. While the request is open, the dialog SHALL show that it is busy, and `Calculate` SHALL not send a second request.

#### Scenario: A valid form

- **WHEN** the visitor clicks `Calculate` on the icon of the split route with valid fields
- **THEN** the storage holds the five car values, and the page sends one request with the `route` `super_optimal`

#### Scenario: The reserve reaches the request

- **WHEN** the visitor enters the reserve `8` with valid other fields, and clicks `Calculate`
- **THEN** the `car` object of the request has the `reserve` `8`

#### Scenario: Calculate after a Use

- **GIVEN** the visitor clicked `Use` once, and the answer asked for another stop
- **WHEN** the visitor clicks `Calculate`
- **THEN** the request carries no chosen station

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
- **THEN** the six fields stay in the dialog, and the visitor can change the fuel and click `Calculate` again

### Requirement: The dialog says when no station is near

When the answer has `stop_needed` true and no station, the dialog SHALL show `No gas station sells this fuel within 50 km of the point where the tank reaches <reserve> L.`, where `<reserve>` is the reserve that the request carried.

#### Scenario: An empty list

- **GIVEN** the request carried the reserve `7.5`
- **WHEN** the answer has `stop_needed` true and an empty `stations` list
- **THEN** the dialog shows `No gas station sells this fuel within 50 km of the point where the tank reaches 7.5 L.`
