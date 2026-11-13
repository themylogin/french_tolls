# Design

## Context

See `proposal.md` for the reason, and `specs/gas-station-inventory/spec.md` for the rules. The current state that shapes the approach:

- `update` in `french_tolls/gas_stations.py` reads the selected pages through `asyncio.gather` and a semaphore of 4. Each `_refresh` call parses its page, then upserts the row in its own session, and commits it.
- `_refresh` returns `"osm"`, `"list"`, or `"failed"`. `update` counts these values for the summary line.
- Only the `gas-stations` run writes `gas_station`. `web` and `bot` read it, and write other tables.
- The store is SQLite in WAL mode. The driver starts a transaction before the first `INSERT`, not before a `SELECT`.
- On the store of 2026-11-08, 8,211 of 9,376 stations are valid. The count of D2 takes 42 ms there, as the median of 10 runs.

## Goals / Non-Goals

**Goals:**

- A refused run leaves every row exactly as it was, the rows of the selected stations too.
- The rule "valid station" takes its fuels from the fuel types of `french_tolls/car.py`, as the refuel planning does. No fuel name is written in `gas_stations.py`.

**Non-Goals:**

- A stored `valid` flag or column. The count reads the prices.
- Use of the valid-station rule outside the run, for example in the refuel planning.
- A check of the stations one by one. The rule compares totals only.

## Decisions

### D1. Read every page, then write once

`_refresh` only reads. It returns the source of the position (`"osm"` or `"list"`) and the row values, or `"failed"`. It no longer opens a session.

After `gather`, `update` opens one session and does these steps:

1. Count the valid stations: `before`.
2. Upsert all the read stations with one batched statement: `insert(GasStation).on_conflict_do_update(...)`, with each column except `id` set from `excluded`, executed with the list of rows. A run that read no station skips this step.
3. Count the valid stations again: `after`. The first `INSERT` started the transaction, so this count sees the new rows.
4. When the run is refused, roll back, log the refusal, and return 1.
5. Otherwise, commit. Then log the summary line, and return 1 when a station failed, or 0.

The run does no write while it reads, so a stop before step 5 leaves the store unchanged.

Alternative: one upsert statement for each station, as before this change. On a copy of the store of 2026-11-08, the 9,376 statements held the write lock for 6 s, more than the busy timeout of 5 s of the other services. The batched statement held it for 0.36 to 0.41 s. Rejected.

Alternative: keep the commit for each station, and restore the old rows when the check fails. That needs a copy of each old row. A crash between the writes and the restore leaves a bad store, with no check at all. Rejected.

Alternative: compute `after` from the read rows and the old validity of each selected station. That needs the old row of each selected station, and separate cases for new and changed stations. A full count after the writes is simpler. Rejected.

### D2. A Python scan counts the valid stations

The function `valid_station_count(session)` reads the `prices` column of every row. It counts the rows that have a fuel of `car.station_fuels("diesel")` and a fuel of `car.station_fuels("95")`. The `car-parameters` spec makes `FUEL_TYPES` the definition point of these names, and `refuel.candidates` reads them the same way. So a new fuel in a type changes the refuel planning and the count together.

The second count runs in the write session, so it sees the rows that are not committed yet.

The function is public, so the tests check the definition with rows they insert.

Alternative: write the fuel names in the count. That gives "95" a second definition, which can drift from `car.py`. Rejected.

Alternative: one SQL query with `json_each` and expanding bound parameters. On a copy of the store of 2026-11-08, it took 21 ms, and the scan 42 ms, as the median of 10 runs. The difference is about 40 ms for each run. The scan is plain Python, with the same pattern as `refuel.candidates`. Rejected.

### D3. The threshold uses integers

The run is refused when `before > 0 and after * 5 <= before * 4`. Integer arithmetic makes the 80% boundary exact. For example, 4 of 5 is refused, and no float rounding can change that.

With `before == 0`, the run is never refused. See "Assumptions to review" in `proposal.md`.

### D4. The refusal is one error line

The run logs `The update is refused: %d valid stations after it, %d before it` at the level `ERROR`. The failure line of each failed station comes before it, as today. A refused run logs no summary line, because it refreshed no station.

### D5. The first count is outside the write transaction

The driver starts the transaction at the first `INSERT`, so the first count reads committed data without a lock. Only this run writes `gas_station`, so that count is still true when the writes start. Step 3 runs inside the transaction.

## Risks / Trade-offs

- [A full run stops after 9 minutes and loses all its reads.] → The proposal accepts this. The next run reads the pages again. With `PT23H` in cron, a daily run selects about one day of stale stations.
- [One transaction holds the write lock for up to about 9,500 upserts with their index triggers.] → The lock covers only the writes, not the 6 to 10 minutes of reads. With the batched upsert and the count of D2, the lock lasted 0.36 to 0.41 s for the 9,376 rows of a copy of the store of 2026-11-08. WAL lets `web` and `bot` read. Their own writes wait inside the default busy timeout of 5 s.
- [All read rows stay in memory until the write.] → About 9,500 small dicts, a few MB.
- [Two `gas-stations` runs at the same time.] → The counts of one run can include the writes of the other. This is not new: two runs already overwrite each other's rows. The operator runs one at a time.
- [A real, lasting drop of 20% or more, for example many stations stop to publish diesel prices.] → Each run is then refused, and the store keeps the old prices. The log line shows the counts, so the operator sees the cause.

## Migration Plan

1. Deploy the new image. No schema change, so `migrate` does nothing new.
2. The next `docker compose run --rm gas-stations PT23H` uses the new rules.

Rollback: deploy the previous image. The store format does not change.
