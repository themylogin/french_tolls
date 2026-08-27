## 1. Publish the outgoing arcs from step 3

- [x] 1.1 Collect the outgoing arcs of every booth node in `booth_groups.GraphBuilder`, over the classes the car profile gives a speed to rather than the through-road classes. The handler returns early on class today, so the collection has to run before that return and stay guarded to booth nodes. Verified: the step prints `1613 arc(s) leaving 1556 booth(s)`, which is the wider set — the through classes alone would give 1 610.
- [x] 1.2 Return the map from `group_booths` and write it as `onward_nodes` in `build_osm_toll_booths.entry`, on representatives and aliases alike, in ascending numeric key order. The field maps each node to its position, not just its id: the node beyond a booth appears nowhere else in the inventory and no service translates an id into a point, so a consumer routing across the arc would otherwise be stuck. Verified: the YAML parses and all 1 556 entries carry the field.
- [x] 1.3 Stop and name the booth when `onward_nodes` would be empty for a retained booth. Split out as `booth_groups.onward_nodes` so the guard is testable on its own. Verified: it refuses a booth with no arc out and a neighbour the extract gives no position for, and accepts the real inventory's 1 613 arcs.
- [x] 1.4 Regenerate `data/osm_toll_booths.yaml` and verify the diff shows added `onward_nodes` lines and nothing else. Verified: 3 169 lines added, 0 removed, being 1 556 `onward_nodes:` headers and 1 613 arcs, with nothing unaccounted for.
- [x] 1.5 Run step 3 twice against the same extract and verify the two inventories are byte-identical.
- [x] 1.6 Verify the added field breaks no consumer. Done by running each loader that reads the inventory against the old file and the new one and comparing what it returns, rather than by re-running steps 4, 7 and 8 — step 8 would spend operator requests to prove a parsing point. `build_vinci_direct_prices.load_inventory`, `build_booth_sides.load_inventory` and the view `build_route_set` takes all return identical results.

## 2. Read the flat charges in step 10

- [x] 2.1 Load the flat-charge booths — `type: passthrough` carrying `price` — resolve each to its lane nodes through the inventory's aliases, and enumerate its arcs from `onward_nodes`. Verified: 239 groups, 286 lane nodes, 288 arcs.
- [x] 2.2 Stop and name the booth when a flat-charge booth's entry carries no `onward_nodes`. Verified against an inventory with the field removed from one such booth.
- [x] 2.3 Measure each arc with a route between its two node coordinates, snapping radius held to a few metres, taking the annotated segment where the arc's node pair appears. Verified: all 288 measure this way. The exploration put 287 because it demanded the arc be the *last* segment of the route; taking it wherever it appears and checking its length instead covers ST MICHEL-MODANE too.
- [x] 2.4 Fall back for an arc the tight route misses to a route that drives past it from a standoff either side, taking the arc from the interior of the annotation. Implemented and kept. Verified: no arc needs it today — the run reports `measured by radius: 288` — so it is a guard against a future extract rather than a path in use.
- [x] 2.5 Reject a measurement whose routed length disagrees with the distance between the arc's two nodes by more than a metre. Verified: all 288 arcs pass it.
- [x] 2.6 Stop and name the group, its tariff and the arc when any arc of a flat-charge group is left unmeasured. Implemented in `measure_flat`, which raises before any file is written.

## 3. Merge the flat charges into the row set

- [x] 3.1 Add `flat_charge_eur` to the target weight alongside `segment_price_eur`, so a segment that both leaves a barrier and carries samples adds both terms. Verified: a 2.00 EUR barrier arc also carrying 0.30 EUR of samples charges 2.30 EUR, adding 414.0 weight to its own 4.0.
- [x] 3.2 Count the segments carrying both and report the count. Verified: the run reports `249454 sampled, 288 flat, 0 both`.
- [x] 3.3 Widen the `rate` column's precision to nine places so the weight `osrm-customize` derives is within 0.01% of the target weight. Verified at the smallest rate the file holds, 0.000642661 at ENTREE TUNNEL DU FREJUS: nine places cost 0.0000778%, six would have cost 0.0778%. The report's flat records were widened to six places for the same reason — at three an arc 1.9 m long no longer reproduces its own row.
- [x] 3.4 Write the merged file and verify it holds 288 rows more than the 249 454 it holds now, still sorted by node pair, with no blank line anywhere. Verified: 249 742 rows, 288 added, 0 removed, sorted, no blank line. The shared rows keep their speed exactly and their rate moves by at most 1.7e-07 relative, which is the six-to-nine-place reformatting.
- [x] 3.5 Verify a rerun from the same inputs is byte-identical. Verified.

## 4. Report the flat charges

- [x] 4.1 Add a report section naming each flat-charge group with its gare code, the operator's name, its tariff, each arc written for it, and that arc's length, class, own weight and rate. Verified: VIADUC DE MILLAU appears as two groups of one arc each, ILE DE RE as one, ENTREE TUNNEL DU FREJUS as six and MONT-BLANC as four.
- [x] 4.2 Report the totals: groups written, arcs written, and the lowest and highest rate written for a flat charge. Verified: 239 groups, 288 arcs, rates 0.000642661 to 1.453938462 against the sampled 1.09 to 27.52.
- [x] 4.3 Carry the same per-barrier record into `data/segment_weights_report.json`. Verified: 288 records over 239 groups, all measured by the tight route, class counts matching the extract.

## 5. Extend the acceptance check

- [x] 5.1 Route every flat-charge arc on both graphs in `--verify` and require the weight difference to equal that booth's tariff at the wage within 1%, or one weight unit, whichever is larger. Verified after the rebuild: all 288 pass, worst disagreement 0.00 weight units. That retires the open question about the new rate regime — `osrm-customize` neither clamped a rate nor failed to match a row.
- [x] 5.2 Stop and name the booth, its tariff and the arc when one arc's weight difference is outside tolerance or nil. Verified by pointing both routers at the untouched graph, which is what a clamped rate, a rounded-away rate or an unmatched row would look like: the check names every arc and refuses.
- [x] 5.3 Verify the existing fixed-pair check still passes: LE PERTHUS to BEZIERS-OUEST, +2314.1 weight against +2610.0 expected, inside the 20% tolerance, durations equal at 3688.7 s. The spec records +2173.4 from an earlier state of `data/vinci_price.yaml`, which has since been edited; the shared rows of the segment file moved by at most 1.7e-07 relative in this change, so the difference is not from here.

## 6. Rebuild both graphs and verify end to end

- [x] 6.1 Run `make build_segment_weights` and verify it completes, reports 239 barriers and writes the file.
- [x] 6.2 Run `make apply_segment_weights` and verify the acceptance check passes, per-arc cases included.
- [x] 6.3 Verify a barrier with no alternative is charged in full. Le Havre to Honfleur across PONT DE NORMANDIE is the case that holds: the same road on both graphs, +1 062.0 weight for a 5.90 EUR tariff, durations equal. The task named La Rochelle to Saint-Martin-de-Ré, and that premise was wrong — see 6.7.
- [x] 6.4 Verify the other barrier journeys are no longer free. All six read +0.0 before this change and none does now: Clermont-Ferrand to Béziers +812.3 on a new road, Rueil to Vélizy +140.6 on a new road, Vélizy to Rueil +430.3, Nantes to Angers +1 679.2 and Angers to Nantes +1 698.6, both of which now go by two ticket booths instead of the barrier.
- [x] 6.5 Verify the ticket network is untouched: Toulouse to Bordeaux still differs by exactly +4 152.0, and an untolled 143.0 km Brittany route reads weight 7 225.6 and duration 120.0 min on both graphs, to the last digit.
- [x] 6.6 Verify durations did not move. On every journey where both graphs return the same road the duration difference is +0.00 s: PONT DE NORMANDIE, Toulouse to Bordeaux and the Brittany control. Where the toll-weighted graph picks a different road the duration moves because the road is different, which is the point of the weighting.

- [x] 6.7 Record what the survey found rather than correct it in code. Routing past each barrier on both graphs, 98 arcs pay in full, 13 have a way round, and 177 probes are unusable because the dead-reckoned standoff does not land on the right road. ILE DE RE is the clearest: the plaza's other lanes carry no `barrier=toll_booth` node, so the inventory holds one lane of a plaza that has several, and the toll-weighted graph reaches the island by way 38108339 for 184.1 weight instead of 2 880. That is a missing booth in the extract, not a missing row in the file, and the fix belongs in OSM.

## 7. State a booth the extract does not tag

- [x] 7.1 Add a `missing_toll_booth` section to `builder/overrides.py`: a list of OSM node ids, carried on `Overrides`, counted in the summary. Verified: the file parses and reports `1 booth(s) the extract does not tag`.
- [x] 7.2 Mirror the existing stale-override check — a node under `toll_booths` must be a booth in the extract, a node under `missing_toll_booth` must not. Verified both directions in isolation.
- [x] 7.3 Add `booth_groups.locate` to find a stated node's position on a drivable way in the carved plaza extract, and stop naming any node it cannot find. The filtered extract cannot supply the position: it keeps only nodes already tagged as a booth or a place.
- [x] 7.4 Collect the stated nodes as booths in `build_osm_toll_booths` after the overrides load and before classification, so classification, grouping and the inventory treat them as ordinary booths. Verified: node 13048100170 became an alias of group 1116803670 with `onward_nodes {7714272796}`, and no group was added or removed.
- [x] 7.5 Verify the plaza then costs the same by either lane. Both Tonnay-Charente arcs `1116803670 -> 7714272796` and `13048100170 -> 7714272796` now charge 126.0 of 126.0 weight, where the second lane charged nothing before.

## 8. Rebuild against the corrected data

- [x] 8.1 Re-run `setup_osrm` after the Ile de Re blacklist entry. Verified: `3 node(s) made impassable: 675137755, 980135734, 11531447312`. The first attempt was OOM-killed at 30% of `osrm-extract` because other work was running alongside it; the second, with both routers stopped, succeeded.
- [x] 8.2 Re-run `build_osm_toll_booths`, `build_booth_sides`, `build_segment_weights` and `apply_segment_weights`. Verified: 1295 groups unchanged, 262 aliases, `bidirectional_booth_sides.yaml` byte-identical, 249 743 CSV rows, 289 flat arcs, 24 unusable pairs and journey error 3.5% / 13.1% all unchanged, acceptance check passing with worst arc disagreement 0.00.
- [x] 8.3 Verify the two fixes and check nothing else opened up. ILE DE RE now pays 16.00 of 16.00 on the same road; both Tonnay lanes pay 0.70 of 0.70. Over all 289 arcs: 236 paid in full, 5 get past for less, 48 probes unusable — the same five as before, four of them Marseille tunnel routes 6 km across the city, and ANCENIS, whose result flips on a sub-metre change of start point.
- [x] 8.4 Record what was deliberately not re-run: `build_route_set` keeps the routes it has and would search for nothing, since no group is new; `build_toll_extent` keeps the extents it has. Both would need operator requests to redo, and step 10's own diagnostics came back unchanged.

## 9. Tidy up

- [x] 9.1 Delete the exploration probes and the verification scripts under `data/_*.py`, and verify nothing in `builder/` imports them.
