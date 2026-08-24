## Context

See proposal.md — Why.

Three facts from the codebase shape the approach.

`build_osm_toll_booths.py` runs before the OSRM graph is guaranteed to exist. The Makefile starts `osrm-optimal` in the step 4 recipe only, and step 3's prerequisites are the source extract and the builder image. Step 4 is the first step that holds both the candidate catalogue and a routing graph.

`/nearest` reports the snapped position, the snap distance, and the two OSM node ids of the snapped segment. It reports the segment's `name` but not its `highway` value. Measured on the 16 endpoints in the report, 6 snapped onto unnamed ways, so the name cannot stand in for the class.

The candidate catalogue holds 1 024 663 place nodes. Measured distribution of the snap distance over a 60 000-node sample:

```
  within   10 m   10.4 %      within  100 m   62.2 %
  within   20 m   24.6 %      within  200 m   77.4 %
  within   50 m   47.7 %      within  500 m   93.5 %
```

and of the snapped segment class:

```
  unclassified 27.9 %   service 20.1 %   tertiary 18.6 %   residential 12.1 %
  secondary 7.7 %   track 7.4 %   primary 2.9 %   ...
  motorway 0.38 %   motorway_link 0.05 %   trunk_link 0.02 %
```

## Goals / Non-Goals

**Goals:**

- Every emitted route begins and ends where a car can begin and end a trip.
- The eligibility sweep costs its full price once, not on every run.
- Moving the distance threshold does not require repeating the sweep.
- The defect class cannot return without failing the build.

**Non-Goals:**

- Repairing an ineligible endpoint by moving it to a nearby road. A candidate is kept or dropped; nothing is relocated.
- Any judgement about which booths a route ought to cross. The search waves are unchanged; only the pool they draw from narrows.
- Guaranteeing that every currently covered target is still coverable. See Risks.

## Decisions

### The test uses OSRM's own snap, not an independent geometry index

The failure is that OSRM snaps a place onto a road it cannot reach. The authority on where OSRM snaps is OSRM. An independently computed nearest-way distance can disagree with it, and a disagreement admits exactly the endpoints this change exists to remove.

*Alternative considered:* build a spatial index over the highway ways in the extract and measure distance directly. This removes the OSRM dependency and would let the test live in step 3. Rejected because it reimplements snapping and can differ from it, and because the `car` profile's routability rules (access tags, barriers) are not reproduced by a plain geometric index.

### The snap must come from a route, not from `/nearest`

`/nearest` was tried first and is not the same question. It reports the geometrically closest segment whether or not a car can drive out of it. `5907006903` (Le Mazet) sits 26.6 m from a `highway=service, service=driveway` stub in its own disconnected component; the router, asked for a real trip, starts 323 m away on the A89 mainline.

```
                   /nearest              route to a real destination
  Le Mazet       26.6 m  driveway    ->  323.0 m  'La Transeuropéenne'
  Les Girasols   37.1 m              ->   37.1 m   same segment
  Gros Bois       8.3 m              ->    8.3 m   same segment
```

That is the defect this change exists to remove, hiding behind a passing measurement. It survived the 50 m rebuild and produced one of the two remaining duplicate-gare failures.

So the distance comes from `waypoints[0].distance` of a route to a destination the graph certainly connects to, and the class from a `/nearest` at the position that route starts from. The destination is the candidate's nearest `place=city` — data-driven rather than a hardcoded list, and short enough to stay cheap. Three anchors are tried before a candidate is recorded as unmeasured; 36 of 1 024 663 reached none.

*Alternative considered:* a self-route (`A;A`). Rejected because both endpoints then land in the same fragment, so an isolated driveway answers 26.6 m exactly as `/nearest` does.

### The sweep runs across processes

Two queries per candidate over a million candidates is two million JSON responses, and a threaded client is bound by the interpreter lock long before OSRM is bound by anything — measured at ~610/s with 64 threads while OSRM sat at 29 % CPU.

Twenty processes of sixteen threads reach 6168/s, so the full sweep takes under three minutes rather than half an hour. Workers are forked, so the place catalogue and the 675 793-node no-access set are inherited read-only and never cross a pipe.

### The sweep runs in step 4 and caches to `data/endpoint_snap.json`

Step 4 is the earliest step holding both inputs. Putting the test in step 3 would make step 3 depend on the OSRM graph, which reorders the Makefile and forces a 40-minute preprocessing run before a one-minute extraction step.

The sweep is 1 024 663 `/nearest` calls. It is written once to `data/endpoint_snap.json` and reused on later runs by the existence check the Makefile already uses for `filtered.osm.pbf` and `plazas.osm.pbf`. The cached record depends on the source extract and the OSRM graph, both of which are themselves governed by existence checks, so it cannot go stale while they are unchanged.

*Alternative considered:* test lazily, only for places the search actually reaches. Rejected because `dispersed_places` and `PlaceIndex.within_band` iterate the whole pool. Filtering after selection returns fewer endpoints per bearing sector than the strategy intends, which silently weakens wave B.

### The cache stores the measurement, not the verdict

Each entry records the snap distance and whether the snapped segment is of a no-access class. The threshold is applied when the cache is read.

This is what makes the fallback ladder in Risks affordable. Raising the threshold from 50 m to 100 m is then a constant change and a re-read, not a repeat of the sweep.

### The class comes from a nationwide extract of the no-access classes only

Step 3 gains a second `osmium tags-filter` pass producing `data/no_access_ways.osm.pbf`, holding ways tagged `highway=motorway`, `motorway_link`, or `trunk_link`. Step 4 loads the node ids of those ways into a set and tests the two node ids `/nearest` returns against it.

Filtering to the three classes keeps the set to the motorway network rather than every highway node in France. The distance test is applied first, so the membership test runs on the surviving candidates only.

*Alternative considered:* a full node-to-class map for every highway way in France. Rejected on size — over 100 million nodes — for a test that only ever asks one yes/no question.

### `trunk` is not a no-access class

`trunk` in France covers ordinary two-way roads with property access as well as motorway-grade routes. Excluding it would drop 0.19 % of candidates for no established defect: no endpoint among the sixteen in the report snapped onto `trunk`. `trunk_link` is included because a link road is a ramp in every case.

### Resume drops a route whose endpoints are no longer eligible

`load_existing` keeps a pair when both endpoints are still present in the catalogue. It gains the eligibility test. Without this the nine reported routes survive regeneration untouched, because each still covers something and the greedy pass never revisits an already-selected route.

### The duplicate-gare check lives in step 5

Step 4 does not know about gares. Step 5 already resolves every covered booth to a gare and already fails on an unmapped booth, so the assertion sits beside an existing failure of the same shape and reuses its reporting style.

The check runs on every invocation, including one with no outstanding routes, matching the existing "Every covered booth must have a gare" requirement.

## Risks / Trade-offs

**The 50 m threshold leaves previously covered targets uncoverable.** → This happened, and the ladder resolved it. `MAX_SNAP_M` is **100 m**. See "Threshold outcome" below.

**The first run costs an extra sweep.** → About 1 million `/nearest` calls. Mitigation: the result is cached like every other expensive intermediate in this pipeline, and `make clean` is the only thing that discards it.

**A legitimate route pays one gare twice and the build fails.** → This turned out to be real, not hypothetical. `Vilallobent → Les Girasols` pays gare `04210 ORANGE` twice because the road that would let a driver carry on is not built yet (way 294125300 is under construction), so the detour back through the same gare genuinely is the fastest route and genuinely is charged twice. The override file gained a `duplicate_gares` list for this. It is keyed by gare rather than by route: a route is identified by its endpoints, which are re-derived on every rebuild, so a route-keyed exemption would go stale almost immediately. An exemption no route exercises is reported and does not fail the run.

**A place that is a valid trip origin snaps onto a motorway.** → A motorway service area mapped as `place=isolated_dwelling` would be dropped. This is correct for this pipeline: a trip starting inside a service area is already past the barrier that a real trip pays.

## Threshold outcome

50 m was built and run first. It removed all nine reported routes and cost two coverage targets: booths 4200516989 and 4200516990, both gare 42004 MENPENTI-PRADO 2, the Prado tunnel tolls in Marseille. Seven further targets that the old route set covered turned out to be stale — booths that are no longer targets under the current inventory, not regressions.

The cause was not the booths. Marseille's own `place=city` node snaps 71.8 m from the nearest routable way, so at 50 m France's second city was not an endpoint. Ten more of the 66 cities were excluded with it, and `dispersed_places` seeds wave A from `place=city` alone, so the threshold was narrowing the backbone sweep as well as the local search.

Eligibility by place value, measured over the whole catalogue:

```
  place                total     <= 50 m      <= 100 m     <= 200 m
  city                    66    55 ( 83%)     66 (100%)    66 (100%)
  town                 1 089  1048 ( 96%)   1081 ( 99%)  1086 (100%)
  village             37 368 34416 ( 92%)  37105 ( 99%) 37335 (100%)
  hamlet             232 086   81%            95%          98%
  isolated_dwelling  256 741   73%            86%          93%
  locality           497 313   15%            32%          57%
```

100 m admits every city and 99 % of towns and villages while still dropping two thirds of localities. It is also the ceiling: at 200 m the Gros Speck → Le Mazet pair becomes eligible again, and that is one of the nine routes this change exists to remove. So the ladder is 50 → 100 and stops.

## Migration Plan

1. Run step 3 to produce `data/no_access_ways.osm.pbf`. The existing `filtered.osm.pbf` and `plazas.osm.pbf` are reused.
2. Delete `data/route_set.yaml`. Resuming is not useful at 30 % survival, and a full run is clearer than a partial one.
3. Run step 4. It builds `data/endpoint_snap.json`, then searches from an empty route set.
4. Compare the new `data/uncovered_booths.json` against the coverage the old route set achieved. If targets regressed, apply the threshold ladder from Risks.
5. Delete `data/vinci_toll_booth.yaml` and run step 5. It re-queries every route and asserts no route pays one gare twice.

Rollback is `git checkout` of the three data files and the builder sources. Nothing in the pipeline is stateful beyond `data/`.
