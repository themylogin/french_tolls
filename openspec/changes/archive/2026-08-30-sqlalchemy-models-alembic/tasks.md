## 1. Dependencies and images

- [x] 1.1 Add `french_tolls/requirements.txt` pinning aiohttp, PyYAML, pytest, python-telegram-bot, SQLAlchemy 2.x, alembic and aiosqlite to exact versions; verify `pip install -r` resolves with no conflict in a scratch container
- [x] 1.2 Rewrite `french_tolls/Dockerfile`: drop every `python3-*` package except `python3` and `python3-venv`, drop `--system-site-packages`, install from `requirements.txt`; verify `python3 -c "import aiohttp, yaml, telegram, sqlalchemy, alembic, aiosqlite, pytest"` succeeds in the built image
- [x] 1.3 Verify the image draws on no distribution package: `python3 -c "import aiohttp, sys; print(aiohttp.__file__)"` reports a path under the venv, not under `/usr/lib/python3`
- [x] 1.4 Give `evaluation/Dockerfile` a venv from the same `requirements.txt` and drop its `python3-aiohttp`; verify `python3 -c "import french_tolls.refine"` succeeds in that image with the package mounted at `/app`

## 2. Models

- [x] 2.1 Write `french_tolls/models.py` with `Base`, `Autocomplete` (`q` primary key, `response` as `JSON`) and `GoogleRequest` (`year_month` primary key, `count`); verify `Base.metadata.tables` names exactly those two tables
- [x] 2.2 Verify the `JSON` column round-trips a list of place mappings unchanged and that SQLite stores it with text affinity despite the declared type; the models are declared on their own merits and are not held to the shape of the hand-written schema they replace

## 3. Alembic

- [x] 3.1 Add `french_tolls/alembic.ini` and `french_tolls/migrations/env.py`, with `env.py` reading the database path from `db.path()` and its target metadata from `models.Base.metadata`; verify `alembic current` runs against an empty directory without error
- [x] 3.2 Autogenerate the baseline revision and check it by hand; verify `alembic upgrade head` on an empty file produces the two tables and `alembic check` reports no drift against the models
- [x] 3.3 Verify re-running `alembic upgrade head` against a database already at head alters nothing and loses no row
- [x] 3.4 Verify the version is recorded: `alembic_version` holds the baseline revision after the upgrade

## 4. The store

- [x] 4.1 Rewrite `french_tolls/db.py` around an async engine (`sqlite+aiosqlite`) with WAL set on connect, an `async_sessionmaker`, and `CACHE_DIR` / `path()` / `current_month()` unchanged; verify a session opens and closes against a temporary file
- [x] 4.2 Delete `SCHEMA`, `LEGACY_NAME`, `_rename_legacy`, `_adopt_legacy_table`, `_drop_fingerprinted`, `_key`, `_now`, `connect`, `read_answer`, `write_answer`, `read_refinement`, `write_refinement`; verify `grep -n "sqlite3\|CREATE TABLE" french_tolls/db.py` returns nothing
- [x] 4.3 Make `requests_this_month` a coroutine reading `GoogleRequest` for the current month; verify it returns 0 for a month with no row
- [x] 4.4 Make `reserve_google_request` a coroutine using the single `INSERT ... ON CONFLICT DO UPDATE ... WHERE count < :ceiling RETURNING count` statement, keeping the `ceiling <= 0` guard; verify a claim below the ceiling returns True and increments by one
- [x] 4.5 Verify a claim at the ceiling returns False and leaves the count unchanged
- [x] 4.6 Verify `ceiling = 0` refuses on the first claim of a fresh month, which is the case the `WHERE` clause does not cover
- [x] 4.7 Verify concurrent claims: gather 10 claims against a ceiling of 10 on an empty month and assert 10 succeed and the count is exactly 10; gather 10 against a ceiling of 4 and assert exactly 4 succeed

## 5. Autocomplete

- [x] 5.1 Convert `french_tolls/autocomplete.py` to the async session for both the read at line 28 and the write at line 66; verify a cached query is served without a network call
- [x] 5.2 Store LocationIQ's answer as it arrived rather than the mapping the page is served, and move that mapping onto the read path so it runs on a hit and a miss alike; verify a row written by a miss and the body served from it on the next hit are the same bytes the miss returned
- [x] 5.3 Verify the handler still answers `application/json`, that a 404 from LocationIQ stores an empty list, and that a stored raw answer carrying a field the mapping ignores is served without it

## 6. Removing the route cache

- [x] 6.1 Remove the cache read at `french_tolls/service.py:164-166` and the booth-set staleness comment above the routing block; verify `get_route` computes on every call
- [x] 6.2 Remove the `db.write_answer` call at `french_tolls/service.py:218`; verify `grep -n "db\." french_tolls/service.py` shows only the `CACHE_DIR` import
- [x] 6.3 Rewrite `_for_delivery`'s docstring: it keeps applying the travel-time factor and deriving `duration` from `duration_osrm`, and stops describing a cache; verify the existing unit suite still passes
- [x] 6.4 Verify the answer is unchanged key for key against the shape `route-service` requires, by running `french_tolls/tests` and the recorded integration suite

## 7. Removing the refinement cache

- [x] 7.1 Delete `_store` at `french_tolls/refine.py:632-634` and return the `Refinement` directly at lines 572, 590 and 629; verify the refinement returned is unchanged in shape
- [x] 7.2 Delete `Refinement.stored()` and `_from_stored`, and remove the cache read and the preference-mismatch discard at `french_tolls/refine.py:502-517`; verify `grep -n "read_refinement\|write_refinement\|stored()" french_tolls/` returns nothing
- [x] 7.3 Drop `encode_polyline` from the import at `french_tolls/refine.py:27`, keeping `decode_polyline` and `SegmentIndex`; verify the module imports and the unit suite passes
- [x] 7.4 Await `db.reserve_google_request` at `french_tolls/refine.py:456`, `556` and `600`; verify a refinement attempted at an exhausted ceiling still returns unrefined waypoints naming the budget
- [x] 7.5 Verify `Refinement.preference` still reaches `api.py:46` through `as_dict()`, and that `french_tolls/integration/google_replay.py` still rejects a cassette recorded at another preference

## 8. The bot

- [x] 8.1 Make `remaining_budget` a coroutine at `french_tolls/bot.py:290` and await it at line 279; verify the drive flow reports the same remaining budget it did before

## 9. Compose

- [x] 9.1 Add a one-shot `migrate` service to `docker-compose.yml`, built from the application image, mounting `cache:`, running `alembic upgrade head`, behind the application profile; verify it exits 0 against an empty volume
- [x] 9.2 Add `depends_on` with `condition: service_completed_successfully` on `migrate` to `web` and `bot`; verify `docker compose up` starts `migrate` first and `web` only after it
- [x] 9.3 Verify a failing migration blocks the serving services: make the revision fail deliberately and confirm `web` and `bot` do not start
- [x] 9.4 Verify `docker compose up` with no profile still starts only the two routers, and that `migrate` is not among them
- [x] 9.5 Have the integration suite apply the schema to its own tmpfs cache at session setup rather than depend on `migrate`; verify `docker compose run integration` passes as a single command

## 10. Tests

- [x] 10.1 Convert `FakeDB` in `french_tolls/tests/test_refine.py:218` so its methods are coroutines; verify the whole of `french_tolls/tests` passes
- [x] 10.2 Add unit coverage for `reserve_google_request` against a temporary database covering the four cases in tasks 4.4 to 4.7; verify the new tests pass
- [x] 10.3 Run the recorded drive-flow suite and verify it passes with no route or refinement stored, and that its run leaves no `routes` or `refinements` table anywhere
- [x] 10.4 Verify the evaluation still imports and runs its report against a recorded fixture, with no network and no Google key

## 11. Deployment

- [x] 11.1 Record the current month's count from the deployed volume before removing it: `sqlite3 <volume>/database.db "SELECT year_month, count FROM google_requests"`
- [x] 11.2 Remove the `cache:` volume and deploy; verify `migrate` creates the two tables and `web` answers a journey
- [x] 11.3 SKIPPED by decision. August stood at 818 of 5000 with one day left; the operator chose to let it reset to zero rather than restore it. Recorded here rather than left undone.
- [x] 11.4 Reviewed `GOOGLE_DIRECTIONS_MAX_REQUEST_PER_MONTH` (the real variable name) against the new cost: left at 5000 with `DEBUG=1`, by decision, which allows about 2 500 calculations a month now that a refinement no longer amortises. `.env.example` states the change so the next reader sets it against calculations rather than journeys.

## 12. Consequences found while implementing

- [x] 12.1 REVERTED. A `cache_dir` setting was added to `config.py` and then removed: nothing read it. No image or Compose service sets `CACHE_DIR`, every one of them mounts the store at the default, and the only test that redirects it patches `db.CACHE_DIR` directly. `CACHE_DIR` is a plain constant again, as it was.
- [x] 12.2 Build the `evaluation` image from the repository root with a root `.dockerignore`, because a COPY cannot reach `french_tolls/requirements.txt` from `evaluation/` and this host's Docker 20.10 rejects `additional_contexts`; verify the context sent is about 1.7 MB of a 26 GB tree
- [x] 12.3 Make `recorder` depend on `migrate` too and put `migrate` in the `record` profile: it writes to the same volume and counts real money against it, which is what `runtime-store` requires of any service that writes the store; verify `docker compose config` resolves it
- [x] 12.4 Apply the schema in the integration suite through a session fixture in `french_tolls/integration/conftest.py`, using alembic rather than `create_all` so the suite exercises the revisions a deployment runs; verify `docker compose run integration` passes as one command
- [x] 12.5 Set `path_separator = os` in `alembic.ini`; verify the legacy-splitting DeprecationWarning no longer appears in either suite
- [x] 12.6 Retire the documentation the change made false: the `clean-cache` target no longer tells an operator to run it after every pipeline rebuild, `api.py`'s refine docstring no longer promises a journey is bought once, and `.env.example` and `docker-compose.yml` state the new per-calculation cost; verify by grep that no comment still describes a stored answer or refinement
- [x] 12.7 Move the Google spend accounting out of `db.py` into `spending.py`, leaving `db.py` owning only where the store is and how a session is opened; `autocomplete` already took a session and wrote its own queries, and the accounting was the one feature hiding its queries in the store module. Drop the `DB_NAME` constant (one use, inlined) and stop exporting `current_month` (no caller outside). Verify both suites pass and the live service answers.
