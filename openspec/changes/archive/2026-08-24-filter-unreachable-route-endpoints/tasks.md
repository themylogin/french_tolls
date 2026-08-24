## 1. Persist the no-access road classes

- [x] 1.1 Add a second `osmium tags-filter` pass to `build_osm_toll_booths.py` producing `data/no_access_ways.osm.pbf` from `w/highway=motorway,motorway_link,trunk_link`, reusing the file when it already exists; verify by deleting `data/osm_toll_booths.yaml`, running step 3, and confirming the new file appears and the second run prints a reuse line rather than re-filtering.
- [x] 1.2 Wire `--no-access` through the step 3 argument parser and the Makefile recipe; verify `make build_osm_toll_booths` completes and `data/no_access_ways.osm.pbf` is listed among its outputs.

## 2. Measure endpoint reachability

- [x] 2.1 Add a reachability sweep to `build_route_set.py` that routes every candidate to its nearest `place=city` and records how far from the candidate the trip actually starts, then reads the segment class from a nearest-query at that start; verify node 5907006903 records 323 m rather than the 26.6 m its closest segment reports.
- [x] 2.2 Load the node ids of `data/no_access_ways.osm.pbf` into a set and mark each candidate whose snapped segment belongs to it; verify that node 2206384711 (Kirschbaeumel) is marked and node 6268094819 (Gros Bois) is not.
- [x] 2.3 Persist the sweep to `data/endpoint_snap.json` holding the distance and the no-access flag per candidate, and reuse it when present; verify a second run of step 4 issues no sweep and starts searching within a minute.
- [x] 2.5 Run the sweep across processes rather than threads, since decoding two million JSON responses is bound by the interpreter lock; verify throughput of at least 4000/s against the ~610/s a single process reaches.
- [x] 2.4 Apply `MAX_SNAP_M = 50.0` and the no-access flag when the record is read, as a single named constant; verify the eligible count printed by step 4 is near 47 % of 1 024 663.

## 3. Apply eligibility to the search

- [x] 3.1 Filter `PlaceCollector` output through the eligibility test before `PlaceIndex` is built and before `dispersed_places` runs; verify the wave A seed list contains no node that fails the test.
- [x] 3.2 Extend `load_existing` to drop a pair whose endpoints are no longer eligible; verify that loading the current `data/route_set.yaml` under the new rule keeps 234 of its 787 routes.
- [x] 3.3 Verify each of the nine reported routes loses at least one endpoint. Not all sixteen endpoints are rejected: Gros Bois, Le Mazet, and Les Girasols are reachable places whose partner is the fault, and dropping one end is enough to remove the route.

## 4. Assert no route pays one gare twice

- [x] 4.1 Add the duplicate-gare check to `build_vinci_toll_booths.py`, running on every invocation including one with no outstanding routes, exempting booths with no gare recorded; verify it reports 9 violations against the original `data/route_set.yaml` and `data/vinci_toll_booth.yaml`.
- [x] 4.3 Accept a `duplicate_gares` list of operator numbers in the override file, normalised to strings so an unquoted `04210` keeps its leading zero, and skip those gares in the check; verify gare 04210 is exempted and that an exemption no route exercises is reported without failing the run.
- [x] 4.4 Reject an unknown top-level section in the override file; verify a mistyped section name stops the step instead of dropping its contents silently.
- [x] 4.2 Make the check exit non-zero and tabulate route endpoints, gare number and name, and each booth's node page; verify the table names AUXERRE SUD, CHALONS MOURMELON, HOCHFELDEN OUEST, USSEL EST, LA NEUVILLETTE, ORANGE, ITTENHEIM GARE, VIERZON-EST, and ARTENAY.

## 5. Regenerate and verify

- [x] 5.1 Run step 3 to produce the no-access extract, then delete `data/route_set.yaml` and run step 4 to completion; verify the run ends with a coverage summary and writes `data/uncovered_booths.json`.
- [x] 5.2 Compare the new uncovered set against the 1340 targets the previous route set covered; verify no target regressed, and if any did, raise `MAX_SNAP_M` one step (50 → 100 → 200), re-run, and record the value that succeeded in design.md.
- [x] 5.3 Run step 5 to completion; verify it exits zero, which means no route pays one gare twice except where the override says it legitimately does.
- [x] 5.4 Re-run the reported nine endpoint pairs against OSRM and verify none of them is present in the new route set.
