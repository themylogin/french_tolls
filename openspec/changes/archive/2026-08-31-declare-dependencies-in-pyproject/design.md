## Context

See `proposal.md` — Why. The constraints that shape the approach:

- The application image is `debian:bookworm-slim` with a plain venv, and its interpreter is Python 3.11.2. A resolution compiled anywhere else can pin a set that interpreter cannot install.
- The host running the Makefile has neither Python 3.11 nor `uv`. Every other pipeline step already runs in a container for the same reason, and the Makefile says so: "All work runs in containers. The host needs only Docker, Compose, and coreutils."
- One image serves five services. Two of them, `tests` and `integration`, run pytest, so pytest is in the image whether or not it is called a development dependency.
- `evaluation/Dockerfile` installs the same `requirements.txt`. Whatever the format becomes, both images consume it.
- The Makefile makes the docker binary overridable — `make DOCKER="sudo -n docker"` — for hosts where the socket is not group-accessible.

## Goals / Non-Goals

**Goals:**

- Every installed package named and pinned in the repository.
- Version decisions written where their reasons can be read.
- A compiled file that anyone can reproduce, on any host, byte for byte.

**Non-Goals:**

- Making the project installable. No `[build-system]`; it runs from `PYTHONPATH`.
- Putting `uv` in any image. It produces the file; it is not needed to consume it.
- `uv.lock` / `uv sync`. Named as not addressed in the proposal.
- Changing any installed version. This change is about what is *written down*.

## Decisions

### `uv pip compile`, not `uv lock`

`uv lock` produces `uv.lock`, a format only `uv` reads, which would put `uv` in both images to install from it. `uv pip compile` produces an ordinary pip-installable `requirements.txt`, so both Dockerfiles are untouched and the tool stays on the authoring side.

*Alternative considered:* `pip-tools` (`pip-compile`), which produces the same shape of file. `uv` was chosen for speed and because it needs no Python environment of its own to run — the official image is self-contained.

### The compile runs in a container, pinned to the image's Python

```make
requirements:
	$(DOCKER) run --rm -v "$$(pwd)/pyproject.toml:/in/pyproject.toml:ro" \
	    ghcr.io/astral-sh/uv:python3.11-bookworm-slim \
	    sh -c '... uv pip compile pyproject.toml -o requirements.txt ... && cat requirements.txt' > requirements.txt
```

Three details, each with a reason:

- **`python3.11-bookworm-slim`**, matching the application image. A marker like `python_version < "3.11"` resolves differently elsewhere, and the pinned set would not be the one the image installs.
- **The compile happens inside the container's own filesystem and the result is `cat`-ed to stdout.** Writing directly into a bind-mounted repository was tried and does not work here: this host's Docker daemon has a private `/tmp`, and — more to the point — the file uv writes lands owned by root. Capturing stdout sidesteps both, and `-o requirements.txt` is still passed so the header uv writes records the command a reader would run.
- **`$(DOCKER)`**, not `docker`, so the target honours the override the rest of the Makefile offers.

### `pyproject.toml` states bounds, and only real ones

`SQLAlchemy>=2` is the one that carries weight: `models.py` is written against `DeclarativeBase` and `Mapped[...]`, and Debian's 1.4 has neither — which is the whole reason this project stopped taking Python packages from the distribution. `python-telegram-bot~=21.0` preserves the `21.*` the image was built with.

Everything else is unbounded. A bound that exists only because a resolver once picked a version is noise, and it is indistinguishable from one that matters.

### No comments in either file

`pyproject.toml` carries the declaration and nothing else. `requirements.txt` carries uv's generated header and nothing else — a hand-written comment there is deleted by the next `make requirements`, so the rationale that used to live in its header could not stay.

### `pytest` is a plain dependency

It could be `[project.optional-dependencies]` with the compile taking `--extra dev`. That would state the intent more precisely and change nothing about what is installed, because the image needs pytest regardless: `tests` and `integration` are two of the five services it serves.

Rejected for now as ceremony — an extra that is always compiled in is an extra in name only. Worth revisiting if the image is ever split.

## Risks / Trade-offs

**A hand-edited `requirements.txt` is silently discarded.** The next `make requirements` overwrites it. Mitigated by the generated header, which says what produced the file, and by the spec requiring that regeneration reproduce the committed file — so a drifted list is detectable by running the target.

**Adding a dependency is two steps, and forgetting the second one is easy.** The image would then install a list that does not include the new package, and the failure is an ImportError at start-up rather than at build. Nothing enforces this automatically; the check is `make requirements` followed by an empty `git diff`.

**The resolution is pinned to one Python version.** If the image's base moves off Python 3.11, the Makefile target has to move with it or it will keep compiling for the wrong interpreter — quietly, since the file will still look correct.

**Twenty-two more lines to review on a dependency bump.** That is the cost of writing down what was already being installed, and it is the point rather than a side effect.
