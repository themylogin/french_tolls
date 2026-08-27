## Why

A `passthrough` booth charges a flat fee for passing one point. There is no entrance, no exit and no ticket, so it produces no priced pair, and step 10 samples nothing but priced pairs. All 239 of them are therefore free on the toll-weighted graph.

Measured on the graphs as they stand, the weight difference between `osrm-toll` and `osrm-optimal` is +0.0 on every journey that crosses one:

| journey | barrier | tariff | weight difference |
|---|---|---|---|
| Clermont-Ferrand to Beziers | VIADUC DE MILLAU | 13.80 | +0.0 |
| La Rochelle to Saint-Martin-de-Re | ILE DE RE | 16.00 | +0.0 |
| Le Havre to Honfleur | PONT DE NORMANDIE | 5.90 | +0.0 |
| Rueil-Malmaison to Velizy | RUEIL, A86 duplex | 11.80 | +0.0 |
| Nantes to Angers | ANCENIS BARRIERE | 10.40 | +0.0 |
| Toulouse to Bordeaux (control) | ticket pair, no barrier | — | +4152, that is +23.07 EUR |

The ticket machinery is right. The barriers are missing. A router asked for the cheapest way across the Millau viaduct answers as though the crossing were free, and 13.80 EUR is 41 minutes of a driver's time at the default wage.

## What Changes

- Step 10 gains a second source of rows. Beside the fitted per-kilometre rates, it writes one row for each directed segment leaving a `passthrough` booth, carrying that booth's whole tariff.
- The charged segment is every arc whose **tail** is a lane node of the group. An OSRM row is an oriented `from,to` pair, so the two senses of a two-way barrier are two rows and never interfere. A vehicle can traverse such an arc only by standing on the booth node, which is what passing the barrier means.
- Every lane of a plaza is charged, aliases included. A plaza with one charged lane and one free lane is worse than no charge, because the router takes the free lane every time.
- Step 3 publishes the arcs. Every entry of `data/osm_toll_booths.yaml`, alias included, gains `onward_nodes`: the nodes a vehicle reaches after passing that node, one per direction it can leave by, each with its position. Step 3 already builds a directed local road graph over the carved plaza extract to group the lanes, so the field costs no further pass, and step 10 reads it from a committed artefact instead of opening an extract of its own.
- `onward_nodes` names the arcs over the road classes the car profile gives a speed to, which is wider than the through-road classes the grouping follows. What the grouping filter is for — keeping car park barriers out of the inventory — does not bear on what lies beyond a booth a vehicle has already reached. Measured, the wider set adds three arcs over the whole inventory, all `service`, and none at a `passthrough` booth: 1 613 against 1 610.
- Each arc's own length, duration and weight come from the router, as they already do for sampled segments. A route between the arc's two node coordinates with the snapping radius held to a few metres can land on nothing else.
- The run stops when any arc of a priced group cannot be measured, rather than writing a partly charged plaza.
- The acceptance check gains a case per barrier: route the arc on both graphs and require the weight difference to equal `price / wage * 3600`.
- The override file gains a `missing_toll_booth` section: OSM node ids the extract does not tag `barrier=toll_booth` and should. Charging the barrier makes the untagged lane of a plaza worth finding, and the router finds it — at Tonnay-Charente ways 826223989 and 1419952091 carry traffic 22.5 m past the tagged booth for nothing. A node named there is collected as a booth wherever booths are collected, and the grouping attaches it to the lane beside it.
- The `rate` column is written with more decimal places. A whole tariff on a short arc asks for rates near 0.0014, and six decimals is a coarser grid there than anywhere else in the file.

### Non-goals

`price` is not exclusive to `passthrough`. 41 gantries and 2 bidirectional booths also carry one. Those are left alone. A gantry is a pair end as well as a flat charge — one carries `price` and `prices` together, and one flat-priced gantry is quoted as a target in another booth's `prices` — so charging it on an arc would count it twice. The 239 `passthrough` booths are never pair ends, so they cannot.

## Capabilities

### New Capabilities

None. This extends what the segment speed file already describes.

### Modified Capabilities

- `toll-booth-inventory`: every entry gains `onward_nodes`, the nodes a vehicle reaches after passing that node; the override file gains a `missing_toll_booth` section for booths the extract does not tag.
- `toll-weighted-graph`: the file gains rows for booths that charge at a point rather than over a distance, sourced from the inventory's topology instead of from priced pairs; the acceptance check gains a per-barrier case.

## Impact

- `builder/booth_groups.py` and `builder/build_osm_toll_booths.py`: collect the outgoing arcs of every booth node and publish them; collect the booths named by `missing_toll_booth` and locate them in the carved plaza extract.
- `builder/overrides.py`: the `missing_toll_booth` section, and the mirror of the existing stale-override check.
- `data/osm_toll_booths.yaml`: 1 613 arcs over 1 556 lane nodes, 1 502 of which leave by one arc and 54 by two. Regenerating the file is about a minute and reuses the carved extracts. The regenerated file must differ from the committed one in the new field alone; a changed grouping would mean the extract or the overrides moved under it, and that is a separate matter to settle before this one is applied.
- `builder/build_segment_weights.py`: the arc measurement, the merge into the row set, the report and the extended acceptance check.
- No `Makefile` change. Step 10's inputs stay committed and it opens no extract it did not open before.
- `data/segment_weights.csv`: about 288 more rows against the 249 454 there now. None of them collide — measured, no arc leaving a `passthrough` booth carries a row today, and no lane node of one appears in any row.
- `data/segment_weights_report.json`: a section naming each barrier, its tariff, its arcs and their rates.
- Both graphs must be rebuilt for the change to reach a driver. Step 10 is two minutes; step 11 is a copy and a customization.

### What the numbers look like

- 239 groups, 286 lane nodes, 288 arcs. 284 lane nodes have one arc out, 2 have two.
- No arc's head is a booth node, so no route can pay two rows for one barrier.
- Arc length: 1.3 m at the shortest, 18.4 m at the median, 227.0 m at the longest. That length is the window in which a journey that starts on the arc pays part of a toll it does not owe, and a journey that stops on it pays part of one it does.
- Arc class: 172 `motorway_link`, 58 `motorway`, 40 `trunk_link`, 14 `trunk`, 4 other.
- Tariff: 0.40 EUR at the lowest, 2.00 at the median, 55.50 at the highest.
- The tight measurement returns 287 of 288 arcs. A dead-reckoned drive-through returns 257, and covers the one the tight route misses. Where both measure the same arc, over 256 of them, they agree to 0.000 m, 0.000 s and 0.000 weight.
