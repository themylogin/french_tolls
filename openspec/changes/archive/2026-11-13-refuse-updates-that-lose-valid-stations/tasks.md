# Tasks

The test command is `docker compose --profile test run --rm --build --no-TTY tests`. The `tests` image copies the code, so `--build` is necessary after each edit.

## 1. Valid-station count

- [x] 1.1 Add the coroutine `valid_station_count(session)` to `french_tolls/gas_stations.py`, with the scan of design D2, and add it to `__all__`. Take the fuels from `car.station_fuels("diesel")` and `car.station_fuels("95")`. Verify that the module imports, and that `gas_stations.py` contains no fuel name.
- [x] 1.2 Add a `prices` parameter, default `'[]'`, to the `insert_station` test helper. Add a parametrized test with the five scenarios of "A valid station sells diesel and 95": insert one station with the literal prices, and assert a count of 1 or 0. Add a test with three stations, two of them valid, that asserts the count 2. Add the scenario "The fuel types decide": patch `car.FUEL_TYPES` with a `95` type that also covers `SP95-E15 (E15)`, and assert the count 1. Verify with the test command.

## 2. One transaction for the run

- [x] 2.1 Change `_refresh` so that it only reads: it returns the source and the row values, or `"failed"`, and opens no session. In `update`, after `gather`, upsert every read station in one session, and commit once (design D1, steps 2 and 5). Verify that every existing test in `test_gas_stations.py` passes, except `test_an_interrupted_run_keeps_what_it_stored`.
- [x] 2.2 Replace `test_an_interrupted_run_keeps_what_it_stored` with `test_an_interrupted_run_stores_nothing`. Hold station 5 of five new stations. Wait until the source has five requests and one open request. Cancel the run. Assert that `stored_ids` is `[]`, that a second run requests the pages `[1, 2, 3, 4, 5]` in any order, and that it returns 0. Verify with the test command.

## 3. Refusal

- [x] 3.1 Add the two counts and the refusal to `update` (design D1 steps 1, 3, and 4, D3, and D4). Log the summary line only after the commit. Verify that the existing tests still pass with the test command.
- [x] 3.2 Add the four scenarios of "A run that loses too many valid stations is refused" as tests. Seed the valid stations with `insert_station`, the prices `[["SP95-E10 (E10)", "2026-11-06", "1.999"], ["Gazole (B7)", "2026-11-06", "2.149"]]`, and `hours_ago(30)`. Build the page with only `E85 (E85)` through the `page(rows=...)` helper. For a refused run, assert that each seeded row equals its row before the run, that the log has `The update is refused: 4 valid stations after it, 5 before it`, that the log has no `stations refreshed`, and that the run returns 1. Use `caplog`, and set `gas_stations.logger.disabled` to `False` as the existing log tests do. Verify with the test command.
- [x] 3.3 In the "Gas stations" section of `README.md`, add that the run writes all stations at its end, that an interrupted run stores nothing, and that a run that leaves 80% or less of the stations with diesel and 95 stores nothing, logs both counts, and exits with the status 1. Verify that each statement matches a requirement of the spec delta.

## 4. Integration checks

- [x] 4.1 Run `openspec validate refuse-updates-that-lose-valid-stations --strict` and the test command. Verify that both pass.
- [x] 4.2 In the `tests` image, copy the real store, read its 9,376 rows, and time the write steps of design D1 for all of them in one session. Verify that the copy keeps 8,211 valid stations, and write the measured time into the lock risk of `design.md`.

## Workflow follow-up

- Archive the change after the review, with `/opsx:archive`.
