## Context

See `proposal.md` — Why. The state that shapes the approach:

- `french_tolls/` is entirely untracked. There is no committed version of the application to roll back to.
- `french_tolls/bot.py` imports `distance_to_road_network` from `.route`, and `french_tolls/api.py` imports `get_route` from `.service`. Both files are out of scope, so those two names and signatures are fixed.
- The front end at `french-tolls.undiscoveredlatitudes.com` reads the `/api/calculate` response and is not in this repository. Its keys are therefore fixed too.
- Both routers are running and answer in 2–11 ms per route on the France extract. The published host ports refuse connections on this host; the Compose network works.
- The toll-weighted graph is `cp -a` of the untouched graph followed by `osrm-customize`, so the two share node ids, geometry, and the hint checksum. Verified: a hint issued by `osrm-toll` is accepted by `osrm-optimal`.
- `data/segment_weights.csv` preserves each segment's speed and moves only its weight, so durations are directly comparable between the two graphs.

## Goals / Non-Goals

**Goals:**

- One code path whose every emitted waypoint was verified on the leg the driver drives.
- Toll accounting on the pipeline's current artefacts, including gantries and the two sides of a two-way barrier.
- A test suite that runs against the real graphs and survives a pipeline rebuild without becoming a wall of noise.

**Non-Goals:**

- Modelling Google Maps exactly. The untouched graph is the model; the contract is reproduction on that graph, and the specs say so.
- Changing the HTTP surface, the front end, or the bot's conversation.
- Any change to the eleven pipeline steps or to the artefacts they write.
- Serving from a persistent process pool, a queue, or a rate limiter. The service stays what it is.

## Decisions

### Module layout under `french_tolls/`

| File | Holds |
| --- | --- |
| `data.py` | loads the four artefacts, builds the booth lookups, computes the fingerprint |
| `osrm.py` | the two router clients, the `Route` value type, the request budget |
| `search.py` | the waypoint search |
| `tolls.py` | the accounting state machine |
| `route.py` | the public names the rest of the package and the bot import |
| `service.py` | orchestration, cache, error taxonomy, response assembly, Maps links |
| `tests/` | the suite and the golden fixture |

`route.py` and `service.py` keep their names because `bot.py` and `api.py` import from them. Everything behind them is new.

### One request per route, geometry as GeoJSON

Each route is one request with `annotations=nodes,distance,duration,weight`, `geometries=geojson`, `overview=full`. The full overview carries exactly one coordinate per annotated node — measured 669 and 669 — so nodes and coordinates pair directly and nothing has to be stitched.

*Alternative rejected:* keep the present per-step polyline concatenation. It decodes at precision 5, which rounds every coordinate by about a metre, and the snapping tolerance it then has to meet is 5 m. It also drops the last point of each step to splice them, which is where the last node of the route goes missing. Dropping it removes the `polyline` dependency outright.

The `Route` type holds `n` node ids, `n` coordinates, and `n − 1` triples of distance, duration, and weight. Nothing zips the two lengths together.

### One snap serves both graphs

A location is snapped once with `nearest` on `osrm-toll`. The returned location and hint are then passed to both routers. Verified above; the hint is URL-encoded, which the present code does not do — it works today only because the alphabet happens to survive.

*Alternative rejected:* snapping on each graph. The two would be free to pick different lanes, and the two routes would then not be comparable at their endpoints.

*Fallback:* if a router rejects a hint, the request is retried without it and the answer is marked. A rejected hint means the two graphs were built from different extracts, which the fingerprint will also show.

### Gallop, then bisect

From an anchor at index `a`, test `a+1`, `a+2`, `a+4`, `a+8`, … until a leg fails or the destination is reached, then bisect between the last success and the first failure. Emit the furthest success as a waypoint and make it the next anchor.

Cost is `O(log d)` requests per waypoint, where `d` is the step actually taken — not `O(log n)` in the route's length. A route needing four waypoints over 7 000 nodes costs roughly 4 × 2 × 11 ≈ 90 requests, under a second at the measured latency.

*Alternative rejected:* the present shrinking search, `right = left + (right - left) // 2`. It never widens, so it cannot find a step longer than half the remainder, and it emits a waypoint whose leg from the actual anchor it never tested.

*Correctness note:* the search relies on a prefix of a fastest path being a fastest path, which makes the predicate monotone in the step length. Where the router breaks a tie in favour of an equally fast alternative, the gallop stops early and one extra waypoint is emitted. That never produces a wrong waypoint, because the waypoint that is emitted is always one whose own leg came back equal.

### A waypoint is validated hint-free before it is emitted

The chosen node's coordinate is snapped with `nearest` and no hint, and the result must lie on a segment of the optimal route. Google is handed a coordinate and nothing else, so this is the question that matters; a hinted leg answers a different one.

Cost: one extra request per waypoint. On failure the search falls back to the previous bisection candidate rather than starting over.

### Nine waypoints, and say so when more were needed

Google Maps directions URLs carry at most nine intermediate waypoints. The cap is a setting defaulting to 9. Above it the first nine are kept, `waypoints_needed` reports the true count, and `complete` is false.

*Alternative rejected:* choosing which nine to keep by cost. A driver follows the link from the start, so a waypoint they reach after the link has already sent them elsewhere is worth nothing.

### Divergence rather than retry

Where not even `a+1` reproduces the route — possible because the optimal route is optimal in the weighted graph, not the fast one — the anchor advances one node, a divergence is recorded, and the search continues. The present code instead restarts from the origin with a doubled parameter, re-issuing every request it has already made; against the 10 s budget that is what produces "Error calculating this route".

### Accounting as a state machine over resolved booths

Walk the node ids. Resolve each through `aliases` to its parent. Collapse consecutive duplicates. For each booth, take its type from `data/vinci_price.yaml`, its gare and name from `data/vinci_toll_booth.yaml`, and — when `bidirectional` — its sides from `data/bidirectional_booth_sides.yaml`. Keep at most one open ticket.

The sense of a two-way barrier comes from the node the route arrived from: an inside neighbour means the vehicle held a ticket, so the crossing is an exit. The preceding node is available because the walk is over the route's own ordered node ids.

Every state the machine cannot resolve produces a passage with a reason and no cost. Nothing raises. Of 1 295 booths, 12 have no gare code and 20 are absent from the price file, so a real route reaches these states.

### Fingerprint and cache

The fingerprint is a SHA-256 over the bytes of `data/osm_toll_booths.yaml`, `data/vinci_price.yaml`, `data/vinci_toll_booth.yaml`, `data/bidirectional_booth_sides.yaml`, and `data/segment_weights.csv`, truncated to 16 hex characters. About 12 MB read once at start-up, tens of milliseconds.

`segment_weights.csv` is in it because it is what the toll-weighted graph is built from: a repriced graph with an unchanged price file would otherwise be answered from the cache.

Cached answers go to `/cache/<fingerprint>/<origin>;<destination>.json`, written to a temporary name and moved into place with `os.replace`. The present `os.rename` with a dead `except FileExistsError` goes: on POSIX it never raises that, so the branch has never run.

`/cache` is a named volume. `./data` is mounted read-only into the application, so the pipeline's artefacts cannot be written by a service that only reads them.

Superseded fingerprint directories are left in place and removed by a documented command. Deleting them automatically would discard the answers of a graph an operator is still comparing against.

### One image, three services

`french_tolls/Dockerfile` on `debian:bookworm-slim`, taking `python3-aiohttp`, `python3-yaml`, and `python3-pytest` from Debian packages, as `builder/Dockerfile` does. `python-telegram-bot` is not packaged by Debian, so it is installed from PyPI into a virtual environment in the image. That is the one place this project's image builds need a package index; it is confined to one layer and only the bot imports it.

Compose gains `web` and `bot` under the `app` profile, and `tests` under the `test` profile. A plain `docker compose up` therefore still starts the two routers and nothing else — which matters because `bot` cannot run without a Telegram token that a pipeline-only checkout has no reason to hold.

Makefile targets: `web`, `bot`, `test`, `test-golden`, and `clean-cache`.

### Golden fixture with a fingerprint stamp

`french_tolls/tests/golden.yaml` holds the expected values and the fingerprint they were produced under. Node id sequences are stored as a SHA-256 digest plus a count: exact, and one line instead of 6 945.

When the live fingerprint differs the suite stops with one message. This is the whole reason exact expected values are usable here: without it, the first pipeline rebuild turns every journey into a failure and the reflex becomes to regenerate unread.

Regeneration is `make test-golden`, which prints a per-journey diff of what moved before writing.

Alongside the recorded values, each journey is checked against the invariants in `route-algorithm-tests`. Those hold across a rebuild and are what still exercises the algorithm on the day the numbers have to be regenerated.

## Risks / Trade-offs

- **The untouched graph is not Google Maps.** A leg verified here can still differ from what Maps drives. → The specs state the contract as reproduction on our own graph, the answer carries `complete` and `divergences`, and the hint-free waypoint validation removes the largest class of practical failure — a waypoint snapping to the wrong carriageway.
- **Ties cost extra waypoints.** An equally fast alternative ends a gallop early. → Correctness is unaffected; the cost is at worst one more waypoint against a cap of nine.
- **Exact golden values churn.** Any pipeline rebuild moves them. → The fingerprint stamp turns the churn into one message and one command, and the invariants keep testing the algorithm meanwhile.
- **The image build needs PyPI.** For `python-telegram-bot` only. → One layer, and the pipeline's own image is untouched. A build without a package index still produces a usable `web` and `tests` if the layer is made conditional; that is not planned unless it is needed.
- **Deleting 191 MB of untracked data.** `toll_booths.json` and `pairs.json` are not in git, so deleting them is irreversible. → The migration commits the application as it stands before anything is replaced, which puts both files under version control first.
- **The response grows new keys.** The front end is not in this repository. → Only additive keys; every existing key keeps its name and meaning, and `route-service` makes that a requirement.
- **The bidirectional fixtures depend on a barrier still being two-way.** A retagging in OSM changes what those journeys test. → The fingerprint catches it, and the failure message names the barrier.

## Migration Plan

No git command is run by this change. The user's decision is that `.git` is not touched, so the rollback point is a copy outside the working tree rather than a commit.

1. Copy the files the rewrite replaces — `route.py`, `service.py`, `toll_booths.json`, `pairs.json` — to a backup directory outside the repository, before anything is overwritten. `pairs.json` alone is 182 MB and nothing regenerates it, so this copy is the only way back.
2. Land the rewrite, the Dockerfile, the Compose services, and the tests.
3. Generate the golden fixture against the current artefacts.
4. Move `french_tolls/toll_booths.json` and `french_tolls/pairs.json` into the backup, so the working tree never holds both data models.
5. Deploy: `docker compose --profile app up -d --build`. The old on-disk cache under `data/cache` and `data/errors` is no longer read; remove it by hand.
6. Rollback is restoring the four files from the backup directory.

## Open Questions

- Which concrete journeys serve as the `bidirectional`, `gantry`, `passthrough`, and plaza-alias fixtures. They are chosen during implementation by scanning the artefacts for a barrier of each kind with routable places on both sides. The specs fix what each fixture must demonstrate; only the coordinates are open, and they change nothing about the approach or the task breakdown.
