# Spec Delta

## RENAMED Requirements

- FROM: `### Requirement: A driver without a car gets seven questions in a fixed order`
- TO: `### Requirement: A driver without a car gets six questions in a fixed order`

## REMOVED Requirements

### Requirement: A car stored before the reserve in liters gets 5 L

**Reason**: The store no longer keeps a reserve in liters.

**Migration**: "A car stored before the gauge gets 16 steps" keeps the gauge rule. "A stored car keeps its reserve in km" states what the schema does with the reserves.

### Requirement: The reserve is a number of liters below the tank volume

**Reason**: The car has one reserve, in km.

**Migration**: "The reserve is a number from 0 to 500 km" gives the question, the limits, and the error message of that reserve.

### Requirement: The range reserve is a number from 0 to 500 km

**Reason**: The range reserve is now the only reserve, and its name and error message say "reserve".

**Migration**: "The reserve is a number from 0 to 500 km" keeps its limits.

### Requirement: A car stored before the range reserve gets 50 km

**Reason**: The schema now also drops the reserve in liters.

**Migration**: "A stored car keeps its reserve in km" keeps the 50 km default and adds the drop.

## MODIFIED Requirements

### Requirement: The store keeps one car for each driver

The store SHALL keep at most one car for each Telegram user id. A car SHALL have a fuel type, a tank volume in liters as an integer, two consumptions in liters per 100 km as floats, one at 80 km/h and one at 130 km/h, the gauge as its number of steps (24, 16, or 12), and the reserve in km as a float. When a driver saves new values, they SHALL replace the old values of that driver.

#### Scenario: A first save creates the car

- **GIVEN** the user `777001` has no car
- **WHEN** the user saves the tank volume `50`, the gauge `16`, the fuel type `diesel`, the consumptions `5.5` and `7.2`, and the reserve `50`
- **THEN** the store has one car for `777001` with these six values

#### Scenario: A second save replaces the car

- **GIVEN** the user `777001` has a car with the tank volume `50`
- **WHEN** the user saves the tank volume `60` and five other values
- **THEN** the store has one car for `777001`, with the tank volume `60`

#### Scenario: Two drivers have two cars

- **WHEN** the users `777001` and `777002` each save a car
- **THEN** each user gets the values that they saved, and not the values of the other user

### Requirement: A driver without a car gets six questions in a fixed order

When a driver without a car sends `/car`, the bot SHALL ask for the tank volume, then the gauge, then the fuel type, then the consumption at 80 km/h, then the consumption at 130 km/h, then the reserve. The bot SHALL ask the next question only after a valid answer to the current one.

#### Scenario: The questions come in order

- **GIVEN** the driver has no car
- **WHEN** the driver sends `/car`, then `50`, then presses `16`, then presses `Diesel`, then sends `5.5`, then `7.2`
- **THEN** the bot asks, in order, `Enter the tank volume in liters.`, `How many sections does your fuel gauge have?`, `Choose the fuel type.`, `Enter the consumption at 80 km/h in liters per 100 km.`, `Enter the consumption at 130 km/h in liters per 100 km.`, and `At how many kilometers of range do you want to refuel? Enter it, for example 50.`

### Requirement: The consumption at 130 km/h is not less than the consumption at 80 km/h

The bot SHALL refuse a consumption at 130 km/h that is less than the consumption at 80 km/h of the same dialog. It SHALL send an error message that names the consumption at 80 km/h, and SHALL ask for the consumption at 130 km/h again. The bot SHALL accept an equal value.

#### Scenario: A lower value at 130 km/h

- **GIVEN** the driver answered `7.2` to the consumption at 80 km/h
- **WHEN** the driver answers `5.5` to the consumption at 130 km/h
- **THEN** the bot sends `The consumption at 130 km/h must be equal to or more than the consumption at 80 km/h, 7.2 L/100 km. Enter it again.`, the next answer is again the consumption at 130 km/h, and the stored car does not change

#### Scenario: An equal value

- **GIVEN** the driver answered `6` to the consumption at 80 km/h
- **WHEN** the driver answers `6` to the consumption at 130 km/h
- **THEN** the bot asks `At how many kilometers of range do you want to refuel? Enter it, for example 50.`

### Requirement: The values are saved only after the last valid answer

The bot SHALL save the six values together after a valid answer to the reserve. It SHALL then send `Your car parameters are saved.` and the saved values. Before the last valid answer, the bot SHALL NOT change the stored car.

#### Scenario: A complete set of answers is saved

- **WHEN** the driver answers `50`, `16`, `Diesel`, `5.5`, `7.2`, and `50`
- **THEN** the store has the car `50`, `16`, `diesel`, `5.5`, `7.2`, `50`, and the bot sends `Your car parameters are saved.` followed by the values

#### Scenario: An unfinished set of answers is not saved

- **GIVEN** the driver has a car with the tank volume `50`
- **WHEN** the driver changes the tank volume to `60` and then sends `/car` again
- **THEN** the stored tank volume is still `50`

#### Scenario: The dialog stops before the reserve

- **GIVEN** the driver has a car with the reserve `50`
- **WHEN** the driver answers every question up to the consumption at 130 km/h, and then sends `/car` again
- **THEN** the stored reserve is still `50`

#### Scenario: The dialog stops before the range reserve

- **GIVEN** the driver has a car with the tank volume `50` and the reserve `50`
- **WHEN** the driver answers every question up to the consumption at 130 km/h with the tank volume `60`, and then sends `/car` again
- **THEN** the stored tank volume is still `50`, and the stored reserve is still `50`

### Requirement: The saved values are shown in one format

The bot SHALL show the values of a car as six lines: `Tank volume: <volume> L`, `Gauge: <steps> sections`, `Fuel type: <button label>`, `At 80 km/h: <consumption> L/100 km`, `At 130 km/h: <consumption> L/100 km`, and `Reserve: <reserve> km`. A consumption and a reserve SHALL be shown without trailing zeros.

#### Scenario: The values of a car

- **GIVEN** a car with the tank volume `50`, the gauge `16`, the fuel type `diesel`, the consumptions `5.5` and `7.0`, and the reserve `42.5`
- **WHEN** the bot shows the car
- **THEN** the lines are `Tank volume: 50 L`, `Gauge: 16 sections`, `Fuel type: Diesel`, `At 80 km/h: 5.5 L/100 km`, `At 130 km/h: 7 L/100 km`, and `Reserve: 42.5 km`

### Requirement: A driver with a car sees the values and chooses to change them

When a driver with a car sends `/car`, the bot SHALL send `Your car parameters:`, the values, and `Do you want to change them?`, with the buttons `Yes` and `No`. `Yes` SHALL start the six questions. `No` SHALL keep the values and send `Your car parameters are unchanged.` After a press, the message SHALL show no buttons.

#### Scenario: The driver keeps the values

- **GIVEN** the driver has a car
- **WHEN** the driver sends `/car` and presses `No`
- **THEN** the bot sends `Your car parameters are unchanged.`, asks no question, and the stored car does not change

#### Scenario: The driver changes the values

- **GIVEN** the driver has a car
- **WHEN** the driver sends `/car` and presses `Yes`
- **THEN** the bot asks for the tank volume, and then for each other value in order

## ADDED Requirements

### Requirement: The reserve is a number from 0 to 500 km

The bot SHALL accept as the reserve only a number from 0 to 500, written in digits, with a point or a comma before an optional decimal part. White space around the number is permitted. Any other answer SHALL make the bot send `The reserve must be a number from 0 to 500 km, for example 50. Enter it again.` and ask the same question again.

#### Scenario: A reserve

- **WHEN** the driver answers `60` to the reserve question
- **THEN** the bot saves the car with a reserve of 60 km

#### Scenario: No reserve

- **WHEN** the driver answers `0` to the reserve question
- **THEN** the bot saves the car with a reserve of 0 km

#### Scenario: A decimal comma

- **WHEN** the driver answers `42,5` to the reserve question
- **THEN** the bot saves the car with a reserve of 42.5 km

#### Scenario: A value outside the limits

- **WHEN** the driver answers `501`, `-1`, `fifty`, or `50 km` to the reserve question
- **THEN** the bot sends `The reserve must be a number from 0 to 500 km, for example 50. Enter it again.`, and the next answer is again a reserve

### Requirement: A car stored before the gauge gets 16 steps

A car that the store held before the gauge existed SHALL have a gauge of 16 steps once the schema is applied. Its other values SHALL NOT change, apart from the reserves that "A stored car keeps its reserve in km" describes.

#### Scenario: An old car

- **GIVEN** a car stored with only the tank volume, the fuel type, and the two consumptions
- **WHEN** the schema is applied
- **THEN** the car has a gauge of 16 steps and a reserve of 50 km, and its other values do not change

### Requirement: A stored car keeps its reserve in km

Once the schema is applied, a stored car SHALL have no reserve in liters. A reserve in liters SHALL NOT be converted to km. A car that the store held before the reserve in km existed SHALL have a reserve of 50 km. A car with a reserve in km SHALL keep it. The other values of the car SHALL NOT change.

#### Scenario: A car with a reserve in liters only

- **GIVEN** a car stored with the gauge `24` and the reserve `8` L, from before the reserve in km
- **WHEN** the schema is applied
- **THEN** the car has a reserve of 50 km and the gauge `24`, and its other values do not change

#### Scenario: A car with both reserves

- **GIVEN** a car stored with the gauge `24`, the reserve `8` L, and the reserve `60` km
- **WHEN** the schema is applied
- **THEN** the car has a reserve of 60 km and the gauge `24`, and no reserve in liters
