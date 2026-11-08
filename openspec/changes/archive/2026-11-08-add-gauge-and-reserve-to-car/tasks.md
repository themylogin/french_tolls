# Tasks

## 1. Rules of the dialog

- [x] 1.1 In `french_tolls/car.py`, add `gauge_steps` and `reserve_km` to `CarParameters` with the default `None`, `gauge_steps` to `CarDialog`, `photo` to `CarReply`, and `parse_reserve`. Make `describe` show the six lines of the spec. In `french_tolls/tests/test_car.py`, rename `test_a_car_is_described_in_four_lines` to `test_a_car_is_described_in_six_lines`, with the spec example; add parser tests: `0`, `50`, `60.5`, ` 7,5 `, and `500` are accepted; `501`, `600`, `-1`, `fifty`, `50 km`, and an empty text are refused. Verify with `make test` that `parse_car` still passes its tests.
- [x] 1.2 Add the `gauge` step after the tank volume, and the `reserve_km` step after the consumption at 130 km/h, with the texts of the spec. Add rule tests: `30` asks `How many sections does your fuel gauge have?` as a photo with one row `24`, `16`, `12`; a typed answer at the gauge step gives the photo again with `Choose your gauge with a button.`; a press on `24` asks `Choose the fuel type.` with the pressed text `Gauge: 24 sections`; an equal consumption at 130 km/h asks the reserve; a valid reserve saves the six values; `600` gives `The reserve must be a number from 0 to 500 km, for example 50. Enter it again.`; a gauge press with a wrong token has expired. Update the sequences of the existing tests with a gauge press and a reserve. Verify with `make test`.
- [x] 1.3 Make `load_car` and `save_car` read and write the two new values. `load_car` returns `None` for a gauge other than 24, 16, or 12. Update the store tests of `test_car.py` for six values. Verify with `make test`.

## 2. Store

- [x] 2.1 Add `gauge_steps` (integer, `server_default` `"16"`) and `reserve_km` (float, `server_default` `"50"`) to `Car` in `french_tolls/models.py`. Generate one revision after `c5fd29a893f0` that adds both columns with `op.batch_alter_table`, and drops them in `downgrade`. Add a test in `test_car.py`: a store at `c5fd29a893f0` with a car row, upgraded to `head`, gives that car the gauge 16 and the reserve 50.0, with its other values unchanged. Verify with `make test` that this test and `test_the_models_and_the_revisions_agree` pass, and that `upgrade head`, `downgrade -1`, and `upgrade head` succeed on an empty file in the image.

## 3. Bot

- [x] 3.1 In `french_tolls/bot.py`, send a reply with `photo` set as `reply_photo` of `french_tolls/assets/gauges.png`, with the text as its caption. In `car_button_handler`, edit the caption when the pressed message has a photo. Verify with the tests of 3.3.
- [x] 3.2 In `french_tolls/integration/telegram_transport.py`, answer `sendPhoto` and `editMessageCaption`, add a photo to their results, and read the caption as the text of a photo, as the gasolinera test transport does. In `french_tolls/integration/chat.py`, make a press on a photo message arrive with that photo. Verify with the tests of 3.3.
- [x] 3.3 In `french_tolls/integration/test_car_dialog.py`, add a gauge press and a reserve to the answer sequences. Add tests: the gauge question is a photo with the caption and the buttons `24`, `16`, `12`; a press edits the caption to `Gauge: 24 sections` and asks the fuel type; a typed answer at the gauge sends the photo again with `Choose your gauge with a button.`; a gauge button of an earlier dialog has expired and keeps the second dialog at its gauge question; a dialog stopped before the reserve keeps the stored reserve. Verify with `docker compose --profile test run --rm --no-TTY integration`.

## 4. Gauge picture

- [x] 4.1 Copy `../gasolinera/gauge/render.py`, `12.png`, `8.jpg`, and `6.webp` to `gauge/`, and change only the output path of `render.py` to `french_tolls/assets/gauges.png`. Copy `../gasolinera/gasolinera/assets/gauges.png` to `french_tolls/assets/gauges.png`. Add the target `gauge-image` to the `Makefile`, with the recipe and the comment of the gasolinera target, and add it to `.PHONY`. Verify that the recipe renders a 1200 × 400 picture equal to the copied one, and that `requirements.txt` names no Pillow.

## 5. Integration checks

- [x] 5.1 Run `make test` and `docker compose --profile test run --rm --no-TTY integration`. Verify that the unit and builder suites pass. Verify that the integration suite fails no test beyond the 4 tests in `test_drive_flow.py` that failed before this change.
- [x] 5.2 With the agreement of the operator, run `make bot`. In Telegram, send `/car` with a stored car. Verify that it shows `Gauge: 16 sections` and `Reserve: 50 km`. Press `Yes`, and answer the six questions. Verify that the gauge question is the photo, and that the saved car shows six lines.
- [x] 5.3 Run `openspec validate add-gauge-and-reserve-to-car --strict`. Verify that the change is valid.
