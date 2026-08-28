## Why

The suite built by `reimplement-route-algorithm` is 24 test functions over 10 fixed journeys, 96 parameterised cases, a 386-line file of recorded values, and 20 seconds of querying the France graphs. It is the wrong shape for what it is meant to protect.

What it mostly does is notice that a number moved. A journey's distance, duration, node digest, passages and waypoints are recorded and compared; when the pipeline is rebuilt they all move at once, the fingerprint guard fires, and the answer is to regenerate them. Regenerating re-records whatever the code now does, correct or not. A recorded value cannot tell a fixed bug from a new one.

It also cannot be run. It needs Docker, both routers, and 30 GB of graph before it will say anything at all. That puts the two pieces of logic actually worth protecting — the waypoint search and the toll accounting — behind the heaviest possible dependency, when neither of them needs a real graph to be exercised.

Both are pure enough to test directly. `account()` already takes a booth table and a list of node ids and returns passages; nothing about it needs France. `plan_waypoints()` needs something that answers routing questions, which a small hand-built graph does exactly as well as a continent — and better, because a hand-built graph can contain the cases that matter, such as a waypoint beside an opposite carriageway, which no one can conjure on demand out of the real extract.

## What Changes

### The existing suite is removed

- **BREAKING** `french_tolls/tests/` is deleted in full: `golden.yaml`, `golden.py`, `journeys.py`, `find_journeys.py`, `regenerate.py`, `run.py`, `conftest.py`, `test_golden.py`, `test_legs.py`, `test_accounting.py`, `test_bounds.py`.
- The golden fixture, its data fingerprint stamp, and the regeneration command go with it.
- The `test-golden` Makefile target is removed.

### Two unit-test modules replace it

- **Waypoints.** The search is driven against a stub router over a small hand-built graph. What is asserted is behaviour, not recorded numbers: that a route needing no waypoint gets none, that the search reaches the furthest reproducing position rather than a midpoint, that every emitted waypoint's own leg was verified, that a position which does not snap back onto the route is rejected in favour of an earlier one, that the cap and the budget truncate and say so, and that a stretch admitting no waypoint is recorded as a divergence rather than raised on or looped on.
- **Cost.** The ticket state machine is driven against hand-built booths. Entrance-to-exit pricing by gare code, flat-charge passthroughs and gantries, a two-way barrier resolved from the side the route arrived from in both directions, plaza lanes resolved through aliases, and every state that cannot be priced — each recorded with its own reason and no cost, never as 0 EUR, and never by raising.

### The test runner stops depending on the graphs and the data

- **BREAKING** The `tests` Compose service no longer mounts `./data` and no longer receives the router URLs. It runs `pytest` in the application image and nothing else.
- `make test` no longer starts `osrm-toll` and `osrm-optimal`, and no longer guards on the graph paths. A checkout with no `.env`, no graphs, and no pipeline output can run it.
- The tests still run in a container, from the same image the application is built from, so what is tested is the code as it ships.

## Capabilities

### Modified Capabilities

- `route-algorithm-tests`: every requirement changes. The suite no longer runs against the real graphs, no longer holds recorded expected values, no longer carries a data fingerprint, and no longer has a regeneration command. In their place: what a unit test may depend on, the stub router, the two subjects, and what each must demonstrate.
- `route-service`: the requirement listing the three Compose services states that all three address the routers by service name. The test runner no longer addresses them at all, and no longer needs the pipeline artefacts mounted.
- `build-pipeline`: the named routing service requirement names the test runner among the consumers that address the routers by service name. It is no longer one.

## Impact

- Deleted: `french_tolls/tests/` in full — 11 files, about 1 400 lines including the fixture.
- New: two test modules and their fixtures, under `french_tolls/tests/`.
- Modified: `docker-compose.yml` (the `tests` service loses its `./data` mount and its router environment), `Makefile` (`test` loses its prerequisites, `test-golden` is removed).
- Unchanged: every module under test. This change adds and removes tests; it does not alter `search.py`, `tolls.py`, `osrm.py`, `data.py`, `service.py`, `route.py`, `bot.py`, `api.py`, or `autocomplete.py`.
- Unchanged: `web` and `bot` keep their `./data` mount and their router environment. Only the test runner drops them.
- Runtime: the suite stops needing Docker Compose, the two routers, and the graphs, and drops from about 20 seconds to well under one.
