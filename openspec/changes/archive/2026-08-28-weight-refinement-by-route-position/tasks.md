## 1. The ranking

- [x] 1.1 In `french_tolls/refine.py`, invert `waypoints_for` so every stretch is located on the optimal route before any is chosen: compute `start` and `end` for each stretch, swap them when the projection inverts, and carry them through to the placement rather than recomputing them; verify the waypoints produced for a set of stretches shorter than the budget are byte-identical to those the current code produces — **verified as a set, not as a list.** `test_every_stretch_is_taken_when_the_budget_covers_them` asserts the same stretches come back. The list's *order* is the ranking's order, and was so before this change too, so it necessarily moves with the ranking. No consumer depends on it: `www/index.js:172` reads `added` as a membership set, and `_first_pass` re-sorts by position before merging
- [x] 1.2 Rank the stretches by `section["length"] * (1.0 - (start / total) / 2)`, where `total` is `along[-1]`, and take the highest-ranked up to the budget; verify a 40 km stretch beginning 50 km along a 1 000 km route outranks a 60 km stretch beginning 950 km along it — `test_an_earlier_stretch_outranks_a_longer_later_one`, 39 000 against 31 500. Extracted as `_rank` so the weight can be tested without building a route
- [x] 1.3 Fall back to a weight of 1.0 when `total` is zero; verify a degenerate route of one repeated point selects by raw length and does not raise — `test_a_degenerate_route_selects_by_raw_length` and `test_a_route_of_no_length_weighs_nothing_down`
- [x] 1.4 Confirm placement, `at_m`, `skipped_m`, `google_detour_m`, and the merge order are untouched, and that no score is stored; verify the keys of an `added` entry are exactly the four they are today — `test_an_entry_carries_four_keys_and_no_score`, `test_the_waypoint_is_the_midpoint_of_the_bypassed_portion`, `test_a_new_waypoint_is_merged_in_route_order`

## 2. Tests

- [x] 2.1 Add `french_tolls/tests/test_refine.py` covering `waypoints_for` as a pure function against a synthetic straight-line route and hand-built stretches, reaching neither Google nor the database; verify the file runs under `make test` with the rest of the suite — 19 tests. The route runs due east from (0, 0), where the haversine of a segment is exactly `R * dlon`, so its cumulative distances are the round numbers the tests name
- [x] 2.2 Cover the spec's ranking scenarios: an early stretch beating a longer late one, a late stretch three times longer still winning, two stretches at the same position ranked by length, and a budget of two out of seventeen; verify each asserts which stretches were chosen, not merely how many — each asserts on `google_detour_m`, which is unique per stretch. `test_raw_length_would_have_chosen_differently` additionally asserts the old ranking would have picked the other one
- [x] 2.3 Cover the invariants: the waypoint is the midpoint of the bypassed portion, the merged list is in route order, an empty stretch list and a zero budget both return `[]`; verify all pass — the merge is covered through a whole `_first_pass` with `_ask`, `_geometry`, and `db` stubbed, so the corridor measure and the merge run for real against a synthetic Google route that leaves the route between 500 and 520 km
- [x] 2.4 Run `make test`; verify the whole suite passes and the count has risen by the tests added — **66 pass**: the 47 that existed plus the 19 added. The suite was broken at HEAD before this change, in two ways left behind by the archived `name-booths-from-osm` change, and both were repaired here at the user's direction (see 2.5)
- [x] 2.5 Repair the committed test breakage that blocked 2.4 — added scope, agreed with the user rather than absorbed. Two defects, both from `name-booths-from-osm` updating the accounting without updating the tests, and both invisible until the test image was rebuilt:
  - `Booth.name` became a read-only property (`french_tolls/data.py:80`), but `french_tolls/tests/booths.py` still passed `name=` to the constructor. All 25 tests in `test_cost.py` failed on `TypeError`. Fixed to pass `operator_name=`, which is the source that wins where a booth has both. `test_a_booth_with_no_name_is_labelled_by_its_node_id` emptied `name` directly to build a nameless booth; it now empties `operator_name`, because `name` is derived and cannot be set.
  - A `passthrough` or `gantry` carrying no tariff is now counted and not listed, but two tests still expected it in `passages`. `test_a_gantry_or_passthrough_carrying_no_amount` now asserts the crossing is silent and counted; `test_no_unpriceable_passage_is_charged_zero_and_every_reason_is_distinct` now asserts the total is one more than the list. Neither assertion was weakened: both still check that nothing unpriceable is charged and that every listed reason is distinct.

  Left alone and reported instead: `BOOTH_NOT_PRICED` (`french_tolls/tolls.py:26`) is now produced nowhere. It is still exported and still asserted distinct by `test_the_eight_reasons_are_all_different_strings`. Removing a public constant is production code and belongs to whoever owns that change, not to this one

## 3. Cost

- [x] 3.1 Measure how many drift stretches a real journey produces and how long the location step takes for all of them, using Bayeux to Apt and the worst journey in `data/google_routes/`; verify the numbers are recorded here — measured over all 20 stored journeys:

  | journey | points | stretches | budget | locate all | locate budget | `drift_sections` |
  |---|---:|---:|---:|---:|---:|---:|
  | Bayeux → Apt | 15 879 | 17 | 2 | 0.319 s | 0.037 s | 0.552 s |
  | Plouzané → Menton | 26 010 | 9 | 5 | 0.280 s | 0.155 s | 0.839 s |
  | Cogolin → Lannion | 22 263 | 8 | 5 | 0.213 s | 0.133 s | 0.759 s |
  | Dunkerque → Argelès-sur-Mer | 17 576 | 10 | 5 | 0.208 s | 0.104 s | 0.692 s |

  Stretch counts run from 3 to 17, so nothing pathological appears in the corpus. The worst added cost is Bayeux → Apt at **+0.282 s**; every other journey adds less than 0.13 s.

- [x] 3.2 Decide from 3.1 whether `_nearest_index` needs `geometry.SegmentIndex` behind it; verify by stating the measured time and either leaving the linear scan with that measurement as the justification, or replacing it and re-running 2.4 — **the linear scan stays.** The worst case adds 0.282 s to a path that already spends 0.552 s in `drift_sections` on the same journey and two network round trips to Google, and that is bought at most twice per journey. A second index in this module is not worth 0.28 s

## 4. Specs and verification

- [x] 4.1 Run `openspec validate weight-refinement-by-route-position --strict`; verify it reports no errors — valid
- [x] 4.2 Take one real journey through the service with a Google key configured and a stretch count above the budget, and read the refined waypoints; verify the added waypoints sit earlier along the route than the raw-length ranking would have placed them, and that every one of them lies on the optimal route — **done against the stored corpus rather than a live request, which is stronger and free.** `data/google_routes/` already holds Google's route through the original waypoints for 20 real journeys, which is exactly the first pass's input. Both rankings were run over all 20. Two select differently:

  - **Plouzané → Menton**, 9 stretches, budget 5, 1 416 km. Old: 441, 725, 1 024, 1 183, 1 193 km. New: 15, 441, 725, 1 024, 1 183 km. A 2 km detour at 1 193 km is dropped for a 1 km detour at 15 km. Mean position 913 km → 678 km.
  - **Cogolin → Lannion**, 8 stretches, budget 5, 1 257 km. Old: 4, 299, 594, 967, 1 256 km. New: 4, 299, 594, 623, 967 km. A 3 km detour at 1 256 km is dropped for a 2 km detour at 623 km. Mean position 624 km → 497 km.

  Every waypoint in both new sets lies on the optimal route. Bayeux → Apt, despite having 17 stretches against a budget of 2, selects the same two under either ranking: its two dominant detours are large enough that the weight cannot move them.

- [x] 4.3 Confirm nothing outside `waypoints_for` changed; verify `git diff --stat` names only `french_tolls/refine.py`, the new test file, and the change's own artefacts — `git diff --stat -- french_tolls/` names three files:

  ```
  french_tolls/refine.py          | 38 ++++++++++++++++++++++++++++++++++++--
  french_tolls/tests/booths.py    |  5 ++++-
  french_tolls/tests/test_cost.py | 29 ++++++++++++++++++++---------
  ```

  `refine.py` is this change. The two test files are the 2.5 repair, which the user asked for after it blocked 2.4. No production code outside `waypoints_for` and its new `_rank` helper was touched. `french_tolls/tests/test_refine.py` and this change's directory are untracked additions. The other paths in the working tree — the `name-booths-from-osm` deletions, the three modified main specs, and the untracked `french_tolls/db.py` — were all there before this change began
