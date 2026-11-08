# Design

## Context

See `proposal.md` for the motivation, and the specs for the limits, the messages, and the scenarios.

- `french_tolls/car.py` holds `CarParameters`. The bot builds it in the `/car` dialog. `parse_car` builds it from the `car` object of `POST /api/refuel`.
- `CarParameters.reserve_km` defaults to `None`, because the web dialog does not send it. Nothing reads it.
- `refuel.fuel_walk` takes the `CarParameters` and compares the fuel with the literal `5` in two places. `refuel.plan` and `_through_chosen` reach the threshold only through `fuel_walk`.
- `save_car` writes `dataclasses.asdict(parameters)` into `car`, so each field name of `CarParameters` must be a column name.
- The head revision is `f99c669a7732`. It added `gauge_steps` and `reserve_km` with `op.batch_alter_table`. That revision is deployed.
- `www/index.js` stores `values.car` as one object under the key `car`, and sends `refuelRequest.car` as the `car` of the request. A new key in `values.car` reaches both without new code.
- The `migrate` service runs `alembic upgrade head` before `web` and `bot` start.

## Goals / Non-Goals

**Goals:**

- One reserve value in liters, from the bot store, the page, and the request, to the refuel walk.

**Non-Goals:**

- No refuel plan in the bot.
- No conversion of the stored km values.
- No new default button in the bot dialog. The question gives `5` as its example.

## Decisions

### The reserve is a required field of the car

`CarParameters` gets `reserve: float` with no default, after `consume_130`. `reserve_km` goes. `gauge_steps` stays optional, because the web dialog still does not send it.

- `parse_car` reads `reserve` and refuses a value that is not a number, a bool, or a value outside `0 <= reserve < tank_volume`. NaN and infinity fail this comparison.
- `fuel_walk` compares the fuel with `parameters.reserve` in place of `5`.
- `plan`, `_through_chosen`, and `api.refuel` do not change, because they pass the `CarParameters` through.

Alternatives:

- A separate `reserve` argument to `plan` and `fuel_walk`. It adds a parameter to three functions for a value that belongs to the car.
- An optional `reserve` in the request, with 5 as the server default. It keeps a stale page working, but it gives the default two homes, the page and the server, and the spec of the request gets an exception.

### The column is `reserve`, without a unit suffix

The column and the field are `reserve`, as `tank_volume` and `fuel` are liters without a suffix. `asdict` then needs no mapping.

### One revision replaces the column

A new revision after `f99c669a7732` uses one `op.batch_alter_table` on `car`:

- `upgrade` drops `reserve_km` and adds `reserve` (float, not null, `server_default` `"5"`);
- `downgrade` drops `reserve` and adds `reserve_km` (float, not null, `server_default` `"50"`).

`Car.reserve` in `french_tolls/models.py` declares the same `server_default`, so `test_the_models_and_the_revisions_agree` passes.

5 L is valid for every stored car, because each stored tank volume is 30 or more.

Alternatives:

- Edit `f99c669a7732` in place. It is deployed, so the stores that ran it would keep `reserve_km`.
- Convert km to liters with the consumption at 130 km/h. The operator does not need the old values, and a conversion needs a speed that the driver did not choose.
- Delete the stored cars. The other five values are still valid, so a reset of the reserve loses less.

### The bot checks the reserve against the tank volume of the dialog

`parse_reserve` takes the text and the tank volume of the dialog. It returns `None` for a text that is not a decimal number, and for a value outside `0 <= reserve < tank_volume`. The dialog step is renamed from `reserve_km` to `reserve`.

The error message names the tank volume, as the 130 km/h error names the 80 km/h value. `describe` shows the reserve with `_number_text` and the unit `L`.

### The page adds one field and reads the default once

- `www/index.html` gets a row with the field `refuel-reserve`, the label `Reserve`, and the unit `L`, between `refuel-consume-130` and `refuel-fuel`. It copies the markup of the fuel row.
- `readRefuelForm` parses the field with `parseDecimal`, and marks it when the value is `null` or not less than a valid tank volume. It adds `reserve` to `car`.
- `clearFieldMarks` clears the new field too.
- `openRefuelDialog` fills the field from the stored reserve. When the storage has no number there, it fills `5`.
- `showRefuelAnswer` reads `refuelRequest.car.reserve` for the "no station" message, with `String`, so `7.5` shows as `7.5`.

## Risks / Trade-offs

- [A page that the browser loaded before the deploy sends no `reserve`, and the server refuses it with 400.] → The dialog shows its error message. A reload loads the new page.
- [The reserves in km of the stored cars are lost.] → Chosen by the operator. Nothing reads them, and each driver can set a new reserve with `/car`.
- [A reserve near the tank volume makes many small stops.] → It is the choice of the driver. `chosen` already stops a plan at 20 stations.
- [A reserve of 0 with exactly 0 L left at the destination asks for a stop at the destination.] → This is the rule "the reserve or less", as it was for 5 L.

## Migration Plan

1. Deploy the application image and the `www` image together. `migrate` applies the revision before `web` and `bot` start. Each stored car gets 5 L.
2. To roll back, run the downgrade of the revision, and deploy the old images. Each stored car then gets 50 km.
