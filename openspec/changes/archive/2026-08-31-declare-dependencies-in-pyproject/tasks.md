## 1. The declaration

- [x] 1.1 Write `pyproject.toml` with a `[project]` table naming the direct dependencies, `requires-python = ">=3.11"`, and no `[build-system]`; verify `python3 -c "import tomllib,pathlib; tomllib.loads(pathlib.Path('pyproject.toml').read_text())"` parses it
- [x] 1.2 Carry only the bounds that have a reason — `SQLAlchemy>=2` for the 2.0 declarative style the models use, `python-telegram-bot~=21.0` for the major the image was built with; verify no other dependency carries a bound
- [x] 1.3 Keep `pytest` a plain dependency rather than an extra, since two of the five services the image serves are the test suites; verify it appears in `dependencies`

## 2. The compiled list

- [x] 2.1 Replace the hand-pinned `requirements.txt` with `uv pip compile` output; verify it carries uv's generated header and that every package line is pinned with `==`
- [x] 2.2 Verified: 32 pinned packages against 10 direct dependencies, each with a `# via` annotation naming what required it. The hand-pinned list named 7 and installed roughly 28.
- [x] 2.3 Verify every direct dependency in `pyproject.toml` appears in the compiled list
- [x] 2.4 Verify no dependency version changed from the hand-pinned set that preceded this: aiohttp 3.14.3, PyYAML 6.0.3, pytest 9.1.1, python-telegram-bot 21.11.1, SQLAlchemy 2.0.52, alembic 1.19.1, aiosqlite 0.22.1

## 3. Reproducing it

- [x] 3.1 Add a `requirements` target to `Makefile` running `uv pip compile` in `ghcr.io/astral-sh/uv:python3.11-bookworm-slim`, matching the application image's interpreter; verify it is listed in `.PHONY`
- [x] 3.2 Use `$(DOCKER)` rather than a bare `docker`, so the target honours the override the rest of the Makefile offers; verify by grep
- [x] 3.3 Verify the target is reproducible: run it against an unchanged `pyproject.toml` and confirm the result is byte-identical to the committed file
- [x] 3.4 Verify the compiled list and the declaration agree — every direct dependency named in `pyproject.toml` resolves in the committed `requirements.txt`

## 4. What must not change

- [x] 4.1 Verify `Dockerfile` still copies `requirements.txt` and installs it with pip, and that `uv` is not in the image
- [x] 4.2 Verify `evaluation/Dockerfile` installs the same file and is otherwise untouched
- [x] 4.3 Verify `pyproject.toml` is neither copied into the image nor named in `.dockerignore`, because the image installs the resolution and has no use for the declaration
- [x] 4.4 Verified untouched by this change. It mentions `requirements.txt` once, in a comment on the `evaluation` build context that the earlier move change wrote; nothing here added or altered a line.

## 5. Verification

- [x] 5.1 Build the application image and verify every dependency imports and resolves under the venv rather than the distribution
- [x] 5.2 Build the evaluation image and verify it still imports `french_tolls.refine` alongside its Debian `osmium`
- [x] 5.3 Run the unit suite; verify it passes
- [x] 5.4 Run the recorded drive-flow suite; verify it passes
- [x] 5.5 Redeploy and verify a journey is answered end to end through `nginx`
