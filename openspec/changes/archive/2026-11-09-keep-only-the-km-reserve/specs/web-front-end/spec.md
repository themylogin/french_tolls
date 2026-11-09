# Spec Delta

## RENAMED Requirements

- FROM: `### Requirement: The icon opens a dialog with eight fields`
- TO: `### Requirement: The icon opens a dialog with seven fields`

## MODIFIED Requirements

### Requirement: The icon opens a dialog with seven fields

A click on the icon SHALL open a modal dialog with seven fields in this order: `Tank volume`, `Fuel type`, `Consumption at 80 km/h`, `Consumption at 130 km/h`, `Reserve`, `Fuel in the tank now`, and `Range now`. Each label SHALL be on the same line as its field. `Fuel type` SHALL be a group of three radio buttons: `Diesel`, `95`, and `98`. The dialog SHALL have the buttons `Cancel` and `Calculate`.

#### Scenario: The dialog opens

- **WHEN** the visitor clicks the gas station icon of the optimal route
- **THEN** a modal dialog opens with the seven fields and the buttons `Cancel` and `Calculate`, each label is on the line of its field, `Reserve` is directly above `Fuel in the tank now`, and `Range now` is directly below `Fuel in the tank now`

#### Scenario: The fuel type is a radio group

- **WHEN** the dialog opens
- **THEN** `Fuel type` shows the radio buttons `Diesel`, `95`, and `98`, and exactly one of them is selected

### Requirement: Each number field shows its unit inside the field

The tank volume, the two consumptions, the reserve, the fuel in the tank, and the range now SHALL each show their unit in grey inside the field, on the right: `L`, `L/100 km`, `L/100 km`, `km`, `L`, and `km`. A typed value SHALL NOT run under the unit. A marked field SHALL keep its unit visible.

#### Scenario: The units of the fields

- **WHEN** the dialog opens
- **THEN** `L` is inside the tank volume field and the fuel field, `L/100 km` is inside both consumption fields, and `km` is inside the reserve field and the range field, on the right, in grey

#### Scenario: A marked field

- **WHEN** the tank volume field is marked as invalid
- **THEN** its unit `L` is still visible

### Requirement: The browser keeps the car values and not the fuel or the range

The page SHALL keep the tank volume, the fuel type, the two consumptions, and the reserve in km in the local storage of the browser. When the dialog opens, it SHALL fill these five fields from the storage. When the storage holds no fuel type, `95` SHALL be selected. When the storage holds no reserve in km, the reserve field SHALL show `50`. A stored reserve in liters SHALL NOT be read. The fuel in the tank and the range SHALL NOT be stored, and their fields SHALL be empty each time the dialog opens.

#### Scenario: A second visit

- **GIVEN** the visitor calculated a fuel stop with the tank volume `50`, `Diesel`, `5.5`, `7.2`, the reserve `60`, and the fuel `20`
- **WHEN** the visitor reloads the page, calculates a route, and opens the dialog
- **THEN** the five car fields hold `50`, `Diesel`, `5.5`, `7.2`, and `60`, and the fuel field and the range field are empty

#### Scenario: A first visit

- **GIVEN** the storage holds no car values
- **WHEN** the visitor opens the dialog
- **THEN** the tank volume, the two consumptions, the fuel in the tank, and the range are empty, `95` is selected, and the reserve field shows `50`

#### Scenario: A storage from before the reserve

- **GIVEN** the storage holds the tank volume `50`, `Diesel`, `5.5`, and `7.2`, and no reserve
- **WHEN** the visitor opens the dialog
- **THEN** the four fields hold these values, and the reserve field shows `50`

#### Scenario: A storage from before the range reserve

- **GIVEN** the storage holds the tank volume `50`, `Diesel`, `5.5`, `7.2`, and only the reserve `8` in liters
- **WHEN** the visitor opens the dialog
- **THEN** the four fields hold these values, and the reserve field shows `50`

### Requirement: Calculate refuses a field that is empty or out of its limits

`Calculate` SHALL check each car field against the limits of `refuel-planning`, and the fuel and the range as "Calculate takes either the fuel or the range" specifies. A field that is empty or out of its limits SHALL be marked and SHALL show its message. The page SHALL then send no request and SHALL NOT change the storage. The messages SHALL be:

- `The tank volume must be a whole number of 30 or more.`
- `The consumption must be a number more than 0 and less than 30, for example 6.5.`
- `The reserve must be a number from 0 to 500 km.`
- `The fuel in the tank must be a number from 0 to the tank volume.`
- `The range must be a number from 0 to 3000 km.`

#### Scenario: An empty fuel field

- **WHEN** the visitor fills the five car fields, leaves the fuel field and the range field empty, and clicks `Calculate`
- **THEN** the fuel field shows `Enter the fuel in the tank or the range.`, and the page sends no request

#### Scenario: A fuel field that is out of its limits

- **WHEN** the visitor fills the five car fields with the tank volume `50`, enters the fuel `51`, leaves the range empty, and clicks `Calculate`
- **THEN** the fuel field shows `The fuel in the tank must be a number from 0 to the tank volume.`, and the page sends no request

#### Scenario: A tank below the limit

- **WHEN** the visitor enters the tank volume `29` and clicks `Calculate`
- **THEN** the tank volume field shows `The tank volume must be a whole number of 30 or more.`

#### Scenario: A reserve equal to the tank volume

- **WHEN** the visitor enters the tank volume `50` and the reserve `50` with valid other fields, and clicks `Calculate`
- **THEN** the reserve field is not marked, because the reserve in km has no link to the tank volume, and the page sends the request

#### Scenario: An empty reserve field

- **WHEN** the visitor clears the reserve field and clicks `Calculate`
- **THEN** the reserve field shows `The reserve must be a number from 0 to 500 km.`

#### Scenario: A range reserve above the limit

- **WHEN** the visitor enters the reserve `501` and clicks `Calculate`
- **THEN** the reserve field shows `The reserve must be a number from 0 to 500 km.`, and the page sends no request

#### Scenario: A range above the limit

- **WHEN** the visitor leaves the fuel empty, enters the range `3001`, and clicks `Calculate`
- **THEN** the range field shows `The range must be a number from 0 to 3000 km.`, and the page sends no request

#### Scenario: Invalid values are not stored

- **GIVEN** the storage holds the consumption at 80 km/h `5.5`
- **WHEN** the visitor changes it to `0` and clicks `Calculate`
- **THEN** the storage still holds `5.5`

### Requirement: Calculate stores the car values and sends one request

When every field is valid, `Calculate` SHALL store the five car values. It SHALL then send one request to `/api/refuel` with the origin, the destination, the route of the clicked icon, the car values with the reserve as `reserve_km`, and either the fuel or the range. The request SHALL carry no chosen station. While the request is open, the dialog SHALL show that it is busy, and `Calculate` SHALL not send a second request.

#### Scenario: A valid form

- **WHEN** the visitor clicks `Calculate` on the icon of the split route with valid fields
- **THEN** the storage holds the five car values, and the page sends one request with the `route` `super_optimal`

#### Scenario: The reserve reaches the request

- **WHEN** the visitor enters the reserve `60` with valid other fields, and clicks `Calculate`
- **THEN** the `car` object of the request has the `reserve_km` `60`, and no `reserve` key

#### Scenario: The range reaches the request

- **WHEN** the visitor leaves the fuel empty, enters the range `300` with valid other fields, and clicks `Calculate`
- **THEN** the request has the `range` `300` and no `fuel`

#### Scenario: Calculate after a Use

- **GIVEN** the visitor clicked `Use` once, and the answer asked for another stop
- **WHEN** the visitor clicks `Calculate`
- **THEN** the request carries no chosen station

### Requirement: Calculate takes either the fuel or the range

While the fuel field has text, the range field SHALL be disabled. While the range field has text, the fuel field SHALL be disabled. A field that becomes disabled SHALL lose its mark. `Calculate` SHALL need one of the two fields. When both are empty, it SHALL mark both with `Enter the fuel in the tank or the range.` The page SHALL then send no request and SHALL NOT change the storage.

#### Scenario: Both fields are empty

- **WHEN** the visitor fills the five car fields, leaves the fuel and the range empty, and clicks `Calculate`
- **THEN** both fields show `Enter the fuel in the tank or the range.`, and the page sends no request

#### Scenario: Text in one field disables the other

- **WHEN** the visitor types `20` in the fuel field
- **THEN** the range field is disabled, and loses its mark

#### Scenario: A cleared field activates the other

- **GIVEN** the visitor typed `300` in the range field
- **WHEN** the visitor clears the range field
- **THEN** the fuel field is active again

#### Scenario: Both fields are active on open

- **WHEN** the dialog opens
- **THEN** the fuel field and the range field are empty and active

#### Scenario: Only the range

- **WHEN** the visitor leaves the fuel empty, enters the range `300` with valid other fields, and clicks `Calculate`
- **THEN** the page sends the request

### Requirement: The dialog says when no station is near

When the answer has `stop_needed` true and no station, the dialog SHALL show `No gas station sells this fuel within 50 km of the point where the range left reaches <reserve> km.`, where `<reserve>` is the `reserve_km` that the request carried. This SHALL hold for a request with the fuel and for one with the range.

#### Scenario: An empty list

- **GIVEN** the request carried the fuel `20` and the `reserve_km` `7.5`
- **WHEN** the answer has `stop_needed` true and an empty `stations` list
- **THEN** the dialog shows `No gas station sells this fuel within 50 km of the point where the range left reaches 7.5 km.`

#### Scenario: An empty list after a range

- **GIVEN** the request carried the range `300`, the `reserve_km` `60`, and no chosen station
- **WHEN** the answer has `stop_needed` true and an empty `stations` list
- **THEN** the dialog shows `No gas station sells this fuel within 50 km of the point where the range left reaches 60 km.`
