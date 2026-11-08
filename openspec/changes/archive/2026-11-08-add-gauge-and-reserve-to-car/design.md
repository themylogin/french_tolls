# Design

## Context

See `proposal.md` for the motivation, and the specs for the questions, the messages, and the limits.

- `french_tolls/car.py` keeps the dialog as pure rules: `start`, `answer_text`, and `answer_button` return a `CarReply` with the text, the next `CarDialog`, the buttons, and an optional `save`. `bot.py` sends the reply and saves the car.
- `../gasolinera/gasolinera/car.py` has the same shape. It adds a `photo` flag to `CarReply`, a `gauge` step after the tank volume, and an `eur_per_hour` and a `reserve_km` step after the consumptions.
- `../gasolinera/gasolinera/bot.py` sends a photo reply with `reply_photo`, and edits the caption with `edit_message_caption` when a button of a photo is pressed.
- gasolinera adds each new column in its own revision, with a `server_default`, through `op.batch_alter_table`, because SQLite cannot add a column with a constraint in place.
- The head revision of this project is `c5fd29a893f0`, the `car` table.
- The fake Telegram transport of this project answers only `sendMessage`, `editMessageText`, `editMessageReplyMarkup`, and three other methods. The gasolinera test transport also answers `sendPhoto` and `editMessageCaption`, and reads the caption as the text of a photo.

## Goals / Non-Goals

**Goals:**

- The `/car` dialog of this bot behaves as the gasolinera `/coche` dialog, without the value of time, in English, with 130 km/h.

**Non-Goals:**

- No use of the gauge or the reserve yet.
- No change to the web dialog or to the refuel plan.

## Decisions

### Copy the rules, not the module

The changes go into the existing `car.py` and `bot.py` of this project:

- `CarParameters` gets `gauge_steps` and `reserve_km`, both with the default `None`. `parse_car` builds a `CarParameters` from the web dialog, which has no gauge and no reserve. The bot always sets both before it saves.
- `CarDialog` gets `gauge_steps`.
- `CarReply` gets `photo`.
- `answer_text` gets the `gauge` and `reserve_km` steps.
- `answer_button` gets the gauge choice, with the pressed text `Gauge: <steps> sections`.
- A new `parse_reserve` accepts a number from 0 to 500, with a point or a comma, as `parse_consumption` does for its range.

The alternative is to copy the gasolinera module whole. It has other names (`consume_120`, `number_text`), Spanish texts, and the value of time, so a copy would need more edits than the additions.

After the consumption at 130 km/h, the dialog goes to the reserve, where gasolinera goes to the value of time. The order check of the two consumptions stays as it is.

`describe` shows the reserve with the same function as the consumptions, so `50.0` shows as `50`.

### One revision for both columns

One revision adds `gauge_steps` (integer, `server_default` `"16"`) and `reserve_km` (float, `server_default` `"50"`) to `car`, with `op.batch_alter_table`, after `c5fd29a893f0`. The model declares the same defaults, so `alembic check` finds no difference. gasolinera has two revisions only because it added the columns in two changes.

`load_car` returns `None` for a row whose gauge is not 24, 16, or 12, as gasolinera does. The dialog then starts as for a driver without a car.

### The photo is a committed file of the package

`bot.py` reads `french_tolls/assets/gauges.png` beside the module, and sends it with `reply_photo`, the text as the caption. The root `.dockerignore` lets `french_tolls/` into the image, so the picture is in the application image without a new rule.

`car_button_handler` edits the caption with `edit_message_caption` when the pressed message has a photo. Otherwise it edits the text, as now. A typed answer while the gauge question is open sends the photo again, with the caption `Choose your gauge with a button.`

### The render tools copy gasolinera's

- `gauge/render.py` and its three source images are copied from `../gasolinera/gauge/`. The only edit in `render.py` is its output path: `french_tolls/assets/gauges.png`.
- The `Makefile` gets `gauge-image`, with the gasolinera recipe: `uv run --no-project --with pillow python gauge/render.py` in `ghcr.io/astral-sh/uv:python3.11-bookworm-slim`, with `$(HOST_USER)` and a cache directory under `/tmp`.
- `french_tolls/assets/gauges.png` is copied too, so a checkout works without the render step.

### The test transport learns photos

`ANSWERED` in `french_tolls/integration/telegram_transport.py` gets `sendPhoto` and `editMessageCaption`. A sent photo gets a `photo` entry in the result, and the text of a `Sent` is the caption for a photo, as in the gasolinera transport. `Chat.press` sends the callback on a message with a photo when the pressed message was a photo. Otherwise `query.message.photo` is empty, and the caption edit is not tested.

## Risks / Trade-offs

- [The gauge and the reserve are stored, but nothing reads them yet.] → Chosen in the proposal. They are the input of a later refuel search in the bot.
- [A driver with a car answers six questions to change one value.] → The same as in gasolinera. A dialog that changes one value is outside this change.
- [The picture comes from another repository and can drift from it.] → `gauge/` holds the sources and `make gauge-image` renders them here, so this copy does not depend on gasolinera after the change.

## Migration Plan

1. Deploy the image. `migrate` applies the revision before `bot` starts, and the cars stored before it get a gauge of 16 steps and a reserve of 50 km.
2. To roll back, run the downgrade of the revision, which drops the two columns, and deploy the old image.
