## 1. Grouping rules

- [x] 1.1 Restrict the grouping graph in `builder/booth_groups.py` to `THROUGH_CLASSES`, and verify the Saint-Michel pair `5923855974` / `5923855978` no longer share a predecessor
- [x] 1.2 Expose a two-way classification from `booth_groups.py` derived from the same `fwd_ok and rev_ok` branch `GraphBuilder` already computes, and verify it returns 52 booths, 46 of them with an explicit `oneway=no`
- [x] 1.3 Exclude a two-way booth from every union, and verify `81055576` and `1042834566` end in different groups while the four Mont Blanc lanes stay in one
- [x] 1.4 Verify the group count lands near 1303 and that all 17 operator-confirmed conflicts are split, using the recorded node pairs for `267165980`, `252927026`, `268212668`, `661810865` and the rest

## 2. Inventory output

- [x] 2.1 Emit `bidirectional: true` on the entries of the 52 two-way booths and on no others, and verify by reading back `data/osm_toll_booths.yaml`
- [x] 2.2 Regenerate `data/osm_toll_booths.yaml` and verify every entry has `latlon`, every alias has `parent_id`, and keys ascend in both blocks
- [x] 2.3 Verify determinism by regenerating a second time and diffing the two files
- [x] 2.4 Verify every booth flagged `bidirectional` is a representative with no aliases

## 3. Route set — direction

- [x] 3.1 Update `builder/build_route_set.py` to read the new inventory shape, and verify it reports the expected group and alias counts at startup without running a search
- [x] 3.2 Record `prev_node_id` for a bidirectional booth from the routing engine's traversed node list, and verify on one known route through `81055576` that the value is one of that booth's two graph predecessors
- [x] 3.3 Emit `covers` as a list of mappings, and verify a regenerated file parses with `node_id` on every entry and `prev_node_id` only on bidirectional ones
- [x] 3.4 Change the coverage universe to direction-qualified targets, and verify with a synthetic input that one bidirectional booth yields two targets and a one-way booth yields one
- [x] 3.5 Update `data/uncovered_booths.json` to name the missing direction, and verify an uncovered direction is distinguishable from an uncovered booth
- [x] 3.6 Update the stdout summary to report covered, uncovered and total against targets rather than groups, and verify the three numbers agree

## 4. Regeneration and verification

- [x] 4.1 Regenerate `data/route_set.yaml` from scratch against the new inventory and record wall-clock time
- [x] 4.2 **Stop and read the uncovered count before accepting the result.** A count far above the previous 9 means a split separated real lanes of one plaza; report the affected booths rather than proceeding
- [x] 4.3 Verify the grouping invariant directly: no route's `covers` list contains two booths of one group, checked over every route in the regenerated file
- [x] 4.4 Verify every `node_id` in every `covers` list is a key of `toll_booths`, and that no alias id appears
- [x] 4.5 Verify the route count is below the number of coverage targets covered
- [x] 4.6 Update `data/mk_summary.py` for both new formats and verify it runs

## 5. Downstream change

- [x] 5.1 Delete the `toll-booth-inventory` delta from `openspec/changes/map-booths-to-vinci-gares/specs/`, which this change supersedes, and verify that change still validates
- [x] 5.2 Update that change's proposal and design to drop the inventory format from its scope and to reference this change as a prerequisite
- [x] 5.3 Update `builder/build_vinci_toll_booths.py` to read the new `covers` shape, and verify it loads the regenerated route set and reports an outstanding route count without issuing a request
- [x] 5.4 Verify `openspec validate --strict` passes for both changes
