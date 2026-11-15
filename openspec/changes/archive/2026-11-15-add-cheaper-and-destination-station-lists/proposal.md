# Proposal

## Why

Gasolinera got two refuel features on 2026-11-14 that the bot of french_tolls does not have. First, the stop list ranks stations near one search point. Cheaper stations often sit earlier on the route, and the driver does not see them. Second, a journey that needs no stop gets only `No need to refuel: …`. The driver gets no advice on where to refuel later.

## What Changes

- The planner of the bot takes the lowest price of a stop list or a destination list as the reference price. It gives the share of all stored stations that sell the fuel of the car below that price, rounded up.
- When the share is above 0, the list message gets a last keyboard row with one button: `Cheaper? (<p>% of gas stations)`. For 10 stations, the rows are `1 2 3 4 5`, `6 7 8 9 10`, and the cheaper button. A share of 0 gives no cheaper button.
- Only a press on the cheaper button starts the cheaper search. The press removes the cheaper button and keeps the other buttons of the list.
- The cheaper search takes every station within 5 km of the route that sells the fuel of the car below the reference price. It looks from the start of the walk to the search point. The start of the walk is the origin or the last chosen station.
- It keeps the 10 stations that are latest on the route. It routes a detour through each one and lists them by cost, as the stop list does.
- The bot sends the cheaper stations as a new list, with the station lines and the number keyboard of the stop list. A press on a number chooses that station, as on the stop list. The bot then plans again through it.
- One stop has one choice. A press on a number of either list closes both lists.
- Only the cheaper button of the latest stop list or destination list of a driver works. A press on an older one gets `That route has expired. Please send the locations again.`
- Without a cheaper station near the route, the bot sends `None of them is within 5 km of your route.` without buttons.
- When no stop is needed and no station is chosen, the bot still lists the stations near the destination. They are ranked by the cost of a stop, as in a stop list.
  - The text is the no-stop sentence, then `Still, these are the <n> cheapest gas stations at your destination:`, an empty line, and the stations.
  - With one station, the text after the sentence is `Still, this is the cheapest gas station at your destination:`.
  - With no station, the text after the sentence is `No gas station sells this fuel within 50 km of your destination.`
- The destination list has the number buttons, the cheaper button when its share is above 0, and `Drive with Google` as the last row.
  - A press on a number chooses that station. The bot plans again through it, and the plan is then finished.
  - The cheaper button searches from the origin to the destination, below the lowest price of the destination list. Its stations are chosen as on any cheaper list.
  - A choice on the destination list or its cheaper list spends `Drive with Google`. A press on `Drive with Google` closes both lists.
- The planner of the bot accepts a station from a destination list or a cheaper list, also when the fuel lasts without it. `POST /api/refuel` still refuses a station that the plan does not need.
- A no-stop answer now requests detours. When the router fails during them, the bot sends the error text of a failed plan.

Assumptions, recorded for review:

- "The same way" means the cheaper list has number buttons, and a press chooses the station. Without them, the list is a dead end in a dialog that exists to choose stops.
- `POST /api/refuel` and the web page do not change. The request named only the Telegram bot.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `telegram-refuel-plan`: the cheaper button on a stop list and on the destination list, the cheaper list and its keyboard, one choice per stop, the expired cheaper button, and the destination list with its keyboard in the no-stop answer.
- `refuel-planning`: for the bot only, the destination list when no stop is needed, the reference price and the share, the route stations, the cheaper selection, and the cheaper detours. A chosen station from a destination list or a cheaper list is placed at its own route point, also when the fuel lasts.

## Impact

- `french_tolls/refuel.py`: the stop list moves into a helper that both answers use. New code finds the route stations, selects the cheaper ones, and routes their detours. `through_chosen` places a chosen station from a destination list or a cheaper list at its route point.
- `french_tolls/gas_stations.py`: a new query counts the stored stations of a fuel type, and the ones below a price.
- `french_tolls/refuel_chat.py`: new texts for the destination list, the cheaper button, and an empty cheaper list.
- `french_tolls/bot.py`: the cheaper button, its handler, the cheaper list, the keyboard of the destination list, and the closing of both lists on a choice or on `Drive with Google`.
- Tests: `french_tolls/tests/test_refuel.py`, `french_tolls/tests/test_refuel_chat.py`, `french_tolls/tests/test_gas_stations.py`, and `french_tolls/integration/test_refuel_flow.py`.
- Router load: a press on the cheaper button routes up to 10 detours, with no more than four open at once. A no-stop answer routes up to 30 detours, as a stop list does. The stop list itself routes nothing more.
- Memory: the bot keeps one planned route for each driver, for the cheaper button of their latest list.
- No Google request, no schema change, no new dependency, no new configuration variable.
