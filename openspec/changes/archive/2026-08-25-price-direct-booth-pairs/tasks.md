## 1. Grid enumeration

- [x] 1.1 Create `builder/build_vinci_direct_prices.py` reading `data/vinci_price.yaml`, `data/vinci_toll_booth.yaml`, and `data/osm_toll_booths.yaml`; verify it reports 516 source groups, 514 target groups, and 1556 blocker node ids without issuing a request
- [x] 1.2 Build the source list from the `enter` and `bidirectional` entries and the target list from the `exit` and `bidirectional` entries; verify a `gantry` or `passthrough` group appears in neither, and that all 48 `bidirectional` groups appear in both
- [x] 1.3 Drop self-pairs and pairs whose source and target carry one gare code; verify 479 same-gare pairs are dropped, including `126236 -> 136834` (03087), `143256 -> 143255` (03001), and `505680 -> 505681` (15018)
- [x] 1.4 Drop pairs whose target gare code already appears in the source's `prices`; verify the outstanding grid is 263 659 pairs against the committed price file
- [x] 1.5 Order the grid source-major and, within a source, shortest route first; verify one source's pairs are contiguous and that the step reports the grid size before routing

## 2. Blocker detection

- [x] 2.1 Build the blocker set from `toll_booths` plus `aliases` and the alias-to-parent map from `parent_id`, as `build_route_set.py:909-916` does; verify 1295 representatives, 261 aliases, and that a known alias resolves to its parent
- [x] 2.2 Route a pair with `annotations=nodes`, `overview=false`, `steps=false` using the booths' own coordinates with no snapping hint; verify a known pair returns the same node count as the same query issued by hand
- [x] 2.3 Resolve the traversed nodes to groups, discard the source and the target, and keep the remainder in driving order; verify a pair crossing booths B then C reports B first
- [x] 2.4 Treat a `gantry`, a `passthrough`, and a booth with no gare as blockers; verify each with a pair known to cross one
- [x] 2.5 Verify the clean rate over a 20 000-pair sample of the grid falls near 8.79%, so the projected clean count is near 22 800

## 3. Rejection database

- [x] 3.1 Create `data/vinci_routes_rejected.sqlite3` with the `rejected` table from design.md, `journal_mode=WAL` and `synchronous=FULL`; verify the schema matches and the file is created on first use
- [x] 3.2 Insert one row per rejected pair, committed before the next pair is routed; verify killing the process immediately after a rejection leaves that pair recorded
- [x] 3.3 Load every recorded pair at startup into a set keyed by `(src, tgt)`; verify a full database of 237 000 rows loads in under a second and produces no route request
- [x] 3.4 Treat a target gare code as unreachable only when every group carrying it is rejected; verify one of the 8 multi-group target codes is still priced when one of its groups routes clean

## 4. Pricing

- [x] 4.1 Reuse the `Rates` client, `to_cents`, `to_euros`, and `check_code` from `builder/build_vinci_prices.py` rather than reimplementing them; verify the module imports and that no duplicate rate client exists
- [x] 4.2 Submit a clean pair as exactly two passages — source gare then target gare — with vehicle category 1, payment option 2, and `ULYS_PASSAGE_DATE`; verify a captured request body carries two passages and no more
- [x] 4.3 Record the returned amount on the source group under the target's gare code in `prices`, leaving the target entry untouched; verify against a known pair that the target's entry is byte-identical before and after
- [x] 4.4 Verify the written file still satisfies the `vinci-price-mapping` format rules — ascending group ids, ascending gare codes, and a byte-identical rewrite from the same state

## 5. Abort conditions

- [x] 5.1 Stop when the service returns no amount for a clean pair, naming the source group, the target group, and both gare codes; verify with a synthetic null-price response carrying `No rate found.`
- [x] 5.2 Stop when a returned item's entrance or exit is not the gare submitted; verify with a synthetic response naming a third gare
- [x] 5.3 Stop when the routing service answers with a code other than `Ok`, naming both groups; verify with an unroutable synthetic pair
- [x] 5.4 Stop when a returned amount differs from one already recorded for that pair, comparing whole cents; verify a pair recorded at 6.80 and answered 7.10 stops the step and one answered 6.80 does not
- [x] 5.5 Stop when a pair's rate request fails five times; verify the pair is absent from both outputs afterwards
- [x] 5.6 Read the override file's `nodes_blacklist` and stop when a route traverses one of those nodes, naming both groups and the node; verify with a synthetic node sequence containing 13461343964
- [x] 5.7 Verify that after any stop the offending pair appears in neither `data/vinci_price.yaml` nor the rejection database, so the next run meets it again

## 5b. Prohibited gare pairs

- [x] 5b.1 Add a `prohibited_gare_pairs` section to `builder/overrides.py`, a list of two-element lists of operator numbers normalised to strings and held as ordered pairs; verify a non-list, a wrong-length entry, and a pair naming one gare twice are each refused
- [x] 5b.2 Drop a prohibited pair from the grid before routing, alongside self-pairs and same-gare pairs, and report the count of prohibitions at startup; verify the pair is routed no more than it is priced, and that a prohibition of A to B leaves B to A alone

## 6. Resume and flush

- [x] 6.1 Derive the outstanding work from the price file and the rejection database alone, with no cursor of the step's own; verify deleting every other file the step wrote changes nothing about what the next run does
- [x] 6.2 Rewrite `data/vinci_price.yaml` every 25 prices and once when the step ends for any reason, including on a stop; verify an interruption costs at most 25 rate answers — flushed every 25 and in a finally block; the 6-hour survey run persisted 21 900 prices incrementally and the stop at TOULOUSE-SUD left the file valid
- [x] 6.3 Verify a run against complete outputs issues no route request and no rate request, and exits successfully — closed unverified. A finding is recorded in neither output, so a rerun meets exactly the findings again; the last run left 335, all `blacklisted route`, and "complete outputs" is unreachable while a blacklisted route is a stop condition. The resume path itself is verified by 6.1 and by the offline checks

## 7. Report

- [x] 7.3 Add a `--survey` mode that records each stop, skips that pair, keeps going, and exits 1; verify a surveyed pair lands in neither output and that a rate request failing every retry still stops the run — verified on the full run: 29 findings collected, exit code 1, every surveyed pair absent from both outputs
- [x] 7.4 Report the findings grouped by kind, each a bordered table carrying both gares with their names and OSM node links, the straight-line distance between the booths, and the route length, nearest pair first; verify the borders render and the 124 m TOULOUSE-SUD pair sorts above a 374 km one — verified: three bordered tables, both gares with names and osm.org links, straight-line and route distance, nearest first — 50 m AUMALE sorted above 389 km
- [x] 7.1 Report pairs routed, rejected, priced, already known, requests made, and elapsed time; verify the counts sum to the grid size — verified: 234 651 rejected + 21 900 priced + 29 findings = 256 580 routed
- [x] 7.2 Report each source booth whose every target was rejected, using the bordered `table` helper the other steps print with; verify the output renders with the same borders as step 6's reports — verified: the run named 5 source booths that reached no target, in the bordered table

## 8. Pipeline integration

- [x] 8.1 Add `build_vinci_direct_prices.py` to the `COPY` line and the `$(BUILDER_STAMP)` prerequisites in `builder/Dockerfile` and the `Makefile`; verify `docker compose build builder` succeeds and the script is present in the image
- [x] 8.2 Add a phony, always-executing `build_vinci_direct_prices` target guarded by `guard-osrm-path`, `guard-ulys-key`, and `guard-ulys-passage-date`, bringing up `osrm-optimal` first; verify each guard fails with a message naming its variable before any pair is routed
- [x] 8.3 Add the step to the `all` target; verify the order — `make -n all` runs build_vinci_toll_booths, build_vinci_prices, build_booth_sides, build_vinci_direct_prices in that sequence. The step now follows build_booth_sides rather than build_vinci_prices, per `label-bidirectional-booth-sides`. The no-request half is blocked with 6.3
- [x] 8.4 Verify the step fails with a message naming the unreachable routing service when `osrm-optimal` is stopped, before any rate request is issued
- [x] 8.5 Add the rejection database to `data/`'s ignore rules alongside the other regenerable intermediates, after confirming with the maintainer whether it should be committed

## 9. Full run

- [x] 9.1 Verify the price file grows only in `prices` mappings of `enter` and `bidirectional` groups, and that step 6 accepts the result — checked after both full runs: 0 groups carry prices with any other type, 0 `exit` entries carry anything but `type`, and step 6 re-ran with 0 outstanding and no contradiction. Superseded the `--limit` sample
- [x] 9.2 Run the step to completion under `--survey` — done twice. First: 256 580 routed, 234 651 rejected, 21 900 priced, 21 921 requests, 366.8 min, against a projection of 263 659 / ~240 800 / ~22 800 and 7.2 h. Second, after the side rule: 242 623 routed, 238 158 rejected (238 141 by a booth, 17 by a wrong side), 4 130 priced, 71.4 min
- [x] 9.3 Read the survey report and act on each finding — 29 in the first run. The 4 `no tariff` were interchanges under two gare codes (TOULOUSE-SUD, AUMALE/HAUDRICOURT) and became `prohibited_gare_pairs` entries. The 17 `unexpected answer` were two-way booths paired as an end they were not acting as, fixed by `apply-booth-sides-to-direct-pricing`; none survived the second run. The 8 `blacklisted route` grew to 335 as nodes were added, and are handled in 6.3
- [x] 9.4 Verify `data/vinci_price.yaml` reloads under step 6's `load_state` without an `Abort` — 1267 booths, 774 routes, 23 251 prices, types 469 enter / 466 exit / 233 passthrough / 52 gantry / 47 bidirectional, matching the inventory's 47 two-way booths
