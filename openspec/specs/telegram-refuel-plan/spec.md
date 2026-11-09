# telegram-refuel-plan Specification

## Purpose

Defines the bot dialog that plans the fuel stops of a journey: from the `Plan refuel` button, through the fuel question and the station lists, to a plan that the driver can drive with Google.

## Requirements

### Requirement: Plan refuel without a car points to /car

When a driver without a stored car presses `Plan refuel`, the bot SHALL send `Use /car to set up your car details in order to use this.` The buttons of the answer message SHALL stay. The press SHALL change no state.

#### Scenario: No car

- **GIVEN** the driver has no car
- **WHEN** the driver presses `Plan refuel`
- **THEN** the bot sends `Use /car to set up your car details in order to use this.`, and the answer message keeps its buttons

#### Scenario: A press after /car

- **GIVEN** the driver pressed `Plan refuel` without a car, and then saved a car with `/car`
- **WHEN** the driver presses the same `Plan refuel` again
- **THEN** the bot asks the fuel question

### Requirement: Plan refuel asks how much fuel is left

With a stored car, a press on `Plan refuel` SHALL remove the buttons of the answer message, and SHALL spend its `Drive with Google` button. The bot SHALL send `How much fuel do you have? Choose it on the gauge or enter the range in kilometers.` with the gauge keyboard of the car. The plan SHALL use the car as stored at this press. The press SHALL cause no Google request.

#### Scenario: The fuel question

- **GIVEN** the driver has a car with a gauge of 16 steps
- **WHEN** the driver presses `Plan refuel`
- **THEN** the answer message has no buttons, and the bot sends the fuel question with the 16-step gauge

#### Scenario: Drive with Google is spent

- **WHEN** the driver presses `Plan refuel`, and then an old copy of the `Drive with Google` button of the same answer
- **THEN** the bot sends `That route has expired. Please send the locations again.`, and makes no Google request

### Requirement: The fuel question shows the gauge of the car

The keyboard SHALL be the gauge of the car: 24, 16, or 12 steps. Each row SHALL run from full to empty, with one button for each step. A row SHALL start with the label that ends the row before it, and both buttons SHALL have the same step.

#### Scenario: The 24-step gauge

- **WHEN** the car has a gauge of 24 steps
- **THEN** the rows are `1 . . | . . 3/4`, `3/4 . . | . . 1/2`, `1/2 . . | . . 1/4`, and `1/4 . . | . . 0`, for the steps 24 down to 0

#### Scenario: The 16-step gauge

- **WHEN** the car has a gauge of 16 steps
- **THEN** the rows are `1 . | , 3/4`, `3/4 . | , 1/2`, `1/2 . | , 1/4`, and `1/4 . | , 0`, for the steps 16 down to 0

#### Scenario: The 12-step gauge

- **WHEN** the car has a gauge of 12 steps
- **THEN** the rows are `1 . 5/6 . 2/3 . 1/2` and `1/2 . 1/3 . 1/6 . 0`, for the steps 12 down to 0

#### Scenario: Two buttons with one step

- **GIVEN** a car with a gauge of 16 steps
- **WHEN** the driver presses the `3/4` at the end of the first row, or the `3/4` at the start of the second row
- **THEN** the fuel is three quarters of the tank in both cases

### Requirement: A gauge press gives the fuel in liters

A press SHALL plan with the tank volume multiplied by the step and divided by the steps of the gauge, in liters. The bot SHALL delete the fuel question.

#### Scenario: Half a tank

- **GIVEN** a car with a tank of 50 L and a gauge of 16 steps
- **WHEN** the driver presses `1/2`
- **THEN** the fuel question is deleted, and the plan starts with 25 L

#### Scenario: A mark between two labels

- **GIVEN** a car with a tank of 50 L and a gauge of 24 steps
- **WHEN** the driver presses the `|` for step 21
- **THEN** the plan starts with 43.75 L

#### Scenario: An empty tank

- **GIVEN** a car with a tank of 50 L
- **WHEN** the driver presses `0`
- **THEN** the plan starts with 0 L

### Requirement: A typed number is the range in kilometers

While the fuel question is open, the bot SHALL read a typed text as a range before it reads a location. A range SHALL be a number from 0 to 3000, with a point or a comma before an optional decimal part. A valid range SHALL start the plan, and the bot SHALL delete the fuel question.

#### Scenario: A range

- **WHEN** the fuel question is open and the driver types `120`
- **THEN** the fuel question is deleted, and the plan starts with a range of 120 km

#### Scenario: A decimal comma

- **WHEN** the fuel question is open and the driver types `87,5`
- **THEN** the plan starts with a range of 87.5 km

### Requirement: Other text at the fuel question is refused

While the fuel question is open, a typed text that is not a range SHALL get `Choose it on the gauge or enter the range in kilometers, for example 120.` The question SHALL stay open.

#### Scenario: Text that is not a range

- **WHEN** the fuel question is open and the driver types `half`, `3001`, or `48.85, 2.35`
- **THEN** the bot sends `Choose it on the gauge or enter the range in kilometers, for example 120.`, and a later gauge press starts the plan

### Requirement: A location or /reset closes the fuel question

A shared location or `/reset` SHALL close the open fuel question of the driver. The bot SHALL treat the location as it does when no question is open. A second press on `Plan refuel` SHALL close the earlier fuel question.

#### Scenario: A shared location

- **WHEN** the fuel question is open and the driver shares a location
- **THEN** the bot sends `Now, send me the destination location`, and a press on the gauge of that question is an old button

#### Scenario: /reset

- **WHEN** the fuel question is open and the driver sends `/reset`, and then types `120`
- **THEN** the bot sends its help message for `120`, and starts no plan

### Requirement: The bot plans on the route of the answer

The bot SHALL plan by the rules of `refuel-planning` on the chosen route: the superoptimal, the optimal, or the fastest route. On the fastest route, the detours SHALL be routed on the graph of the fastest route. While it plans, the bot SHALL show `⏳ Finding gas stations...`, and the answer SHALL replace that text. A plan SHALL cause no Google request.

#### Scenario: A chosen fastest route

- **GIVEN** the driver pressed `Fastest`, and then `Plan refuel`
- **WHEN** the driver presses `1/2` on the gauge
- **THEN** the bot plans along the fastest route, and routes each detour on its graph

#### Scenario: A chosen superoptimal route

- **GIVEN** the driver pressed `Super`, and then `Plan refuel`
- **WHEN** the driver presses `1/2` on the gauge
- **THEN** the bot plans on the superoptimal route, and the month's count of Google requests does not change

### Requirement: The bot says when no stop is needed

When no stop is needed and no station is chosen, the bot SHALL send `No need to refuel: you'll arrive with <n> L.` after a gauge press. After a typed range, it SHALL send `No need to refuel: you'll arrive with <n> km of range.` `<n>` SHALL be rounded down to a whole number. The message SHALL have one `Drive with Google` button, which drives the route without a station.

#### Scenario: Enough fuel

- **WHEN** the plan says 12.7 L are left at the destination
- **THEN** the bot sends `No need to refuel: you'll arrive with 12 L.` with a `Drive with Google` button

#### Scenario: Enough range

- **WHEN** the plan says 83.4 km of range are left at the destination
- **THEN** the bot sends `No need to refuel: you'll arrive with 83 km of range.`

#### Scenario: The route without a station is driven

- **WHEN** the driver presses that `Drive with Google`
- **THEN** the links and the Google requests are those of the `Drive with Google` button of the answer message

### Requirement: The stations are listed in one message

When a stop is needed, the bot SHALL send the stations in one HTML message without a link preview and without a header. The stations SHALL be numbered from 1, in the order of the plan, with an empty line between two stations.

#### Scenario: Ten stations

- **WHEN** the plan lists 10 stations
- **THEN** the bot sends one message whose first line is the first line of station 1, and the stations are numbered from 1 to 10

### Requirement: Each listed station has two lines

The first line SHALL be the number, the name as a link to the Google Maps position of the station, the badge in bold when the station has one, then ` · ` and the distance from the previous stop in whole km. The second line SHALL be the price with three decimals and ` €/L`, then ` · ` and the detour in whole minutes with a sign. When the toll change is not 0.00, the second line SHALL end with ` · ` and the toll change with a sign, two decimals, and ` €`.

#### Scenario: One station

- **WHEN** the first station is `Leclerc` with the badge `24`, the distance from the previous stop 235,400 m, the price `1.799`, the detour 420 s, and the toll change 0
- **THEN** its lines are `1. <a href="https://www.google.com/maps/search/?api=1&amp;query=…">Leclerc</a> <b>24</b> · 235 km` and `1.799 €/L · +7 min`

#### Scenario: A detour that pays more tolls

- **WHEN** a listed station has the toll change 1.15 and the detour 420 s
- **THEN** its second line ends with `· +7 min · +1.15 €`

#### Scenario: A detour that saves time and tolls

- **WHEN** a listed station has the detour -120 s and the toll change -1.25
- **THEN** its second line ends with `· -2 min · -1.25 €`

#### Scenario: No badge

- **WHEN** a listed station has no badge
- **THEN** its first line has no bold text

### Requirement: The station texts are safe HTML

The bot SHALL escape the name and the badge of a station for HTML. An empty or missing name SHALL be shown as `Unnamed station`.

#### Scenario: A name with HTML characters

- **WHEN** the station name is `A&B <24h>`
- **THEN** the message shows `A&amp;B &lt;24h&gt;`

#### Scenario: No name

- **WHEN** the station name is null
- **THEN** the message shows `Unnamed station` as the link text

### Requirement: The driver chooses a station with a number button

The list message SHALL have one button for each station, labeled with its number, in rows of five. A press SHALL edit the list message into the two lines of that station only, with no buttons. The bot SHALL then plan again with every chosen station, in the order of choice.

#### Scenario: The keyboard of ten stations

- **WHEN** the plan lists 10 stations
- **THEN** the keyboard has the rows `1 2 3 4 5` and `6 7 8 9 10`

#### Scenario: The keyboard of seven stations

- **WHEN** the plan lists 7 stations
- **THEN** the keyboard has the rows `1 2 3 4 5` and `6 7`

#### Scenario: A press

- **WHEN** the driver presses `3`
- **THEN** the list message holds only the two lines of station 3, starting with `3. `, with no buttons, and the bot plans again with station 3 as the first chosen station

### Requirement: A plan that needs another stop lists the next stations

When the plan with the chosen stations needs another stop, the bot SHALL send a new list for that stop, with its own number buttons. A press on it SHALL add its station after the stations chosen before.

#### Scenario: A second stop

- **GIVEN** the driver chose station A, and the plan through A needs another stop
- **WHEN** the bot lists the stations for that stop, and the driver presses `2` on station B
- **THEN** the bot plans again with the chosen stations A and B, in this order

#### Scenario: The distance of a later list

- **WHEN** a station of the second list is 310 km from A and 530 km from the origin
- **THEN** its first line ends with `· 310 km`

### Requirement: A finished plan offers Drive with Google

When the plan with the chosen stations needs no more stop, the bot SHALL delete `⏳ Finding gas stations...`. It SHALL add one `Drive with Google` button to the message of the last chosen station, and SHALL send no other message. The press SHALL drive the route through the chosen stations, as `telegram-drive-flow` drives a refuel plan.

#### Scenario: The plan is ready

- **WHEN** the route through the chosen stations A and B reaches the destination with 12.7 L
- **THEN** the message of station B offers `Drive with Google`, no other message follows it, and the bot makes no Google request

#### Scenario: The plan is driven

- **WHEN** the driver presses that `Drive with Google`
- **THEN** each link that the bot sends goes through A and B

### Requirement: A plan with too many stops for one link is not offered

When the chosen stations and the stops of a split route are more than one directions link carries, the finished plan SHALL get `The refuel plan has too many stops for one Google Maps link.` The message SHALL have no button.

#### Scenario: Too many stops

- **WHEN** the plan is finished with 8 chosen stations on a split route with 2 stops
- **THEN** the bot sends `The refuel plan has too many stops for one Google Maps link.`, and offers no button

### Requirement: The bot says when no station is near

When a stop is needed and the list is empty, the bot SHALL send `No gas station sells this fuel within 50 km of the point where the range left reaches <reserve> km.`, with the reserve of the car in km. This SHALL hold after a gauge press, after a typed range, and after a chosen station. The plan SHALL end.

#### Scenario: No station after a gauge press

- **GIVEN** the car has the reserve `50`
- **WHEN** the plan after a gauge press lists no station
- **THEN** the bot sends `No gas station sells this fuel within 50 km of the point where the range left reaches 50 km.`

#### Scenario: No station after a typed range

- **GIVEN** the car has the reserve `42.5`
- **WHEN** the plan after a typed range, with no chosen station, lists no station
- **THEN** the bot sends `No gas station sells this fuel within 50 km of the point where the range left reaches 42.5 km.`

#### Scenario: No station after a chosen station

- **GIVEN** the plan started from a typed range, the driver chose a station, and the car has the reserve `50`
- **WHEN** the next plan lists no station
- **THEN** the bot sends `No gas station sells this fuel within 50 km of the point where the range left reaches 50 km.`

### Requirement: A failed plan ends the plan

When the planner cannot route the journey, a chosen station, or a split route, the bot SHALL replace `⏳ Finding gas stations...` with `Error finding gas stations. I am very sorry for that 😞`. The plan SHALL end.

#### Scenario: The router does not answer

- **WHEN** the driver presses `1/2` and the routing service does not answer
- **THEN** the bot shows `Error finding gas stations. I am very sorry for that 😞`, and offers no button

### Requirement: An old refuel button changes nothing

A press on a `Plan refuel`, gauge, or station button that is not open SHALL start no plan and SHALL make no Google request. The bot SHALL remove the buttons of that message and SHALL send `That route has expired. Please send the locations again.`

#### Scenario: A second press on a list

- **WHEN** the driver presses `3` and then `5` on the same list
- **THEN** the bot plans once, and answers the second press with `That route has expired. Please send the locations again.`

#### Scenario: A gauge after a typed range

- **WHEN** the driver types `120` at the fuel question, and then presses `1/2` on its gauge
- **THEN** the bot sends `That route has expired. Please send the locations again.`, and plans only for the range

#### Scenario: Plan refuel after Drive with Google

- **WHEN** the driver presses `Drive with Google`, and then an old copy of `Plan refuel` of the same answer
- **THEN** the bot sends `That route has expired. Please send the locations again.`, and asks no fuel question

### Requirement: The refuel dialog belongs to one application

The open fuel question, the open lists, and the chosen stations SHALL belong to the bot application that received them. Two applications in one process SHALL NOT share them.

#### Scenario: Two applications do not share a fuel question

- **WHEN** two applications are built in one process, and the same user id opens a fuel question in the first one only
- **THEN** the second application answers a typed `120` from that user with its help message
