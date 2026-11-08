# Proposal

## Why

The `/car` dialog stores the reserve in km, but nothing reads it. The refuel plan uses a fixed reserve of 5 L instead. This change keeps one reserve, in liters, with 5 L as the default. The bot stores it, the page asks for it, and the refuel plan uses it.

## What Changes

- **BREAKING** The reserve of a car is in liters, not in km.
  - The bot asks `At how many liters left in the tank do you want to refuel? Enter it, for example 5.`
  - The bot accepts a number of 0 or more and less than the tank volume of the same dialog.
  - The bot shows the reserve as `Reserve: <reserve> L`.
- **BREAKING** The store drops the column `reserve_km` and adds the column `reserve`, with the default 5. Each stored car gets a reserve of 5 L. The old km values are not converted. The other values of the car stay.
- **BREAKING** `POST /api/refuel` requires `reserve` in the `car` object. It has the same limits as in the bot. A request without it gets the status 400.
- The refuel plan uses the reserve of the request in place of the fixed 5 L:
  - the search point is the first point where the tank holds the reserve or less;
  - no stop is planned when the fuel left at the destination is more than the reserve.
- The refuel dialog of the page gets a sixth field, `Reserve`, with the unit `L`, just above `Fuel in the tank now`.
  - The page keeps the reserve in the local storage with the other car values.
  - When the storage holds no reserve, the field shows `5`.
  - `Calculate` refuses a reserve that is empty or out of its limits, with `The reserve must be a number of 0 or more and less than the tank volume.`
- The message for no near station names the reserve of the request: `... where the tank reaches <reserve> L.`

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `car-parameters`:
  - the store keeps the reserve in liters;
  - the reserve question, its limits, and its error message;
  - the six-line format shows `L`;
  - stored cars get a reserve of 5 L;
  - the example answers use a reserve of 5.
- `refuel-planning`:
  - the request carries the reserve in `car`, with its limits;
  - the search point and the "no stop" rule use the reserve in place of 5 L.
- `web-front-end`:
  - the dialog has six fields, with `Reserve` before `Fuel in the tank now`;
  - the unit of the reserve field;
  - the storage keeps the reserve, with 5 as the default;
  - the reserve check and its message;
  - the request carries the reserve;
  - the "no station" message names the reserve.

## Impact

- Changed files:
  - `french_tolls/car.py`, `french_tolls/models.py`, `french_tolls/refuel.py`;
  - a new revision under `alembic/versions/`;
  - `www/index.html` and `www/index.js`;
  - the tests `french_tolls/tests/test_car.py`, `french_tolls/tests/test_refuel.py`, `french_tolls/integration/test_car_dialog.py`, and `french_tolls/integration/test_refuel_endpoint.py`.
- Data: the reserve values in km of the stored cars are lost. Each stored car gets 5 L. The operator accepts this loss.
- A page that the browser loaded before the deploy sends no `reserve`, and gets the error message of the dialog. A reload fixes it.
- Unchanged: the gauge, the other car questions, the route answers, and the drive flow of the bot. The bot does not plan a refuel yet.
