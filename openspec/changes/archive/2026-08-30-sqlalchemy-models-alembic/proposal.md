## Why

`french_tolls/db.py` is a schema in a string literal, five hand-written statements, and three one-shot migration functions that decide what to do by reading `PRAGMA table_info`. There is no record of what version a database is at. `_drop_fingerprinted` exists because `CREATE TABLE IF NOT EXISTS` will not alter a table that is already there, and the next schema change needs another function exactly like it.

The calls also block. `db.py` says so in its own docstring and names the fix — put them behind an executor — which is the wrong fix twice over: the application is aiohttp throughout, and an executor is a thread pool bolted to a driver that has an async one.

Two of the four tables are being retired at the same time, so the store shrinks to the two rows that are worth keeping: an autocomplete answer that cost a paid LocationIQ request, and the count of what has been spent this month.

## What Changes

### The schema is declared once, in models

- `french_tolls/models.py` SHALL hold every table the application reads or writes, as SQLAlchemy declarative models. There SHALL be two: `Autocomplete` and `GoogleRequest`.
- The `SCHEMA` string in `db.py` goes. So do `_rename_legacy`, `_adopt_legacy_table`, and `_drop_fingerprinted`: a version table replaces all three, and the databases they were written for are being discarded.
- The builder's `data/vinci_routes_rejected.sqlite3` is **not** in scope. It is a scratch file for one long build, deleted and rebuilt from routing alone, and it keeps its raw `sqlite3` access.

### Alembic owns the schema

- A baseline revision creates the two tables. A one-shot `migrate` Compose service runs `alembic upgrade head`, and `web` and `bot` depend on it. Two processes migrating one SQLite file at once is the failure this avoids.
- **BREAKING, operationally.** The `cache:` volume SHALL be deleted before the first run. The existing database already has both tables, so the baseline revision cannot apply to it. This discards the paid autocomplete answers and resets this month's Google request count to zero, which leaves the monthly ceiling unenforced until the month turns.

### Every store call is async

- **BREAKING** `db.requests_this_month` and `db.reserve_google_request` become coroutines, on `aiosqlite` through SQLAlchemy's async session. `bot.remaining_budget` becomes one with them.
- `reserve_google_request` keeps its guarantee — counted before the request is issued, never understating, atomic against a concurrent journey — through one statement rather than an explicit `BEGIN IMMEDIATE`, built with SQLAlchemy's SQLite `insert` rather than written as SQL:

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

  A row comes back when the claim succeeded and nothing comes back at the ceiling. One statement is atomic, so the transaction mode stops carrying the correctness.

- Nothing catches `SQLAlchemyError`. A store that cannot be written is a fault worth surfacing, not one worth logging and continuing past.

### The route cache goes

- **BREAKING** The `routes` table and `db.read_answer` / `db.write_answer` are removed. Every journey is routed from nothing, every time.
- This costs latency and no money. A repeat journey now spends the same few hundred local OSRM requests the first one did, in about a second.
- It also removes a class of wrong answer. `route-service` records that a rebuilt pipeline reaches a cached journey, that the cache must be purged by hand after a rebuild, and that a stale toll total is indistinguishable from a correct one. Nothing can go stale once nothing is stored.

### The refinement cache goes

- **BREAKING** The `refinements` table and `db.read_refinement` / `db.write_refinement` are removed, with `Refinement.stored()`, `_from_stored`, and `_store`.
- **This costs money, and it is the one cost worth stating plainly.** `google-route-refinement` guarantees that a journey costs at most two Google requests *ever*. That guarantee is withdrawn. Each refinement is bought fresh: a redirect costs one request, and drawing the overlay costs two — per look, not per journey.
- `web-front-end` requests the refinement for every journey calculated while the debug setting is on. Under that setting the monthly ceiling is now consumed at two requests per calculation, with no repeat journey ever coming back free.
- The two budgets still bound it. `reserve_google_request` is unchanged in what it promises, and an exhausted month still returns unrefined waypoints naming the budget that stopped it. What is lost is the amortisation, not the ceiling.

### The application image is built from a package index

- **BREAKING** `french_tolls/Dockerfile` stops installing `python3-aiohttp`, `python3-yaml` and `python3-pytest` from Debian and stops using `--system-site-packages`. One venv is built from a pinned `requirements.txt`: aiohttp, PyYAML, pytest, python-telegram-bot, SQLAlchemy, alembic, aiosqlite.
- Debian bookworm ships SQLAlchemy 1.4.46 and alembic 1.8.1. 1.4 has no `DeclarativeBase` and no `Mapped[...]`, so the declarative style this change is for is unavailable from the distribution. Pinning versions in one file is also the smaller thing to reason about than a venv that half-sees the system packages.
- `evaluation/Dockerfile` needs the same treatment or a smaller fix. `evaluation/report.py` and `evaluation/fetch_google_routes.py` import `french_tolls.refine`, which imports `db` at module level, which will import SQLAlchemy. That image is Debian-only with no package index today, and it will fail to import.

## Capabilities

### New Capabilities

- `runtime-store`: what the application persists, how the schema is declared and versioned, how a schema change reaches a running deployment, and why every call into the store is a coroutine.

### Modified Capabilities

- `route-service`: the route cache is gone, so the requirement fixing the cache key is removed and the requirement placing the store outside `data/` narrows to what is left; a fifth application service appears; the image stops coming from Debian packages.
- `google-route-refinement`: a refinement is no longer stored, so "each phase is bought once" and everything downstream of it is withdrawn.
- `web-front-end`: the overlay's stated cost changes from two requests per journey to two per calculation, which is what a reader of that requirement needs to know before turning the setting on.

## Impact

- New: `french_tolls/models.py`, `french_tolls/requirements.txt`, `french_tolls/alembic.ini`, `french_tolls/migrations/`.
- Rewritten: `french_tolls/db.py` — an async engine and session, `current_month`, `requests_this_month`, `reserve_google_request`, and `CACHE_DIR`. Nothing else survives.
- Modified: `french_tolls/autocomplete.py` (async session; the `JSON` column returns a list, so the response body is re-serialised), `french_tolls/service.py` (no cache read, no cache write; `_for_delivery` stays because the travel-time factor still has to be applied, and its docstring stops describing a cache), `french_tolls/refine.py` (no stored refinement, three `await`s on the reservation, `encode_polyline` import becomes unused), `french_tolls/bot.py` (`remaining_budget` awaited), `french_tolls/tests/test_refine.py` (`FakeDB` methods become coroutines).
- Modified: `french_tolls/Dockerfile`, `evaluation/Dockerfile`, `docker-compose.yml`.
- Unchanged: the routing, the waypoint search, the toll accounting, the pipeline, the builder's rejection store, and every key the page and the bot read from an answer.
- **Latency up on repeat journeys**, from a cache hit to a full route search.
- **Paid requests up**, without bound per journey. This is the change's real price and it is stated in `google-route-refinement`'s delta rather than left to be discovered.
- Not addressed: whether `service.py`'s failure records under `/cache/errors/` should become a table. They are loose JSON files today, nothing reads them programmatically, and moving them is a separate change.
