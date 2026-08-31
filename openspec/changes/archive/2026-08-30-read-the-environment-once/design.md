## Context

See `proposal.md` — Why.

What constrains the shape:

- **Settings are read at import today**, in nine modules. `service.BOOTHS` loads 12 MB of YAML at import and `service` raises `SystemExit` at import when `URL` is empty. The integration suite already sets its environment in Compose because of this. Nothing here should change that timing; it is depended on.
- **The unit suite imports with no environment at all.** `route-algorithm-tests` requires it to run on a checkout with no `.env`, no graphs and no `data/`. It imports `osrm`, `data`, `search`, `tolls`, `refine`, `drive`, `equivalence`. So importing must never require a value.
- **`.env.example` is not in any image.** The `french_tolls` build context is `./french_tolls`, and the file is at the repository root. The `tests` service mounts nothing and `integration` mounts only `./data`. A test that checks the documentation has to be given the file.
- Three of the settings are already imported across modules: `bot` reads `FIT_THRESHOLD` and `MONTHLY_CEILING` from `refine`.

## Goals / Non-Goals

**Goals:**

- One declaration per setting, carrying name, type, default and purpose.
- No `os.environ` outside it, in `french_tolls/`.
- The seven undocumented settings dealt with: six deleted, one documented.

**Non-Goals:**

- Changing when anything fails. Every start-up failure keeps its moment.
- Changing any default.
- `evaluation/` and `builder/`. Separate images; `builder` cannot import the package.
- A configuration file, a schema library, or environment layering. Nine settings do not need any of it.

## Decisions

### What counts as a setting

A value is a setting when two environments legitimately disagree about it. Twelve did not, and they leave:

```
  DATA_DIR   /data       every Compose service mounts ./data there
  CACHE_DIR  /cache      four of them mount a cache there
  PORT       8080        nginx proxies to it; a variable that moves it
                         takes the site down rather than moving the site
  OSRM_TOLL_URL          http://osrm-toll:5000     one network, service names,
  OSRM_OPTIMAL_URL       http://osrm-optimal:5000  published ports refuse
  OSRM_TIMEOUT_S    30.0
  GOOGLE_TIMEOUT_S  30.0
  GOOGLE_FIT_THRESHOLD  0.98   measured, not chosen
  MAX_WAYPOINTS         9      what a Google Maps URL carries
  QUERY_BUDGET      1000   raised from 500; a guard, not a dial
  SNAP_REACH_M      1000.0  and bot.py reads it instead of its own literal
  REFINE_CORRIDOR_M  ->  deleted; refine uses geometry.DEFAULT_CORRIDOR_M
```

`QUERY_BUDGET` stays in `osrm.py` rather than moving anywhere. It bounds how many local routing requests one journey's search may issue, at 2–11 ms each, and the measurement that justifies it — the dearest journey across France costs 325 — belongs beside the code it bounds. Raising it to 1000 doubles the headroom for a graph that will grow; the search still stops rather than looping.

`SNAP_REACH_M` is the clearest case in the list for a different reason: it was a setting in one place and a literal in two others. `bot.py` compared against its own `1000` and told the driver "not within a kilometer" in prose, so setting the variable moved the router's reach and left the bot rejecting at the old one. Frozen in `osrm.py` and imported by `bot.py`, the three finally say the same thing.

Two of them were actively misleading rather than merely unused. `MAX_WAYPOINTS` overrides only the search's nine, while `refine` keeps its own and a Maps URL keeps its nine, so raising it makes the search place points the link drops in silence. `GOOGLE_FIT_THRESHOLD` looks like the knob that keeps the evaluation and the drive flow agreeing, and it is not: `evaluation/report.py` imports `FIT_THRESHOLD` from `refine`, so they agree through the constant and the variable moved only one of them.

Each becomes a constant beside the code that uses it, with a note saying who fixes the value. `CACHE_DIR` lives in `db.py`, which owns the store, and `service.py` imports it rather than declaring a second one.

`REFINE_CORRIDOR_M` goes furthest: it is deleted rather than frozen. Its default was `geometry.DEFAULT_CORRIDOR_M`, so the corridor already had a home, and the evaluation reads that constant directly. Keeping the variable meant the corridor had two answers and one of them was never given.

`MAX_WAYPOINTS` becomes `search.MAX_WAYPOINTS`, read directly, as `REFINE_CORRIDOR_M` becomes `geometry.DEFAULT_CORRIDOR_M`. Both had another module's constant as their default, which is the shape of a value that already had a home.

*The exception, and it is a real one:* `GOOGLE_ROUTES_ENDPOINT` is hardcoded in Compose too, and it stays a setting. It is what `drive-flow-integration-tests` points at the replay server, and that capability requires it — with the endpoint at localhost, a real key left in the environment buys nothing. Hardcoding it would delete the property that makes the suite unable to spend money.

### A frozen dataclass, built once at import

```python
from .config import config
config.query_budget        # int
config.public_site_url     # str
config.debug               # bool
```

Frozen, so a value cannot be changed under a module that read it at import — which would give two modules two answers and no way to tell.

Built at import from `os.environ`, because that is when everything reads it today. A lazily-evaluated object would let a test set a variable after import and half the application would see it, which is a worse trap than the one being removed.

*Alternative rejected:* a settings library. It would add a dependency to an image built from Debian packages plus one pip install, to replace about eighty lines.

### Requiring is separate from reading, and stays where it is now

Every field has a value after construction — a default, or the empty string for a required one. Nothing raises during construction.

A service then declares what it cannot run without:

```python
config.require("public_site_url")     # SystemExit naming the variable
```

`service.py` calls it at import, exactly where the `SystemExit` lives today, so the failure keeps its moment and its message.

`autocomplete.py` does the same for the LocationIQ key, and here the improvement is larger than it first looked. `os.environ["LOCATIONIQ_API_KEY"]` reads like it fails fast on a missing key, but Compose passes `"${LOCATIONIQ_API_KEY:-}"`, so the variable always exists and holds the empty string. It never raises. The service starts with no key and fails at the first autocomplete request instead — which is how it is running now.

*Why not raise on access?* Because a field would then have two behaviours depending on who touched it, and the unit suite — which imports `refine` with no environment — would depend on never reading the wrong attribute. A `require` call at the entry point says what the service needs, in the service.

### One reader per kind, and a switch that reads what an operator writes

```python
_int("GOOGLE_DIRECTIONS_MAX_REQUEST_PER_MONTH", 0)
_str("LOG_LEVEL", "INFO")      _bool("DEBUG", False)
```

Each raises `SystemExit` naming the variable and the value it could not read. Today `MONTHLY_CEILING` guards an empty string with `or 0` and `TIME_MULTIPLIER` does not, so an empty value crashes the import with a `ValueError` naming neither the variable nor the service.

`_bool` accepts `off`, `no`, `0`, `false`, `n` and empty as off, case-insensitively, and `on`, `yes`, `1`, `true`, `y` as on. Anything else is an error rather than a guess. Today `DEBUG` is `not in ("", "0", "false", "False")`, so `FALSE` means on and so does `no`.

### The module constants go, and their comments become the declaration

The aliases are deleted and call sites read `config.x`. The long comments attached to them move with the value — to the config declaration for a real setting, and to the constant for a frozen one. That is what makes the result "documented" rather than merely typed: the reasoning stays attached to the number, wherever the number ends up.

Two names for one value is the state this change exists to end, so keeping the aliases would be keeping it.

*Consequence:* `bot.py` stops importing `MONTHLY_CEILING` from `refine` and reads it from `config`. It keeps importing `FIT_THRESHOLD`, which is now a constant rather than a setting.

### The documentation is not checked by a test

It was, briefly. `.env.example` was mounted into the `integration` service and a suite asserted both directions — every setting documented, every documented variable read by someone.

It worked, and it was not worth its price. The set of variable names is not derivable from the declaration: two fields are named differently from their variables, so the test needed either a second hand-written list, which goes stale and defeats the purpose, or a mutable global in `config.py` filled as a side effect of reading each field and exported from production code for one test to import. Both are worse than the drift they guard against.

`.env.example` is still required to document every setting. Keeping it honest is a job for whoever adds one.

## Risks / Trade-offs

- **Nine modules change at once, and the unit suite cannot see most of it.** → The integration suite drives the bot end to end over real routes, so a setting wired to the wrong field shows up as a failed journey rather than a passing test.
- **The query budget doubles**, 500 to 1000. → It is a ceiling, so nothing changes for a journey that never approached it — the dearest measured costs 325. What changes is the worst case a pathological journey can cost the router, from about two seconds to about four.
- **`DEBUG=FALSE` changes meaning**, from on to off. → It was a defect; anyone who wrote `FALSE` meant off. Worth stating because a deployment relying on the old reading would quietly stop drawing the overlay.
- **A frozen object read at import means a test cannot vary a setting.** → It already cannot, and the integration suite already sets its environment in Compose. This makes the constraint explicit rather than introducing it.
- **`GOOGLE_ROUTES_ENDPOINT` becomes documented**, and it points the application at whatever host it names. → Discoverable is right, and the line for it says plainly that it decides where route requests go. It is the only one of the six undocumented reads that survives as a setting; the rest are gone.
- **Deleting a variable is not reversible for someone who set it.** Anyone with `REFINE_CORRIDOR_M` or `OSRM_TIMEOUT_S` in an environment would silently get the default instead. → Neither appears in `.env`, `.env.example` or any Compose file, so there is nobody to surprise. Verified by search, not assumed.

## Migration Plan

1. Freeze the eleven non-settings as constants where they are used, and delete `REFINE_CORRIDOR_M`.
2. Write `config.py` with the nine settings, their defaults and their documentation.
2. Replace the reads module by module, deleting the aliases; unit suite green after each.
3. Add `require` at the two entry points that need it, keeping the messages.
4. Document `GOOGLE_ROUTES_ENDPOINT` in `.env.example`; the other six undocumented reads are gone rather than documented.
5. Mount `.env.example` into `integration` and add the two-way documentation test.
6. Run both suites and start the services.

Rollback is reverting the module; nothing persists a setting anywhere.

## Open Questions

None. `QUERY_BUDGET` and `SNAP_REACH_M` were the last two, and both are frozen: the budget at 1000 in `osrm.py`, the reach at 1000 metres and read by `bot.py` instead of its own literal.
