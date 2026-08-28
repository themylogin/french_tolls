## Why

`french_tolls/` holds an aiohttp application and a Telegram bot that answer one question: what does the cheapest sensible drive across France cost, and which waypoints must a driver paste into Google Maps so that Maps drives it. Nothing in the repository describes how it works, none of it is tracked by git, and the algorithm is wrong in ways that are visible from the code and from the data it reads.

The application is also a generation behind its own pipeline. It prices journeys from `french_tolls/toll_booths.json` and `french_tolls/pairs.json`, two snapshots taken on 29 July, on a booth model that predates every spec in `openspec/specs/`. That model has no `gantry` type at all, so the 52 priced gantries the pipeline now carries charge nothing. Meanwhile `data/vinci_price.yaml`, `data/vinci_toll_booth.yaml`, `data/osm_toll_booths.yaml`, and `data/bidirectional_booth_sides.yaml` are committed deliverables that answer the same questions, currently, and are 190 MB smaller.

## What Changes

### The waypoint search is replaced

The present search walks a shrinking interval — `right = left + int((right - left) / 2)` — and never widens it, so it never tests how far a leg could reach and emits more waypoints than the route needs. It then proves the wrong thing: it verifies that the fastest route from `O[left]` to `O[right]` follows the optimal route, and emits `O[right]` as a waypoint, but the leg Google actually drives is `start` to `O[right]`, which nothing checks. Two fastest paths laid end to end are not a fastest path.

The replacement is a greedy furthest-reach search. From the current anchor it gallops forward — one node, two, four, eight — until a leg no longer reproduces the optimal route, then binary-searches the last bracket. Every emitted leg is the leg that was verified, so the waypoint list is correct by construction rather than by argument.

- **BREAKING** The search no longer restarts itself from the top with a doubled parameter after a failure, re-issuing every request it already made. That retry, against the 10 s budget in `service.py`, is what turns a hard route into "Error calculating this route".
- The number of waypoints is bounded. Google Maps URLs carry at most nine intermediate waypoints; the response now says when the optimal route needs more, instead of emitting a link Maps cannot honour.
- A stretch where no waypoint helps is reported as a divergence rather than raised or looped on.

### Route reconstruction is replaced

- `route()` zips `annotation.nodes` against `annotation.distance`. Measured on the live graph, a Lyon–Paris route returns 8 642 node ids and 8 641 distances, so `zip` silently discards the last node id of every route. A booth on the final node is never charged.
- Geometry is stitched from per-step polylines at precision 5, then matched against a 5 m snapping threshold whose own rounding error is about a metre. `geometries=geojson&overview=full` returns exactly one coordinate per annotated node — 669 and 669 on the probe — so the stitching, the `polyline` dependency, and the tolerance all go away.
- `Route.cut(n)` keeps `n - 1` nodes. `cut(1)` yields a route with no nodes, which `analyze_route` then indexes.
- `bind_location` snaps every origin and destination by routing it to a fixed point in central Paris. A location that cannot reach that point cannot be used.

### Toll accounting is replaced

- **BREAKING** Pricing moves to `data/vinci_price.yaml`, `data/vinci_toll_booth.yaml`, `data/osm_toll_booths.yaml`, and `data/bidirectional_booth_sides.yaml`. `french_tolls/toll_booths.json` and `french_tolls/pairs.json` are deleted.
- Gantries are charged. The old snapshot does not contain the type.
- A `bidirectional` barrier is resolved by the side the route arrives from, using the `inside_nodes` and `outside_nodes` that `bidirectional-booth-sides` establishes for all 47 of them. The present code books every bidirectional barrier as an entrance whenever no ticket is open, whatever direction the vehicle drives.
- Plaza lanes are resolved through the inventory's `aliases`, so a route pays whichever of a plaza's lanes the router chose.
- An unexpected barrier sequence marks one passage unpriced. It no longer raises and fails the whole request.
- A tariff is read from a named mapping rather than taken as element `[0]` of a list of differently-priced entries, and a missing tariff is reported rather than silently booked as 0 EUR.

### The service layer is replaced

- The cache key names the tariff date and the two graphs, so a rebuilt price file is not answered from a stale cache. The present key is the coordinate pair alone, cached forever.
- The timeout is a query budget rather than a wall clock on an unbounded recursion, and `os.rename`'s dead `except FileExistsError` goes.
- Module import no longer reads 182 MB of JSON.

### The application is packaged and tested

- `docker-compose.yml` gains three services: `web` for the aiohttp application, `bot` for the Telegram bot, and a profiled one-shot `tests` runner.
- Integration tests run against the real France graphs from inside the Compose network, comparing against committed golden values with a documented regeneration path. They must run inside the network: the published host ports refuse connections on this host, so a test suite on the host cannot reach either router.
- `french_tolls/bot.py`, `french_tolls/api.py`, and `french_tolls/autocomplete.py` keep their present behaviour. Only their packaging changes.

## Capabilities

### New Capabilities

- `waypoint-route-search`: how the optimal and fast routes are obtained, how a location is snapped, and how the optimal route is reduced to the shortest waypoint list whose legs a fastest-path router reproduces.
- `journey-toll-accounting`: how the booths a route traverses become an ordered list of named, priced passages and a total, including plaza aliases, bidirectional sides, gantries, and the passages that cannot be priced.
- `route-service`: the answer a route query returns, its cache key and invalidation, its query budget, and how the application and the bot are packaged and run.
- `route-algorithm-tests`: the golden fixture format, what each fixture asserts, how a fixture is regenerated after a pipeline rebuild, and how the suite is invoked.

### Modified Capabilities

- `build-pipeline`: the project layout requirement enumerates only `builder/` and `data/`; it must also place the application under `french_tolls/`. The named routing service requirement must account for the application services that share the Compose network, and for the fact that the published host ports are not a reachable path to the routers on every host.

## Impact

- Replaced: `french_tolls/route.py`, `french_tolls/service.py`.
- Deleted: `french_tolls/toll_booths.json` (9.3 MB), `french_tolls/pairs.json` (182 MB).
- Unchanged: `french_tolls/bot.py`, `french_tolls/api.py`, `french_tolls/autocomplete.py`, `french_tolls/__init__.py`.
- New: `french_tolls/Dockerfile`, `french_tolls/tests/`, the golden fixture file.
- Modified: `docker-compose.yml` (three services and a cache volume), `Makefile` (serve and test targets), `.env.example` (bot token, LocationIQ key, published port). The response cache moves to a named volume, so `.gitignore` needs no entry for it.
- Dependencies: `polyline` is dropped. The web and test images take `aiohttp`, `PyYAML`, and `pytest` from Debian packages; the bot image additionally installs `python-telegram-bot` from PyPI, which Debian bookworm does not package.
- Data: the four committed pipeline artifacts under `data/` become runtime inputs to the application, so `data/` is mounted into the application containers as it already is into `builder`.
