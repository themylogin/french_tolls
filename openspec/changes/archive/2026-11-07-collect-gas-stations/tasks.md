# Tasks

## 1. Dependencies

- [x] 1.1 Add `beautifulsoup4` and `isodate` to `dependencies` in `pyproject.toml`, without bounds. Change the `requirements` recipe in the `Makefile` so that uv also gets the committed `requirements.txt` and keeps its pins, and resolves for Python 3.11.2, the `python3` of the image. Run `make requirements`. Verify that the diff of `requirements.txt` only adds `beautifulsoup4`, `soupsieve`, and `isodate`, and that a second `make requirements` gives no diff.
- [x] 1.2 Build the application image. Verify that `docker compose --profile test run --rm --no-TTY --entrypoint python3 tests -c "import bs4, isodate, sqlite3; print([o for (o,) in sqlite3.connect(':memory:').execute('pragma compile_options') if 'RTREE' in o])"` prints `['ENABLE_RTREE']`.

## 2. Schema

- [x] 2.1 Add the models `GasStation` and `GasStationArea` to `french_tolls/models.py`, with the columns of design D4, and add them to `__all__`. Verify that `Base.metadata.tables` names `autocomplete`, `google_requests`, `gas_station`, and `gas_station_area`.
- [x] 2.2 Generate a revision with `alembic revision -m "gas stations"`. In it, create `gas_station` with `op.create_table`, and create the R*Tree table and the three triggers of design D2 with `op.execute`. Add a comment that a batch copy of `gas_station` drops the triggers. Write `downgrade` in the reverse order. Verify that the filename starts with the date and time, and that `upgrade head`, `downgrade -1`, and `upgrade head` all succeed on an empty file.
- [x] 2.3 Add the `include_object` hook of design D4 to both `context.configure` calls in `alembic/env.py`, with a comment that says why. Verify that `alembic check` after `upgrade head` reports no new operations.
- [x] 2.4 Create `french_tolls/tests/test_gas_stations.py` with a fixture that migrates a temporary store with Alembic, as `test_spending.py` does. Add the schema tests: `command.check` passes; `sqlite_master` holds only `alembic_version`, `autocomplete`, `google_requests`, `gas_station`, and `gas_station_area` with its `_node`, `_parent`, and `_rowid` tables. Verify with `make test`.
- [x] 2.5 Add the trigger tests: an inserted station has one index entry at its position; a moved station has its entry at the new position, and a box around the old position does not find it; a deleted station has no entry. Verify with `make test`.

## 3. Page parser

- [x] 3.1 Save `french_tolls/tests/station_29520005.html`: the page of station 29520005, reduced to the `#details_pdv` block. Verify that the file contains `details_pdv` and `Coordonnées station`, and no `<script`.
- [x] 3.2 Write `parse_station_page` and its parse error in `french_tolls/gas_stations.py`, with the rules of design D5. Add a fixture test. It requires the name `Leclerc`, the address `["Rue de quimper", "29520 Chateauneuf du faou"]`, the services `["Lavage automatique"]`, and the prices `[["SP95-E10 (E10)", "2026-11-06", "1.999"], ["E85 (E85)", "2026-10-26", "0.877"], ["Gazole (B7)", "2026-11-06", "2.149"]]`. Verify with `make test`.
- [x] 3.3 Add tests on small HTML strings: a block without a `Marque` line gives the name `None` and puts every line in the address; an empty services section gives `[]`; the price `2.100` stays the string `"2.100"`; a page without the price table, without the station block, or with a price and no date raises the parse error. Verify with `make test`.

## 4. Area query

- [x] 4.1 Write the coroutine `stations_in_area(south, west, north, east)` with the query of design D3. Add the tests of the spec: only the stations in the box; a station on the edge; `EXPLAIN QUERY PLAN` contains `VIRTUAL TABLE INDEX`. Verify with `make test`.

## 5. Update run

- [x] 5.1 Write the coroutine `update(max_age, base_url="https://www.prix-carburants.gouv.fr")`, steps 2 to 5 of design D7: the list read, its check, and the selection. Add tests against a local `aiohttp` server: a list status of 503, or a body that is not a list, returns the status 1, requests no page, and changes no row. Verify with `make test`.
- [x] 5.2 Add the selection tests: a fresh station is not requested and its row does not change; a stale station is requested and its row is replaced; a new station is created; `PT0S` requests every listed station; a stored station that is not in the list does not change. Verify with `make test`.
- [x] 5.3 Write steps 6 to 8 of design D7: the page reads through `asyncio.Semaphore(4)` and a 30 s timeout, one upsert and commit per station, and the final counts. Add tests: the position of the list replaces the stored position; `last_updated_at` is between the start and the end of the run; a 404 leaves that row unchanged, refreshes the others, and returns 1; a page with no price table is logged with its id (use `caplog`); a run without a failure returns 0. Verify with `make test`.
- [x] 5.4 Add the load test: the server counts its open page requests, and holds each one for a short time. A run of 100 stale stations never has more than four open. Verify with `make test`.
- [x] 5.5 Add the interruption test: the server answers the first pages and holds the last one. Cancel the run after the first commits. A second run requests only the pages that the first run did not store. Verify with `make test`.
- [x] 5.6 Write `main(argv)`: `argparse` with the positional `max_age` of type `isodate.parse_duration`, logging from `config.log_level` as `web.py` does, then `asyncio.run(update(...))` and `sys.exit` with its status. Add the module guard `if __name__ == "__main__"`. Add tests: `23h` exits with the status 2; no argument exits with the status 2 and prints the usage (use `capsys`). Verify with `make test`.

## 6. Compose service and documentation

- [x] 6.1 Add the service `gas-stations` of design D8 to `docker-compose.yml`, and add `gas-stations` to the `profiles` of `migrate`. Verify that `docker compose config --services` does not list `gas-stations`, that `docker compose --profile gas-stations config --services` lists it with `migrate`, and that the service has no `ports`.
- [x] 6.2 Add a section "Gas stations" to `README.md`. It gives the command `docker compose run --rm gas-stations PT23H`, the meaning of the age, the exit status, the duration of a full run, and a cron line. Verify that the command in the README is the one that task 7.2 runs.

## 7. Integration checks

- [x] 7.1 Run `make test`. Verify that both suites pass.
- [x] 7.2 With the agreement of the operator, run `docker compose run --rm gas-stations PT23H` against the real site. Verify that the run logs its counts, and that the number of rows in `gas_station` is near the number of listed stations.
- [x] 7.3 Run `docker compose run --rm gas-stations PT23H` again at once. Verify that the log shows 0 selected stations, and that the run exits with the status 0.
- [x] 7.4 Call `stations_in_area(48.0, -4.0, 48.4, -3.6)` in the container against the filled store. Verify that the answer contains station `29520005` with the name `Leclerc`.
- [x] 7.5 Run `openspec validate collect-gas-stations --strict`. Verify that the change is valid.
