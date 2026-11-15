# Spec Delta

## MODIFIED Requirements

### Requirement: The bot says when no stop is needed

When no stop is needed and no station is chosen, the message SHALL start with `No need to refuel: you'll arrive with <n> L.` after a gauge press. After a typed range, it SHALL start with `No need to refuel: you'll arrive with <n> km of range.` `<n>` SHALL be rounded down to a whole number. The message SHALL have a `Drive with Google` button, which drives the route without a station.

#### Scenario: Enough fuel

- **WHEN** the plan says 12.7 L are left at the destination
- **THEN** the message starts with `No need to refuel: you'll arrive with 12 L.` and has a `Drive with Google` button

#### Scenario: Enough range

- **WHEN** the plan says 83.4 km of range are left at the destination
- **THEN** the message starts with `No need to refuel: you'll arrive with 83 km of range.`

#### Scenario: The route without a station is driven

- **WHEN** the driver presses that `Drive with Google`
- **THEN** the links and the Google requests are those of the `Drive with Google` button of the answer message

### Requirement: The driver chooses a station with a number button

A stop list, a destination list, and a cheaper list SHALL have one button for each station, labeled with its number, in rows of five. A press SHALL edit the list message into the two lines of that station only, with no buttons. The bot SHALL then plan again with every chosen station, in the order of choice.

#### Scenario: The keyboard of ten stations

- **WHEN** the plan lists 10 stations, and the share is 0
- **THEN** the keyboard has the rows `1 2 3 4 5` and `6 7 8 9 10`

#### Scenario: The keyboard of seven stations

- **WHEN** the plan lists 7 stations, and the share is 0
- **THEN** the keyboard has the rows `1 2 3 4 5` and `6 7`

#### Scenario: A press

- **WHEN** the driver presses `3`
- **THEN** the list message holds only the two lines of station 3, starting with `3. `, with no buttons, and the bot plans again with station 3 as the first chosen station

#### Scenario: A press on a cheaper list

- **GIVEN** the driver chose station A on an earlier list
- **WHEN** the driver presses `2` on a cheaper list
- **THEN** the cheaper list message holds only the two lines of its station 2, starting with `2. `, with no buttons, and the bot plans again with A and that station, in this order

#### Scenario: A press on a destination list

- **GIVEN** the fuel lasts to the destination
- **WHEN** the driver presses `2` on the destination list
- **THEN** the destination list message holds only the two lines of station 2, starting with `2. `, with no buttons, and the bot plans again with station 2 as the first chosen station

#### Scenario: A destination station finishes the plan

- **WHEN** the driver presses `2` on the destination list, and the route through station 2 reaches the destination with 30 L
- **THEN** the message of station 2 offers `Drive with Google`, and no other message follows it

### Requirement: A failed plan ends the plan

When the planner cannot route the journey, a chosen station, a split route, or a detour, the bot SHALL replace `⏳ Finding gas stations...` with `Error finding gas stations. I am very sorry for that 😞`. The plan SHALL end.

#### Scenario: The router does not answer

- **WHEN** the driver presses `1/2` and the routing service does not answer
- **THEN** the bot shows `Error finding gas stations. I am very sorry for that 😞`, and offers no button

#### Scenario: The router stops during the destination detours

- **GIVEN** the fuel lasts to the destination
- **WHEN** the routing service stops answering during the detours to the stations at the destination
- **THEN** the bot shows `Error finding gas stations. I am very sorry for that 😞`, and offers no button

### Requirement: An old refuel button changes nothing

A press on a `Plan refuel`, gauge, station, or cheaper button that is not open SHALL start no plan and no cheaper search, and SHALL make no Google request. The bot SHALL remove the buttons of that message and SHALL send `That route has expired. Please send the locations again.`

#### Scenario: A second press on a list

- **WHEN** the driver presses `3` and then `5` on the same list
- **THEN** the bot plans once, and answers the second press with `That route has expired. Please send the locations again.`

#### Scenario: A gauge after a typed range

- **WHEN** the driver types `120` at the fuel question, and then presses `1/2` on its gauge
- **THEN** the bot sends `That route has expired. Please send the locations again.`, and plans only for the range

#### Scenario: Plan refuel after Drive with Google

- **WHEN** the driver presses `Drive with Google`, and then an old copy of `Plan refuel` of the same answer
- **THEN** the bot sends `That route has expired. Please send the locations again.`, and asks no fuel question

#### Scenario: A cheaper button after a choice

- **WHEN** the driver presses `3` on a stop list, and then an old copy of its cheaper button
- **THEN** the bot sends `That route has expired. Please send the locations again.`, and routes no detour through a cheaper station

## ADDED Requirements

### Requirement: The no-stop answer lists the cheapest stations at the destination

When no stop is needed, no station is chosen, and the plan lists stations near the destination, the bot SHALL send one HTML message without a link preview. Its first line SHALL be the no-stop sentence, a space, and `Still, these are the <n> cheapest gas stations at your destination:`. `<n>` SHALL be the number of listed stations. An empty line SHALL follow, then the stations, as in a stop list.

#### Scenario: Ten stations

- **WHEN** 12.7 L are left at the destination, and the plan lists 10 stations
- **THEN** the first line is `No need to refuel: you'll arrive with 12 L. Still, these are the 10 cheapest gas stations at your destination:`, and the stations are numbered from 1 to 10 after an empty line

#### Scenario: Three stations with a range

- **WHEN** 83.4 km of range are left, and the plan lists 3 stations
- **THEN** the first line is `No need to refuel: you'll arrive with 83 km of range. Still, these are the 3 cheapest gas stations at your destination:`

#### Scenario: The station lines

- **WHEN** the first station is `Leclerc` without a badge, 410,300 m from the origin, with the price `1.799`, the detour 100 s, and the toll change 0
- **THEN** its lines are `1. <a href="https://www.google.com/maps/search/?api=1&amp;query=…">Leclerc</a> · 410 km` and `1.799 €/L · +2 min`

### Requirement: The keyboard of the destination list

The message with the stations at the destination SHALL have the number rows of its stations. The cheaper row SHALL follow them when the share of the list is above 0. The last row SHALL hold one `Drive with Google` button.

#### Scenario: Ten stations with a share of 6

- **WHEN** the plan lists 10 stations at the destination, and the share is 6
- **THEN** the keyboard has the rows `1 2 3 4 5`, `6 7 8 9 10`, `Cheaper? (6% of gas stations)`, and `Drive with Google`

#### Scenario: Three stations with a share of 0

- **WHEN** the plan lists 3 stations at the destination, and the share is 0
- **THEN** the keyboard has the rows `1 2 3` and `Drive with Google`

### Requirement: One destination station uses the singular

When the plan lists exactly one station near the destination, the text after the no-stop sentence SHALL be `Still, this is the cheapest gas station at your destination:`.

#### Scenario: One station

- **WHEN** 12.7 L are left at the destination, and the plan lists 1 station
- **THEN** the first line is `No need to refuel: you'll arrive with 12 L. Still, this is the cheapest gas station at your destination:`

### Requirement: No station at the destination is reported

When the plan lists no station near the destination, the message SHALL be the no-stop sentence, a space, and `No gas station sells this fuel within 50 km of your destination.`

#### Scenario: No station at the destination

- **WHEN** 12.7 L are left at the destination, and the plan lists no station
- **THEN** the bot sends `No need to refuel: you'll arrive with 12 L. No gas station sells this fuel within 50 km of your destination.` with one `Drive with Google` button

### Requirement: A choice on the destination list spends Drive with Google

A number press on a destination list or on its cheaper list SHALL spend the `Drive with Google` button of the destination list. A press on an old copy of that button SHALL make no Google request and SHALL get `That route has expired. Please send the locations again.`

#### Scenario: Drive with Google after a choice

- **WHEN** the driver presses `2` on the destination list, and then an old copy of its `Drive with Google`
- **THEN** the bot sends `That route has expired. Please send the locations again.`, and the month's count of Google requests does not change

### Requirement: Drive with Google closes the destination list

A press on the `Drive with Google` button of a destination list SHALL close that list and its cheaper list. A later press on one of their number buttons or on the cheaper button SHALL be a press on a button that is not open.

#### Scenario: A number after Drive with Google

- **WHEN** the driver presses `Drive with Google` on the destination list, and then an old copy of its `2`
- **THEN** the bot sends `That route has expired. Please send the locations again.`, and plans nothing

### Requirement: A stop list offers the cheaper stations with a button

When the share of a stop list is above 0, its keyboard SHALL end with a row of one button, `Cheaper? (<p>% of gas stations)`. `<p>` SHALL be the share. A share of 0 SHALL give no such row. This SHALL hold for the first stop list and for the list after a chosen station.

#### Scenario: Ten stations with a share of 6

- **WHEN** the plan lists 10 stations, and the share is 6
- **THEN** the keyboard has the rows `1 2 3 4 5`, `6 7 8 9 10`, and `Cheaper? (6% of gas stations)`

#### Scenario: Three stations with a share of 15

- **WHEN** the plan lists 3 stations, and the share is 15
- **THEN** the keyboard has the rows `1 2 3` and `Cheaper? (15% of gas stations)`

#### Scenario: A share of 0

- **WHEN** no stored station sells the fuel below the lowest price of the list
- **THEN** the keyboard has only the number rows

#### Scenario: The list after a chosen station

- **WHEN** the plan through the chosen station A lists the next stations, and the share is 4
- **THEN** the keyboard ends with the row `Cheaper? (4% of gas stations)`

### Requirement: A press on the cheaper button lists the cheaper stations

A press SHALL remove the cheaper row of its list and keep the other rows. The bot SHALL show `⏳ Finding gas stations...`, and SHALL replace it with the cheaper stations in the form of a stop list. The cheaper list SHALL have its number keyboard and no other button. The press SHALL cause no Google request.

#### Scenario: The press on a stop list

- **GIVEN** a stop list of 10 stations with the share 6
- **WHEN** the driver presses `Cheaper? (6% of gas stations)`, and the search finds 3 cheaper stations
- **THEN** the stop list keeps the rows `1 2 3 4 5` and `6 7 8 9 10`, and a new message lists the 3 stations with the row `1 2 3`

#### Scenario: The press on a destination list

- **GIVEN** a destination list of 3 stations with the share 8
- **WHEN** the driver presses `Cheaper? (8% of gas stations)`
- **THEN** the destination list keeps the rows `1 2 3` and `Drive with Google`

#### Scenario: The station lines

- **WHEN** the first cheaper station is `Total` without a badge, 120,400 m from the previous stop, with the price `1.699`, the detour 100 s, and the toll change 0
- **THEN** the cheaper list starts with `1. <a href="https://www.google.com/maps/search/?api=1&amp;query=…">Total</a> · 120 km` and `1.699 €/L · +2 min`

#### Scenario: No Google request

- **WHEN** the driver presses the cheaper button
- **THEN** the month's count of Google requests does not change

### Requirement: No cheaper station near the route is reported

When the cheaper search finds no station, the bot SHALL replace `⏳ Finding gas stations...` with `None of them is within 5 km of your route.`, without buttons. The list with the cheaper button SHALL stay open.

#### Scenario: No cheaper station near the route

- **WHEN** the driver presses the cheaper button of a stop list, and no station within 5 km of the route is below the lowest price of the list
- **THEN** the bot shows `None of them is within 5 km of your route.`, and a later press on `2` of the stop list chooses its station 2

### Requirement: A failed cheaper search keeps the list

When the planner cannot route a cheaper detour, the bot SHALL replace `⏳ Finding gas stations...` with `Error finding gas stations. I am very sorry for that 😞`. The list with the cheaper button SHALL stay open.

#### Scenario: The router stops after the stop list

- **WHEN** the routing service stops answering, and the driver presses the cheaper button of a stop list
- **THEN** the bot shows `Error finding gas stations. I am very sorry for that 😞`, and a later press on `2` of the stop list chooses its station 2

### Requirement: One stop has one choice

A number press on a stop list or a destination list, or on its cheaper list, SHALL close both lists. A later press on the other list SHALL be a press on a button that is not open.

#### Scenario: A choice on the cheaper list

- **WHEN** the driver presses `2` on the cheaper list, and then `5` on the stop list
- **THEN** the bot plans once, and answers the second press with `That route has expired. Please send the locations again.`

#### Scenario: A choice on the stop list

- **WHEN** the driver presses `5` on the stop list, and then `2` on the cheaper list
- **THEN** the bot plans once, and answers the second press with `That route has expired. Please send the locations again.`

#### Scenario: A choice on the cheaper list of a destination list

- **WHEN** the driver presses `2` on the cheaper list of a destination list, and then `1` on the destination list
- **THEN** the bot plans once, and answers the second press with `That route has expired. Please send the locations again.`

### Requirement: Only the cheaper button of the latest list works

Each new stop list or destination list of a driver SHALL close the cheaper button of the driver's earlier lists.

#### Scenario: A cheaper button of an earlier journey

- **GIVEN** the driver got a stop list with a cheaper button, and then a destination list for another journey
- **WHEN** the driver presses the cheaper button of the first list
- **THEN** the bot sends `That route has expired. Please send the locations again.`, and routes no detour through a cheaper station
