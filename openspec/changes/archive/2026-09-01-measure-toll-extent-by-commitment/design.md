## Context

See `proposal.md` — Why, for the defect and its size. What matters here is that five separable choices sit behind the word "commitment", and each of them moves the published node:

1. How far the graph has to reach, so whether a region is bounded by the road or by the data.
2. Which roads the graph carries at all, so which escapes are real.
3. What counts as a road class, so what counts as an escape from the corridor.
4. Which end of the boundary is published: the last node inside the region, or the first node outside it.
5. What to do when the boundary is not a single node.

Each is measured below against the whole inventory, because each measurement is the reason for a decision and a later reader will want to know whether it still holds. Two of them were decided wrongly first — the reach and the published end — and both mistakes are recorded with what exposed them, since neither was visible in the artefact they produced.

The graph itself is not a new idea in this pipeline. `builder/booth_groups.py` already parses `data/plazas.osm.pbf` into a directed adjacency and decides direction with `two_way()`; `builder/patch_car_profile.py` already knows which gates are shut and which nodes are not there. This change computes a different question over the same material, and has to admit exactly what the router admits — see the first decision below.

## Goals

- One extent per role that depends on the road alone, so that rebuilding the route set cannot move it.
- No tolled section that runs along a road nobody pays for.
- The same fields, the same names, the same coordinates. No consumer changes.

## Non-Goals

- Correcting individual booths by hand. `data/osm_toll_booths_overrides.yaml` already does that and keeps doing it.
- Changing the routing profile. This change reads what the profile already decides; it does not decide anything for it.
- Changing what a per-kilometre price is measured between. It is still extent to extent.

## Decisions

### Post-dominance, not convergence

A node belongs to an entrance's region when every road leaving it leads into the region. That is post-dominance by the booth, and it is what "no choice but to pay" means. The exit's region is the mirror: every road entering it came from inside.

The alternative was to keep convergence and sample harder — more places, or places chosen to lie in different directions. It does not work. The sample cannot distinguish a corridor from a road that every sampled approach happens to share, and at an interchange every approach shares the ring by construction. Adding places narrows the arc; nothing bounds it at the junction.

A fixed point over an adjacency also replaces 36 500 router requests with three passes over the extract. Measured over the whole inventory, the derivation is 6.7 minutes: 223 seconds to read the extract three times and build the graph, and the regions themselves are small enough to be free.

The step as a whole takes 20.0 minutes, against about 14 today. The difference is not the derivation but the price file: `bp.write_state` costs 0.76 s and the step calls it after every one of the 1 024 roles, which is 13 minutes. That checkpointing is what makes the step resumable and it is what the previous step did too. Keeping it was a deliberate choice: a faster cadence would repeat more work after an interruption, and 20 minutes for an artefact rebuilt a few times a year is not where the pipeline's time goes.

### The step carves its own extract, reaching 11 km

The first implementation reused `data/plazas.osm.pbf`, the extract `booth_groups` carves for grouping. That was wrong, and the way it was wrong is worth recording because nothing in the output announced it.

Those cells reach about 2 km around a booth. AMBLAINVILLE's tolled slip road runs 8.11 km. The region grew 30 nodes, ran off the edge of the data, and found no free side at all — not because the road ends, but because the file does. I then published the booth node for it, and the MERU to AMBLAINVILLE pair, the one this whole capability was built to fix, went from 0.19 to 1.03 EUR/km. Fifteen extents did that; eleven more reached the edge and found a boundary anyway, which is a boundary the data did not establish.

A carve has to reach further than the answers it bounds. The whole country's drive network would, at 40.8 million nodes — but the graph is held in memory, and that is over 30 GB. So two cached stages, the pattern `build_osm_toll_booths.run_tags_filter` already uses:

```
france-latest.osm.pbf   4 831 MB   40.8 M drive-class nodes
  tags-filter w/highway=<drive classes>   ->  drive_ways.osm.pbf    522 MB
  extract -p cells of 0.1 deg             ->  extent_ways.osm.pbf   248 MB, 18.2 M nodes
```

0.1 degrees is 11.1 km of latitude, and one cell of padding on every side makes that the guaranteed reach wherever in its cell a booth sits. Against a longest observed extent of 8.11 km that is margin enough to see the junction that ends it.

The memory is why the graph keeps no coordinates: 18.2 million positions cost about 3 GB to answer roughly a thousand questions, so the positions of the published nodes are read back in one further pass. The graph itself is 11 GB, which is in line with what `osrm-partition` already asks of the same machine.

Eleven kilometres is not always enough, and the data said so. RESTIGNE sits on a stretch of the A 85 with no junction for nineteen: its region ran 17.5 km and reached the edge of the carve, and the same booth's other role ran 16.6 km. Two roles, over two booths.

So there is a second carve, cut around exactly the booths whose first-pass regions ran out of extract, at 0.3 degrees — 33 km. Measured, that is 9 cells, 5.9 MB and 961 144 edges, seconds to build, and it bounds RESTIGNE at 19.03 km, the longest extent in the inventory. Nothing remains unbounded after it.

It is deliberately not cached: its booth set is the first pass's finding rather than an input, so a file kept from an earlier set would answer for the wrong booths.

The guard is over-eager, and that is the right setting. Of the 18 roles it defers, 16 return exactly the same answer at 33 km as at 11 km — their region touches an incidental road-end past the 8 km threshold rather than the edge of the data — and only RESTIGNE's two roles needed the reach. Five minutes of carve and graph to catch one real case is worth paying, because the failure it prevents is a fabricated boundary that nothing in the output would flag.

Alternatives rejected: a bigger first cell (0.2 deg reaches 22 km and roughly doubles an 11 GB graph, to answer for two booths); the full drive network (over 30 GB). Carving twice was the alternative I rejected when I thought one carve sufficed — it did not, and the second one is small precisely because it is targeted.

### A branch is a way out only if it gets you out

Found by inspection, not by measurement: Péage de Gye on the A 31 mainline had its extent at the barrier, and its operator knew the tolled road starts 2 km north.

The junction before the barrier is a `highway=motorway_junction` carrying a `motorway_link` of exactly two nodes that then stops. The first rule read that as a choice — a road leaving the junction that does not reach the booth — and refused the junction the region. But a driver taking it arrives at the end of the data and can only turn round and come back through the barrier. It is not an escape under either reading: not if the stub is a mapping artefact, and not if it is a genuine cul-de-sac.

Inspection then found the second kind at ARGENTAN. An on-ramp merges fifty metres past that exit's barrier, so the node after the merge has a predecessor from outside the region and the region stopped there. But the ramp is fed seven metres back by OSM node 14061571393, `barrier=toll_booth`, name "Argentan" — a real booth the override file marks `type: ignore`. Its traffic has paid. ARGENTAN's tolled road runs 9.13 km, to a junction one segment short of the roundabout at 1260054903.

`type: ignore` says no route passes that lane, which settles pricing and grouping. It does not settle what stands on the ground, and this rule asks the second question. So an ignored booth counts as a toll point here and nowhere else.

So a branch bars its predecessor only when its own closure reaches the open network without crossing a toll point. Two constants fell out of measuring it, and both matter more than they look:

- **The closure is bounded at 500 nodes.** A pocket is a plaza's roads or a ramp between two barriers — ARGENTAN's is two nodes. At 20 000 a whole tolled carriageway counts as a pocket, an exit's region runs on until the network releases it, and a quarter of all roles reach the edge of the extract — needing a second carve the size of France.
- **A dead end within 8 km of the barrier is not a carve edge.** The extract reaches at least 11 km, so a nearer one stops because the map says so. Without the distance test every absorbed dead end sent its region to the wider carve, at 25% of roles.

The effect over the inventory is larger than the stub rule alone: extents lengthen from a p90 of 0.78 km to 2.45 km, 18 roles need the wider carve rather than 2, and the rate table returns to where it was before the change — max 0.5355 EUR/km against 0.5355 before, where the previous rule left it at 1.5775.

### The graph admits exactly what the routing profile admits

Access tags, the barrier whitelist, the gate rule and `data/nodes_blacklist.yaml`, all four.

A region is a claim that there is no way out, so every road the graph carries that the router will not drive is a false escape, and a false escape stops a region early. Three sources, all already known to this pipeline and none previously read here: the profile's access blacklist resolved through `motorcar` → `motor_vehicle` → `vehicle` → `access`; the barrier whitelist plus the gate rule `builder/patch_car_profile.py` compiles in; and the three blacklisted nodes, each a connection the map asserts and the ground does not.

Over the carve, that bars 29 294 ways and leaves 9 031 nodes impassable.

**It changes almost nothing, and that is worth stating plainly.** Measured against a graph that ignores all four rules, on the extract this step now carves:

```
                    ending at the barrier   no free side   extents differing
drive + rules               112                  2               —
drive, rules ignored        112                  2           4 of 1 024
```

Four extents, and where they differ the looser graph is shorter by a median of 245 m — it finds escapes the router does not have. An earlier measurement on the 2 km grouping carve put this at 17 extents and a 220-to-203 swing in barrier-endings; those figures were the carve's truncation showing through, not the rules, and they should not be quoted.

The rules stay for two reasons that survive the small number. A false escape can only shorten a tolled section, so the four are wrong in the direction that quietly under-charges. And the alternative is a graph deliberately unlike the one `build_segment_weights` routes on — the coupling that the "extent node not on the route" fallback punishes silently.

### The region is grown over the drive classes

Every road a car can drive counts as an escape, `service` and `unclassified` included. The rule is "could the driver still leave", and the driver does not consult the highway tag.

Like the profile rules, this decides less than it appeared to. Measured on the carved extract, with the profile rules on in both:

```
                     ending at the barrier   extents differing   through is longer by
drive classes                112                    —                     —
through classes              112               16 of 1 024        median 167 m, max 313 m
```

Sixteen extents, none by more than 313 m, and the barrier-ending count is identical. The earlier figures — 490 of 990 agreeing, differences up to 10.8 km, 28 extents gaining over a kilometre, a 203-against-112 split in barrier-endings — were all measured on the 2 km carve, where the class set determined how far a region got before it ran out of data rather than what bounded it. On an extract that reaches far enough, the road bounds it either way.

The reason to keep the drive classes is therefore the principle rather than the margin: a section a driver can leave by is a section the driver was not committed to, and charging a tariff over it repeats, in miniature, the defect this change exists to remove. The 16 differences are all in that direction.

### The published node is the region's own boundary, not the free node beside it

The two candidates are one segment apart, a median of 19 m, and they name the same junction: the free node is the last at which a choice existed, the inside node the first at which none does. As a measurement they are interchangeable, which is what I first concluded — the free node is a single node for 74% of extents and the inside node for 75%, and the rate distributions they produce are indistinguishable:

```
EUR/km        median   p90      p99      max
free node     0.1037   0.1465   0.2124   1.2915
inside node   0.1037   0.1465   0.2124   1.3005
```

What separates them is not the measurement but whether the consumer can use it. `builder/build_segment_weights.py` routes between the two published coordinates and discards any pair whose route does not traverse the nodes it was given. A junction is exactly where that fails: the router snaps the coordinate to one of the arms meeting there, and on a roundabout or a slip-road mouth it need not be the arm the corridor uses.

```
"extent node not on the route", of 23 410 priced pairs
  before this change   3 100
  free node            3 912
  inside node            326
```

Twelve times fewer, and ten times better than the convergence extents this change replaces — those were mid-corridor nodes taken from a route, so a route through them was guaranteed by construction. The inside node recovers that property while keeping the commitment definition.

So the rule finds the free node and the file publishes the node beside it. Booth 142268 records 3011249583 rather than 1320680243; booth 137232 records 8006502773 rather than ring node 805520.

I recorded the opposite decision first, on the grounds that the field name says "where the tolled road begins" and that the choice cost nothing. It cost 15% of all priced pairs, which I had not measured. The flag remains so the comparison can be repeated.

### An ambiguous boundary takes the nearest node

254 of 1 024 regions have more than one free-side node: two roads meeting the corridor at one point. Publishing the nearest to the booth by road distance is the conservative choice — it never claims tolled road the other branch's traffic did not drive.

The alternative, publishing the region's inside boundary node when the free side is ambiguous, was rejected for mixing two conventions in one file. A consumer that reads `first_toll_node_id` should not have to ask which rule produced it.

The count is reported, so a later reader can see how much of the file rests on a tie-break.

### A rising EUR/km is the change working, not failing

The original capability was justified by a rate that was too *high*: MERU to AMBLAINVILLE read 1.2422 EUR/km booth to booth, and finding the tolled road brought it to 0.19. It is natural to carry that over and expect every rate to fall. It should not, and the tasks originally said so, which was wrong.

Convergence put extents wherever the sampled journeys stopped agreeing, and that could be far up an approach road: the worst pair measured 24 820 m, of which about 17 km was road its drivers never paid for. Spreading the tariff over that road is the defect. Removing it necessarily raises the rate on the road that remains.

Measured over the 23 410 priced pairs:

```
EUR/km   before   median 0.1032   p90 0.1443   p99 0.2012   max 0.5355
         after    median 0.1038   p90 0.1466   p99 0.2124   max 1.2915
distance change   median -24 m    p10 -2 261 m   p90 +373 m
80 pairs (0.3%) rose by more than half
```

So the distribution is intact and the tail moves. The criterion that matters is not "no rate rises" but "no rate rises for a reason other than free road being dropped", and that is checked by inspecting the pairs that moved, not by a bound on the maximum.

## Risks / Trade-offs

- **An open service road ends a tolled section at the barrier.** → 203 of 1 024 extents, whose old measurement claimed a longer tolled road. Their EUR/km rises. The step reports them as a group, task 7.1 inspects them, and `data/osm_toll_booths_overrides.yaml` states an extent by hand for any that are wrong.
- **The carved extract bounds a region instead of the road doing it.** → This is not hypothetical: reusing the 2 km grouping carve did it to 15 extents, AMBLAINVILLE included, and its pair went from 0.19 to 1.03 EUR/km. The step now carves its own extract reaching at least 11 km, reports any region that reaches a node the graph stops at, and refuses to publish a boundary the data did not establish.
- **A one-way tagging error makes a corridor look like a dead end, and the region swallows a whole town.** → The region is capped at a stated size and a booth that reaches the cap is reported, not published.
- **850 of 990 extents move at once, so every per-kilometre rate moves with them.** → `data/segment_weights.csv` is rebuilt in the same change, and `build_segment_weights.py --verify` already asserts that the toll-weighted graph charges what the table says. The rate table's own outliers are the check on whether the new distances are sane.
- **The routing profile changes and the extent graph does not follow.** → The two are now one rule. A profile change that is not mirrored here reintroduces the silent fallback in `build_segment_weights.py`, which reports a count rather than an error. Task 6.5 asserts that count does not grow.
- **A booth whose extent was right by luck now moves.** → 155 of 990 already agree with the commitment boundary.
- **A tolled section is shorter than the road the tariff really covers.** → This is the accepted direction of error. A short section under-claims a tariff's reach; a long one paints toll weight on free road, which is the failure being fixed.

## Migration Plan

1. Rewrite the derivation in `builder/build_toll_extent.py`. The file's inputs, its output fields and its resumption logic stay; the router, the place list and the convergence go.
2. Delete `data/vinci_price.yaml`'s extent fields and re-run step 9 to repopulate them, rather than editing in place. The step is resumable on presence, so a stale value would otherwise survive.
3. Re-run `build_segment_weights` and `apply_segment_weights`. Both are keyed to the price file, so `make all` orders them once the price file changes.
4. Compare the rate table before and after. A tariff whose EUR/km falls into the ordinary range is the outcome; one that leaves it is a booth to inspect.
5. Rollback is the previous `data/vinci_price.yaml` and `data/segment_weights.csv`, both tracked.

## Open Questions

- What threshold should the report name an extent past? It is a reporting choice and can be set when the report is written, against a list a person can read.
- The profile bars `access=destination` outright, so a road signed for local traffic only is not an escape here. That matches the router, which is what this design ties itself to, but it is arguably not what a driver can do. It changes no field and no requirement, only values, and inspecting the 203 barrier-ending extents is what should decide whether it needs revisiting.
