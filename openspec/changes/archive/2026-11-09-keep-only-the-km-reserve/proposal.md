# Proposal

## Why

A car has two reserves now: one in liters for a fuel in liters, and one in km for a typed range. A driver thinks of one reserve: "I refuel when 50 km are left". Two reserves cost a question in `/car` and a field on the page, and they can disagree. This change keeps only the reserve in km. A driver can still give the fuel in liters, on the page or as a share of the tank on the gauge.

## What Changes

- **BREAKING** The car has one reserve, in km, from 0 to 500. The reserve in liters goes from the store, the bot, the API, and the page.
  - `/car` asks six questions again. The last one asks the reserve in km.
  - The bot shows it as `Reserve: <km> km`.
  - The store drops the column `reserve`. Each stored car keeps its `reserve_km`.
- **BREAKING** `POST /api/refuel` takes no `reserve` in `car`. `reserve_km` stays required. A request with `car.reserve` is still accepted, and the key is ignored.
- When the walk is in liters, the reserve applies along the road ahead:
  - The search point is the first route point where the fuel left drives only `reserve_km` more of this route, at the speeds and consumptions of its own segments.
  - Past the destination, the route has no segments. There, the fuel for the remaining km uses the consumption at 130 km/h.
  - This applies to a fuel in liters at the origin, and to the walk after each chosen station.
- No stop is planned when the fuel left at the destination is more than the fuel for `reserve_km` at 130 km/h.
- After a walk by the range, the first stop buys `tank_volume` minus the fuel that the next `reserve_km` of the route need from the search point.
- The "no station near" texts of the bot and the page always end with `where the range left reaches <reserve_km> km.`
- The page has seven fields. `Range reserve` becomes `Reserve`, with the unit `km`. The field `Reserve` in liters goes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `car-parameters`: one reserve in km; six questions; its error text and its line; the store drops the liters.
- `refuel-planning`: the request has no reserve in liters; the search point and the "no stop" rule of a walk in liters read the reserve in km along the route; the liters of a stop after a walk by the range.
- `telegram-refuel-plan`: the "no station near" text always names the reserve in km.
- `web-front-end`: seven fields; the reserve field in km; its storage, check, and message; the request; the "no station near" message.

## Impact

- Code: `french_tolls/car.py`, `french_tolls/models.py`, a new revision under `alembic/versions/`, `french_tolls/refuel.py`, `french_tolls/refuel_chat.py`, `french_tolls/api.py`, `www/index.html`, and `www/index.js`.
- Tests: `french_tolls/tests/test_car.py`, `test_refuel.py`, `test_refuel_chat.py`, and the integration tests `test_car_dialog.py`, `test_refuel_endpoint.py`, and `test_refuel_flow.py`.
- Data: the stored reserves in liters are lost. Each car keeps its reserve in km.
- Behavior: the same car can stop at another point than before, because the reserve now follows the speed of the road ahead.
- Unchanged: the gauge, the typed range, the walk by the range, the station costs, and the drive flow.
