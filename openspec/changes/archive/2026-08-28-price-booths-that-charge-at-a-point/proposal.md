## Why

Step 10 writes a flat row for a booth that charges at a point, and it decides which booths those are by `record["type"] == PASSTHROUGH`. 41 booths that charge at a point are typed something else, so they carry no row and are free on the toll-weighted graph: 39 `gantry` and 2 `bidirectional`, 128.20 EUR of tariff over 22 gares.

They include the whole A13/A14 free-flow corridor — Montesson, Chambourcy, Buchelay, Rosny-sur-Seine, Incarville, Heudebouville, Bourg-Achard, Bourneville, Toutainville, Beuzeville, Quetteville, Dozulé, Troarn, Cagny — and Boulay on the A4.

`add-passthrough-booth-weights` left them out for a stated reason: a gantry "is a pair end as well as a flat charge", so charging its arc would count it twice. That is true of 2 of the 41 and false of the other 39. Measured against the price file and the report as they stand:

| test | result |
|---|---|
| do any of the 20 gantry gare codes appear as a target in any of the 522 `prices` maps | no |
| is any group carrying one of those codes anything but `gantry` | no |
| does any row of `data/segment_weights.csv` name one of their lane nodes | no |
| is any of their arcs a segment some priced pair drove | no |
| does any of them carry `prices` of its own | no |

The type never described the charge. `build_osm_toll_booths.py:148` sets `gantry` from the OSM tag `highway=toll_gantry` alone, and that tag covers three unrelated behaviours. Node 7346104910 at Chambéry Nord carries `payment:none=yes` and `comment=Entrée sans ticket`: it takes no money, the exit barrier does, and it holds `prices` rather than a `price`. The A79 gantries open and close priced sections. The other 43 charge a fixed amount for passing one point, exactly as a barrier does, and 55 of the 56 gantry nodes carry no payment tag at all.

Chambéry Nord also shows the two are genuinely different roads rather than one plaza recorded twice. Routed on `osrm-toll` to gare 03015:

    gantry  7346104910 -> ST MARTIN BELLEVUE   50.2 km, 878 nodes, barrier 12608140 not on it
    enter   12608140   -> ST MARTIN BELLEVUE   51.5 km, 931 nodes, gantry  7346104910 not on it

Two entrances to one gare, both at 10.70 EUR, and a driver takes one or the other.

## What Changes

- Step 10 stops selecting flat-charge booths by type. A group gets a flat row when it **carries a `price`** and **ends no placed pair**. The two clauses describe what the type was standing in for, and they hold whatever a future inventory calls the booth.
- The second clause is what `add-passthrough-booth-weights` was reaching for. It rejects the two A79 gantries at Montbeugny Est: 11578487422 is the target of 22530 -> 22540 at 1.90 EUR over 3.55 km, and 11578487423 carries `price` and `prices` together.
- A third clause was considered and rejected: refusing a group whose arc already carries a sample. It fires on nothing, because a pair whose route crosses a third booth is rejected before it can sample anything, so an arc leaving a booth is sampled only when that booth is itself a pair end. It would also contradict the requirement that a flat charge and a per-kilometre rate add on the same segment, by dropping the booth's whole tariff where that requirement says to charge both.
- The flat set is chosen **after** the sampling rather than before it. The second clause reads the placed pairs, which do not exist until the routing has run. `--dry-run` therefore stops naming a number of arcs it can no longer know, and names the groups carrying a `price` instead.
- The arc length check becomes proportional: `max(1 m, 1% of the straight line)` rather than a flat metre. Two of the 44 new arcs are half a kilometre long, and a curving motorway cannot be within a metre of its own chord.
- `--verify` reads the flat set from `data/segment_weights_report.json` rather than deriving it. The acceptance check routes no pair, so it cannot tell which groups ended one, and a check that recomputed the set by a different rule would not be checking the file that was written.

### Non-goals

Four gantries stay free, and no rule here reaches them: Rosny-sur-Seine (12636038010, 12636038011), Cagny (12736493889) and Beuzeville (13283109044). All four are typed `absent_passthrough` in `data/osm_toll_booths_overrides.yaml` — the operator's service does not carry them — and none states a `price`, so `build_vinci_prices` writes them no entry at all. `overrides.py:78` already permits a stated price on that type. What is missing is three tariffs off the operator's published table, not a rule in this step.

## Capabilities

### New Capabilities

None. This corrects which booths an existing requirement selects.

### Modified Capabilities

- `toll-weighted-graph`: a flat-charge booth is defined by what it carries and what it ends rather than by its type; the flat set is chosen after the sampling; the arc length check becomes proportional; the acceptance check takes its subjects from the report.

## Impact

- `builder/build_segment_weights.py`: `flat_charges` becomes a predicate over two clauses and moves after `collect`; `ARC_LENGTH_TOLERANCE_M` gains a proportional companion; `verify` reads the report.
- `data/segment_weights.csv`: 249 743 rows today, 249 787 after — 44 more, none of them colliding with a sampled segment.
- `data/segment_weights_report.json`: 289 flat records today, 333 after.
- No change to `data/vinci_price.yaml`, `data/osm_toll_booths.yaml` or the `Makefile`. The step reads the same inputs and opens no extract it did not open before.
- Both graphs must be rebuilt for the change to reach a driver.

### What the numbers look like

Measured against the committed inputs, with every arc routed on `osrm-toll`:

- The clauses select 280 groups and 333 arcs: the 239 `passthrough` groups written today, plus 39 `gantry` and 2 `bidirectional`. 993 groups carry no `price`, and 2 that do are rejected for ending a placed pair.
- The 41 new groups carry 44 arcs over 22 gares. Tariff 0.70 EUR at the lowest, 2.50 at the median, 10.80 at the highest, 128.20 EUR in total.
- No arc's head is a booth lane node, of its own group or any other, so no route can pay two rows for one point.
- All 44 arcs measure on the first method, the tight-radius route between the arc's own two nodes. None needs the dead-reckoned drive-past.
- Arc length: 6.2 m at the shortest, 40.7 m at the median, 501.7 m at the longest; 9 over 100 m and 2 over 250 m. A barrier's arcs are shorter — 18.4 m at the median — because a barrier sits in a plaza and a free-flow gantry sits on open motorway, where the next node can be far away. That length is the window in which a journey joining or leaving the road pays part of a toll it does not owe, or escapes part of one it does.
- Routed length against the straight line between the two nodes: 0.07 m at the median and 1.53 m at the worst, which is 0.4874%. The flat 1 m rule rejects two arcs on that alone — BUCHELAY FL at 501.7 m against 500.1 m and BOURNEVILLE FL ECH at 477.7 m against 476.3 m. Every radius and every standoff returns the same length for both, so the measurement is not in doubt; the rule is. `max(1 m, 1%)` rejects none of the 44.
