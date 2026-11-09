# Proposal

## Why

The page plans fuel stops on a route, but the bot does not. A driver in the car uses the bot, and the bot is where the stops are useful. Gasolinera already lets a driver give the fuel on a gauge keyboard or as a typed range. This change brings that dialog and the stop list of the page into the bot. It also lets the page and the planner start from a range in km.

## What Changes

- **BREAKING** The answer of the bot asks two questions before it drives:
  1. Which route: `Super`, `Optimal`, and `Fastest`, each where it differs from the others. With nothing to choose, the bot skips this question. The superoptimal summary is titled `Superoptimal:`.
  2. What to do with the chosen route: `Drive with Google` or `Plan refuel`.
- The answer carries no directions link any more. A route that needs no Google request gets its link from `Drive with Google`, with no request.
- `Drive with Google` for the fastest route sends a link with no waypoints and makes no Google request.
- A press on `Plan refuel` without a stored car sends `Use /car to set up your car details in order to use this.` The button stays.
- With a car, the press removes the buttons of the answer. The bot asks the fuel with the gauge keyboard of gasolinera, for the gauge of the car. The driver presses a mark, or types the range in km. The bot then deletes the question.
- The bot lists the 10 cheapest stops, as gasolinera lists them, with a number keyboard. A press on a number keeps only the paragraph of that station in the list message.
  - When more fuel is needed, the bot lists the stations for the next stop, as the page does.
  - When the plan is finished, the paragraph of the last station gets `Drive with Google`. The press drives the route through the chosen stations by the rules of the drive flow.
  - When no stop is needed, the bot says so and sends `Drive with Google` for the route as it is.
- The bot plans on the chosen route, also on the fastest route. There, the detours go on the graph of the fastest route.
- The drive rules accept gas stations as stops. Every link of such a part goes through each chosen station, also a link that needs no Google request.
- **BREAKING** The car gets a second reserve, the range reserve in km, from 0 to 500. `/car` asks it after the reserve in liters, so the dialog has seven questions. Each stored car gets 50 km.
- **BREAKING** `POST /api/refuel` requires `reserve_km` in `car`. It takes either `fuel` in liters or `range` in km, not both.
- With a range, the planner walks the route by distance. The search point is where the range left reaches the range reserve. The first stop buys the tank volume minus the reserve in liters.
- The page gets two fields: `Range reserve` and `Range now`, both in km. The visitor fills either `Fuel in the tank now` or `Range now`.

## Capabilities

### New Capabilities

- `telegram-refuel-plan`: the bot dialog from `Plan refuel` to a finished plan: the car check, the gauge keyboard, the typed range, the station list and its keyboard, the next stops, the messages, and the expired buttons.

### Modified Capabilities

- `telegram-drive-flow`: the choice of route gets `Fastest`; the chosen route offers `Drive with Google` and `Plan refuel`; the answer carries no directions link; a part can have gas station stops, and every link goes through them.
- `car-parameters`: the range reserve, its question, its limits, its line, and the default for stored cars; the dialog has seven questions.
- `refuel-planning`: the request takes `fuel` or `range`, and `car` carries `reserve_km`; the range walk, the liters of a stop after a range walk, and `range_left`.
- `web-front-end`: the two range fields, the "fuel or range" rule, the storage of the range reserve, and the messages for a range.

## Impact

- Code: `french_tolls/bot.py`, `french_tolls/drive.py`, `french_tolls/refuel.py`, `french_tolls/route.py`, `french_tolls/car.py`, `french_tolls/api.py`, `french_tolls/models.py`, a new revision under `alembic/versions/`, `www/index.html`, and `www/index.js`.
- Tests: the unit tests of the car, the planner, and the drive decision; the integration tests of the car dialog, the drive flow, the refuel endpoint, and a new bot refuel flow.
- Data: each stored car gets a range reserve of 50 km.
- A page that the browser loaded before the deploy sends no `reserve_km`, and its dialog shows the error message. A reload fixes it.
- Google: a refuel plan makes no Google request. Only a press on `Drive with Google` can make one, as before.
- Unchanged: the route answers of the API, the station data, and the station costs.
