## Why

Some booths are wrong in a way no rule can fix from the data alone. `14061571393` sits in a layout no real route drives through. `13719126553` is a lane of the Montreuil-aux-Lions plaza reached only through a way tagged `service`, so the through-road graph cannot see its approach and it is stranded as a singleton. Three more are private site tolls that are in the inventory only because they sit on a `tertiary` road.

Each was diagnosed individually and then deferred, because the alternative was a heuristic that would misfire elsewhere. What is missing is a way to state the exception directly and have it checked.

`data/osm_toll_booths_overrides.yaml` already exists and is hand-maintained. Nothing reads it.

## What Changes

- Two steps read `data/osm_toll_booths_overrides.yaml` through a shared parser: extraction consumes `type: ignore` and `parent_id`, the gare mapping consumes `vinci` and the `absent_*` types. Because the file is not a make prerequisite, the gare mapping also checks the inventory against it and stops with the rebuild command when they have drifted apart.
- `type: ignore` removes a booth from the pipeline entirely — it is not grouped, not an inventory entry, and not a coverage target. It is recorded in the exclusion report so the inventory and that report still account for every booth in the extract.
- `parent_id: <id>` forces a booth into a named group with no topological calculation.
- `vinci: {id, name}` states a booth's operator gare by hand, for a gare the operator places too far from any driven lane to match by position.
- `type: absent_enter | absent_exit | absent_passthrough` says the booth is real but the operator does not carry it. Unlike `ignore` it stays in the inventory and stays a coverage target; only the requirement to find a gare for it is waived. `absent_passthrough` may carry `price`.
- Re-running extraction reuses the filtered and carved extracts instead of deriving them from the 4.7 GB source again, so an override edit costs about a minute rather than six. The override file is deliberately not a make prerequisite: keying an expensive step to a modification time is what the pipeline avoids everywhere else.
- Every override SHALL be checked against the extract. An override naming a node that is not a booth, a `parent_id` naming a booth that is absent or that is not itself a group representative, an unknown `type` or key, `price` on anything but `absent_passthrough`, or a contradictory combination such as `ignore` with `vinci`, SHALL stop the step and name the offending entry. A stale override is a silent wrong answer otherwise.
- `enter`, `exit` and `passthrough` remain accepted as valid `type` values and recorded as no-ops. They are the border classification already in the file; rejecting them would break it, and accepting anything at all would let a typo pass unnoticed.

`build_route_set` needs no change: it derives everything from the inventory, so a removed booth is already invisible to it. `build_vinci_toll_booths` reads the file directly for the `vinci` and `absent_*` keys.

## Capabilities

### Modified Capabilities
- `toll-booth-inventory`: adds the override file and its format, the ignore rule, absent booths, hand-stated gares, forced group membership, the validation that makes a stale override fail loudly, and the extract reuse that makes a rebuild cheap.

## Impact

- `builder/overrides.py` — new shared module: parses and validates the file for both steps that read it.
- `builder/build_osm_toll_booths.py` — applies `ignore`, passes forced parents to grouping, reuses the carved extracts.
- `builder/build_vinci_toll_booths.py` — consumes `vinci` and `absent_*`.
- `builder/booth_groups.py` — accepts forced group membership and rejects a `parent_id` target that is not a representative.
- `data/osm_toll_booths_overrides.yaml` — becomes a tracked pipeline input rather than an unread note.
- `data/osm_toll_booths.yaml` — regenerated; nine booths leave the inventory and one changes group.
- `data/vinci_toll_booth.yaml` — one booth gains a hand-stated gare, and twelve stop being required to have one.
- `data/excluded_booths.json` — gains the ignored booths with an override reason.

Not affected: `builder/build_route_set.py`, which reads the inventory and inherits the result.
