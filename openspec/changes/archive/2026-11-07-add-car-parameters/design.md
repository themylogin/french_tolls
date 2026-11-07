# Design

## Context

See proposal.md for the motivation. The specs `car-parameters` and the `runtime-store` delta give the required behavior.

The current state:

- `french_tolls/bot.py` holds the Telegram shell. `ChatState` keeps the per-application state in `bot_data`: the origin of each driver (`users_from`) and the pending route parts (`pending`).
- `text_message_handler` takes each text and each location that is not a command. It reads a location with `parse_location`, or it sends the help.
- `drive_button_handler` has no callback pattern. It takes every button press.
- `french_tolls/drive.py` holds the route rules as values. `bot.py` only performs them. The spec `telegram-drive-flow` requires this split, and the integration suite drives the real application through a fake transport (`french_tolls/integration/chat.py`).
- The store has three tables: `autocomplete`, `google_requests`, and `gas_station` with its R*Tree index. `test_gas_stations.py` asserts this exact set.
- The last revision is `cd499fbf77cb` (`2026-11-07_15-52_gas_stations.py`).
- The host has no Python environment for the project. Alembic runs only in the application image, under `/app`.

## Goals / Non-Goals

**Goals:**

- Keep the dialog rules testable as values, without Telegram, like the route rules.
- Keep the dialog state in `ChatState`, next to the other per-application state.
- Add no dependency.

**Non-Goals:**

- A use of the stored car. The mapping in D1 is for the change that uses it.
- A conversation timeout. An open dialog stays open until the driver ends it, or until the bot restarts.
- A way to leave the dialog without an answer. The driver answers each question.

## Decisions

### D1. Three fuel types: Diesel, 95, and 98

The `gas_station` table on 2026-11-07 holds 9,357 stations. Their `prices` lists use six fuel names:

| Station fuel name | Stations | Median price (€/l) |
| --- | ---: | ---: |
| `Gazole (B7)` | 9,130 | 2.199 |
| `SP95-E10 (E10)` | 7,059 | 2.012 |
| `SP98 (E5)` | 6,834 | 2.159 |
| `E85 (E85)` | 3,761 | 0.879 |
| `SP95 (E5)` | 2,698 | 2.109 |
| `GPLc (LPG)` | 1,495 | 1.070 |

Seven stations have no price. There is no other fuel name, and no station sells electricity.

The bot offers only Diesel, 95, and 98. The mapping to the station fuel names is:

| `fuel_type` | Button label | Station fuel names |
| --- | --- | --- |
| `diesel` | Diesel | `Gazole (B7)` |
| `95` | 95 | `SP95-E10 (E10)`, `SP95 (E5)` |
| `98` | 98 | `SP98 (E5)` |

The reasons:

- 95 and 98 are octane grades. `SP95-E10 (E10)` and `SP95 (E5)` are two 95 fuels with a different ethanol content. 8,596 stations sell at least one of them.
- 6,834 stations sell 98. 116 stations sell 98 and no 95, and 1,878 stations sell 95 and no 98.
- At one station, E10 is the cheapest grade. `SP95 (E5)` costs a median 0.06 € more, and `SP98 (E5)` 0.10 € more.
- `E85 (E85)` and `GPLc (LPG)` map to no fuel type. They are out of scope.

The key of a fuel type is its label in lower case. `95` and `98` are text values in the `fuel_type` column.

Alternatives:

- Four types: diesel, petrol, E85, and LPG. Rejected: only Diesel, 95, and 98 are of interest.
- One type for each station fuel name. Rejected: `SP95-E10 (E10)` and `SP95 (E5)` are both 95. The driver chooses between them at the pump, not when they enter the car.
- A separate type for a 95 car that cannot use E10. Deferred: `fuel_type` is text, so a later change can add the value without a schema change.

The `car` row stores only the `fuel_type` key. `FUEL_TYPES` in `french_tolls/car.py` holds the station fuel names of each type, and `station_fuels(fuel_type)` returns them. A later station query then reads the names from one place.

Alternative: a column in `car` with the station fuel names. Rejected: it needs a migration, and the rows keep the old names when the mapping changes.

### D2. The `car` table

The model `Car` in `french_tolls/models.py`:

| Column | Type | Null | Note |
| --- | --- | --- | --- |
| `telegram_user_id` | `Integer` | no | primary key, `autoincrement=False` |
| `fuel_type` | `Text` | no | `diesel`, `95`, or `98` |
| `tank_volume` | `Integer` | no | liters |
| `consume_80` | `Float` | no | liters per 100 km |
| `consume_130` | `Float` | no | liters per 100 km |

A Telegram user id has at most 52 bits, so it fits the SQLite integer.

The table has no `CHECK` constraint. The dialog is the only writer, and the limits then have one definition point: `french_tolls/car.py`.

Alternative: one JSON column with the four values. Rejected: the `runtime-store` rule for one-column storage covers bought answers only. These values have a fixed shape, and separate columns let a later query read them.

### D3. The revision

The revision has the name `car` and the down revision `cd499fbf77cb`. It uses `op.create_table`, and its `downgrade` uses `op.drop_table`. It has no hand-written statement.

The host has no Alembic, so the revision is generated in the application image. A bind mount writes the file into the work tree:

```
docker compose run --rm --no-deps -v "$PWD/alembic:/app/alembic" \
    --entrypoint alembic migrate revision -m car
```

The `file_template` in `alembic.ini` gives the filename `<date>_<time>_car.py`. The existing test `test_the_models_and_the_revisions_agree` in `test_gas_stations.py` runs `command.check`. It then compares the revision with the model.

### D4. The dialog state is explicit, in `ChatState`

`ChatState` gets the dict `car_dialogs`: Telegram user id to `CarDialog`. `CarDialog` is a frozen dataclass in `french_tolls/car.py`:

- `token`: a string that `ChatState` issues for each new dialog, from the counter that it already has;
- `step`: `confirm`, `tank_volume`, `fuel_type`, `consume_80`, or `consume_130`;
- `tank_volume`, `fuel_type`, `consume_80`: the valid answers so far, or `None`.

Alternative: `telegram.ext.ConversationHandler`. Rejected for these reasons:

- It keeps the state inside the handler, where a test cannot build it. `telegram-drive-flow` requires that the flow state is explicit and belongs to the application.
- With a `CallbackQueryHandler` in its states and `per_message=False`, the library emits `PTBUserWarning` at each start.
- Its `conversation_timeout` needs the `job-queue` extra, which adds APScheduler.
- The routing between a dialog answer and a location is one test in `text_message_handler`.

### D5. The rules are values, and `bot.py` performs them

`french_tolls/car.py` does not import `telegram`. It holds:

- the fuel types of D1, as an ordered tuple of `(key, label, station fuel names)` entries, and `station_fuels(fuel_type)`;
- `parse_tank_volume(text)` and `parse_consumption(text)`, which return the value or `None`;
- `start(token, car)`: the first reply of `/car`, for a driver with or without a car;
- `answer_text(dialog, text)` and `answer_button(dialog, choice)`: the next reply;
- `describe(car)`: the four lines of the spec;
- `load_car(telegram_user_id)` and `save_car(telegram_user_id, values)`, the two store coroutines.

Each rule function returns a `CarReply` frozen dataclass:

- `text`: the message to send;
- `buttons`: the button rows as `(label, choice)` pairs, or empty;
- `dialog`: the next `CarDialog`, or `None` when the dialog ends;
- `save`: the four values to save, or `None`;
- `pressed_text`: the new text of the message whose button the driver pressed, or `None` to keep its text.

`bot.py` adds the handlers `car_command_handler` and `car_button_handler`. Each one reads `ChatState`, calls one rule, saves when `save` is set, stores `dialog` or drops the entry, edits the pressed message, and sends `text`. The shell holds no rule.

Alternative: put the rules in `bot.py`. Rejected: `bot` imports `route`, which loads the booth artefacts at import. A unit test cannot import it (`route-algorithm-tests`), so the rules would be testable only in the integration suite.

### D6. Number parsing uses a full match

- Tank volume: `re.fullmatch(r"\s*(\d{1,18})\s*", text)`, then `int`, then the test `>= 30`. Eighteen digits always fit the 64-bit SQLite integer, so a long answer cannot make the insert fail.
- Consumption: `re.fullmatch(r"\s*(\d+)(?:[.,](\d+))?\s*", text)`, then `float` of the parts joined with a point, then the test `0 < value < 30`.

The patterns refuse a sign, an exponent, `nan`, `inf`, and a unit by construction. `float()` alone accepts `nan`, `inf`, and `1e1`.

### D7. Callback data carries a prefix and the dialog token

A car button has the callback data `car:<token>:<choice>`. The choice is a fuel type key, `yes`, or `no`. The longest value is about 20 bytes, below the Telegram limit of 64 bytes.

- `drive_button_handler` gets the pattern `^d\d+$`, the form of the route tokens that `ChatState.remember` issues.
- `car_button_handler` gets the pattern `^car:`.
- A press is current only when the user has an open dialog, its token matches, and the choice fits the step: a fuel key at `fuel_type`, `yes` or `no` at `confirm`. Any other press gets the expired reply of the spec, and the bot removes the keyboard from that message.

The token makes a button of an old dialog expire even when the new dialog is at the same step.

Alternative: no token, only the step test. Rejected: a fuel button of an old dialog would then answer the fuel question of a new dialog.

### D8. Order of the checks in `text_message_handler`

1. A shared location goes to `handle_location`, as today. It does not change the dialog.
2. A text from a user with an open dialog goes to `answer_text`.
3. Any other text goes to `parse_location` or to the help, as today.

`/car` is a `CommandHandler`. The existing filter `~filters.COMMAND` keeps it out of `text_message_handler`. `/car` drops an open dialog and starts a new one with a new token.

### D9. Saving

`save_car` runs one `INSERT ... ON CONFLICT (telegram_user_id) DO UPDATE` and one commit, as `gas_stations._refresh` does. When the save raises, the shell logs the error, drops the dialog, and sends `Error saving your car parameters. I am very sorry for that 😞`. The old row stays, because the statement did not commit.

### D10. Display of numbers

`describe` shows the tank volume as an integer. It shows a consumption with `f"{value:.6f}"`, without trailing zeros and without a trailing point. `7.0` shows as `7`, and `0.00001` shows as `0.00001`, not as `1e-05`.

Alternative: `f"{value:g}"`. Rejected: it shows `29.99999` as `30`, which is outside the limits.

### D11. Tests

- `french_tolls/tests/test_car.py`, unit suite:
  - the parsers, with every value in the spec scenarios;
  - the rules, as sequences of `answer_text` and `answer_button` calls from `start`, with no Telegram;
  - the store, on a temporary SQLite file migrated by Alembic, with the fixture pattern of `test_gas_stations.py`.
- `french_tolls/tests/test_gas_stations.py`: the table set test names `car`, and its name says four tables.
- `french_tolls/integration/test_car_dialog.py`, integration suite, through `Chat`:
  - the command menu, read from the `setMyCommands` call;
  - a full dialog, the confirm step, `/car` again, an old button, and `6,5`;
  - two applications in one process.
  - An autouse fixture deletes the `car` rows before each test, because the suite shares one store for the whole session.

The tests assert the literal texts of the spec. They do not import the texts from `car.py`.

## Risks / Trade-offs

- [The dialog takes every typed message until it ends. A driver who forgets an open dialog and types `48.85, 2.35` gets a validation error.] → The error message names the expected value. A shared location still reaches the route flow, because the dialog takes only typed text.
- [An open dialog is lost when the bot restarts.] → The stored car does not change. The driver sends `/car` again. `users_from` and `pending` have the same behavior.
- [`car_dialogs` grows by one entry per driver who leaves a dialog open.] → One small entry per driver. A restart clears it.
- [The validator of OpenSpec requires each existing scenario name in a MODIFIED block. The `runtime-store` delta therefore keeps "Three tables in all".] → That scenario now names the three tables that hold no data entered by a driver. "Four tables in all" states the full set.
- [The fuel names come from the source. A renamed fuel, for example a new label for E10, would match no fuel type.] → Nothing filters by the mapping in this change. The change that uses it must check the names against the store again.

## Migration Plan

1. Deploy the new image. `migrate` applies the `car` revision before `web` and `bot` start. The revision only adds a table.
2. Rollback: `alembic downgrade cd499fbf77cb` drops the `car` table and its rows. Then deploy the old image. The old image does not read the table, so the rollback can also leave the table in place.
