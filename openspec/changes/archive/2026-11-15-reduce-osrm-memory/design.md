# Design

## Context

See proposal.md for the motivation.

Both routers run `osrm-routed --algorithm mld` from the image `ghcr.io/project-osrm/osrm-backend:26.8-debian`. Without `--mmap`, each router copies its graph files into memory at start. `osrm-routed --list-inputs` names the files it loads. Sizes from the France graph of 9 November 2026:

| File | MB | Content | Read by this project | Loaded with `ROUTE_STEPS` disabled |
|---|---|---|---|---|
| `geometry` | 1,973 | segment nodes, weights, durations, data sources | yes | yes |
| `cell_metrics` | 1,828 | 4 metric sets of 457 MB: no exclusion, `toll`, `motorway`, `ferry` | only set 0 | yes |
| `mldgr` | 1,020 | multi-level graph | yes | yes |
| `nbg_nodes` | 710 | coordinates and OSM node ids | yes | yes |
| `edges` | 278 | turn instructions, lanes, entry classes, bearings | no | yes |
| `ebg_nodes` | 276 | edge-based nodes | yes | yes |
| `icd` | 219 | intersection bearings | no | no |
| `partition` | 179 | cell of each node | yes | yes |
| `turn_*_penalties` | 159 | turn weights and durations | yes | yes |
| `names` | 24 | names, refs, destinations | waypoint `name` only | yes |
| others | 23 | `cells`, `ramIndex`, small files | yes | yes |

The sum is 6,689 MB. A router on this graph holds 6.69 GB of anonymous memory after it loads, so the files are its resident memory. The `fileIndex` (1,132 MB) is mapped from disk and is not in this sum.

The consumers send these requests:

- The application: `/nearest` (reads `hint`, `nodes`, `distance`, `location`), `/route` with `annotations=nodes,distance,duration`, `geometries=geojson`, `overview=full`, `steps=false`, and `/match` with `annotations=nodes`, `steps=false`.
- The build steps: `/route` with `steps=false` or no `steps`, `/nearest`, `/table`. `build_segment_weights.py` adds the `weight` annotation.
- The evaluation: `/table` with `exclude=ferry`. This is the only exclusion in the repository.

No consumer asks for steps.

`builder/patch_car_profile.py` already edits a copy of the stock profile at fixed anchors. It stops when an anchor is missing or appears twice. The setup stamp depends on the patch script, so an edit to it rebuilds both graphs.

## Goals / Non-Goals

**Goals:**

- Remove from memory the data that no consumer reads.
- Keep every route, snap, match and table answer as it is now.

**Non-Goals:**

- `--mmap`. The user decided against it.
- A lower peak for `osrm-extract`. No change in this design lowers it. Decision 4 records the one candidate that was measured.
- Fewer road classes in the graph. That changes routes.

## Decisions

### 1. The patch removes the `excludable` declaration

The patch script deletes the `excludable = Sequence { ... }` block from the profile copy. It does this on every run, also when no node is blacklisted and no gate is found. The block must appear exactly once. Otherwise the script stops, as it does for its other anchors.

OSRM reads `excludable` only when the profile declares it. The stock `foot.lua` declares none. Without it, `osrm-customize` writes one metric set.

The extract stores the classes either way, so the edge-based graph and the partition stay the same. The one remaining metric set is the set 0 of today, 457 MB.

`classes` stays. A change of class at a node stops OSRM from merging the two segments, so removing the classes could change the graph.

Alternatives:

- An empty `excludable = Sequence {}`. The result is the same, but deleting the block leaves less to check.
- Keep `ferry` only. That saves 914 MB per graph instead of 1,371 MB. The user chose to drop all three and to replace the ferry question in the evaluation.

### 2. Both routers start with `--disable-feature-dataset ROUTE_STEPS`

The flag goes into the `command` of `osrm-toll` and `osrm-optimal` in `docker-compose.yml`. The pipeline steps use the same services, so they get the flag too. No rebuild is needed.

The flag takes more than one value. Placed before the graph path, it reads the path as a dataset name, and the router stops with `Unknown feature dataset`. So the graph path comes first in the command.

Measured on the current graph, with the router started twice:

| | Without the flag | With the flag |
|---|---|---|
| anonymous memory after load | 6,690 MB | 6,471 MB |
| `/nearest`, `/route`, `/route` through a via, `/route` with `weight`, `/match`, `/table` | `Ok` | `Ok`, byte-identical bodies |
| `/route` with `steps=true` | `Ok` | 400 `DisabledDataset` (`IntersectionBearings`) |

In OSRM 26.8 the flag skips `icd` only. The turn data and the names still load, and waypoint names stay in the answers.

OSRM offers a second dataset, `ROUTE_GEOMETRY`. This project cannot disable it, because the application reads the route geometry and the `nodes` annotation.

### 3. The evaluation uses a meridian

`build_test_cities.py` drops `exclude=ferry` from its `/table` request. Before that request, it removes each candidate with a longitude above 8.4 and reports the count. The router check stays, without the exclusion, and still removes unreachable candidates.

Of the 1,155 city and town candidates in `data/filtered.osm.pbf`, the easternmost mainland one is Wissembourg (7.945°E). The westernmost Corsican one is Ajaccio (8.738°E). No candidate is on an island that only a ferry reaches.

### 4. Street names stay in the profile

Without names, OSRM can merge more segments, so the graph could get smaller. The measurement used the full France extract of 9 November 2026 and the live profile. The two runs differed only in the `WayHandlers.names` and `WayHandlers.destinations` handlers. Memory is the maximum of anonymous memory plus swap of the container, sampled every 2 seconds.

| | With names | Without names |
|---|---|---|
| `osrm-extract` peak, RAM and swap | 27.89 GB | 27.74 GB |
| `osrm-extract` peak, as OSRM reports it | 15.37 GB | 15.29 GB |
| `osrm-extract` time | 1,550 s | 1,464 s |
| edge-based nodes | 22,312,793 | 21,802,903 |
| edge-based edges | 39,780,795 | 39,270,905 |
| one metric set | 457 MB | 485 MB |
| router memory, one metric set, `icd` skipped | 5,099 MB | 5,062 MB |

The extract peak falls by 0.5%. The graph loses 2.3% of its nodes, but the partition then gets more boundary nodes, and each metric set grows by 28 MB. The net gain is 37 MB per router. That does not pay for a profile change that alters the graph.

## Risks / Trade-offs

- [A borrower that uses the relay sends `exclude=` or `steps=true`] → It gets an error from the router. No consumer in this repository sends either. The relay is shared only with deployments of this project.
- [The rebuild changes routes] → The no-exclusion metric does not depend on the other metric sets. The segment weight step runs again after the rebuild, and `data/segment_weights.csv` must come out byte-identical. Its `--verify` check also runs.
- [The rebuild runs out of memory on the 15 GB host] → Stop the local routers and add temporary swap first. On 14 November 2026, the full extract needed 27.9 GB of RAM and swap and ran with 16 GB of added swap.
- [`memory.peak` of a router includes the page cache it reads at start] → The memory checks use `anon` in `memory.stat`, not `memory.peak`.

## Migration Plan

1. Deploy the router flag. Restart both routers. No rebuild.
2. Deploy the patch script. Run `make apply_segment_weights`. The setup stamp is out of date, so the step rebuilds the untouched graph, the segment weights and the toll-weighted graph, and restarts both routers.
3. Rollback: revert the compose change and restart the routers. Revert the patch script and run `make apply_segment_weights` again.
