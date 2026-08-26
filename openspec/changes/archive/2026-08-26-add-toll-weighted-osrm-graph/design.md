## Context

See proposal.md — Why. What the design has to work around is set by four facts about the existing tree and about OSRM.

**The price file is a booth-pair table, not a road table.** `data/vinci_price.yaml` holds 23 376 tariffs across 522 source booths (470 `enter`, 45 `bidirectional`, 7 `gantry`). Every one resolves to at least one target group; 459 of them resolve to two, giving 23 835 candidate ordered pairs. A tariff names two points and says nothing about the road between them.

**The graph's weight is not its duration.** The patched profile keeps the stock `weight_name = 'routability'`, so a segment's weight is its duration divided by a rate the profile lowers for a road it wants to avoid. On motorway the two coincide, but the pipeline must not assume it — the routes also run over links and through plazas.

**OSRM already publishes what is needed.** A `/route` query with `annotations=nodes,distance,duration,weight` returns four parallel arrays, one entry per consecutive OSM node pair. That is the segment identity the CSV keys on and the original duration and weight in the same response. The proposal's guess that a Lua patch would be needed does not hold; the numbers are already on the wire.

**`osrm-customize` takes the file.** The graph is MLD (`osrm-routed --algorithm mld`), so `osrm-customize data.osrm --segment-speed-file f.csv` is the tool, not `osrm-contract`. It rewrites the customized layer in place and needs the extract and partition output that is already there.

Docker is reached through the Makefile's `DOCKER`/`COMPOSE` variables; the host account here cannot open the socket directly, so every measurement below is taken from inside a container.

## Goals / Non-Goals

**Goals:**

- One directed-segment rate table derived only from committed inputs and the untouched graph.
- Durations identical on both graphs, to within OSRM's decisecond storage.
- A weight difference between the graphs that is exactly the sum of the driver's time to pay the tolls on the route, with no second effect.
- A report that says how well a per-segment rate can describe the operator's tariffs at all, not only whether it validated.

**Non-Goals:**

- A general-purpose solver. The fit is a fixed-point iteration in log space, not a least-squares library call; see D7 for why that was enough and what it buys.
- Modelling the fixed per-plaza component of a French tariff separately from the per-kilometre component. The whole tariff is spread over the distance.
- Serving the toll-weighted graph to anything. Nothing in the pipeline queries `osrm-optimal`; it exists to be queried from outside.
- Changing any answer the first eight steps give. The `toll` graph is today's `optimal` graph, moved.

## Decisions

### D1: Per-segment duration and weight come from route annotations, not from a Lua patch

`annotations=nodes,distance,duration,weight` gives, for a route of N nodes, N-1 entries of each. Segment `i` is the ordered pair `(nodes[i], nodes[i+1])` with `distance[i]`, `duration[i]` and `weight[i]`.

*Alternative considered:* patching `car.lua` to emit speed and rate per way. Rejected on two counts. The CSV keys on node pairs, not ways, so a way-level dump still needs the geometry to be split; and a number read out of the profile is not necessarily the number the graph was built with, because `osrm-extract` applies its own clamping afterwards. The annotation is the graph's own answer.

*Alternative considered:* reading `.osrm.geometry` and `.osrm.edges` directly. Rejected — it couples the pipeline to OSRM's on-disk format for a number the HTTP API already returns.

### D2: The speed column is written as a real number, not rounded to whole km/h

The wiki example shows an integer, but `updater.cpp` parses it as `double` and computes

```cpp
const auto speed_in_ms = speed_in_kmh / 3.6;
const auto duration = distance_in_meters / speed_in_ms;
segment_duration = max(1, round(duration * 10.));
```

so writing `distance[i] / duration[i] * 3.6` at full precision reproduces the original duration to the decisecond OSRM stores. Rounding to whole km/h would move a 130 km/h segment by up to 0.4%, which over a 200 km route is about 20 seconds of drift with no reason behind it.

Task 1.4 confirms the parser accepts a fractional speed before anything is built on it. If it does not, the fallback is whole km/h and a widened duration bound in the acceptance check.

### D3: The rate column is `length / target_weight`

`updater.cpp` computes `segment_weight = round(distance_in_meters / rate * weight_multiplier)`, and the HTTP API reports weight already divided by that multiplier. So a rate of `distance[i] / w` reproduces an API weight of `w` whatever the multiplier is, and nothing in the pipeline needs to know its value. Weight is stored as an integer after multiplication, giving a granularity of 0.1 at the default precision — three orders below the tens or hundreds of seconds a toll adds.

The target weight is

```
segment_price_eur = price_per_km * distance_m / 1000
target_weight     = original_weight + segment_price_eur / wage_eur_per_hour * 3600
rate              = distance_m / target_weight
```

Turn weights are not touched, so a route's weight on the toll-weighted graph is its weight on the untouched graph plus the sum of the added terms. That identity is what the acceptance check tests.

### D4: A segment's observations are reduced by minimum, not by mean

OSRM folds a turn penalty into the segment before the turn, so the same directed segment can be reported at 2.77 s on a route that runs straight through and 5.77 s on one that turns off immediately after. Averaging would bake a penalty into a segment that does not have one.

A penalty only ever adds, so the smallest observed duration and the smallest observed weight are the clean ones — provided at least one route drove the segment without turning. The step reports how many segments never got a consistent second reading, so the cases where it cannot tell are visible.

This applies to duration and weight. It does not apply to the price samples, which are averaged as specified.

### D5: The first and last segment of each route are dropped

The router snaps an endpoint onto a lane part-way along a segment, and the annotation reports the part, not the whole. Its speed is right but its length and weight are a fraction of the segment's, so it would both misstate the segment's own numbers and, if emitted, change the duration of a segment nobody measured properly.

Both dropped segments are inside a toll plaza and are a few tens of metres. They are dropped from the emitted rows and from the sample table; the route's full length, including them, is still the denominator of the price per kilometre, because that is the distance the driver was charged for.

### D6: The spread is reported and gates nothing

The step holds, per directed segment, a running count, sum, minimum and maximum, plus the pair that produced each extreme. Deviation is `(max - min) / mean`.

The deviation describes the *samples*, and it keeps that meaning after D7 made the fitted rate what the file carries. It is the evidence about how far the tariffs disagree with each other, which is a different question from what rate best reproduces them.

The gate this once had is gone. It stopped the run when any segment spread more than 10%, and measured, 97.9% do — after the denominator was fixed, aliases resolved, interchange loops dropped and zero tariffs excluded. Every one of those corrections removed extremes and left the median at 59.4%, which is the point at which the spread stopped being evidence of a defect and started being evidence about French tolls: two journeys on different concessions pay different rates for the same distance, and no pipeline fixes that.

So a limit on it would stop every run forever for something nobody can act on. What can be acted on is the journey error, and D7 is what acts on it. The spread is still reported worst-first with the way carrying each segment — it is how four separate measurement errors were found, and it stays for that — but nothing about it stops the run.

### D7: The rates are fitted to the tariffs, and regularised toward the means

The mean is the wrong estimator here, and no amount of better measurement fixes it. Four measurement errors were found and corrected — the denominator, alias resolution, interchange loops and zero tariffs — and the median segment deviation moved only 63.9% to 59.4%. The residual is real: different concessions charge different rates for the same distance, and a journey that votes one number onto all of its segments cannot express that.

So each journey becomes an equation, `sum over its segments of rate * length = tariff`, and the rates are fitted to minimise the error in those equations. That is the journey error itself — the quantity a driver feels — rather than a per-segment agreement journeys need not follow.

**Solved by iteration in log space, not by a solver.** Each journey computes the correction it wants, `log(tariff / built)`; each segment takes the mean of what its journeys asked; repeat. Twelve iterations is where it stops moving. This keeps every rate positive without a constraint and needs no linear algebra library — scipy is not in the builder image, and a 23 352 x 249 454 non-negative least-squares problem would be a heavy dependency for something fifteen lines express.

**Regularised, because the system is underdetermined.** 23 352 equations do not pin 249 454 unknowns, and unconstrained the fit exploits that: rates reach 7.94 EUR/km on a VAL DE LOING slip road crossed by four journeys, 35 times its mean. Half a kilometre there carries 4.24 EUR instead of 0.12 — a 12-minute penalty on any journey nobody priced, which is nearly all of them. The graph exists to answer arbitrary questions, so a rate that is only correct in aggregate over the priced pairs is not good enough.

Each segment is therefore a weighted average of what its journeys want and what its own samples said:

    x <- (count * (x + correction) + lambda * log(mean)) / (count + lambda)

The data is weighted by how many journeys there are and the prior by `lambda`, so the shrinkage is `lambda / (count + lambda)`: a segment 1 500 journeys cross moves where the data says, one 4 journeys cross barely moves. One number says how many journeys it takes before a segment is trusted over its own mean.

`lambda` was swept:

| lambda | median | p90 | within 10% | max rate | >1 EUR/km | near 0 |
|---|---|---|---|---|---|---|
| means | 8.5% | 23.2% | 56.7% | 0.5355 | 0 | 0 |
| 0 | 3.1% | 11.3% | 87.9% | 7.9412 | 587 | 1909 |
| 1 | 3.3% | 11.8% | 86.8% | 1.5786 | 29 | 10 |
| 2 | 3.3% | 12.3% | 86.0% | 0.7612 | 0 | 0 |
| **5** | **3.5%** | **13.1%** | **84.4%** | **0.5386** | **0** | **0** |
| 10 | 3.7% | 14.0% | 82.8% | 0.5372 | 0 | 0 |
| 250 | 6.1% | 18.7% | 71.3% | 0.5356 | 0 | 0 |

Five is the knee. It takes most of the journey-error gain an unconstrained fit reaches and leaves the highest rate at 0.5386 against the means' own highest of 0.5355 — so no segment is priced outside the range some real journey actually paid, which is the property that makes the graph safe on routes nobody priced. Below five it goes: at one, 29 segments exceed 1 EUR/km and ten fall to nothing.

*What is given up.* A rate is no longer explainable as "the average price per kilometre of the journeys through here". It is the rate that best reproduces those journeys' tariffs, held near that average. The deviation report still describes the samples and is unaffected — it remains the evidence about the tariffs, and it is not what the file carries.

The fit costs 156 seconds on top of the routing.

### D8: `optimal` is a copy of `toll`, made fresh each time

`osrm-customize` rewrites the customized layer in place. Customizing an already-customized graph a second time layers one update on another, so the only way to get a graph that differs from `toll` in exactly the rows of the CSV is to copy `toll` first.

*Alternative considered:* hardlinking the files `osrm-customize` does not write. Rejected — which files it writes is not documented, and a wrong guess corrupts the untouched graph through the link. The copy costs 9.2 GB and a few minutes.

The apply step therefore: checks free space, removes `$(OSRM_OPTIMAL_PATH)/france-latest.osrm*`, copies every `france-latest.osrm*` from the toll path, runs `osrm-customize --segment-speed-file /data/segment_weights.csv`, restarts `osrm-optimal`, and touches its stamp.

### D9: `toll` keeps port 5000, `optimal` takes 5001

Every committed script addresses `http://osrm-optimal:5000` on the Compose network, and the untracked host-side diagnostics under `data/` address `127.0.0.1:5000`. Both mean the untouched graph. Renaming the service to `osrm-toll` and leaving it on host port 5000 keeps the host-side scripts correct without touching them; the Compose-network URLs inside `builder/*.py` change to `http://osrm-toll:5000` with the Makefile.

The container port stays 5000 in both services — it is the published host port that differs.

### D10: `--survey` mode, as in step 8, reporting deviations and prices as separate findings

Step 8 established the convention: collect every stop condition, keep going, print the findings grouped by kind in the bordered `table` helper, and exit 1 without writing. Step 9 adopts it for the same reason — 23 835 pairs is too many to fix one abort per run.

Three kinds of finding, and the first two are the ones the survey exists to show:

- **`outstanding deviation`** — a directed segment whose sample spread exceeds `--max-deviation`. Reported with its node pair, count, extremes, mean, deviation, and the priced pair behind each extreme with that pair's gare codes, tariff and route length. Worst first.
- **`outstanding price`** — a priced pair whose reconstruction `sum(mean_rate * length)` misses the operator's tariff. Reported with both gare codes, the tariff, the reconstruction, the absolute and relative error, and the route length. Largest absolute error first.
- **`unusable pair`** — a pair that contributed no samples, because its route crossed a third booth or because the router returned none. Reported with the reason and the blocking booth.

Keeping the first two apart matters because they can disagree in both directions. A junction segment shared by a 12 km hop and a 240 km run will show a large deviation while every journey through it still reconstructs closely, because the segment is a few hundred metres of either journey. The reverse also happens: a long route whose segments are each inside the limit can still miss its tariff by euros, because the errors are correlated along it and add rather than cancel. A survey that reported only one of the two would hide whichever failure mode the data actually has.

Both tables need a bound on how many rows they print. The deviation table is capped and the count of suppressed rows is stated; the full per-segment record goes to `data/segment_weights_report.json` regardless, so nothing is only ever summarised.

Under `--survey` the deviation limit is reported and not enforced, an unusable pair is excluded from the sample table rather than stopping the run, and no file is written. Exit is non-zero when any finding was collected.

### D11: Memory and file size

Measured: 223 174 directed segments, 22.8 million observations of them, and a peak of 586 MB RSS. The estimate here was tens of megabytes, from a guess at the segment count made before any of it was routed; the arrays hold, but the per-pair segment lists and the report structure cost more than the guess allowed. 586 MB is unproblematic — the same step's `osrm-customize` peaks at 6.5 GB — so it is recorded rather than optimised away.

The file is 223 174 rows and 9.0 MB.

### D12: The findings name the way, not only the node pair

A node pair is what OSRM keys on and what the CSV carries, and it is not something a reader can look up. `--ways` scans the extract for the ways carrying the observed segments and puts the way id and its highway class into the deviation table and the report file. It costs 4.2 minutes against the routing's 1.6, and it matches 223 174 of 223 174 segments.

The class is there because "is it the ramps?" is the first question anyone asks of the deviation, and it needs an answer from the data rather than from intuition. The answer is no; see D13.

### D13: Excluding `*_link` was tested and does not help

The `*_link` classes look like the culprit — a ramp is shared by a short hop paying a near-fixed charge and a long run paying by distance, and the very worst segments in the table are indeed ramps (815% on a motorway_link shared by a 2 km hop at 1.90 EUR and a 26 km journey at 2.00 EUR).

They are not the culprit. Dropping every link makes the distribution slightly *worse*:

| | segments | median | p90 | p99 | over 10% |
|---|---|---|---|---|---|
| everything | 223 174 | 63.9% | 122.6% | 339.6% | 98.6% |
| links only | 56 607 | 54.3% | 109.3% | 274.6% | 95.1% |
| **no links** | 166 567 | **66.1%** | **125.1%** | **347.1%** | **99.8%** |

Links are 78.5% of the best band (0–25%) and only 17–25% of every band above 100%. They hold the top few rows of a table sorted by deviation, which is what makes them look responsible, but they are a minority of the tail and better than mainline on every percentile. Excluding them would discard 56 607 well-behaved segments — 8.3% of the network's metres — and raise every summary figure.

Two other candidate explanations were tested and also rejected:

- **A fixed per-plaza charge.** A least-squares fit over one entry booth's 41 tariffs gives `tariff = 0.77 EUR + 0.1216 EUR/km`. The fixed part is 77 cents, too small to explain a 64% median spread.
- **Short journeys.** Excluding pairs under a minimum length barely moves it: at a 100 km minimum the median falls from 63.9% to 57.1% while 87% of the segments are lost. Median EUR/km is flat across length bands (0.098–0.115).

What the data does show is spread *within* every length band — at 100–200 km, journeys run 0.086 to 0.155 EUR/km. The cause is geographic: different concessions charge different rates for the same distance, and a segment on a shared corridor is driven by journeys priced on different schedules. No uniform per-journey spreading can reconcile that, which is exactly what D7 would address.

### D14: A booth is found on a route by resolving aliases, never by its own node id

A plaza has one lane per booth group and the inventory records the others as aliases with a `parent_id`. `blockers_of` has always resolved through them; the checks added for this step did not, and asked whether the group's own node id appeared in the route.

That is wrong whenever the router picks a different lane, which it does as soon as the route is requested from further away than the booth itself. It cost 3 401 pairs, each silently falling back to a barrier-to-barrier measurement — including ANNECY NORD to ST MARTIN BELLEVUE A41 N, which reads 1.4000 EUR/km measured barrier to barrier and 0.3787 measured properly.

Every check that asks "did this route cross that booth" now resolves, including the side test, which previously called `nodes.index(group)` and raised when the group's own id was absent.

### D15: A pair whose route loops out and back is not a journey

Two ramps of one interchange under two gare codes produce a route that leaves the network and comes back, crossing no third booth — so `blockers_of` clears it and the tariff is divided by a distance nobody drove. GACE SENS 2 to GACE SENS 1 is 0.70 km apart and routes 20.8 km for 20.40 EUR.

The discriminator is the ratio of the barrier-to-barrier route to the straight line between the barriers. Measured over all 23 376 pairs:

| percentile | ratio |
|---|---|
| 50 | 1.26 |
| 90 | 1.59 |
| 99 | 2.09 |
| 99.9 | 2.69 |
| max | 69.10 |

Then a gap: 3.9, then 5.6, 29.7, 48.3, 69.1. `--max-detour` defaults to 5, which drops those four and nothing else. Three is too tight — it would take TOURNUS to LE MIROIR, 32.7 km apart and 101.6 km routed at a plausible +19% reconstruction, which is the network genuinely going around.

*The ratio is measured barrier to barrier, not between the extents.* This matters: MERU to AMBLAINVILLE is 1.0 barrier to barrier and 6.8 between the ends of its tolled road, so an extent-based test would discard exactly the pairs the extents exist to fix. The barrier distance costs nothing to obtain — the extent-to-extent route crosses both barriers, so it is a slice of an annotation already in hand.

### D16: A tariff of nothing is not a rate of nothing

Twenty-one pairs are priced at 0.00 EUR, nearly all at ordinary detour ratios, so D15 catches only one of them. Each puts a sample of 0 EUR/km on every segment of a real motorway journey: one set the low end of a segment 1 504 journeys use, dragging its mean to 0.1336 and making it the worst-deviating segment in the table.

They are excluded from the sample table and reported. Whether a free section is a real fact about the network is a question for the price file; it is not something this step's arithmetic can express, because a zero numerator says the road is free for everyone rather than free for that pair.

## Risks / Trade-offs

- **The deviation limit stops the first run** → Expected; see D6. The full report is printed before the stop, `--survey` reports without stopping, and `--max-deviation` widens the limit while the data is worked on.
- **A segment that only ever appears before a turn keeps its turn penalty** → Its weight and duration are overstated by up to the penalty, so it looks slower and costlier than it is on both graphs equally. The step counts these and reports them. They are approach and exit links, not through segments.
- **A tariff that is mostly a fixed charge** — a gantry pair, a short plaza-to-plaza hop — spreads a large price over a short distance and produces a very high EUR/km sample for every segment it touches → Exactly what the deviation report is for. If these prove to be the sole cause of the spread, the remedy to discuss is excluding pairs below a minimum route length, not changing the arithmetic.
- **Node ids move when the extract is refreshed** → The CSV is committed against one extract. A `download_pbf` that fetches a newer France invalidates it silently, because unmatched rows are ignored rather than reported. Mitigated by the setup stamp: rebuilding the graph re-runs steps 9 and 10, and the acceptance check in step 9 fails loudly if the file no longer describes the graph.
- **Two graphs on one filesystem** → Measured: the graph is 9.2 GB and the extract 4.7 GB, so preprocessing peaks near 14 GB and the two graphs plus that peak want about 23 GB. `MIN_FREE_GB` is 25 and the apply step checks 12 for the copy alone. Both check before doing work.
- **`osrm-optimal` is not a drop-in for `osrm-toll`** → A route on the toll-weighted graph is the cheapest in money-and-time, not the fastest, so every existing step must keep querying `osrm-toll`. The rename is what makes a mistake here visible: a step left pointing at `osrm-optimal` gets a graph whose name no longer says "the one everything uses".

## Migration Plan

The untouched graph already exists at the current `OSRM_OPTIMAL_PATH`. Nothing needs rebuilding.

1. `docker compose down` — `osrm-routed` maps the graph at startup and the directory is about to move.
2. `mv .data/osrm/optimal .data/osrm/toll` (or the equivalent for whatever the current `OSRM_OPTIMAL_PATH` is).
3. In `.env`: set `OSRM_TOLL_PATH` to the moved directory, and `OSRM_OPTIMAL_PATH` to a sibling that does not yet exist.
4. `make setup_osrm` — finds `$(OSRM_TOLL_PATH)/.setup.stamp` in place and skips. This is the check that the move was complete.
5. `docker compose up -d osrm-toll`, then `make build_segment_weights apply_segment_weights`.

Rollback is the move in reverse plus reverting the two files; the toll graph is byte-identical to the graph before the change, so no pipeline output is affected. The toll-weighted directory is deleted.

## Open Questions

Both are measurements taken during implementation, not decisions. Neither changes the specs, the approach or the task list.

- The bound in "the two durations agree". D2 predicts a decisecond per segment; the acceptance check needs the measured figure over a real 150 km route.
- The tolerance on the 43.5-minute weight difference for the fixed pair. It is set by how far the fitted per-segment means reconstruct that one pair's tariff, which task 5.2 reports for every pair.
