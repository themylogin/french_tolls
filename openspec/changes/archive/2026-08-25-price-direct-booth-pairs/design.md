## Context

See proposal.md — Why.

The numbers below come from measurements against the committed data files and the running `osrm-optimal` container. They decide most of the design, so they are recorded here rather than rediscovered.

```
sources     enter 468 + bidirectional 48                   =  516 groups
targets     exit  466 + bidirectional 48                   =  514 groups
grid        minus self-pairs, same-gare pairs, known prices=  263 659

blockers    osm_toll_booths.yaml toll_booths 1295
                                 + aliases      261        =  1 556 node ids

clean rate  8.79% of a 20 000-pair sample
projected   ~22 800 clean pairs
```

Two existing scripts already hold most of the machinery. `build_vinci_prices.py` has the rate client, its one-per-second throttle, the cent-exact money handling, and the five-digit gare-code check. `build_route_set.py` has the alias resolution that turns a route's raw OSM node ids into booth groups. Neither needs changing.

## Goals / Non-Goals

**Goals:**

- Price every entrance/exit pair a vehicle can drive without passing a third booth.
- Resume from the outputs alone after any interruption, at a cost of at most 25 rate answers.
- Spend no longer on bookkeeping than on work.

**Non-Goals:**

- Changing `data/vinci_price.yaml`'s format. New amounts land in the `prices` mapping the file already defines.
- Pricing gantries. They are blockers here and nothing else.
- Re-running steps 1 to 4. The step reads committed files and the routing service.
- Deciding whether a pair *should* have a tariff. The rate service decides; a disagreement stops the step.

## Decisions

### Route every pair, rather than prefiltering with the distance matrix

The first design used `/table` and the identity `d(u,v) == d(u,b) + d(b,v)` to find booths on a path without routing, as the route set's Wave C does. One request over 1295 locations would have replaced 260 000 route requests.

Measurement killed it. Routing the whole grid is already cheap:

| workers | routes/s | full grid |
|---|---|---|
| 1 | 86 | 50 min |
| 8 | 683 | 6.4 min |
| 16 | 684 | 6.4 min |

The prefilter would also have been unsound in the direction that matters. A booth group's representative is one lane of a plaza; a route using a different lane breaks the equality even though it crosses the group. That produces a pair the matrix calls clean and the route calls blocked — recoverable — and, on ties, a pair the matrix calls blocked and the route calls clean, which silently loses a real tariff. Node identity has neither failure mode.

**Alternative rejected**: a Dijkstra per source over a booth-blocked road graph would answer every target for one source in a single search. It needs a France-wide graph in process, which nothing in this repository builds.

### No snapping hints

`build_route_set.py` uses `snap_to_booth` to pin a query to the segment carrying a booth. That exists because step 4 routes from `place` nodes, which sit off the road.

Booth nodes sit on the lane, so the concern does not carry over. Measured on 982 source and target groups:

```
own segment ranked first   648
own segment ranked second  333      all at distance 0
own segment ranked third     1
```

The 334 that do not rank first are the way splitting at the booth node, and both candidates carry the same geometry. Routing 600 real pairs twice, plain coordinates against own-segment hints:

```
identical blocker set        600 / 600
same clean/blocked verdict   600 / 600
route distance differs >1km    0 / 600
```

Plain coordinates. One fewer `/nearest` call per booth and one fewer thing to get wrong.

### Blockers come from the committed inventory, not from a fresh grouping run

`data/osm_toll_booths.yaml` carries both the 1295 representatives and the 261 aliases with their `parent_id`. That is the whole lane-to-group map, already in a committed file.

So the step needs no PBF, no `osmium`, and no `booth_groups` run — only the routing service. That is what makes a fix-and-rerun cycle cheap.

Booths the overrides mark `ignored` are already absent from the inventory, so they need no handling. The 20 booths with no gare are present and do block, which is deliberate: a booth the operator does not carry still ends a ticket.

### SQLite for rejections, YAML for prices

The step rejects on the order of 237 000 pairs. Step 6's pattern — rewrite the whole state file after every unit of work — does not survive that.

```
                              write, whole run   startup read   size
YAML, rewrite per rejection            201 h        12.21 s     5.6 MB
SQLite, commit per row, sync=FULL         56 s       0.11 s     9.6 MB
```

At `journal_mode=WAL` with `synchronous=FULL`, a durable commit per row costs 56 seconds across the entire run. There is no flush-granularity decision to make and nothing is lost on abort.

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous  = FULL;

CREATE TABLE rejected (
    src      INTEGER NOT NULL,   -- enter or bidirectional group id
    tgt      INTEGER NOT NULL,   -- exit or bidirectional group id
    code     TEXT    NOT NULL,   -- the target's gare code
    blocker  INTEGER NOT NULL,   -- first booth group in driving order
    route_m  INTEGER,            -- route length
    PRIMARY KEY (src, tgt)
) WITHOUT ROWID;
```

Keyed by target **group**, not by gare code. Only 8 target codes carry more than one group, so this costs 4 155 extra rows, and it records each group's own verdict instead of picking one group's blocker and discarding the rest.

Prices stay in `data/vinci_price.yaml`. It is the deliverable, step 6's strictness checks read it, and one source of truth is worth the cost:

```
22 857 prices, rewrite per price   125 min
                rewrite every 25     5 min,  ≤25 rate answers lost on a hard kill
```

Every 25, and once when the step ends for any reason.

**Alternative rejected**: mirroring prices into the same database and rendering the YAML at exit. Zero flush cost, but two stores that can disagree about the deliverable.

### Abort when a clean pair has no tariff

A route with no booth in the way describes a ticket the operator must sell. When the service answers with no amount, the more likely explanation is that the route really does pass a booth and the inventory does not have it. Recording the pair as "no tariff" would bury a data defect under a plausible-looking output.

This follows the project's existing rule: fix the OSM data, not the pipeline.

The risk is real and quantified below.

### Same-gare pairs are excluded from the grid

479 pairs have a source and a target carrying one gare code — the two carriageways of one plaza:

```
126236 (enter, 03087 VOREPPE)     -> 136834 (exit, 03087 VOREPPE)
143256 (enter, 03001 ST QUENTIN)  -> 143255 (exit, 03001 ST QUENTIN)
505680 (enter, 15018 ST MARTIN)   -> 505681 (exit, 15018 ST MARTIN)
```

A ticket from a gare to itself is not a journey, so the service would almost certainly answer with no amount and stop the run 479 times. Excluding them removes 479 near-certain aborts and loses nothing.

### Order the grid source-major, shortest route first within a source

Source-major keeps one source's rows contiguous and makes the report per source natural. Within a source, shortest first banks the near-certain tariffs before reaching the long-distance pairs, which is where an abort will come from.

## Risks / Trade-offs

**A clean pair with no published tariff stops the run** → This is the chosen behaviour, not an accident. It will fire. 674 of 1757 sampled clean pairs cross operator prefixes, and the tail runs to 599 km:

```
599 km  10159 VIRY               -> 07140 MONTREUIL AUX LIONS
569 km  07141 MONTREUIL          -> 09253 LA COTIERE
561 km  10159 VIRY               -> 05601 LA FOLIE-B/PARIS
```

VIRY is at the Geneva border and MONTREUIL AUX LIONS is on the A4 east of Paris. A 599 km route between them crossing no booth means the route left the tolled network onto free roads. The operator prefix cannot be used to filter these out — cross-operator tickets are real, and 194 of the 1025 existing prices cross one.

Mitigation is operational, not technical: each stop names the pair, a human inspects the route, and the missing booth is added to the inventory or the overrides. Every price already banked is kept, and the rerun costs only the pairs after the stop.

**Adding a booth to cure a stop can invalidate a price already recorded** → A pair that was clean before the inventory grew may now be blocked, and its recorded amount then describes a journey nobody drives. Nothing detects this today. The step routes every unrecorded pair and skips recorded ones, so it will not notice. Left as a follow-up rather than solved here, because the check is cheap only if the whole grid is re-routed.

**The rejection database is 9.6 MB and regenerable in about seven minutes** → Whether it belongs in version control is a judgement this design does not make. It is regenerable, which puts it alongside the other intermediates the pipeline does not commit.

**A first run takes about 7.2 hours** → 51 minutes of routing and 6.3 hours of rate requests at the existing one-per-second limit.

Routing is batched per source booth rather than issued one pair at a time. A source's outstanding targets are routed together in a thread pool, its rejections are recorded, and only then are its clean pairs priced. That is needed anyway to order a source's clean pairs by actual route length, and it takes the routing from 51 minutes to about 6, for a run near 6.4 hours.

The batch is a barrier, not a read-ahead: no routing overlaps a rate request, and recording stays ordered and single-threaded. Overlapping the two would save nothing further, since the rate calls dominate.

**Batching several pairs into one rate request was considered and dropped** → The service pairs an entrance with the exit that follows it, so `[E1, X1, E2, X2, …]` would likely return one item per pair and cut 6.3 hours to about 32 minutes. It was dropped for simplicity: one pair per request makes every answer unambiguous and every abort trivially attributable.

## Open Questions

None that change the specs, the approach, or the tasks.
