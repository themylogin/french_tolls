## Why

**Four build files sit inside the Python package they build.** `french_tolls/` holds the application's modules — and also its `Dockerfile`, its `requirements.txt`, its `alembic.ini` and its `migrations/`. None of those are importable, none are part of the package, and their being there is what forces the awkwardness around them: the `evaluation` image already builds from the repository root with a root `.dockerignore`, for the single reason that a `COPY` in `evaluation/` cannot reach `french_tolls/requirements.txt`. The dependency list is a project fact, not a package module, and putting it where project facts live removes the reason that workaround existed.

**A revision's filename says nothing about when it was written.** `e8eba9c91637_baseline.py` sorts by a hash. A directory of them sorts arbitrarily, so reading the migration history means opening files to find their `Create Date`. The order revisions were written in is the one thing a reader wants from the listing.

**`requests_this_month` does not say whose requests.** `spending.py` counts Google Routes requests and nothing else, but the name reads as a general counter — and `bot.py` already writes `config.google_max_requests_per_month - await spending.requests_this_month()`, where one side names the provider and the other does not.

## What Changes

### The build files move to the repository root

- `french_tolls/Dockerfile` → `Dockerfile`
- `french_tolls/requirements.txt` → `requirements.txt`
- `french_tolls/alembic.ini` → `alembic.ini`
- `french_tolls/migrations/` → `alembic/`, keeping `env.py`, `script.py.mako` and `versions/`

The directory is renamed to `alembic` because at the root it needs to say which tool owns it; inside the package `migrations/` was unambiguous by position.

- **BREAKING (build)** The application image's build context becomes the repository root. Six Compose services build from `./french_tolls` today and will build from `.`; the `Dockerfile`'s `COPY . /app/french_tolls/` becomes explicit copies of the package, the pinned list, and the alembic files.
- The root `.dockerignore` gains `requirements.txt`, `alembic.ini` and `alembic/`. It already exists and already names what may be sent.
- `evaluation/Dockerfile` copies `requirements.txt` rather than `french_tolls/requirements.txt`. Its own build context is already the root, for exactly this reason.
- `alembic.ini`'s `script_location` becomes `%(here)s/alembic`.
- Everything that names `alembic.ini` by path follows it: the `migrate` service's command, `french_tolls/integration/conftest.py`, and `french_tolls/tests/test_spending.py`.

### A revision is named for when it was written

- `alembic.ini` gains `file_template = %%(year)d-%%(month).2d-%%(day).2d_%%(hour).2d-%%(minute).2d_%%(slug)s`, so a new revision lands as `2026-08-30_17-46_baseline.py`.
- The existing baseline is renamed to match. Alembic identifies a revision by the `revision` string inside the file, never by its filename, so the rename does not touch `alembic_version` and no deployed database notices.
- **The revision hash leaves the filename.** That is the point — it is what made the listing unsortable — but it is a real loss: the filename no longer states the id, and two revisions generated in the same minute would collide on name.

### `requests_this_month` says whose requests

- **BREAKING (internal)** `spending.requests_this_month` becomes `spending.google_requests_this_month`. One caller in `bot.py`, and the assertions in `french_tolls/tests/test_spending.py`.
- No comment is added to `spending.py`. The name is the documentation this change is for.

## Capabilities

### Modified Capabilities

- `route-service`: the application image is no longer defined under `french_tolls/`, and its services no longer build from that directory.
- `runtime-store`: a revision file gains a naming convention, so a listing reads in the order revisions were written.

The `requests_this_month` rename is deliberately **not** specced. It is an internal Python name; no requirement names it, and specs here do not carry function names.

## Impact

- Moved: `french_tolls/Dockerfile`, `french_tolls/requirements.txt`, `french_tolls/alembic.ini`, `french_tolls/migrations/` → the root, the last as `alembic/`.
- Modified: `docker-compose.yml` (six build stanzas, the `migrate` command), `.dockerignore`, the moved `Dockerfile` and `alembic.ini`, `evaluation/Dockerfile`, `french_tolls/integration/conftest.py`, `french_tolls/tests/test_spending.py`, `french_tolls/spending.py`, `french_tolls/bot.py`.
- Unchanged: every module of the package, the store's schema, the deployed database, and what any service does at runtime. This moves files and renames one function.
- **The application image's context grows** from `french_tolls/` alone to whatever the root `.dockerignore` admits. That file is what keeps it small, and it is already doing the job for `evaluation`.
- Not addressed: `data/probe_pref.py` calls `db.requests_this_month()`, which has not existed since the accounting moved to `spending.py`. It is an untracked scratch script under `data/` and is already broken; this change does not adopt it.
