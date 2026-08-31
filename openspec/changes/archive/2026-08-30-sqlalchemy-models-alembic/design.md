## Context

See `proposal.md` — Why. The constraints that shape the approach:

- One SQLite file on one Docker named volume, opened by two long-lived processes (`web`, `bot`) plus, in the integration suite, a third against a tmpfs of its own.
- The application is aiohttp end to end. There is no synchronous entry point anywhere in `web.py`, `api.py`, `bot.py` or `service.py`.
- `evaluation/` mounts the application package at `/app` and imports `french_tolls.refine` for its corridor measure. `refine` imports `db` at module level, so the evaluation image transitively depends on whatever `db` imports.
- The image built from `french_tolls/Dockerfile` runs four things: the web application, the bot, the unit suite, and the recorded integration suite. Whatever the dependency arrangement becomes, it has to serve all four.

## Goals / Non-Goals

**Goals:**

- One module that states every table the application has.
- A schema change that is a revision file, not a function that reads `PRAGMA table_info` and guesses.
- Store access that does not block the event loop.
- The paid-request claim keeps its atomicity without depending on a connection's transaction mode.

**Non-Goals:**

- Normalising a route answer or a refinement into typed tables. Both are being deleted, so the question does not arise.
- Modelling `data/vinci_routes_rejected.sqlite3`. See the proposal.
- Moving `/cache/errors/*.json` into a table. Named as not addressed in the proposal.
- Any change to routing, waypoint search, pricing, or the shape of an answer.

## Decisions

### SQLAlchemy 2.x from pip, not 1.4 from Debian

Bookworm ships SQLAlchemy 1.4.46 and alembic 1.8.1. 1.4 has no `DeclarativeBase` and no `Mapped[...]`; models would be written in the pre-2.0 `declarative_base()` / `Column(...)` style against a version already superseded.

*Alternative considered:* apt-install 1.4 and write 1.x-style models. Rejected — the whole point of moving to models is to stop maintaining a schema by hand, and starting on a superseded API means doing the migration twice.

Consequence: `--system-site-packages` goes. An environment that half-draws on the distribution is the arrangement that makes "which SQLAlchemy is this" a question at all. One `requirements.txt` pins aiohttp, PyYAML, pytest, python-telegram-bot, SQLAlchemy, alembic and aiosqlite.

### `evaluation/` gets the same requirements file

`evaluation/report.py` and `evaluation/fetch_google_routes.py` import `french_tolls.refine`, which imports `db`, which will import SQLAlchemy. That image is Debian-only with no package index today and would fail at import.

*Alternative considered:* make `refine`'s import of `db` lazy, so the evaluation never pulls the store in. Rejected as the primary fix — it makes a module-level dependency conditional to suit one consumer, which is the coupling the Dockerfile comment at `evaluation/Dockerfile:20-24` already argued against for aiohttp. Installing the same pinned list is the same trade that file already made.

The evaluation image therefore builds a venv from the same `requirements.txt`. It carries alembic and python-telegram-bot it does not use; that is the cost of one dependency list over two that can drift.

### `JSON` column for the autocomplete response, not `Text`

`autocomplete.response` holds a list of place mappings. A `JSON` column serialises and deserialises it, so nothing in the application does `json.dumps` around a store call.

Consequence at `autocomplete.py:31`: the handler currently serves `row[0]` straight out as the response body, which works only because the column holds a string. It must `json.dumps` the list it now gets back. One `json.dumps` on the hit path, on a list of at most five entries.

*Alternative considered:* keep `Text` and serialise by hand, preserving the byte-for-byte pass-through. Rejected — it keeps a raw-SQL habit in a change whose purpose is to remove them, to save a serialisation that is not on any measured path.

### `stored_at` disappears with the tables that had it

`routes` and `refinements` were the only tables with a timestamp column, and both are removed. Neither surviving table has one, so the question of `Text` ISO-8601 versus a `DateTime` column — where SQLAlchemy's SQLite `DateTime` writes a format that will not parse the `+00:00` strings already on disk — does not arise. Worth recording because it would have been the trap if the tables had survived.

### The paid-request claim is one statement

Today: `BEGIN IMMEDIATE`, `SELECT`, compare, `INSERT ... ON CONFLICT DO UPDATE`, `COMMIT`. The correctness rests on the transaction being IMMEDIATE. Reproducing that under an async session means either forcing every transaction to IMMEDIATE with a `connect`/`begin` event listener on the sync engine, or running the reservation on a second engine configured differently.

Instead, one statement, built with SQLAlchemy's SQLite `insert` rather than written as SQL:

```python
insert(GoogleRequest)
.values(year_month=current_month(), count=1)
.on_conflict_do_update(
    index_elements=[GoogleRequest.year_month],
    set_={"count": GoogleRequest.count + 1},
    where=GoogleRequest.count < ceiling,
)
.returning(GoogleRequest.count)
```

A single statement is atomic regardless of transaction mode. A row comes back when the claim succeeded; nothing comes back when `count >= ceiling`, because the `DO UPDATE` is skipped and the conflicting insert is a no-op.

**The statement is built per call rather than once at module level with `bindparam`.** A module-level statement executed as `session.scalar(stmt, {"month": ..., "ceiling": ...})` is routed by the ORM as a bulk insert: the mapping is read as a row to insert rather than as bind parameters, and the execution fails with `A value is required for bind parameter 'ceiling'`. Building it with its values inline avoids the ambiguity and reads better.

Two details this does not handle, which stay in Python:

- **`ceiling <= 0`.** On the first claim of a month there is no conflict, so the `WHERE` never runs and the insert proceeds unconditionally. The existing `if ceiling <= 0: return False` guard at `db.py:251` must stay, or a zero ceiling would admit exactly one request per month.
- **`RETURNING`** needs SQLite 3.35 or later. Bookworm has 3.40, and the pinned image is the only place this runs.

*Alternative considered:* the event-listener approach that makes every transaction IMMEDIATE. Rejected — it makes every unrelated read take a write lock to protect one statement, and it puts the correctness of the spend counter in a listener registered somewhere else in the module.

### One `migrate` service, not migrate-on-startup

`web` and `bot` mount the same volume and start together. Either could be first to apply a revision.

*Alternatives considered:*

- **Migrate on startup behind a SQLite advisory lock.** No new service, but the lock has to be right and it is exercised only during a deploy, which is when it is least observed.
- **Migrate only in `web`, and have `bot` wait.** Makes `web` special for a reason unrelated to serving, and gives `bot` a startup dependency on a service it otherwise does not need.

A one-shot `migrate` service with `depends_on: { migrate: { condition: service_completed_successfully } }` on both is explicit, fails visibly, and is the piece an operator can run alone.

The integration suite is the exception. It gets its own tmpfs cache directory, so it applies the schema itself at session setup rather than depending on `migrate` — the suite must remain runnable as a single `docker compose run`.

### `refine` returns its `Refinement` directly

`_store` is the only caller of `Refinement.stored()` and `db.write_refinement`. With storage gone it collapses to `return result`, so the three call sites at `refine.py:572`, `590` and `629` return the object they were constructing. `_from_stored` loses its only caller. `Refinement.preference` stays — `as_dict()` emits it at `refine.py:135` and `api.py:46` passes that through, and the integration cassettes check it independently in `google_replay.py:65`.

`encode_polyline` becomes unused in `refine.py` and comes off the import at line 27. `decode_polyline` and `SegmentIndex` stay.

### `_for_delivery` stays, with a new reason

`service.py:96` exists because the travel-time factor is a setting rather than a property of a journey, and applying it before the cache would freeze the factor into stored rows. There is no cache now, so that reason is gone — but the function still applies the factor and derives `duration` from `duration_osrm`, which `route-service` requires on every answer. It keeps its work and loses its docstring's premise.

## Risks / Trade-offs

**Every look at a journey buys Google requests again → the ceiling is the only bound left.** `GOOGLE_MAX_REQUESTS_PER_MONTH` should be re-chosen against the number of *calculations* expected rather than the number of distinct journeys, especially wherever `web-front-end`'s debug setting is on. Stated in the delta specs rather than left to a bill.

**Deleting the `cache:` volume resets the month's count to zero mid-month → the ceiling stops holding until the month turns.** Accepted, by decision. If it matters on the day, read `SELECT count FROM google_requests WHERE year_month = ...` from the old volume first and insert that row after the migration.

**Deleting the volume discards paid LocationIQ answers → those queries are bought again.** Bounded by how many distinct place searches recur, and each is one cheap request.

**A repeat journey re-routes → latency where there was a cache hit.** A few hundred local OSRM requests, about a second. No money. This is the trade the change makes deliberately, and it buys the removal of a stale-answer class that nothing detected.

**`--system-site-packages` goes → the image build now needs a package index for everything, not just python-telegram-bot.** A network failure that used to break one layer now breaks the build. The pinned file is what keeps a rebuild reproducible.

**`aiosqlite` runs SQLite on a worker thread per connection.** It does not make SQLite concurrent; it stops the loop waiting. WAL is still what lets a reader and a writer coexist, and must stay set on the engine.

**A deployment that starts `web` without Compose resolving `depends_on` gets an unmigrated database.** It will fail on a missing table rather than create one silently, which is the behaviour `runtime-store` requires.

## Migration Plan

1. Stop the application profile.
2. Optionally record the current month's count: `sqlite3 <volume>/database.db "SELECT year_month, count FROM google_requests"`.
3. Remove the `cache:` volume.
4. Deploy. `migrate` creates the two tables from the baseline revision; `web` and `bot` start after it.
5. If step 2 was taken and the month has not turned, insert that row.

Rollback is the previous image plus a fresh volume. The old code recreates its own schema on first open, so nothing has to be undone in the database — but the volume cannot be shared between the two versions in either direction, because the baseline revision will not apply to a database that already has the tables.
