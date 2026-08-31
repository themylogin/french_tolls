## Why

**One file was doing two jobs, and doing the second one silently.** `requirements.txt` held ten hand-pinned lines. Those lines were the *decisions* — SQLAlchemy must be 2 or later because `models.py` uses `DeclarativeBase`; python-telegram-bot is held at 21 — and they were also, by omission, the *resolution*: pip went off and installed twenty-odd further packages that nothing in the repository named. `greenlet`, `Mako`, `MarkupSafe`, `httpx`, `anyio` and the rest were running in production and written down nowhere.

That is the failure mode a pinned list is supposed to prevent. A rebuild months later resolves those transitive packages afresh, against whatever the index holds then, and the file that claims to say "what the application runs against" does not mention them.

**And a version bound had nowhere to explain itself.** `SQLAlchemy==2.0.52` states a resolution where the actual decision is `>=2`. A reader cannot tell which pins are load-bearing and which are just what pip happened to pick, so every one of them looks equally deliberate and equally frightening to change.

## What Changes

### Intent and resolution are separated

- `pyproject.toml` declares the direct dependencies, with only the bounds that have a reason: `SQLAlchemy>=2` because the models need the 2.0 declarative style, `python-telegram-bot~=21.0`, and the rest unbounded.
- `requirements.txt` becomes the compiled transitive closure — every package that will be installed, pinned exactly, each annotated with what pulled it in. It is generated, not written.

```
sqlalchemy==2.0.52
    # via
    #   french-tolls (pyproject.toml)
    #   alembic
```

- **The set of installed versions did not change.** Every direct dependency resolved to the version that was hand-pinned before. What changed is that the twenty-odd transitive packages are now written down.
- `pyproject.toml` declares no `[build-system]`. The application is put on `PYTHONPATH` and run from there, never installed, so declaring it a distribution would be a fiction.
- `pytest` is a plain dependency rather than a development extra, because one image serves five services and two of them are the test suites.

### The compiled file is reproducible

- `make requirements` regenerates `requirements.txt` from `pyproject.toml`, running `uv pip compile` in a container on the interpreter the application image uses.
- In a container because a resolution is specific to a Python version, and the host has neither that version nor `uv`. Compiling against whatever is installed on a developer's machine would pin a set the image cannot install.

### Nothing about how the image installs

- The image still copies `requirements.txt` and installs it with pip. `uv` is a tool for producing the file, not a runtime dependency, and is not in the image.
- `pyproject.toml` is not copied into the image and is not named in `.dockerignore`. The image installs the resolution; it has no use for the intent.

## Capabilities

### Modified Capabilities

- `runtime-store`: the pinned list gains a stated origin — it is compiled from a declaration rather than maintained by hand — and the transitive packages come under the same guarantee as the direct ones.

`route-service` is deliberately **not** modified. Its Compose requirement says the application image installs from a pinned list rather than from the distribution, and that is still exactly what happens.

## Impact

- New: `pyproject.toml`, and a `requirements` target in `Makefile`.
- Rewritten: `requirements.txt`, from ten hand-pinned lines to the full compiled closure.
- Unchanged: `Dockerfile`, `evaluation/Dockerfile`, `docker-compose.yml`, `.dockerignore`, and every installed version.
- **Adding a dependency is now two steps.** Name it in `pyproject.toml`, run `make requirements`, commit both. A `requirements.txt` edited by hand will be overwritten by the next compile, and hand-written comments in it are lost — which is why the rationale that used to live in its header now lives in `pyproject.toml`.
- Not addressed: `uv.lock` and `uv sync`. This uses `uv pip compile` only, so the output stays an ordinary pip-installable `requirements.txt` and no image needs `uv`.
