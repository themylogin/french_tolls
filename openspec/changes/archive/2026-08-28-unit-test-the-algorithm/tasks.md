## 1. The fixtures the tests are built from

- [x] 1.1 Write `french_tolls/tests/booths.py` building a `BoothData` from named booths — `entrance`, `exit_`, `passthrough`, `gantry`, `two_way`, `lane` — allocating node ids itself; verify a built table resolves a lane to its plaza and carries the tariffs, gares and sides it was given
- [x] 1.2 Write `french_tolls/tests/graph.py` with a graph builder taking an optimal node sequence, a mapping of legs that differ from it, and the positions that snap off-route; verify a built graph reports one coordinate per position and that a position and its coordinate are interchangeable
- [x] 1.3 Add `FakeRouters` to `graph.py` answering `snap` and `fast`, counting requests, and raising `BudgetExhausted` at the budget exactly as `osrm.Routers` does; verify a search against it issues requests, that the count matches, and that no HTTP call is made

## 2. The toll total

- [x] 2.1 Test entrance-to-exit pricing by the exit's gare code; verify one passage named `<entrance> → <exit>` carrying the mapped amount
- [x] 2.2 Test a `passthrough` and a `gantry` charging their own flat amount; verify neither opens nor closes a ticket, by pricing a ticketed section that spans one of them
- [x] 2.3 Test a `bidirectional` barrier reached from an outside node and, separately, from an inside node; verify the first opens a ticket, the second closes one, and the two passage lists differ
- [x] 2.4 Test a `bidirectional` barrier whose preceding node is neither side, resolved from the following node with the sense reversed; verify the sense matches the direction of travel through it
- [x] 2.5 Test lane resolution and consecutive-node collapsing; verify a lane is charged against its plaza, two consecutive nodes of one booth make one passage, and the same booth reached again later makes another
- [x] 2.6 Test that the total is the sum of the priced passages and excludes the unpriced ones; verify against a journey mixing both

## 3. Every state that cannot be priced

- [x] 3.1 Test an exit with no ticket open, and an entrance reached while one is already open; verify each carries its own reason and no cost
- [x] 3.2 Test an exit whose gare the entrance does not price, and an exit carrying no gare code; verify the two are told apart by their reasons
- [x] 3.3 Test a booth absent from the price file, and a `passthrough`/`gantry` carrying no amount; verify each is named and carries its own reason
- [x] 3.4 Test a two-way booth whose neighbours resolve to neither side, and a route ending with a ticket still open; verify both are recorded and neither raises
- [x] 3.5 Test that no unpriceable passage carries a cost of zero, that every one carries a reason, that the reasons of the eight states are all distinct, and that the unpriced count matches; verify across one journey holding several of them

## 4. The waypoint search

- [x] 4.1 Test a graph whose fast and optimal routes agree; verify no waypoint is emitted, the answer is complete, and the destination was reached in one leg
- [x] 4.2 Test a graph whose furthest reproducing position is at nine tenths of the route; verify the waypoint lands there rather than at a midpoint
- [x] 4.3 Test that each emitted waypoint's own leg from the preceding anchor was requested and reproduced the route; verify by inspecting the legs the stub was asked for
- [x] 4.4 Test a graph where the furthest reproducing position snaps off-route; verify an earlier position is emitted instead and that its own leg was verified
- [x] 4.5 Test a leg that leaves the optimal route and rejoins it before the far end; verify it does not count as reproducing the route
- [x] 4.6 Test the endpoint tolerance from both sides — a leg carrying the optimal route's neighbour of an endpoint, and a leg carrying any other extra node; verify the first reproduces and the second does not
- [x] 4.7 Test the waypoint cap on a graph needing four; verify two are returned with the cap at two, four is reported as needed, and the answer is marked incomplete by the cap
- [x] 4.8 Test the query budget set below what the search needs; verify the verified waypoints are returned, the answer is marked incomplete by the budget, and nothing is raised
- [x] 4.9 Test a stretch where no leg from the anchor reproduces the route; verify a divergence is recorded, the search reaches the destination, and no leg is requested twice

## 5. Removing what it replaces

- [x] 5.1 Copy the 11 files under `french_tolls/tests/` that this change removes to the backup directory outside the repository, since the repository takes no commits; verify the backup holds `golden.yaml`, `golden.py`, `journeys.py`, `find_journeys.py`, `regenerate.py`, `run.py`, `conftest.py`, `test_golden.py`, `test_legs.py`, `test_accounting.py`, and `test_bounds.py`
- [x] 5.2 Delete those 11 files; verify `french_tolls/tests/` holds only `__init__.py`, `booths.py`, `graph.py`, `test_cost.py`, and `test_waypoints.py`
- [x] 5.3 Strip the `tests` Compose service of its `./data` mount, the `OSRM_*` variables, `DATA_DIR`, and `CACHE_DIR`, keeping its profile and its image; verify `docker compose --profile test config` shows no volume and no router address for it
- [x] 5.4 Remove the `test-golden` Makefile target and its `.PHONY` entry, and drop `guard-osrm-paths-differ` and the router start-up from `test`; verify `make -n test` prints one compose invocation and nothing else

## 6. Verification

- [x] 6.1 Run the suite with both routers stopped; verify every test passes and the run takes under a second of test time
- [x] 6.2 Run the suite with `data/` moved aside; verify it passes, proving no artefact is read, then restore `data/`
- [x] 6.3 Confirm no test imports `french_tolls.service`, and that the suite issues no HTTP request; verify by import inspection and by running with the routers stopped
- [x] 6.4 Break one rule at a time in a scratch copy — the tariff lookup taking the wrong gare, the two-way sense ignoring the arrival node, the gallop stopping at the midpoint — and confirm each breaks a test whose name identifies it; verify all three, and restore the code
- [x] 6.5 Rewrite the `## Purpose` of `openspec/specs/route-algorithm-tests/spec.md`, which still describes an integration suite with recorded values and a regeneration command; verify it describes what the capability now requires
- [x] 6.6 Confirm `web` and `bot` are unchanged — both still mount `data/` read-only and still carry both router addresses; verify with `docker compose --profile app config`
