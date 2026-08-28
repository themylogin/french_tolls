## Context

See proposal.md — Why. The state that shapes the approach:

- `flat_charges(priced)` (`build_segment_weights.py:191`) returns `{group: eur}` for entries where `record["type"] == PASSTHROUGH and record.get("price")`. `run()` calls it at line 1466 and `verify()` at line 1558, both before any routing.
- `load_arcs(path, groups)` turns that group set into arcs from the inventory's `onward_nodes`, and raises when a group carries none.
- `measure_arc` rejects a measurement whose routed length differs from the straight line between the arc's two nodes by more than `ARC_LENGTH_TOLERANCE_M = 1.0`.
- `collect()` produces `records` (the placed pairs) and `segments`. Nothing downstream of it feeds back into the flat set today.
- `verify()` reconstructs the flat set from the price file alone. It has no router-driven pair list and never will: it exists to be run against two finished graphs.
- `write_report` already writes a `flat` list carrying `group`, `f`, `t`, `eur`, `m`, `s`, `w`, `rate`, `how`, `shared`, `way`, `class`.

## Goals / Non-Goals

**Goals:**

- Select flat-charge booths by what they carry and what they end, so the selection survives a retyped inventory.
- Keep `run()` and `verify()` selecting the same set, without `verify()` guessing.
- Keep the run stopping on an unmeasurable arc, while not calling a correctly measured half-kilometre arc unmeasurable.

**Non-Goals:**

- Any change to how a sampled segment's rate is derived. The fit, the regularisation and the journey error are untouched.
- Any change to `data/vinci_price.yaml` or `data/osm_toll_booths.yaml`. This step reads them and does not write them.
- Supplying the three missing tariffs named in proposal.md — Non-goals.

## Decisions

### The predicate is two clauses, not three

A group is a flat-charge booth when it carries a `price` and is not the source or target of any placed pair.

A third clause was drafted — refuse a group any of whose arcs already carries a sample — and rejected. `blockers_of` (`build_vinci_direct_prices.py:321`) scans every node of a candidate route against `traversable`, which `load_inventory` builds from every booth node and every alias (line 108). A pair whose route crosses a booth that is neither its source nor its target is rejected before it samples anything. So an arc leaving a booth can only be sampled when that booth is one of the pair's own ends, and such a booth fails the second clause already. Measured, the third clause rejects nothing.

Keeping it would also have contradicted the requirement that a flat charge and a per-kilometre rate add on the same segment. Where the two sources meet, that requirement says charge both; the third clause would have dropped the booth's tariff entirely, which is the worse of the two failures and the one that leaves a barrier free.

Alternative considered: widen the type test to `(PASSTHROUGH, GANTRY, BIDIRECTIONAL)` and keep everything else. Rejected. It reproduces today's bug in a new place — it admits the two A79 gantries that must stay out, and it still depends on a field that describes hardware. `payment:none=yes` on the Chambéry Nord gantry shows the OSM tag alone cannot separate a charge from a passage.

### `flat_charges` moves after `collect`, and takes the placed pairs

`run()` becomes:

    pairs      = enumerate_pairs(...)
    segments, records, ... = collect(...)          # unchanged
    ends_pair  = {r["src"] for r in records} | {r["tgt"] for r in records}
    charges    = flat_charges(priced, ends_pair)
    arcs       = load_arcs(args.booths, charges)
    flat       = measure_flat(router, arcs, charges, ...)

`ends_pair` is built from `records`, which holds exactly the pairs that produced samples. A pair that was rejected as unusable is not in it, and must not be: its tariff never reached a segment, so the booth's passage is not paid for and the flat charge is the only thing that would charge it.

The cost is that `--dry-run` can no longer report an arc count. It reports the groups carrying a `price` instead, which is the part it can know without routing.

### `verify` reads the flat set from the report

`verify()` cannot apply the second clause: it routes no pairs. Three options were weighed.

1. Re-run the pair routing inside `verify`. Rejected — it turns a two-minute check into the whole step, and it would re-derive rather than check.
2. Have `run()` write the flat group set to a side file. Rejected — a second artefact carrying what the report already carries.
3. Read `data/segment_weights_report.json`, whose `flat` list already names every arc written, its group and its tariff. Chosen.

Option 3 also makes the check stronger. It now verifies the arcs the run actually wrote, rather than an independently derived set that could agree with the file by luck. A report naming an arc the file does not carry is a fault the check should catch, and it now can.

`verify` gains a stop when the report is absent or holds no `flat` list, for the same reason the step stops on an inventory with no `onward_nodes`: an empty set of subjects makes a check that passes on a graph with no barriers priced at all.

### The arc length bound becomes `max(1 m, 1%)`

The bound exists to reject a route that came back with some other stretch of road. It has never been the thing that identifies the arc — `arc_in` does that, by matching the consecutive node pair, which is unique.

A flat metre is a bound on an absolute quantity for an error that scales. Measured over the 44 new arcs the disagreement is 0.4874% at its worst and 1.53 m at its largest, and the two are the same arc. The two rejections are both about 500 m long, both on a curve, and both measured identically by all three radii and all four standoffs.

One per cent was chosen over a looser figure because it still rejects any plausible wrong road: the shortest arc is 6.2 m, where 1% is 6 cm and the floor of 1 m governs, and the longest is 501.7 m, where 1% is 5 m against a 240 m gap to the next node on that road. Alternative considered: raise the flat bound to 5 m. Rejected — it loosens the check on the 18 m barrier arcs, which are the majority, to fix two long ones.

The floor stays at one metre so that a short arc is held as tightly as it is today.

## Risks / Trade-offs

- **A booth typed `passthrough` that does end a placed pair would now lose its flat row, where today it keeps it.** → Measured, no `passthrough` group ends a placed pair: the 239 written today are all still selected. The step reports the count of groups rejected by each clause, so a future change to that fact is visible in the run output rather than in the file.
- **`ends_pair` depends on which pairs the routing placed, so a routing regression silently changes which booths are charged.** → It changes them in the safe direction: a pair that stops being placed adds a flat row rather than removing one, and the acceptance check then measures that row against its tariff. The run already reports unusable pairs.
- **`verify` now depends on an artefact of the run rather than on the committed inputs.** → The report is written before the file, in the same run, from the same set. If it is stale relative to the file, the arc-weight check fails, which is the correct outcome.
- **The 44 new arcs include two of about 500 m.** → A journey joining or leaving the motorway inside that stretch pays part of a toll it does not owe, or escapes part of one it does. The arc is what the inventory says lies beyond the booth; shortening it means adding a node in OSM, not adding a rule here.
- **Three gantries remain unpriced and therefore free.** → Named in proposal.md — Non-goals. The acceptance check does not cover them, because nothing writes a row for them.

## Migration Plan

1. Apply the code change and rerun step 10. It rewrites `data/segment_weights.csv` and `data/segment_weights_report.json`.
2. The file must grow by exactly 44 rows and the report's `flat` list by exactly 44 records. A different number means the predicate selected a different set, and the run's per-clause counts say which clause moved.
3. Rebuild the toll-weighted graph — copy the untouched graph and run `osrm-customize` with the new file.
4. Run `--verify`. It now covers 333 arcs. Every one must differ by its own tariff at the wage.

Rollback is the previous `data/segment_weights.csv` and a re-customization; nothing else in the pipeline reads the flat set.
