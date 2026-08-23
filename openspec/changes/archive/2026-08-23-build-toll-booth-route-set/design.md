## Context

See `proposal.md` — Why. This is the repository's first change; there is no existing code to integrate with, so the design is mostly about choosing an approach that stays tractable at national scale.

The constraints that actually shape it:

- `france-latest.osm.pbf` is roughly 4.7 GB and holds on the order of hundreds of millions of nodes. Anything that touches every node with a per-node callback in a scripting language is a multi-minute operation at best.
- OSRM preprocessing for a country-sized extract dominates the pipeline's wall-clock (tens of minutes) and its disk footprint (~25 GB). Everything else is minutes.
- Route queries, by contrast, are cheap — single-digit milliseconds. The budget is lopsided enough that the search can afford to be generous with candidates and stingy with preprocessing runs.
- The reference machine has 24 cores, 62 GB RAM, and ~122 GB free disk. Disk is the tightest of the three.
- `ghcr.io/project-osrm/osrm-backend:26.8-debian` is the pinned image; it was verified to exist and to ship `osrm-extract`, `osrm-partition`, `osrm-customize`, `osrm-contract`, and `osrm-routed`.

## Goals / Non-Goals

**Goals:**

- Determine booth coverage *exactly*, not by geometric proximity.
- Keep the expensive OSRM build strictly once-only and resumable.
- Keep large intermediates and OSM extracts out of version control, while committing the artifacts the pipeline is asked to produce.
- Make partial coverage loud rather than silent.

**Non-Goals:**

- Minimality of the route set. Greedy set cover is a `ln n`-approximation and that is accepted.
- Any handling of traffic or `--segment-speed-file`. A second, traffic-loaded instance is anticipated later but is out of scope here; `route_set.yaml` describes the untrafficked graph only.
- Routing profiles other than `car`.
- Toll *pricing*. This change produces trips that touch booths; what those trips cost is someone else's problem.

## Decisions

### Coverage is read from OSRM's node annotations

OSRM's route service accepts `annotations=nodes`, which returns the raw OSM node ids along the returned path:

```
GET /route/v1/driving/{lon},{lat};{lon},{lat}?annotations=nodes&overview=false&steps=false
   → {"routes":[{"legs":[{"annotation":{"nodes":[26744, 26745, 1284993, ...]}}]}]}
```

Intersecting that list with the booth inventory gives exact coverage — no polyline buffering, no snapping tolerance, no false positives. Both target tags survive OSRM's node handling: `toll_booth` is in the `car` profile's `barrier_whitelist`, and `highway=toll_gantry` carries no `barrier` tag at all, so it passes through as ordinary geometry.

`overview=false&steps=false` keeps the response small; the node annotation is the only part we read.

### MLD

`osrm-partition` + `osrm-customize`, served with `osrm-routed --algorithm mld`.

MLD wins on both axes that matter here — lighter preprocessing now, and minutes rather than an hour to re-apply a speed file when the traffic instance is eventually built. `--segment-speed-file` is not tied to either algorithm; the v26.8.0 sources show both `osrm-contract` and `osrm-customize` accepting it.

The choice is not free to reverse: the algorithm must match between preprocessing and `osrm-routed`, and any future instance meant to be comparable must use the same one. Because `osrm-extract` output is shared, switching later means re-running partition/customize (or contract), not re-extracting.

### Two-stage PBF parse

```
osmium tags-filter france-latest.osm.pbf \
    n/barrier=toll_booth n/highway=toll_gantry n/place=city,town,village
        │   C++, single streaming pass, ~2 min, output a few MB
        ▼
pyosmium reads the filtered file — effectively instant
```

Putting the C++ filter first keeps the Python callback layer off the full extract, where it would spend minutes to find a few thousand nodes. The `n/` prefixes restrict matching to nodes, which is exactly the spec's eligibility rule, so the filter does double duty as the eligibility test.

The filtered PBF is **kept**, not discarded: it already holds every booth and every endpoint candidate from a single parse, so it doubles as the hand-off from step 3 to step 4. Step 4 reads endpoint candidates out of it with pyosmium in negligible time. Because both steps consume the same parse, the booth inventory and the endpoint catalogue cannot drift apart if the source extract is refreshed between them, and the tag rules live in exactly one place.

### Two different place sets: catalogue vs. referenced

These are easy to conflate and are not the same thing:

```
  filtered.osm.pbf          route_set.yaml → places:
  ~35 000 candidates        a few hundred, only those used as from/to
  INPUT to step 4           OUTPUT of step 4, sorted by node_id
  internal, binary          part of the published contract
```

The `places` list exists to make the published artifact self-describing, so a consumer can resolve a `from: 123` to a name and a coordinate without holding the extract. It is scoped to referenced endpoints only; the full catalogue stays internal, as step 4's input.

`latlon` is recorded **latitude first**, deliberately matching the requested schema — which is the reverse of the `{lon},{lat}` order OSRM route URLs take. Since step 4 does that conversion internally and downstream consumers will do it again, the ordering is called out in the spec; getting it backwards yields routes in the wrong hemisphere rather than an error.

Sorting `places` by `node_id` keeps regeneration diff-stable.

### Plaza lanes are grouped by topology, not proximity

A plaza is routinely mapped one booth node per lane on parallel ways. Only one
lane can ever be on a route, so per-lane booths are not independent coverage
targets and treating them as such makes full coverage unsatisfiable.

Booths group when they share a common predecessor and a common successor with no
other booth on the path between:

```
                     ┌──[booth a]──┐
    ─────────── P ───┼──[booth b]──┼─── S ───────────
                     └──[booth c]──┘
```

A group is the transitive closure of that relation, because a wide plaza fans
out and merges in stages: its outer lanes share nothing directly, only through
the lanes between them.

Reach is bounded by **1 km along the road**, and the bound has to be tight.
Given enough reach any two booths eventually "reconverge" by looping around an
interchange, merging a mainline barrier with a slip-road barrier — booths one
route drives straight through, one after the other. A looser earlier rule merged
302 of 530 groups, some spanning 46 km, and five of its groups were traversed
twice by a single route.

Transitivity is safe precisely because the radius is tight: two distinct plazas
never form a link to chain through.

Nothing about the decision uses straight-line distance. Road distance bounds the
reach, and a grid of cells bounds how much network is loaded; neither is a
proximity test between booths. A proximity rule both splits long plazas whose
lanes exceed the threshold and merges unrelated booths that happen to sit close
together.

Three details carry the result:

- **Implicit one-way.** `motorway`, `motorway_link`, and `trunk_link` are one-way
  without an explicit `oneway` tag. Ignoring that makes every lane look
  bidirectional, and P and S stop distinguishing anything.
- **Contraction counts distinct neighbours, ignoring direction.** Testing
  `len(fwd) == 1` only contracts one-way chains: on a two-way road every interior
  node has both neighbours in `fwd` and in `rev`, so the road reads as solid
  junctions and the collapsed edges carry the wrong length.
- **Edges carry their real length.** Reachability is a distance-bounded search
  over segment lengths measured from node coordinates.
- **Candidates are deduplicated by witnessed booth set.** A component holds
  hundreds of thousands of predecessor nodes but only a handful of distinct
  booth sets. Pairing nodes directly is quadratic in node count and does not
  terminate; pairing distinct member sets is immediate.

The invariant that settles any future change to this rule: **no single route
may traverse two booths of one group.** Booths a route visits in succession are
not alternatives. It is checked against the generated route set, and it is what
proved the earlier rule wrong.

### Candidate generation in two waves, then greedy

The set-cover instance has no enumerable universe of sets: ~35 000 place nodes give more than a billion ordered pairs. Candidates are therefore generated, not enumerated.

```
  WAVE A — backbone                     WAVE B — residuals
  ~100 geographically dispersed         for each still-uncovered booth:
  places (network extremities:            take K≈20 nearest place nodes
  Lille, Strasbourg, Nice, Perpignan,     keep pairs whose bearings to the
  Bayonne, Brest, Bordeaux, Metz…)        booth differ by > 120° — i.e. the
        │                                 booth lies roughly between them
   ~10k ordered pairs                            │
        │                                        │
        └────────────┬───────────────────────────┘
                     ▼
        GREEDY: repeatedly take the candidate with the
        largest number of not-yet-covered booths; stop
        when Wave B stops yielding anything new
                     ▼
        VERIFY: union(covers) == inventory?
                     └── no ──▶ data/uncovered_booths.json + stdout summary
```

Pairs are **ordered**, not unordered: a toll plaza is usually two distinct nodes, one per carriageway, so A→B and B→A cover genuinely different sets.

Wave A is expected to sweep the motorway trunk, where most booths are. Wave B exists because branch autoroutes and isolated plazas will not be on any long-haul trunk route, and a targeted local pair is the cheapest way to reach them.

Since queries cost milliseconds, the candidate pool can be large without the search becoming the bottleneck; parallelising the client against a multi-threaded `osrm-routed` keeps even a six-figure query count inside a few minutes.

Every candidate is a plain `from`/`to` pair, which is what keeps `covers` reproducible: a consumer replaying the pair against the same instance gets the same path the search measured.

### Idempotency via a stamp file and order-only prerequisites

`osrm-extract`, `osrm-partition`, and `osrm-customize` produce a spread of `.osrm.*` files across three commands, any of which can exist while the sequence as a whole is incomplete. The step therefore writes `$(OSRM_OPTIMAL_PATH)/.setup.stamp` only after all three succeed, so the marker means "the whole sequence finished" rather than "some file appeared".

Make's ordinary prerequisites are timestamp-based, so touching the PBF would trigger a fresh half-hour of preprocessing. Order-only prerequisites give the existence-only semantics the spec asks for:

```make
$(OSRM_DIR)/.setup.stamp: | data/france-latest.osm.pbf
#                         ^ order-only: presence is checked, mtime is not
```

### The extract lives in `./data`; the OSRM copy is transient

`osrm-extract` has no output-directory flag — it writes `.osrm.*` next to its input. Keeping the ~25 GB graph out of the repository tree therefore requires the extract to sit under `$OSRM_OPTIMAL_PATH` while preprocessing runs.

So the master copy stays in `./data` (where the booth extraction step reads it anyway), a copy is placed in `$OSRM_OPTIMAL_PATH` for preprocessing, and that copy is unlinked once `osrm-customize` finishes — partition and customize only touch `.osrm.*` files, so the release can happen as soon as the last of the three completes.

```
 $OSRM_OPTIMAL_PATH over time
                                                    ┌── rm the copy
   4.7 GB ──┐                                       ▼
   copy in  │ extract ──▶ partition ──▶ customize ──▶ ~20–25 GB steady
            └─────────── peak ≈ 30 GB ──────────┘

 ./data keeps the master extract permanently (4.7 GB)
```

The step also removes any stale copy on entry, so a partial file left by a failed run cannot be mistaken for valid input.

*Optimisation, optional:* when `./data` and `$OSRM_OPTIMAL_PATH` share a filesystem, `cp -l` hardlinks instead — instant and free. `cp -l … || cp …` degrades safely.

### Compose topology

```yaml
services:
  osrm-optimal:                       # long-running query server
    container_name: osrm-optimal
    image: ghcr.io/project-osrm/osrm-backend:26.8-debian
    command: osrm-routed --algorithm mld /osrm/france-latest.osrm
    volumes: [ "${OSRM_OPTIMAL_PATH}:/osrm" ]

  osrm-tools:                         # one-shot extract / partition / customize
    image: ghcr.io/project-osrm/osrm-backend:26.8-debian
    volumes: [ "${OSRM_OPTIMAL_PATH}:/osrm" ]
    profiles: ["tools"]

  builder:                            # our own image: steps 3 and 4
    build: ./builder
    volumes: [ "./data:/data", "${OSRM_OPTIMAL_PATH}:/osrm" ]
    profiles: ["tools"]
```

Service name and `container_name` are both `osrm-optimal` so the Docker name and the URL the builder calls (`http://osrm-optimal:5000`) are the same string — no ambiguity about which network alias resolves.

`profiles: ["tools"]` is what stops a bare `docker compose up` from launching the one-shot containers; without it, `up` starts everything.

`osrm-tools` is deliberately generic rather than named after the optimal instance: when a traffic instance arrives it will be a second *server* service, not a second tools container.

`-t` is omitted from `osrm-routed`, which already defaults to hardware concurrency — no hardcoded core count to drift out of date.

### Readiness by client retry

`osrm-routed` must finish loading before the first request, which is a real race in step 4. `build_route_set.py` retries the connection for a bounded period, which assumes nothing about what tooling the OSRM image ships and fixes the same race for the future consuming scripts, which will not run under this Makefile at all.

### The Makefile reads `.env` itself

Compose substitutes `.env` into `docker-compose.yml` on its own, but Make also needs `OSRM_OPTIMAL_PATH` — the stamp path and the copy target are both under it. So the Makefile does `include .env` plus `export`, and guards on the variable being non-empty; otherwise `$(OSRM_DIR)/.setup.stamp` silently resolves to `/.setup.stamp`.

## Risks / Trade-offs

**Lane-level booth mapping makes full coverage unsatisfiable** → At a large *péage*, OSM sometimes maps `barrier=toll_booth` once per lane on parallel one-way stubs. OSRM picks one lane deterministically, so the sibling nodes are unreachable by *any* `from`/`to` pair.

```
                    ┌──[booth 1]──┐
   ───────────┬─────┼──[booth 2]──┼─────┬───────────
              └─────┼──[booth 3]──┼─────┘
                    └──[booth 4]──┘
                          ▲  OSRM always takes the fastest lane;
                             the other three are uncoverable.
```

*Mitigation:* proceed on the optimistic assumption, but make the failure legible — `data/uncovered_booths.json` plus a stdout summary, and a cluster-size histogram of booths within ~50 m emitted during extraction so the scale of the problem is a number rather than a surprise. If the histogram shows a long tail, the spec's coverage requirement needs revisiting (cluster-level coverage, or via-points, which would change the YAML schema).

**Booths mapped as standalone nodes, not attached to any way** → provably uncoverable; no route annotation can ever contain them. *Mitigation:* they surface through the same uncovered-booths report. Distinguishing them from lane siblings requires a ways pass over the extract; worth adding to the report only if the uncovered count turns out to be non-trivial.

**Disk exhaustion mid-preprocessing** → ~30 GB peak against ~122 GB free is comfortable, but a failure 40 minutes into `osrm-extract` is an expensive way to find out the margin was wrong. *Mitigation:* check free space at the top of `setup_osrm` and fail immediately with a clear message.

**Geofabrik's `france-latest` moves** → the file is regenerated daily, so a re-download months later yields a different graph and can invalidate a `route_set.yaml` built against the old one. *Mitigation:* existence-based skipping means the extract is never silently refreshed; a deliberate re-download is a deliberate rebuild of everything downstream.

**Greedy leaves an awkward tail** → the last few percent of booths tend to need one route each, inflating the set. Accepted; minimality is a non-goal, and the coverage requirement outranks size.

**`covers` is only valid against this exact configuration** → a consumer pointing at a differently-built OSRM instance, a different profile, or a traffic-loaded instance will get different routes and silently different coverage. *Mitigation:* stated as a requirement in the spec and recorded here; the named `osrm-optimal` service exists partly so consumers have an unambiguous target.

## Open Questions

- How many toll booth nodes does France actually contain, and what does the ~50 m cluster-size distribution look like? Answered for free by the first run of `build_osm_toll_booths`; it does not change the approach, only how much the lane-duplication risk matters.
- Wave A's dispersed-place count (~100) and Wave B's `K` (~20) and bearing threshold (~120°) are starting points. Tuning them is a matter of observing the coverage curve on the first full run; none of the specs depend on the values.
