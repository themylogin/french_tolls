# Spec Delta

## MODIFIED Requirements

### Requirement: The page and the API answer on one origin

The page requests `/api/calculate`, `/api/autocomplete`, and `/api/refuel` as paths relative to its own origin. Whatever serves the page SHALL therefore also answer `/api/`, by proxying those requests to the aiohttp application over the Compose network.

The page SHALL NOT be given the API's address, and SHALL NOT be made to send a cross-origin request. A page carrying the address of its back end has to be rebuilt to be deployed anywhere else, and a cross-origin arrangement adds a preflight and a CORS policy to maintain in place of a proxy rule that states the same thing once.

The front end service SHALL be the only one of the application services publishing a host port. Two public ports serving overlapping things is an arrangement that can disagree with itself, and a driver who reaches the API port directly gets a 404 for the page.

#### Scenario: The page reaches the API

- **WHEN** a browser loads the page and calculates a route
- **THEN** its request to `/api/calculate` is answered by the aiohttp application

#### Scenario: The page reaches the refuel endpoint

- **WHEN** a visitor calculates a fuel stop in the gas station dialog
- **THEN** its request to `/api/refuel` is answered by the aiohttp application

#### Scenario: The API is not published separately

- **WHEN** the running services' published ports are listed
- **THEN** only the front end service publishes one

#### Scenario: The page carries no back end address

- **WHEN** the page's source is inspected
- **THEN** it names no host or port for the API

## ADDED Requirements

### Requirement: The optimal route and the split route offer a gas station icon

Beside the title of the optimal route and of the split route, the page SHALL show a gas station icon with the hover text `Find a gas station`. The icon SHALL come after the Google Maps link when the page shows that link. When the route has no link, the icon SHALL still be shown. The fastest route SHALL show no icon.

#### Scenario: The optimal route

- **WHEN** the optimal route is listed with a Google Maps link
- **THEN** the gas station icon is shown after that link

#### Scenario: A split route without a link

- **WHEN** `super_optimal` carries a null `google_url`
- **THEN** its title shows the gas station icon and no Google Maps link

#### Scenario: The fastest route

- **WHEN** the fastest route is listed
- **THEN** its title shows no gas station icon

### Requirement: The icon opens a dialog with five required fields

A click on the icon SHALL open a modal dialog with five fields in this order: `Tank volume`, `Fuel type`, `Consumption at 80 km/h`, `Consumption at 130 km/h`, and `Fuel in the tank now`. Each label SHALL be on the same line as its field. `Fuel type` SHALL be a group of three radio buttons: `Diesel`, `95`, and `98`. The dialog SHALL have the buttons `Cancel` and `Calculate`.

#### Scenario: The dialog opens

- **WHEN** the visitor clicks the gas station icon of the optimal route
- **THEN** a modal dialog opens with the five fields and the buttons `Cancel` and `Calculate`, and each label is on the line of its field

#### Scenario: The fuel type is a radio group

- **WHEN** the dialog opens
- **THEN** `Fuel type` shows the radio buttons `Diesel`, `95`, and `98`, and exactly one of them is selected

### Requirement: Each number field shows its unit inside the field

The tank volume, the two consumptions, and the fuel in the tank SHALL each show their unit in grey inside the field, on the right: `L`, `L/100 km`, `L/100 km`, and `L`. A typed value SHALL NOT run under the unit. A marked field SHALL keep its unit visible.

#### Scenario: The units of the fields

- **WHEN** the dialog opens
- **THEN** `L` is inside the tank volume field and the fuel field, and `L/100 km` is inside both consumption fields, on the right, in grey

#### Scenario: A marked field

- **WHEN** the tank volume field is marked as invalid
- **THEN** its unit `L` is still visible

### Requirement: The browser keeps the car values and not the fuel in the tank

The page SHALL keep the tank volume, the fuel type, and the two consumptions in the local storage of the browser. When the dialog opens, it SHALL fill these four fields from the storage. When the storage holds no fuel type, `95` SHALL be selected. The fuel in the tank SHALL NOT be stored, and its field SHALL be empty each time the dialog opens.

#### Scenario: A second visit

- **GIVEN** the visitor calculated a fuel stop with the tank volume `50`, `Diesel`, `5.5`, `7.2`, and the fuel `20`
- **WHEN** the visitor reloads the page, calculates a route, and opens the dialog
- **THEN** the four car fields hold `50`, `Diesel`, `5.5`, and `7.2`, and the fuel field is empty

#### Scenario: A first visit

- **GIVEN** the storage holds no car values
- **WHEN** the visitor opens the dialog
- **THEN** the tank volume, the two consumptions, and the fuel in the tank are empty, and `95` is selected

### Requirement: Calculate refuses a field that is empty or out of its limits

`Calculate` SHALL check each field against the limits of `refuel-planning`. A field that is empty or out of its limits SHALL be marked and SHALL show its message. The page SHALL then send no request and SHALL NOT change the storage. The messages SHALL be:

- `The tank volume must be a whole number of 30 or more.`
- `The consumption must be a number more than 0 and less than 30, for example 6.5.`
- `The fuel in the tank must be a number from 0 to the tank volume.`

#### Scenario: An empty fuel field

- **WHEN** the visitor fills the four car fields and clicks `Calculate` with an empty fuel field
- **THEN** the fuel field shows `The fuel in the tank must be a number from 0 to the tank volume.`, and the page sends no request

#### Scenario: A tank below the limit

- **WHEN** the visitor enters the tank volume `29` and clicks `Calculate`
- **THEN** the tank volume field shows `The tank volume must be a whole number of 30 or more.`

#### Scenario: Invalid values are not stored

- **GIVEN** the storage holds the consumption at 80 km/h `5.5`
- **WHEN** the visitor changes it to `0` and clicks `Calculate`
- **THEN** the storage still holds `5.5`

### Requirement: Calculate refuses a consumption at 130 km/h below the one at 80 km/h

When both consumptions are valid numbers and the consumption at 130 km/h is less than the consumption at 80 km/h, `Calculate` SHALL mark the 130 km/h field. The field SHALL show `The consumption at 130 km/h must be equal to or more than the consumption at 80 km/h.` The page SHALL then send no request and SHALL NOT change the storage. An equal value SHALL be valid.

#### Scenario: A lower value at 130 km/h

- **WHEN** the visitor enters `7.2` at 80 km/h and `5.5` at 130 km/h, and clicks `Calculate`
- **THEN** the 130 km/h field shows `The consumption at 130 km/h must be equal to or more than the consumption at 80 km/h.`, and the page sends no request

#### Scenario: An equal value

- **WHEN** the visitor enters `6` at 80 km/h and `6` at 130 km/h with valid other fields, and clicks `Calculate`
- **THEN** the page sends the request

### Requirement: Calculate stores the car values and sends one request

When every field is valid, `Calculate` SHALL store the four car values. It SHALL then send one request to `/api/refuel` with the origin, the destination, the route of the clicked icon, the car values, and the fuel. While the request is open, the dialog SHALL show that it is busy, and `Calculate` SHALL not send a second request.

#### Scenario: A valid form

- **WHEN** the visitor clicks `Calculate` on the icon of the split route with valid fields
- **THEN** the storage holds the four car values, and the page sends one request with the `route` `super_optimal`

### Requirement: Cancel closes the dialog and changes nothing

`Cancel` SHALL close the dialog. It SHALL send no request and SHALL NOT change the storage.

#### Scenario: The visitor cancels

- **GIVEN** the storage holds the tank volume `50`
- **WHEN** the visitor changes the tank volume to `60` and clicks `Cancel`
- **THEN** the dialog closes, no request is sent, and the storage still holds `50`

### Requirement: The dialog lists the stations of the answer

When the answer has `stop_needed` true and stations, the dialog SHALL list the stations in the order of the answer, below the fields. Each row SHALL have four columns: the name as a link to `google_url` that opens in a new tab, the distance in whole km, the price per liter, and the detour time in whole minutes with its sign. A null name SHALL be shown as `Unnamed station`.

#### Scenario: A listed station

- **WHEN** the answer lists the station `Leclerc` with the distance 235,400 m, the price `1.799`, and the detour time 420 s
- **THEN** the row shows `Leclerc` as a Google Maps link, `235 km`, `1,799 €/L`, and `+7 min`

#### Scenario: A detour that saves time

- **WHEN** a listed station has the detour time -120 s
- **THEN** its detour column shows `-2 min`

#### Scenario: The fields stay

- **WHEN** the dialog lists the stations
- **THEN** the five fields stay in the dialog, and the visitor can change the fuel and click `Calculate` again

### Requirement: The dialog says when no stop is needed

When the answer has `stop_needed` false, the dialog SHALL show `No need to refuel: you'll arrive with <n> L.`, where `<n>` is `fuel_left` rounded down to a whole number.

#### Scenario: Enough fuel

- **WHEN** the answer is `{"stop_needed": false, "fuel_left": 12.7}`
- **THEN** the dialog shows `No need to refuel: you'll arrive with 12 L.`

### Requirement: The dialog says when no station is near

When the answer has `stop_needed` true and no station, the dialog SHALL show `No gas station sells this fuel within 50 km of the point where the tank reaches 5 L.`

#### Scenario: An empty list

- **WHEN** the answer has `stop_needed` true and an empty `stations` list
- **THEN** the dialog shows `No gas station sells this fuel within 50 km of the point where the tank reaches 5 L.`

### Requirement: The dialog says when the request fails

When the request fails or the answer status is not 200, the dialog SHALL show `Error finding gas stations. I am very sorry for that 😞`

#### Scenario: A failed route

- **WHEN** `/api/refuel` answers with the status 502
- **THEN** the dialog shows `Error finding gas stations. I am very sorry for that 😞`, and the fields stay
