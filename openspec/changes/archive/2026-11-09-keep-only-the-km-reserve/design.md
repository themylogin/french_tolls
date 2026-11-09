# Design

## Context

See `proposal.md` for the motivation, and the specs for the texts, the limits, and the scenarios.

- `car.CarParameters` has `reserve` (L) and `reserve_km`. `parse_car` checks both. The `/car` dialog asks `reserve`, keeps it in `CarDialog.reserve`, and saves at the `reserve_km` step. `describe` shows `Reserve: <L> L` and `Range reserve: <km> km`.
- `save_car` writes `dataclasses.asdict`, so each field of `CarParameters` is a column of `car`. The head revision is `5eebff3c5c55`. It added `reserve_km`.
- `refuel.fuel_walk(route, parameters, fuel, start)` stops at the first node where `fuel <= parameters.reserve`. `refuel._walk` picks `fuel_walk` or `range_walk` from a `Start`. `plan` buys `tank_volume - parameters.reserve` liters after a range walk.
- `refuel._segment_consumption` gives the consumption of one segment from its speed, or `consume_80` for a segment of 0 s.
- `refuel_chat.no_station_text(parameters, by_range)` names the liters or the km. `bot.plan_and_answer` passes `by_range`.
- `www/index.html` has the rows `refuel-reserve` (L) and `refuel-reserve-km` (`Range reserve`, km). `www/index.js` reads, checks, stores, and sends both.

## Goals / Non-Goals

**Goals:**

- One reserve, in km, for every walk.
- A walk in liters places the stop by the fuel that the road ahead needs for that reserve.

**Non-Goals:**

- No change to the walk by the range, the station costs, or the drive flow.
- No conversion of the stored liters to km.

## Decisions

### The reserve fuel is read along the road ahead

`fuel_walk` gets the fuel for `reserve_km` at each node from two cumulative lists over the route: `along`, the distance in m to each node, and `burn`, the fuel in L to each node. Each segment adds `distance / 1000 * _segment_consumption(...) / 100` to `burn`.

For the node `i`, the reserve fuel is:

- with `target = along[i] + reserve_km * 1000` on the route: `burn[j] - burn[i]` plus the share of segment `j` up to `target`, where `j` is the segment that holds `target` (found with `bisect`);
- with `target` past the destination: `burn[-1] - burn[i]` plus `(target - along[-1]) / 1000 * consume_130 / 100`.

The walk compares `fuel - (burn[i] - burn[start])` with the reserve fuel of `i`, from `start` on. At the destination, the reserve fuel is `reserve_km` at `consume_130`. The lists cost O(n), and each node costs one bisect.

`reserve_fuel(route, parameters, index)` is its own function, because `plan` also needs it for the liters after a range walk. The lists are built once per call of `fuel_walk`, and once more in `plan` for that one node.

Alternatives:

- A fixed rate: `reserve_km * consume_130 / 100` liters at each node. The operator chose the road ahead, because it is what "50 km of range left" means on that road.
- An average consumption of the whole route. It gives a city stop the reserve of a motorway, and the reverse.

### The liters after a range walk use the same reserve fuel

`plan` buys `max(0, tank_volume - reserve_fuel(route, parameters, search_index))` after a range walk. The floor keeps a reserve longer than a full tank from a negative purchase.

### The car loses `reserve`

- `CarParameters.reserve` and `CarDialog.reserve` go. `parse_car` no longer reads `reserve`, so a key from an old page is ignored. `parse_reserve` goes.
- After the consumption at 130 km/h, the dialog asks `At how many kilometers of range do you want to refuel? Enter it, for example 50.` at the step `reserve_km`, which saves the car. The error becomes `The reserve must be a number from 0 to 500 km, for example 50. Enter it again.`
- `describe` shows `Reserve: <km> km` as its sixth and last line.
- `Car.reserve` goes from `french_tolls/models.py`. A new revision after `5eebff3c5c55` drops the column in one `op.batch_alter_table`. Its downgrade adds `reserve` (float, not null, `server_default` `"5"`), so `test_the_models_and_the_revisions_agree` still holds on both sides.

The column and the field keep the name `reserve_km`. A rename to `reserve` would reuse the name of the dropped liters for another unit, in the store, the API, and the browser storage.

### One text for "no station near"

`no_station_text(parameters)` loses `by_range`, and always ends with `where the range left reaches <reserve_km> km.` `bot.plan_and_answer` calls it with the car only.

### The page drops a row and relabels another

- `www/index.html` loses the row `refuel-reserve`. The row `refuel-reserve-km` keeps its id and its unit, and its label becomes `Reserve`.
- `readRefuelForm` no longer reads `reserve`. The message of `reserve-km` becomes `The reserve must be a number from 0 to 500 km.` The `car` object carries `reserve_km` only.
- `clearFieldMarks` drops `reserve`. `openRefuelDialog` fills `refuel-reserve-km` from `car.reserve_km`, or `50`.
- `showRefuelAnswer` always names `refuelRequest.car.reserve_km` in the "no station near" message.

The browser storage keeps the key `car`. A stored `reserve` in liters stays there and is never read.

## Risks / Trade-offs

- [A reserve longer than a full tank makes every walk after a chosen station stop at that station.] → The plan then lists stations near the last stop, and the driver sees it. The limits stay 0 to 500 km, and most cars drive more than 500 km on a full tank.
- [The same car can stop at another point than before.] → This is the point of the change. The reserve now follows the speed of the road ahead.
- [The stored reserves in liters are lost.] → Each car keeps its reserve in km, which every car already has.
- [A page loaded before the deploy sends `reserve` with `reserve_km`.] → The API ignores `reserve`, so that page still works.

## Migration Plan

1. Deploy the application image and the `www` image together. `migrate` drops the column before `web` and `bot` start.
2. To roll back, run the downgrade of the revision, and deploy the old images. Each car then gets a reserve of 5 L.
