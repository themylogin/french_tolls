## 1. Moving the files

- [x] 1.1 Move `french_tolls/Dockerfile` to `Dockerfile`, `french_tolls/requirements.txt` to `requirements.txt`, `french_tolls/alembic.ini` to `alembic.ini`, and `french_tolls/migrations/` to `alembic/`; verify `ls french_tolls/` shows Python modules, `integration/` and `tests/` and nothing else
- [x] 1.2 Verify the moved `alembic/` still holds `env.py`, `script.py.mako` and `versions/`, and that no `__pycache__` came with it

## 2. The image

- [x] 2.1 Replace `COPY . /app/french_tolls/` with explicit copies of `french_tolls/`, `alembic.ini` and `alembic/`, keeping `WORKDIR /app` and `PYTHONPATH=/app`; verify the built image has `/app/french_tolls/api.py`, `/app/alembic.ini` and `/app/alembic/versions/`
- [x] 2.2 Verify the image does **not** contain `/app/french_tolls/alembic.ini` or `/app/french_tolls/migrations/`, which would mean a stale layer is still being used
- [x] 2.3 Add `!requirements.txt`, `!alembic.ini` and `!alembic` to the root `.dockerignore`; verify the build succeeds and reports a context of a few megabytes rather than gigabytes
- [x] 2.4 Point `evaluation/Dockerfile` at `requirements.txt` instead of `french_tolls/requirements.txt`; verify `python3 -c "import french_tolls.refine, osmium, yaml"` still succeeds in that image with the package mounted at `/app`

## 3. Compose

- [x] 3.1 Change all six application services — `web`, `bot`, `migrate`, `tests`, `integration`, `recorder` — from `build: ./french_tolls` to the root context with the root `Dockerfile`; verify `docker compose config -q` parses and `docker compose build` succeeds for each
- [x] 3.2 Shorten the `migrate` command to `alembic upgrade head`, relying on `WORKDIR /app` and `alembic.ini` beside it; verify it exits 0 against a scratch volume and creates both tables
- [x] 3.3 Verify `docker compose up` with no profile still starts only `osrm-toll` and `osrm-optimal`
- [x] 3.4 Verify `builder`, `www` and `evaluation` build definitions are untouched apart from `evaluation`'s one `COPY` path

## 4. Alembic configuration

- [x] 4.1 Set `script_location = %(here)s/alembic` in the moved `alembic.ini`; verify `alembic current` runs from `/app` without `-c` and without error
- [x] 4.2 Add `file_template = %%(year)d-%%(month).2d-%%(day).2d_%%(hour).2d-%%(minute).2d_%%(slug)s`; verify a throwaway `alembic revision -m "try it"` lands as `<date>_<time>_try_it.py`, then delete that revision
- [x] 4.3 Rename `e8eba9c91637_baseline.py` to `2026-08-30_17-46_baseline.py`, taking the stamp from its own `Create Date`; verify the `revision` string inside is untouched
- [x] 4.4 Verify the rename changed no database: `alembic current` against the deployed volume still reports `e8eba9c91637`, and `alembic upgrade head` is a no-op
- [x] 4.5 Verify `alembic check` reports no drift against the models, and that a fresh volume still migrates to both tables from empty

## 5. The paths that named the old layout

- [x] 5.1 Update `french_tolls/integration/conftest.py` to find `alembic.ini` at the repository root; verify `docker compose run integration` still applies the schema to its own tmpfs and passes as one command
- [x] 5.2 Update `french_tolls/tests/test_spending.py`'s `ALEMBIC_INI`; verify the store tests still migrate into `tmp_path`
- [x] 5.3 Verify by grep that nothing outside `openspec/changes/archive/` still names `french_tolls/Dockerfile`, `french_tolls/requirements.txt`, `french_tolls/alembic.ini` or `french_tolls/migrations`

## 6. The rename

- [x] 6.1 Rename `spending.requests_this_month` to `google_requests_this_month` at its definition and in `__all__`; verify no comment was added to `french_tolls/spending.py` by diffing the file and confirming only the two name occurrences changed
- [x] 6.2 Update the caller in `bot.py` and the nine assertions in `french_tolls/tests/test_spending.py`; verify `grep -rn "requests_this_month" french_tolls/` shows only the new name
- [x] 6.3 Verify `remaining_budget` still reports the same number for a month with a known count

## 7. Verification

- [x] 7.1 Run the unit suite; verify it passes
- [x] 7.2 Run the recorded drive-flow suite; verify it passes
- [x] 7.3 Rebuild and redeploy all six application services; verify `migrate` exits 0, `web` and `bot` start after it, and a journey is answered end to end through `nginx`
- [x] 7.4 Verify the deployed store still reports schema version `e8eba9c91637` after the redeploy, and that the month's request count was not reset
- [x] 7.5 Retire the documentation this makes false: any comment naming the old paths, in `Dockerfile`, `evaluation/Dockerfile`, `alembic.ini`, `docker-compose.yml`, `.dockerignore` and `.env.example`; verify by grep
