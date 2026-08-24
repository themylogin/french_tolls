## 1. Reading and validating

- [x] 1.1 Read `data/osm_toll_booths_overrides.yaml` in `builder/build_osm_toll_booths.py`, treating a missing file as empty, and verify the step runs unchanged when the file is absent
- [x] 1.2 Reject an entry carrying both `type` and `parent_id`, an unknown `type`, and a node the extract does not carry as a booth — verify each with a synthetic override naming the offending entry
- [x] 1.3 Reject a `parent_id` naming a booth that the through-road filter excluded or that is itself ignored, and verify the message names the entry
- [x] 1.4 Accept `enter`, `exit` and `passthrough` as inert, and verify an inventory built with them is identical to one built without them

## 2. Ignore

- [x] 2.1 Remove ignored booths before grouping and verify none appears under `toll_booths` or `aliases`
- [x] 2.2 Record each ignored booth in `data/excluded_booths.json` with a reason naming the override, and verify the inventory plus the exclusion report still account for every booth in the extract
- [x] 2.3 Verify a group that loses an ignored member is otherwise unchanged

## 3. Forced membership

- [x] 3.1 Accept forced parents in `builder/booth_groups.py`, merging the overridden booth's whole group into the target's after the grouping rules have run
- [x] 3.2 Reject a `parent_id` target that the rules made an alias of another group, and verify the message names the entry
- [x] 3.3 Verify the merged group's representative is still the smallest member id
- [x] 3.4 Verify `13719126553` is an alias of `635884768` in the regenerated inventory

## 4. Absent booths, hand-stated gares, and cheap re-runs

- [x] 4.0 Move the loader into `builder/overrides.py` so both consuming steps share one parser and one set of validation rules
- [x] 4.0a Accept `vinci: {id, name}`, normalise the operator number to a string, and reject a missing or extra key; verify `04801` survives as a string
- [x] 4.0b Accept `absent_enter`, `absent_exit`, `absent_passthrough`; verify such a booth stays in the inventory and remains a coverage target
- [x] 4.0c Accept `price` only on `absent_passthrough` and only as a number; verify both rejections
- [x] 4.0d Reject `absent_*` combined with `vinci`, and `ignore` combined with either
- [x] 4.0e Reuse `filtered.osm.pbf` and `plazas.osm.pbf` when present; verify a rebuild after an override edit takes about a minute
- [x] 4.0f Remove the override file from the inventory's make prerequisites, restoring existence-based skipping

## 5. Regeneration

- [x] 5.1 Regenerate `data/osm_toll_booths.yaml` and verify the four ignored booths are gone, the group count moved as expected, and the file is deterministic across two runs
- [x] 5.2 Regenerate `data/route_set.yaml` and read the change in the uncovered count before accepting it; report which targets appeared or disappeared and why
- [x] 5.3 Re-run `build_vinci_toll_booths` and report whether the `12010 SEES` abort still occurs — it does, unchanged; no booth-level override can move a placemark, so it needs an upstream fix or a gare-level exemption
- [x] 5.4 Verify `openspec validate apply-booth-overrides --strict` passes
