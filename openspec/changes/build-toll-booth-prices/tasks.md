## 1. Traversal-ordered covers

- [x] 1.1 Change `cover_many` in `builder/build_route_set.py:288` to accumulate hits in traversal order with first-occurrence dedup, keeping an unordered view for the solver; verify a synthetic node sequence with a repeated group yields one entry at its first position
- [x] 1.2 Update the three set consumers — `:685` `uncovered -= covered`, `:512` `greedy_select`, `:773` `union.update` — and verify a full `build_route_set` run reports the same coverage totals as the committed run
- [x] 1.3 Drop the `sorted(cov, key=target_key)` in `write_route_set` at `:579` so `covers` is written in the order it was collected; verify the emitted YAML shape is otherwise unchanged
- [x] 1.4 Run `make update_route_set` and verify the rewritten `data/route_set.yaml` differs from the committed one only in the order of `covers` entries — same routes, same node ids, same `prev_node_id` values
- [x] 1.5 Run `make build_vinci_toll_booths` against the rewritten route set and verify it finds nothing outstanding, issues no request, and reports no unmapped booth
- [x] 1.6 Commit the reordered `data/route_set.yaml`

## 1b. Booth type in the inventory

- [x] 1b.1 In `builder/build_osm_toll_booths.py`, replace `bidirectional: true` with `type: bidirectional` and add `type: gantry` for `highway=toll_gantry` booths, stopping when a booth qualifies as both; verify the regenerated `data/osm_toll_booths.yaml` differs only by that field — 49 entries renamed, 56 gained `gantry`, 1451 untouched, every `latlon` and `parent_id` identical
- [x] 1b.2 Update `builder/build_route_set.py` to read `type: bidirectional`; verify it reports 49 two-way booths and 1344 coverage targets as before
- [x] 1b.3 Re-run `make update_route_set` and verify `data/route_set.yaml` is unchanged, then re-run `make build_vinci_toll_booths` and verify it finds nothing outstanding

## 1c. Node blacklist

- [x] 1c.1 Add a `nodes_blacklist` section to `builder/overrides.py`, validated as a list of OSM node ids; verify a non-list and a non-integer entry are both refused
- [x] 1c.2 Discard any candidate route whose node sequence touches a blacklisted node in `cover_many`, and pass the override file to step 4 from the `Makefile`; verify the count of discarded routes is reported and that an empty count is called out as stale
- [x] 1c.3 Re-run `make update_route_set` and verify the route through the L'Arverne service area is gone, then re-run `make build_vinci_toll_booths` for any replacement routes

## 2. Configuration

- [x] 2.1 Add `ULYS_PASSAGE_DATE` to `.env.example` with a value and a comment on why one date prices the whole file, and add it to the `builder` service `environment:` block in `docker-compose.yml`; verify with `docker compose run --rm builder printenv ULYS_PASSAGE_DATE`
- [x] 2.2 Add a `guard-ulys-passage-date` target to the `Makefile` mirroring `guard-ulys-key`, and verify it fails with a message naming the variable when the value is unset

## 3. Pricing step

- [x] 3.1 Create `builder/build_vinci_prices.py` reading `data/route_set.yaml`, `data/vinci_toll_booth.yaml`, and the override file; verify it reports 781 routes, 1287 covered groups, and the outstanding count without issuing a request
- [x] 3.2 Build the passage list from each route's ordered `covers`, resolving each group to its gare code and splitting the code into `operatorId` and `tollId` as two-character and three-character strings; verify a known route produces the expected codes in the driven order
- [x] 3.3 Implement the skip rule — a route covering an `absent_enter` or `absent_exit` booth is not submitted, an `absent_passthrough` booth is dropped from the passage list — and verify exactly 7 routes are skipped and named
- [x] 3.4 Implement the request with vehicle category 1, payment option 2, and `ULYS_PASSAGE_DATE` on every passage; verify a replay of the sample nine-passage request returns the five documented items
- [x] 3.5 Implement the cursor: advance to the next passage matching `entranceToll.code`, consume it, and require the following passage to match `exitToll.code` when present; verify against the sample that nine passages are consumed by five items
- [x] 3.6 Read gare codes from the response `code` field and verify `operatorId: 5, tollId: 55` is read as `05055` rather than `555`
- [x] 3.7 Parse amounts as decimals and store whole cents; verify `7.80` and `6.80` compare equal to themselves across a write-and-reload cycle
- [x] 3.8 Implement classification — `entranceToll` alone is `passthrough` with a price, both tolls make the entrance `enter` with `prices[exit code]` and the exit `exit` — and verify each against the sample items
- [x] 3.9 Implement the four stop conditions (type change, passthrough price change, pair price change, cursor with no matching passage) and verify each with a synthetic response
- [x] 3.10 Implement the consumed-passage check and verify a synthetic response missing one item reports the unpriced passages and continues
- [x] 3.11 Report any non-empty `comments` with its route and gares, and verify with a synthetic response
- [x] 3.12 Copy `absent_passthrough` prices from the override file into the output, and verify `1391610490` at 1.4, `12288199204` at 1.9, and `12752375307` at 1.9 appear while the four unpriced `absent_passthrough` booths do not
- [x] 3.13 Implement the writer for `data/vinci_price.yaml` — `toll_booths` in ascending numeric key order, `prices` in ascending code order, `routes` last — and verify a rewrite from the same state is byte-identical
- [x] 3.14 Implement resume: skip routes already in `routes`, append a route only after its whole response is attributed; verify that interrupting a run and restarting repeats at most one route
- [x] 3.15 Implement one request per second on a single thread with five attempts and exponential backoff; verify exhausted retries stop the step and leave that route absent from `routes`
- [x] 3.16 Report every covered group with no entry at the end of a complete run, with the reason, and exit 0; verify the run with nothing outstanding still produces the report
- [x] 3.17 Read `type` from `data/osm_toll_booths.yaml` and record such a group under that same type — `bidirectional` or `gantry` — carrying `price`, `prices`, or both; verify a typed group reported as an entrance and then as an exit does not stop the step, that a gantry priced 1.90 paired and 0.90 alone carries both, and that an untyped group changing role still stops the step
- [x] 3.18 Treat a returned item with no amount as the service reporting no tariff rather than as a malformed response: consume its passages so the cursor stays in step, record nothing, report them; verify against the `04210 ORANGE` route where the service prices `04342 -> 04210` and answers `No rate found.` for `04218`

## 4. Pipeline wiring

- [x] 4.1 Add `build_vinci_prices` to the `Makefile` as an always-executing target depending on `guard-ulys-key` and `guard-ulys-passage-date` and the gare mapping output, with no OSRM dependency; verify `make build_vinci_prices` runs it with the `osrm-optimal` service stopped
- [x] 4.2 Add the step to `all` and verify `make all` executes the six steps in order on a complete tree, performing no work and issuing no request
- [x] 4.3 Add `data/vinci_price.yaml` to the tracked deliverables and verify it is not git-ignored

## 5. Full run and verification

- [x] 5.1 Run the step over all 774 submittable routes and record wall-clock time; verify it stays near the 13-minute estimate implied by the one-per-second limit
- [x] 5.2 Report the counts — routes submitted, routes skipped, groups classified `passthrough` / `enter` / `exit` / `bidirectional` / `gantry`, pair prices recorded — and verify the classified groups plus the reported gaps account for all 1287 covered groups
- [x] 5.3 Read what the service returned for the `04210 ORANGE` route where one gare is driven twice, and record the answer in `design.md` under Open Questions
- [x] 5.4 Check which of the 20 operators produced no price and record them; verify each appears in the unpriced-passage report rather than being silently absent
- [x] 5.5 Verify the 6 groups predicted to be unpriced — `143224`, `14790565`, `130221205`, `393881364`, `410650377`, `720736848` — are exactly the ones reported, and that no other group is missing for an unexplained reason
- [x] 5.6 Re-run the completed step and verify it issues no request and exits 0
- [x] 5.7 Commit `data/vinci_price.yaml`
- [x] 5.8 Verify `openspec validate build-toll-booth-prices --strict` passes and every scenario in the three spec deltas has been exercised or explicitly accounted for
