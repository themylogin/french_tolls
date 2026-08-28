## Context

See `proposal.md` — Why. The facts that shape the approach:

- `tolls.account(data, node_ids)` is already pure. It takes a `BoothData` and a sequence of node ids and returns a `Journey`. Nothing in it touches the network or the filesystem.
- `BoothData`, `Booth`, `Route` and `Snap` are frozen dataclasses that can be constructed directly. `BoothData(booths=..., booth_of_node=..., fingerprint=...)` needs no file.
- `data.py` reads `DATA_DIR` at import, but only to compute a path string. It opens nothing until `load()` or `fingerprint()` is called. Importing it is safe.
- `service.py` calls `load_or_exit()` at module level. Importing it requires the artefacts, so no unit test may import it.
- `search.plan_waypoints(routers, optimal, origin, destination, *, max_waypoints)` takes the routing client as its first argument. It calls exactly two methods on it: `routers.fast(start, end)` and `routers.snap(location, reach_m=...)`. It also reads `routers.exhausted` indirectly, through `BudgetExhausted` being raised from inside those two.
- `osrm.Routers` raises `BudgetExhausted` from `_get` when the count reaches the budget. A stub has to reproduce that, because the budget path is one of the behaviours under test.

## Goals / Non-Goals

**Goals:**

- Two test modules that between them cover the waypoint search and the toll total, and run in under a second with no service and no artefact.
- Cases the real extract cannot supply on demand: a waypoint beside a parallel carriageway, a stretch that lies on no fastest path, an exit whose gare its entrance does not price.
- A failure that names the behaviour that broke.

**Non-Goals:**

- Any change to the code under test. This change adds and removes tests.
- Testing `osrm.py`'s HTTP handling, `data.py`'s YAML parsing, or `service.py`'s cache. They are not what the user asked to protect, and each would need either a fake HTTP server or a temporary directory, which is the dependency this change exists to remove.
- Keeping any part of the integration suite behind a second target. It goes.

## Decisions

### The stub router

One class, `FakeRouters`, in a shared `graph.py` beside the tests. It answers the two methods the search calls and counts requests so the budget can be reached.

It is built from a declarative description of a graph:

- `node_ids` — the optimal route as a sequence of node ids, with a coordinate per node derived from the index, so a coordinate and a position are interchangeable and a test can say "the waypoint should be position 7".
- `fast_legs` — a mapping from `(from position, to position)` to the node sequence the fast graph returns for that leg. A leg not named in it defaults to the optimal slice, so a test writes down only the legs that are supposed to differ.
- `off_route` — the set of positions whose bare coordinate snaps onto a segment the optimal route does not drive, which is how the parallel-carriageway case is expressed.

That last one is the reason for a stub rather than a recorded transcript. Making a real French coordinate snap to the wrong carriageway is a hunt; making position 7 do it is one line.

*Alternative rejected:* recording real OSRM responses and replaying them. It fixes the flakiness but not the expressiveness — the recorded transcript contains whatever France happened to contain, and the interesting cases still have to be found in it rather than written.

*Alternative rejected:* `unittest.mock`. The search calls two methods in a loop whose call sequence is the thing under test; asserting on a mock's call list would encode the search's internal order, and every legitimate change to the gallop would break every test.

### What a leg default of "the optimal slice" means

`fast_legs` defaulting to the optimal slice makes the common case — the fast graph agrees with the optimal one here — free to write. A test that wants a route needing no waypoint writes no legs at all.

The stub SHALL apply the same endpoint bookkeeping the real router does when a test asks for it: a leg may be declared as carrying the neighbour node of an endpoint. That is how the tolerance in `_reproduces` gets tested from both sides — one node that must be forgiven, and one that must not.

### Two modules, one subject each

| File | Subject |
| --- | --- |
| `tests/graph.py` | the stub router and the graph builder |
| `tests/booths.py` | a builder for `BoothData` from a short description |
| `tests/test_waypoints.py` | `search.plan_waypoints` |
| `tests/test_cost.py` | `tolls.account` |

No `conftest.py` beyond what pytest needs, and no session fixtures: every test builds the small thing it needs. A session fixture was what made the old suite's failures unreadable — one broken run took a dozen tests with it.

### The booth builder

`booths.py` turns a short description into a `BoothData`:

```
build_booths(
    entrance("A", gare="00001", prices={"00002": 13.70}),
    exit_("B", gare="00002"),
    gantry("G", price=2.20),
    two_way("C", gare="00003", inside=[10], outside=[20], prices={...}),
    lane("B2", of="B"),
)
```

Names rather than numbers, with node ids allocated by the builder, so a test reads as the journey it describes. The real artefacts key everything by OSM node id, which is right for the pipeline and unreadable in a test.

### Running it

The `tests` Compose service keeps its profile and its image and loses everything else — no `./data` mount, no `OSRM_*`, no `DATA_DIR`, no `CACHE_DIR`. `make test` loses `guard-osrm-paths-differ` and the `up -d osrm-toll osrm-optimal` line.

The suite can then also be run outside Compose by anyone with pytest and the two Debian packages, which is a side effect rather than a goal — the contract is that it runs in the image.

### The capability's Purpose

`openspec/specs/route-algorithm-tests/spec.md` opens with a Purpose describing an integration suite, recorded values, and regeneration. A delta cannot change a Purpose, so it is edited directly as an explicit task rather than left to say the opposite of what the spec now requires.

## Risks / Trade-offs

- **A stub can drift from the real router.** If OSRM changes how it annotates a snapped endpoint, the stub keeps agreeing with the tests while the application breaks. → The endpoint tolerance is derived from a measurement recorded in `waypoint-route-search`, and the stub reproduces that measurement rather than inventing a convention. Nothing in this suite claims to verify the application against a live OSRM; that verification is gone with the integration suite, which is the cost the user accepted.
- **Nothing now tests against real French tariffs.** A wrong gare code in `data/vinci_price.yaml` would not be caught here. → It never was: the old suite compared against values recorded from the same pipeline, so it would have recorded the wrong tariff as expected. The pipeline's own steps are where that is checked.
- **Nothing now tests that the two graphs are wired up.** A misconfigured `OSRM_OPTIMAL_URL` would pass. → It fails immediately on the first real request, and `make web` brings both routers up.
- **Deleting 1 400 lines of tests.** → They are in the archived change and in git history; nothing here is unrecoverable. The two behaviours they covered that survive — leg reproduction and waypoint snapping — are carried into the new suite as direct assertions.

## Migration Plan

1. Write `tests/graph.py` and `tests/booths.py`, and confirm each can build what the tests need before any test is written against it.
2. Write `test_cost.py` first. It depends on nothing but `tolls` and the booth builder, so it either passes at once or has found something.
3. Write `test_waypoints.py`.
4. Delete the 11 old files once the new suite covers what replaces them, so the two never both exist in a state where `make test` runs some of each.
5. Strip the `tests` service and the Makefile targets.
6. Edit the `route-algorithm-tests` Purpose in the main spec.
7. Verify: `make test` passes with `docker compose down` having stopped both routers, and with `data/` renamed aside.

Rollback is restoring `french_tolls/tests/` from the archived change at `openspec/changes/archive/2026-08-28-reimplement-route-algorithm/` — which holds the planning artifacts but not the test code. The test code exists only in the working tree, and this repository takes no commits, so step 4 SHALL copy the deleted files to the same backup directory the previous change used rather than removing them outright.

## Open Questions

None. The two subjects, the isolation level, and the fate of the old suite were all settled before the artifacts were written.
