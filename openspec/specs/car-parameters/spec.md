# car-parameters Specification

## Purpose
Defines what the bot stores about the car of a driver, how the `/car` command collects and changes these values, the limits on each value, and the fuel types that the bot offers.

## Requirements

### Requirement: The store keeps one car for each driver

The store SHALL keep at most one car for each Telegram user id. A car SHALL have a fuel type, a tank volume in liters as an integer, two consumptions in liters per 100 km as floats, one at 80 km/h and one at 130 km/h, the gauge as its number of steps (24, 16, or 12), and the reserve in liters as a float. When a driver saves new values, they SHALL replace the old values of that driver.

#### Scenario: A first save creates the car

- **GIVEN** the user `777001` has no car
- **WHEN** the user saves the tank volume `50`, the gauge `16`, the fuel type `diesel`, the consumptions `5.5` and `7.2`, and the reserve `5`
- **THEN** the store has one car for `777001` with these six values

#### Scenario: A second save replaces the car

- **GIVEN** the user `777001` has a car with the tank volume `50`
- **WHEN** the user saves the tank volume `60` and five other values
- **THEN** the store has one car for `777001`, with the tank volume `60`

#### Scenario: Two drivers have two cars

- **WHEN** the users `777001` and `777002` each save a car
- **THEN** each user gets the values that they saved, and not the values of the other user

### Requirement: A car stored before the reserve in liters gets 5 L

A car that the store held before the reserve in liters existed SHALL have a reserve of 5 L once the schema is applied. A reserve in km SHALL NOT be converted. A car that the store held before the gauge existed SHALL also have a gauge of 16 steps. The other values of the car SHALL NOT change.

#### Scenario: An old car

- **GIVEN** a car stored with only the tank volume, the fuel type, and the two consumptions
- **WHEN** the schema is applied
- **THEN** the car has a gauge of 16 steps and a reserve of 5 L, and its other values do not change

#### Scenario: A car with a reserve in km

- **GIVEN** a car stored with the gauge `24` and the reserve `80` km
- **WHEN** the schema is applied
- **THEN** the car has a reserve of 5 L, and its gauge and its other values do not change

### Requirement: The bot offers the command /car

The command menu of the bot SHALL contain `/car` with the description `Enter car parameters`. The existing commands `/help` and `/reset` SHALL stay in the menu.

#### Scenario: The menu names the command

- **WHEN** the bot starts
- **THEN** it sets the commands `help`, `reset`, and `car`, and the description of `car` is `Enter car parameters`

### Requirement: A driver without a car gets six questions in a fixed order

When a driver without a car sends `/car`, the bot SHALL ask for the tank volume, then the gauge, then the fuel type, then the consumption at 80 km/h, then the consumption at 130 km/h, then the reserve. The bot SHALL ask the next question only after a valid answer to the current one.

#### Scenario: The questions come in order

- **GIVEN** the driver has no car
- **WHEN** the driver sends `/car`, then `50`, then presses `16`, then presses `Diesel`, then sends `5.5`, then `7.2`
- **THEN** the bot asks, in order, `Enter the tank volume in liters.`, `How many sections does your fuel gauge have?`, `Choose the fuel type.`, `Enter the consumption at 80 km/h in liters per 100 km.`, `Enter the consumption at 130 km/h in liters per 100 km.`, and `At how many liters left in the tank do you want to refuel? Enter it, for example 5.`

### Requirement: The tank volume is a whole number of 30 or more

The bot SHALL accept as the tank volume only a whole number of 30 or more, written in digits. White space around the digits is permitted. The bot SHALL refuse any other answer with an error message and SHALL ask the same question again.

#### Scenario: The lowest permitted volume

- **WHEN** the driver answers `30` to the tank volume question
- **THEN** the bot accepts it and asks for the gauge

#### Scenario: A volume below the limit

- **WHEN** the driver answers `29` to the tank volume question
- **THEN** the bot sends `The tank volume must be a whole number of 30 or more. Enter it again.`, and the next answer is again a tank volume

#### Scenario: A volume that is not a whole number

- **WHEN** the driver answers `50.5`, `50 l`, or `fifty` to the tank volume question
- **THEN** the bot refuses each answer with the same error message

#### Scenario: A number that the store cannot hold

- **WHEN** the driver answers `99999999999999999999` to the tank volume question
- **THEN** the bot refuses the answer with the same error message, and the bot does not fail

### Requirement: The gauge is chosen on a picture

The gauge question SHALL be one photo: three gauges side by side at one size, with no text on it. Its caption SHALL be `How many sections does your fuel gauge have?` It SHALL have one row of three buttons, `24`, `16`, and `12`. After a press, the caption SHALL become `Gauge: <steps> sections`, and the photo SHALL have no buttons.

#### Scenario: The driver presses 24

- **WHEN** the driver presses `24`
- **THEN** the caption becomes `Gauge: 24 sections`, and the bot asks `Choose the fuel type.` with the three fuel buttons

#### Scenario: Text instead of a button

- **WHEN** the driver types `24` while the gauge question is open
- **THEN** the bot sends the photo again with the caption `Choose your gauge with a button.` and the three buttons

### Requirement: One command renders the gauge picture

`make gauge-image` SHALL render `french_tolls/assets/gauges.png` from `gauge/12.png`, `gauge/8.jpg`, and `gauge/6.webp`, in a container. Each gauge SHALL be scaled to the same square size and SHALL keep its proportions. The gauges SHALL be in the order of the buttons `24`, `16`, `12`, and the picture SHALL have no text. The rendered picture SHALL be committed, and the bot SHALL NOT render it at run time.

#### Scenario: The picture is rendered

- **WHEN** `make gauge-image` runs
- **THEN** `french_tolls/assets/gauges.png` holds three gauges of one size side by side, with no text

#### Scenario: The application image has no image library

- **WHEN** the requirements of the application are read
- **THEN** they do not name Pillow

### Requirement: The fuel type is chosen with a button

The bot SHALL show the fuel type question with exactly three buttons, one on each row, in this order: `Diesel`, `95`, `98`. They SHALL store the fuel types `diesel`, `95`, and `98`. After a press, the question SHALL name the chosen type and SHALL show no buttons.

#### Scenario: A press selects the fuel type

- **WHEN** the driver presses `95`
- **THEN** the question changes to `Fuel type: 95` without buttons, and the bot asks for the consumption at 80 km/h

#### Scenario: A typed fuel type is refused

- **WHEN** the driver types `diesel` at the fuel type question
- **THEN** the bot sends `Choose the fuel type with a button.` with the three buttons again

### Requirement: A consumption is a number more than 0 and less than 30

The bot SHALL accept as a consumption only a number more than 0 and less than 30, written in digits, with a point or a comma before an optional decimal part. White space around the number is permitted. The bot SHALL refuse any other answer with an error message and SHALL ask the same question again.

#### Scenario: A decimal comma

- **WHEN** the driver answers `6,5` to a consumption question
- **THEN** the bot stores the consumption `6.5`

#### Scenario: Values inside the limits

- **WHEN** the driver answers `0.1`, `7`, or `29.9` to the consumption question at 80 km/h
- **THEN** the bot accepts the answer

#### Scenario: Values outside the limits

- **WHEN** the driver answers `0`, `30`, `-5`, `1e1`, `nan`, or `6.5 l` to a consumption question
- **THEN** the bot sends `The consumption must be a number more than 0 and less than 30, for example 6.5. Enter it again.`, and asks the same question again

### Requirement: The consumption at 130 km/h is not less than the consumption at 80 km/h

The bot SHALL refuse a consumption at 130 km/h that is less than the consumption at 80 km/h of the same dialog. It SHALL send an error message that names the consumption at 80 km/h, and SHALL ask for the consumption at 130 km/h again. The bot SHALL accept an equal value.

#### Scenario: A lower value at 130 km/h

- **GIVEN** the driver answered `7.2` to the consumption at 80 km/h
- **WHEN** the driver answers `5.5` to the consumption at 130 km/h
- **THEN** the bot sends `The consumption at 130 km/h must be equal to or more than the consumption at 80 km/h, 7.2 L/100 km. Enter it again.`, the next answer is again the consumption at 130 km/h, and the stored car does not change

#### Scenario: An equal value

- **GIVEN** the driver answered `6` to the consumption at 80 km/h
- **WHEN** the driver answers `6` to the consumption at 130 km/h
- **THEN** the bot asks `At how many liters left in the tank do you want to refuel? Enter it, for example 5.`

### Requirement: The reserve is a number of liters below the tank volume

The bot SHALL accept as the reserve only a number of 0 or more and less than the tank volume of the same dialog. The number SHALL be written in digits, with a point or a comma before an optional decimal part. White space around the number is permitted. Any other answer SHALL make the bot send an error message that names the tank volume, and ask the same question again.

#### Scenario: A reserve

- **GIVEN** the driver answered `50` to the tank volume
- **WHEN** the driver answers `5` to the reserve question
- **THEN** the bot saves the car with a reserve of 5 L

#### Scenario: No reserve

- **WHEN** the driver answers `0` to the reserve question
- **THEN** the bot saves the car with a reserve of 0 L

#### Scenario: A decimal comma

- **WHEN** the driver answers `7,5` to the reserve question
- **THEN** the bot saves the car with a reserve of 7.5 L

#### Scenario: A value that is too high

- **GIVEN** the driver answered `50` to the tank volume
- **WHEN** the driver answers `50` or `60` to the reserve question
- **THEN** the bot sends `The reserve must be a number of 0 or more and less than the tank volume, 50 L. Enter it again.`, and the next answer is again a reserve

#### Scenario: An answer that is not a number

- **GIVEN** the driver answered `50` to the tank volume
- **WHEN** the driver answers `-1`, `five`, or `5 l` to the reserve question
- **THEN** the bot sends the same reserve error, and the next answer is again a reserve

### Requirement: The values are saved only after the last valid answer

The bot SHALL save the six values together after a valid answer to the reserve. It SHALL then send `Your car parameters are saved.` and the saved values. Before the last valid answer, the bot SHALL NOT change the stored car.

#### Scenario: A complete set of answers is saved

- **WHEN** the driver answers `50`, `16`, `Diesel`, `5.5`, `7.2`, and `5`
- **THEN** the store has the car `50`, `16`, `diesel`, `5.5`, `7.2`, `5`, and the bot sends `Your car parameters are saved.` followed by the values

#### Scenario: An unfinished set of answers is not saved

- **GIVEN** the driver has a car with the tank volume `50`
- **WHEN** the driver changes the tank volume to `60` and then sends `/car` again
- **THEN** the stored tank volume is still `50`

#### Scenario: The dialog stops before the reserve

- **GIVEN** the driver has a car with the reserve `5`
- **WHEN** the driver answers every question up to the consumption at 130 km/h, and then sends `/car` again
- **THEN** the stored reserve is still `5`

### Requirement: The saved values are shown in one format

The bot SHALL show the values of a car as six lines: `Tank volume: <volume> L`, `Gauge: <steps> sections`, `Fuel type: <button label>`, `At 80 km/h: <consumption> L/100 km`, `At 130 km/h: <consumption> L/100 km`, and `Reserve: <reserve> L`. A consumption and a reserve SHALL be shown without trailing zeros.

#### Scenario: The values of a car

- **GIVEN** a car with the tank volume `50`, the gauge `16`, the fuel type `diesel`, the consumptions `5.5` and `7.0`, and the reserve `5.0`
- **WHEN** the bot shows the car
- **THEN** the lines are `Tank volume: 50 L`, `Gauge: 16 sections`, `Fuel type: Diesel`, `At 80 km/h: 5.5 L/100 km`, `At 130 km/h: 7 L/100 km`, and `Reserve: 5 L`

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

### Requirement: An open dialog takes the typed messages of the driver

From `/car` until the dialog ends, the bot SHALL treat each typed message of the driver as an answer to the current question. It SHALL NOT read the message as a location. A dialog ends when the values are saved, or when the driver presses `No`.

#### Scenario: A decimal comma is not a location

- **GIVEN** the driver has sent no origin
- **WHEN** the driver answers `6,5` to a consumption question
- **THEN** the bot accepts the consumption, and it does not reply `Now, send me the destination location`

#### Scenario: After the dialog, a typed message is not an answer

- **WHEN** the dialog has ended and the driver types `50`
- **THEN** the bot sends its help message, as it does for any text that is not a location

### Requirement: /car during a dialog starts the dialog again

When the driver sends `/car` during an open dialog, the bot SHALL drop the answers of that dialog and SHALL start again as for a first `/car`.

#### Scenario: The driver starts again

- **GIVEN** the driver has answered the tank volume `60`
- **WHEN** the driver sends `/car` again
- **THEN** the bot drops the answer `60`, and asks the first question of a new dialog

### Requirement: An old button does not change the values

A press on a gauge button, a fuel button, or a `Yes` or `No` button that does not belong to the current question SHALL NOT change the dialog or the store. The bot SHALL remove the buttons from that message and SHALL send `This question has expired. Send /car to start again.` A press on such a button SHALL NOT reach the route buttons.

#### Scenario: A fuel button after the dialog

- **GIVEN** the dialog has ended
- **WHEN** the driver presses a fuel button of that dialog
- **THEN** the bot sends `This question has expired. Send /car to start again.`, and the stored car does not change

#### Scenario: A gauge button of an earlier dialog

- **GIVEN** the driver sent `/car` and `50`, then `/car` and `50` again
- **WHEN** the driver presses `12` on the gauge photo of the first dialog
- **THEN** the bot sends `This question has expired. Send /car to start again.`, and the second dialog is still at its gauge question

#### Scenario: A car button is not a route button

- **WHEN** the driver presses an old car button
- **THEN** the bot does not send `That route has expired. Please send the locations again.`

### Requirement: The dialog belongs to one application

The open dialog and its answers SHALL belong to the bot application that received them. Two applications in one process SHALL NOT share a dialog.

#### Scenario: Two applications do not share a dialog

- **WHEN** two applications are built in one process, and the same user id sends `/car` to the first one only
- **THEN** the second application answers a typed `50` from that user with its help message, not with the next question

### Requirement: Each fuel type names the station fuels that it covers

The application SHALL keep, for each fuel type, the fuel names of the gas station table that the type covers, exactly as the station prices store them. `diesel` SHALL cover `Gazole (B7)`. `95` SHALL cover `SP95-E10 (E10)` and `SP95 (E5)`. `98` SHALL cover `SP98 (E5)`. No fuel type SHALL cover `E85 (E85)` or `GPLc (LPG)`.

#### Scenario: A 95 car covers two station fuels

- **WHEN** the station fuels of `95` are read
- **THEN** they are `SP95-E10 (E10)` and `SP95 (E5)`

#### Scenario: Diesel and 98 cover one station fuel each

- **WHEN** the station fuels of `diesel` and `98` are read
- **THEN** `diesel` gives `Gazole (B7)`, and `98` gives `SP98 (E5)`

#### Scenario: E85 and LPG are not covered

- **WHEN** the station fuels of all three fuel types are read
- **THEN** none of them is `E85 (E85)` or `GPLc (LPG)`

#### Scenario: The names match the store

- **WHEN** the covered names are compared with the fuel names in the prices of the gas station table
- **THEN** each covered name occurs there
