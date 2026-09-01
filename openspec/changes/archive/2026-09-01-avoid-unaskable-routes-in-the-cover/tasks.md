## 1. One definition of "blocking"

- [x] 1.1 Add `BLOCKING = ("absent_enter", "absent_exit")` to `builder/overrides.py` beside `ABSENT`, `BORDER` and `PRICED_TYPES`, and verify `python3 -c "import overrides; print(overrides.BLOCKING)"` runs from `builder/`
- [x] 1.2 Add an `Overrides` accessor that returns the set of booth ids typed with one of those values, and verify it against `data/osm_toll_booths_overrides.yaml`: it returns exactly `{16567653, 28128388, 469982848, 14040228495, 1838205657}`
- [x] 1.3 Replace `BLOCKING_ABSENT` in `builder/build_vinci_prices.py:123` with the import, keeping `passages_for` unchanged, and verify `build_vinci_prices.py --help` still runs
- [x] 1.4 Correct the header comment at `builder/overrides.py:47` — an `absent_*` booth no longer unconditionally "stays in the route set", and the enter/exit suffix is no longer something "nothing consumes yet" — and verify the comment names which suffix has which effect

## 2. The route search

- [x] 2.1 Pass the blocking set from the already-loaded `ov` at `builder/build_route_set.py:889` into `coverage_targets`, and exclude those booths from the returned targets; verify the run prints a target total five lower than before against the current inventory
- [x] 2.2 Give `cover_many` the blocking set and omit any pair whose computed `covers` intersects it, testing the resolved group representatives; verify with the unit test in 3.2
- [x] 2.3 Report the omission where a resumed route is dropped for it, on its own line, separate from the existing "no longer cover anything" count; verify the next `update_route_set` run prints "dropped 7" against the current route set
- [x] 2.4 Confirm the blocking set reaches all four `cover_many` call sites (`:987`, `:1011`, `:1047`, `:1079`) and verify by grep that no call omits the argument

## 3. Tests

- [x] 3.1 Create `builder/tests/`, add a `builder-tests` service to `docker-compose.yml`, and run it from `make test`; verify both suites run. The builder image is separate rather than folded into the `tests` service because `build_route_set` imports `osmium` and `requests`, which the application image does not carry.
- [x] 3.2 Test `cover_many` with an `Osrm` subclass whose `route_nodes` returns canned node lists: a pair crossing a blocking booth is absent from the result, a pair crossing an `absent_passthrough` booth is present, and the present pair's `covers` still lists that booth; verify `make test` passes
- [x] 3.3 Test that `coverage_targets` omits a booth typed `absent_enter` and keeps one typed `absent_passthrough`; verify `make test` passes
- [x] 3.4 Test that the blocking-set accessor reads `absent_enter` and `absent_exit` and ignores `absent_passthrough`, `ignore` and the border types; verify `make test` passes
- [x] 3.5 Test that an alias resolving onto a blocking representative withholds its route, so the search and the pricing step test the same domain of ids

## 4. Regenerate the data

Do not run `make clean`. It drops `$(ROUTE_SET)` and `$(PRICES)` together and costs roughly 24,000 Ulys requests to relearn what is already on disk.

Run in `french_tolls3`, which still has a routing graph — `clean-osrm` removed the one in `french_tolls2` during the deployment test. 4.4 and 4.5 spend Ulys requests and are not started.

- [x] 4.1 Run `make update_route_set` and verify stdout reports 7 resumed routes dropped as unaskable and a lower target total — `1342 -> 1337` targets, `kept 779, dropped 7 that cross a booth the operator does not carry`, waves added 8, final 787 routes
- [x] 4.2 Diff `data/route_set.yaml` and verify no remaining route's `covers` contains any of the five blocking booths — 0 of 787
- [x] 4.3 Diff `data/uncovered_booths.json` booth by booth and verify the five blocking booths have left it; record any freed booth that has entered it — unchanged at 8, all border booths the direct pricing step handles. The five blocking booths were covered before and are not targets now, so neither list holds them.
- [x] 4.3a Verify no booth lost askable coverage: booths with a gare on a route nothing blocks went 1268 -> 1275, none lost, the 7 gained being exactly the 7 that were stranded
- [x] 4.4 Run `build_vinci_toll_booths` — ran, 590 requests, 9.8 min, and the mapping did not change: 1283 booth records before and after, none added, removed or edited. Only the `routes:` provenance list grew, 1570 -> 2160.

  **The task as written was wrong, and so was its cost estimate.** It assumed the step would ask only about the 8 routes 4.1 added. In the tree it ran in, 590 of the 787 routes were outstanding, because `route_set.yaml` had been regenerated without steps 5 and 6 being re-run behind it. 582 of the 590 requests were pre-existing backlog. The lesson for the next tree: measure the outstanding count before quoting a cost. It is `route_set.yaml`'s pairs minus the `routes:` list of the consuming file.

- [ ] 4.5 Run `build_vinci_prices` and verify it reports zero routes skipped as not askable, and that the entry count did not fall

  **Not run, by decision.** 631 of 787 routes are outstanding in that tree — about 631 Ulys requests and 11 minutes, against 7 routes' worth of work that belongs to this change. The backlog is not this change's to pay off.

- [ ] 4.6 Run `build_toll_extent`, `build_segment_weights` and `apply_segment_weights`, and verify the segment weights acceptance check passes — blocked on 4.5

## 5. Verify the change did what it claims

- [x] 5.1 Confirm the seven booths stranded before the change — 393881364, 720736848, 747145320, 4001140435, 4001140454, 4365283548, 4802326993 — all seven are now covered by an askable route. Whether each carries a price depends on 4.5, which was not run.
- [ ] 5.2 Verify `data/vinci_price.yaml` gained entries and lost none, which `load_state` guarantees on the update path — blocked on 4.5
- [x] 5.3 Run `make test` and verify the whole suite passes — 132 + 13
- [x] 5.4 Run `openspec validate avoid-unaskable-routes-in-the-cover --strict` and verify it reports no errors
- [x] 5.5 Re-run `make update_route_set` and verify it is idempotent — `kept 787`, zero routes added in every wave, 1329/1337 covered, unchanged
