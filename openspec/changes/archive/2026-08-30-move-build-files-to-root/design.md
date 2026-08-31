## Context

See `proposal.md` — Why. The constraints that shape the approach:

- Six Compose services build from `./french_tolls`: `web`, `bot`, `migrate`, `tests`, `integration`, `recorder`. All six move to the root context together or none does.
- A root `.dockerignore` already exists, added so `evaluation` could build from the root and reach `french_tolls/requirements.txt`. It is `*` with `!french_tolls` and `!evaluation` named back in, and it keeps the context at about 1.7 MB of a 26 GB tree.
- `alembic.ini` currently holds `script_location = %(here)s/migrations` and `sqlalchemy.url`. It no longer holds `prepend_sys_path`, so `french_tolls` is importable only because the image sets `PYTHONPATH=/app`.
- Three places name `alembic.ini` by a path built from `__file__` or from `/app/french_tolls/`: the `migrate` service's command, `french_tolls/integration/conftest.py`, and `french_tolls/tests/test_spending.py`.
- `spending.requests_this_month` has one application caller (`bot.py`) and nine assertions in `french_tolls/tests/test_spending.py`.

## Goals / Non-Goals

**Goals:**

- `french_tolls/` holds Python and nothing else.
- A revision directory that lists in the order revisions were written.
- A name that says whose requests are being counted.

**Non-Goals:**

- Moving `builder/Dockerfile`, `evaluation/Dockerfile` or `www/Dockerfile`. Each belongs to its own image and stays with it; only the application's rises to the root, because only the application's is inside a Python package.
- Changing what any service does at runtime, the store's schema, or the deployed database.
- Adopting `data/probe_pref.py`. Named as not addressed in the proposal.

## Decisions

### The directory is `alembic/`, not `migrations/`

At the root a bare `migrations/` says what it holds but not who reads it, and the root is where a reader looks first. `alembic/` names the tool that owns it, matches `alembic.ini` beside it, and is what `alembic init` produces by default.

### `file_template`, and what `%(name)` resolves to

Alembic has no `%(name)s` token. The tokens are `%(rev)s`, `%(slug)s`, and the date parts. `%(slug)s` is the `-m` message slugified — it is what produced `baseline` in `e8eba9c91637_baseline.py` — so it is the one that matches the requested shape:

```ini
file_template = %%(year)d-%%(month).2d-%%(day).2d_%%(hour).2d-%%(minute).2d_%%(slug)s
```

The `%%` is required: alembic.ini is read by `ConfigParser`, where a single `%` starts an interpolation.

*Consequence, accepted:* the revision id leaves the filename. That is the point — it is what made the listing sort by a hash — but it costs two things. The filename no longer states the id, so mapping `alembic_version` to a file means opening one. And two revisions generated in the same minute collide on name; alembic will not overwrite, but the second needs a hand-chosen name. Both are cheap against a directory that reads in order.

### The existing baseline is renamed

`e8eba9c91637_baseline.py` becomes `2026-08-30_17-46_baseline.py`, from the `Create Date` in its own docstring.

Safe because alembic resolves revisions by importing every file under `versions/` and reading the `revision` string inside, never from the filename. The deployed database records `e8eba9c91637`, that string is untouched, and `alembic current` will report the same version after the rename as before.

*Alternative considered:* leave it, and let only new revisions take the new shape. Rejected — one file out of the ordering is exactly the listing problem this change is for, and it would be the first file a reader sees.

### The image copies what it needs, by name

`COPY . /app/french_tolls/` works today only because the context *is* the package. From the root it would copy the whole tree into the package directory. It becomes explicit:

```dockerfile
COPY requirements.txt /tmp/requirements.txt      # unchanged, the path is now the root's
...
COPY french_tolls/ /app/french_tolls/
COPY alembic.ini /app/alembic.ini
COPY alembic/ /app/alembic/
```

`WORKDIR /app` and `PYTHONPATH=/app` are unchanged.

### `migrate` stops naming the config file

With `alembic.ini` at `/app/alembic.ini` and `WORKDIR /app`, alembic finds it by its own default. The command becomes:

```yaml
command: alembic upgrade head
```

*Alternative considered:* keep `-c /app/alembic.ini` explicit. Rejected — it names a path that is now the default, and the two would have to be kept agreeing.

The two test entry points still need the path, because pytest's working directory is not `/app` in every invocation. Each builds it from `__file__` and each gets shorter by one level.

### `.dockerignore` gains three names

```
!requirements.txt
!alembic.ini
!alembic
```

Named rather than left to a broader pattern, for the reason already written in that file: excluding everything and naming what may be sent is what stops a later directory being shipped by accident.

### The rename is mechanical, and `spending.py` gains no comment

`requests_this_month` → `google_requests_this_month`, at its definition, in `__all__`, in `bot.py`, and in nine assertions. No comment is added to `spending.py`: the change exists so the name carries the fact, and a comment restating it would be the thing the rename was meant to replace.

## Risks / Trade-offs

**Six services change build context at once → a mistake in `.dockerignore` reaches every one of them.** The failure is loud: either the build cannot find a file it copies, or the context transfer jumps from megabytes to gigabytes and is obvious in the build output. The task list checks the context size explicitly rather than trusting it.

**A stale image is indistinguishable from a working one until something is copied.** `docker compose build` must be re-run for all six; `up` without `--build` would keep serving the old image, which still has `/app/french_tolls/alembic.ini` and would migrate happily. The task list rebuilds and checks the file layout inside the image.

**Renaming a revision file feels riskier than it is.** The mitigation is to verify rather than argue: `alembic current` against the deployed volume must report `e8eba9c91637` after the rename, and `alembic upgrade head` must be a no-op.

**`git mv` versus a plain move.** Four of the moved paths are untracked in the working tree today. Whichever is used, the point is that history is not the deliverable here and the files' contents are unchanged apart from the edits listed above.

## Migration Plan

No data migration. Rebuild all six application services and redeploy; `migrate` runs as it does on any deploy and finds the database already at head.

Rollback is the previous image. The database is untouched in both directions, so a rollback needs nothing done to it.
