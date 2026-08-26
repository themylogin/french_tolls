## 1. Publish the passage from step 3

- [x] 1.1 Return the directed neighbours from `booth_groups.group_booths`: build `{booth: (predecessor, successor)}` for the booths named in `one_way`, taken from `GraphBuilder.rev` and `GraphBuilder.fwd` before contraction, choosing deterministically where there is more than one. Verify by printing the pairs for the nine border booths and checking them against the ways in `plazas.osm.pbf`.
- [x] 1.2 Raise a `ValueError` naming the booth when a border-typed booth has no predecessor or no successor. Verify by adding a fabricated border override on a booth that no through-class way reaches and confirming the step stops.
- [x] 1.3 Write `passage: [[lat, lon], [lat, lon]]` in `build_osm_toll_booths.entry()` for border-typed booths only, rounded to 7 decimal places like `latlon`, dumped inline with the existing `LatLon` representer. Verify that no non-border entry gains the key.
- [x] 1.4 Rebuild the inventory with `rm data/osm_toll_booths.yaml && make build_osm_toll_booths` and verify that exactly nine entries carry `passage`, that the rest of the file is unchanged against the previous version, and that a second run is byte-identical.

## 2. Submit the stub in step 5

- [x] 2.1 Add a precision-6 polyline encoder to `build_vinci_toll_booths.py`, the inverse of the existing `decode_polyline`. Verify by round-tripping the nine legs and by reproducing the two encodings recorded during the probe.
- [x] 2.2 Read `passage` from the inventory in `load_inventory`, alongside the positions it already reads. Verify that the nine booths carry one and that no other booth does.
- [x] 2.3 Extend the override drift check to stop when a border-typed booth carries no `passage`, alongside the existing `ignored` and `forced` clauses, and to print the same rebuild command. Verify by adding a border override without rebuilding the inventory and confirming the step stops with that message.
- [x] 2.4 Build the stub loop: for each border-typed booth absent from `done_pairs` as `(booth, booth)`, form the three-point leg, encode it, submit it through the existing `Placemarks` client, and pass the response to `process_route` with a synthetic route `{"from": booth, "to": booth, "covers": [{"node_id": booth}]}`. Verify that the eight unresolved booths record `04390`, `04345`, `06028`, `02001`, and `02057` as the probe reported.
- [x] 2.5 Stop the run and name the booth when a stub returns an empty placemark list, rather than treating it as a route with no tolls. Verify by submitting a stub built from a passage that does not cross the booth and confirming the step stops.
- [x] 2.6 Record `(booth, booth)` in `done` only after the response has been processed in full, and write state as the route loop does. Verify that interrupting mid-stub leaves that booth absent from `routes`.

## 3. Close the accounting

- [x] 3.1 Add the end-of-run check that every border-typed booth has a gare, running on every invocation including one with nothing outstanding, and failing with the booth named. Verify by deleting one border booth's entry from `data/vinci_toll_booth.yaml` and re-running with every route processed.
- [x] 3.2 Verify the closing invariant on a complete run: every group representative in `data/osm_toll_booths.yaml` either carries a gare in `data/vinci_toll_booth.yaml` or is typed `absent_*` in the override file. Expect 1295 = 1283 + 12.

## 4. Correct the override file

- [x] 4.1 Correct the comment above `1154852457` from `# Saint-Michel-Barrière` to name the operator's gare `02057 ST MICHEL-MODANE`, and note that the OSM `name` and `operator:ref` on that node disagree with the operator. Verify the file still loads through `overrides.load`.
- [x] 4.2 Update the `overrides.py` module docstring and the comment above `BORDER`, which currently say the border types exist only for a way tagged `oneway=no`. Seven of the nine booths are already one-way in the extract and are stated for the other reason: no route reaches them. Verify by reading the comment against the nine entries.

## 5. End to end

- [x] 5.1 Run `make build_vinci_toll_booths` twice in succession and verify the second run issues no request and leaves `data/vinci_toll_booth.yaml` byte-identical.
- [x] 5.2 Verify `data/route_set.yaml` is unchanged by the whole change, and that the double-paid check and the covered-booth check still pass.
