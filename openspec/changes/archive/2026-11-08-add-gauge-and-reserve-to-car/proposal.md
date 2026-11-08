# Proposal

## Why

The sister project `../gasolinera` asks two more things in its car dialog: the type of the fuel gauge, chosen on a picture, and the reserve in km at which the driver wants to refuel. A later refuel search in the bot needs both. This change copies that part of the dialog to the `/car` command of this bot, in English.

## What Changes

- `/car` asks six questions, in this order:
  1. the tank volume, as now;
  2. **new:** the gauge, as one photo of three gauges with the buttons `24`, `16`, and `12`, which give the number of steps on the gauge;
  3. the fuel type, as now;
  4. the consumption at 80 km/h, as now;
  5. the consumption at 130 km/h, as now;
  6. **new:** the reserve, a number from 0 to 500 km.
- The bot saves the car after a valid reserve, and shows it in six lines: tank volume, gauge, fuel type, the two consumptions, and reserve.
- The `car` table gets the columns `gauge_steps` and `reserve_km`. A car that is stored before this change gets a gauge of 16 steps and a reserve of 50 km, as in gasolinera.
- The gauge photo, `french_tolls/assets/gauges.png`, is a copy of the gasolinera picture. Its three source images and `render.py` come too, under a new `gauge/` directory. `make gauge-image` renders the picture again in a throwaway container with Pillow, so the application image needs no image library.
- The fake Telegram transport of the integration suite learns `sendPhoto` and `editMessageCaption`, as the gasolinera test transport has.
- Not copied from gasolinera:
  - the value of the driver's time: this project uses `EUR_PER_HOUR`;
  - the consumption at 120 km/h: this project keeps 130 km/h, the French motorway limit;
  - the Spanish fuel labels and their order: the buttons stay `Diesel`, `95`, `98`;
  - the decimal comma in the shown values: the bot keeps English numbers.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `car-parameters`:
  - the store keeps the gauge and the reserve;
  - the dialog has six questions;
  - two new questions with their limits and messages;
  - the six-line format;
  - the old buttons include the gauge buttons;
  - the defaults for cars stored before this change;
  - one command renders the gauge picture.
- `build-pipeline`: the requirement "Project layout" names `gauge/` as the place of the gauge sources and their render script.

## Impact

- Changed files:
  - `french_tolls/car.py`, `french_tolls/bot.py`, and `french_tolls/models.py`;
  - a new revision under `alembic/versions/`;
  - `Makefile`;
  - the tests `french_tolls/tests/test_car.py`, `french_tolls/integration/test_car_dialog.py`, and `french_tolls/integration/telegram_transport.py`, with the helpers in `french_tolls/integration/chat.py`.
- New files: `french_tolls/assets/gauges.png`, `gauge/render.py`, `gauge/12.png`, `gauge/8.jpg`, and `gauge/6.webp`.
- The dialog is longer: a driver who changes the car answers six questions in place of four.
- No new Python dependency of the application. `make gauge-image` uses the `ghcr.io/astral-sh/uv:python3.11-bookworm-slim` image, which pulls Pillow when it runs.
- Unchanged: the web dialog and its LocalStorage values, the 5 L threshold of the refuel plan, the route answers, and the drive flow of the bot. Nothing reads the gauge or the reserve yet.
