## 1. Rollback point and packaging

- [x] 1.1 ~~Commit `french_tolls/` exactly as it stands~~ — **dropped by user decision: do not touch `.git` at all.** No git command is run anywhere in this change. The rollback point is instead a copy of the replaced files outside the repository, made in 6.6
- [x] 1.2 Write `french_tolls/Dockerfile` on `debian:bookworm-slim` with `python3-aiohttp`, `python3-yaml`, `python3-pytest` from Debian packages and `python-telegram-bot` from PyPI into a venv; verify `docker compose build web` succeeds and `python3 -c "import aiohttp, yaml, telegram"` runs in the image
- [x] 1.3 Add `web`, `bot`, and `tests` to `docker-compose.yml` — one build context, `./data` read-only, a `cache` named volume at `/cache`, `web` and `bot` under profile `app`, `tests` under profile `test`; verify `docker compose config` parses and `docker compose up -d` still starts only `osrm-toll` and `osrm-optimal`
- [x] 1.4 Add `TELEGRAM_BOT_TOKEN`, `LOCATIONIQ_API_KEY`, and the web port to `.env.example` with the same commented style the file already uses; verify every variable the three services reference appears there
- [x] 1.5 Add `web`, `bot`, `test`, `test-golden`, and `clean-cache` targets to the Makefile; verify `make -n web` and `make -n test` print the expected compose invocations

## 2. Data loading and fingerprint

- [x] 2.1 Write `french_tolls/data.py` loading the four artefacts into booth, alias, gare, tariff, and side lookups; verify a load reports 1 295 booths, 262 aliases, 1 283 gares, 1 275 priced booths, and 47 booths with sides
- [x] 2.2 Compute the data fingerprint as a truncated SHA-256 over the four artefacts and `data/segment_weights.csv`; verify two loads of unchanged files agree and touching one byte of any of the five changes it
- [x] 2.3 Fail at start-up naming the file when an artefact is missing or unparseable; verify the container exits with that message when `data/vinci_price.yaml` is not mounted

## 3. Router client and route reading

- [x] 3.1 Write `french_tolls/osrm.py` with a client per graph addressing `osrm-toll` and `osrm-optimal` by service name, a shared request counter, and a budget that stops the search rather than raising; verify a Lyon–Paris route is answered from inside the Compose network
- [x] 3.2 Read a route as `n` node ids, `n` coordinates from the full GeoJSON overview, and `n − 1` segment measures; verify a Lyon–Paris route reads 8 642 nodes and 8 641 segments and its last node id is present
- [x] 3.3 Implement snapping on `osrm-toll` returning location and URL-encoded hint, with the reach check and its error; verify the hint is accepted by `osrm-optimal` and a coordinate 4 km from the network is rejected naming the distance
- [x] 3.4 Retry a request without its hint when a router rejects it, and mark the answer; verify by submitting a corrupted hint
- [x] 3.5 Keep `distance_to_road_network` in `french_tolls/route.py` with its present name and signature; verify `french_tolls/bot.py` imports unchanged

## 4. Waypoint search

- [x] 4.1 Implement leg reproduction — request the fast route between two positions with both hints and compare the whole node id sequence; verify a leg that leaves and rejoins the optimal route is reported as not reproducing it
- [x] 4.2 Implement the gallop-then-bisect step that finds the furthest reproducing position from an anchor; verify on a journey whose furthest reach is past the midpoint that the search reaches it rather than stopping at the midpoint
- [x] 4.3 Validate each candidate waypoint by a hint-free snap that must land on a segment of the optimal route, falling back to an earlier candidate; verify a candidate beside an opposite carriageway is rejected
- [x] 4.4 Assemble the greedy search over anchors, emitting only waypoints whose leg from their own anchor was verified; verify a journey whose two routes are identical emits no waypoint
- [x] 4.5 Apply the waypoint cap, reporting `waypoints_needed` and `complete`; verify a journey needing four waypoints run with the cap at two returns two, reports 4, and is marked incomplete
- [x] 4.6 Record a divergence and advance one position where no leg reproduces the route, and never restart a search from the origin; verify the search terminates and issues no repeated leg request
- [x] 4.7 Return the verified waypoints and mark the answer incomplete when the query budget is reached; verify a long journey under a lowered budget returns waypoints and raises nothing

## 5. Toll accounting

- [x] 5.1 Write `french_tolls/tolls.py` resolving each route node through the aliases to its booth and collapsing consecutive duplicates; verify a route crossing an alias lane is accounted against the plaza
- [x] 5.2 Implement the ticket state machine for `enter`, `exit`, `passthrough`, and `gantry`, reading a tariff by the exit's gare code; verify a ticketed section is named `<entrance> → <exit>` and carries the mapped amount
- [x] 5.3 Resolve a `bidirectional` barrier from the node the route arrived from, falling back to the following node with the sense reversed; verify one journey through such a barrier opens a ticket and the reverse journey closes one
- [x] 5.4 Record every unresolvable state as a passage with a reason and no cost, and count them; verify a journey beginning inside the toll network records an unpriced exit and is still answered
- [x] 5.5 Name a passage from the gare mapping and an unmapped booth by its OSM node id; verify against one of the 12 booths carrying no gare code
- [x] 5.6 Sum the priced passages into the route total for both routes; verify the total equals the sum of the passage costs shown

## 6. Service layer

- [x] 6.1 Rewrite `french_tolls/service.py` to keep `get_route(from_, to)` and its `{"fast": ..., "optimal": ...}` shape with every existing per-route key unchanged; verify `french_tolls/bot.py` and `french_tolls/api.py` run unmodified against it
- [x] 6.2 Add `waypoints`, `waypoints_needed`, `complete`, `divergences`, and `unpriced`, and a `reason` on each unpriced passage; verify the fast route carries an empty `waypoints` and `complete` true
- [x] 6.3 Build the three Google Maps links from the origin, the waypoints, and the destination; verify a link with four waypoints carries them in driven order and a link with none carries no `waypoints` parameter
- [x] 6.4 Cache answers under `/cache/<fingerprint>/`, written to a temporary name and moved with `os.replace`; verify a second identical query is served from the cache and a changed fingerprint recomputes it
- [x] 6.5 Implement the error taxonomy — location out of reach, no route, router unavailable — recording each failure with its cause and not an exception repr; verify each of the three produces its own message
- [x] 6.6 Move `french_tolls/toll_booths.json`, `french_tolls/pairs.json`, and the replaced `route.py`/`service.py` to a backup directory outside the repository, rather than deleting them, since 1.1 was dropped and no git rollback point exists; verify no file under `french_tolls/` holds a booth inventory or a tariff table and the backup holds all four

## 7. Tests

- [x] 7.1 Write the suite skeleton under `french_tolls/tests/` that reaches both routers by service name and stops with one message when a router or an artefact is absent; verify `docker compose --profile test run --rm tests` collects and runs
- [x] 7.2 Implement the fixture format, the fingerprint stamp, and the guard that stops the run with the regeneration command when the fingerprints differ; verify a deliberately altered stamp produces that one message and no journey failures
- [x] 7.3 Implement `make test-golden` regeneration printing a per-journey diff of what moved; verify it rewrites the fixture and that an ordinary run leaves the fixture unchanged
- [x] 7.4 Choose and record the concrete journeys for the `passthrough`, `gantry`, `bidirectional` both ways, plaza-alias, begins-inside, and ends-inside cases by scanning the artefacts; verify each chosen journey actually crosses the booth kind it is meant to
- [x] 7.5 Add the no-toll journey and the Lyon–Paris journey, asserting distance, duration, node digest, passages by name and cost, waypoints, and totals; verify both pass against the current artefacts
- [x] 7.6 Add the journeys from 7.4 with the same assertions; verify the two `bidirectional` directions produce different passage lists and the gantry journey charges its gantry
- [x] 7.7 Implement the invariant checks — waypoints lie on the optimal route, each leg re-verifies, each waypoint snaps back unaided, optimal duration is not less than fast duration, passages follow node order; verify they run on every fixture journey
- [x] 7.8 Add the bound tests that lower the cap, the budget, and the reach on real journeys; verify each produces the documented answer without raising
- [x] 7.9 Make a failure name the journey, the field, the expected and actual value, and show only the differing passages; verify by perturbing one passage cost in the fixture

## 8. Verification

- [x] 8.1 Run the full suite against the live graphs and record the result; verify every journey and every invariant passes
- [x] 8.2 Bring up the application and answer a query end to end through `/api/calculate`; verify the response carries both routes, the new keys, and links that open in Google Maps
- [x] 8.3 Run the bot against the same build; verify the reach rejection, the location parser, and the formatted reply are as before. **`bot.py` needed one added line — `import os`.** It used `os.environ` at line 132 without importing the module, so `python3 -m french_tolls.bot` died with `NameError` before this change; the bot could not start at all. No behaviour was altered. The live two-message Telegram exchange was not exercised: no bot token is available in this environment, and the run reaches Telegram's token rejection, which is as far as it goes without one
- [x] 8.4 Confirm a plain `docker compose up` still starts only the two routers, and that `data/` is mounted read-only in `web`, `bot`, and `tests`; verify with `docker compose ps` and `docker compose config`
