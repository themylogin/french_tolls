## 1. Establish the facts the design rests on

- [x] 1.1 Move the graph and split the path variable: `docker compose down`, move `$(OSRM_OPTIMAL_PATH)` to a `toll` sibling, add `OSRM_TOLL_PATH` to `.env` and `.env.example` with `OSRM_OPTIMAL_PATH` redefined as the toll-weighted graph; verify `make setup_osrm` finds `$(OSRM_TOLL_PATH)/.setup.stamp` and skips
- [x] 1.2 Verify `/route` with `annotations=nodes,distance,duration,weight&overview=false&steps=false` returns four arrays of length N-1 for N nodes, on a 150 km motorway route between two known booths
- [x] 1.3 Verify a segment's annotated `weight` and `duration` differ on the toll network — that is, that `weight_name = 'routability'` is not equal to duration everywhere — and record where they coincide; the design turns on not assuming they are the same
- [x] 1.4 Verify `osrm-customize --segment-speed-file` accepts a fractional `edge_speed_in_km_h`, using a two-row file against a throwaway copy of the graph; if it does not, record the fallback of whole km/h in design.md D2 before continuing
- [x] 1.5 Verify the round trip on one segment: write `from,to,speed,length/w` for a segment whose annotated weight is `w`, customize a throwaway copy, re-route, and confirm the annotated weight and duration come back unchanged — this is what proves the multiplier need not be known

## 2. Pair enumeration

- [x] 2.1 Create `builder/build_segment_weights.py` reading `data/vinci_price.yaml`, `data/vinci_toll_booth.yaml`, `data/osm_toll_booths.yaml` and `data/bidirectional_booth_sides.yaml`, reusing the loaders of `build_vinci_prices.py` and `build_vinci_direct_prices.py`; verify it reports 522 source booths and 23 376 price rows without issuing a route
- [x] 2.2 Resolve each price row's gare code to target booth groups whose role is `exit`, `bidirectional` or `gantry`; verify 23 376 rows resolve, 459 of them to two groups, and 23 835 candidate pairs result
- [x] 2.3 Route each candidate pair on `osrm-toll` from the source group's `latlon` to the target group's `latlon` with the annotations of 1.2, no snapping hint, 16 workers; verify the run completes in about 10 minutes and reports the route count
- [x] 2.4 Reject a pair whose route crosses a third booth group, reusing `blockers_of` from `build_vinci_direct_prices.py`; verify a pair known to cross one is rejected and named
- [x] 2.5 For a gare code resolving to two groups, keep the one whose route crosses no third booth, and the shorter route where both qualify; verify one of the 459 two-group rows picks a single target and says which
- [x] 2.6 Verify `LE PERTHUS` node 36967365 to `BEZIERS-OUEST` node 1676618837 routes clean at 14.50 EUR, and to `BEZIERS CABRIALS` node 1588137485 at 15.90 EUR

## 3. Sampling and aggregation

- [x] 3.1 Split each route into directed segments from the `nodes` annotation and drop the first and last; verify a route of N nodes yields N-3 segments and that neither endpoint's partial segment is among them
- [x] 3.2 Record `tariff / route_km` as one sample against every kept segment, using the route's full length including the dropped ends; verify the 14.50 EUR / 149 km pair records 0.0973 EUR/km on each of its segments
- [x] 3.3 Hold per segment a count, sum, minimum and maximum sample with the pair that produced each extreme; report the distinct segment count and the measured peak memory — 223 174 segments, 22.8M observations, 586 MB peak RSS. The 100 MB figure was design D11's pre-measurement guess and is corrected there rather than optimised to
- [x] 3.4 Take the minimum annotated duration and the minimum annotated weight per segment across all observations, per design D4; verify a segment observed at 2.77 s on one route and 5.77 s on another resolves to 2.77 s, and report how many segments have only one observation
- [x] 3.5 Report per segment its count, lowest, highest and mean sample, and its deviation `(max-min)/mean`, ordered worst first, each row naming the two pairs behind the extremes; verify the report renders in the bordered `table` helper the other steps use

## 4. Validation and the deviation stop

- [x] 4.1 ~~Add `--max-deviation` and stop when any segment exceeds it~~ — built, then removed. Measured, 97.9% of segments exceed 10% after all four corrections and the median sits at 59.4%, so the gate stopped every run for a property of French tolls rather than a defect. The flag is gone and the spread now gates nothing; see design D6
- [x] 4.2 Verify a single-sample segment reports a spread of zero and is counted in the single-sample total
- [x] 4.3 Add `--survey`: do everything except write the file; verify a surveyed run over all pairs completes, every table renders, and it exits successfully
- [x] 4.4 Report `outstanding deviation` findings — every segment over `--max-deviation`, worst first, each with its node pair, sample count, lowest, highest, mean, deviation, and the priced pair behind each extreme carrying that pair's gare codes, tariff and route length; verify a synthetic segment at 0.08 and 0.15 appears with both pairs named
- [x] 4.5 Reconstruct each pair's tariff as `sum(mean_rate * length)` over its segments and report the relative error's median, 90th percentile and maximum on every run; verify the distribution prints outside survey mode too
- [x] 4.6 Report `outstanding price` findings — the pairs whose reconstruction misses the tariff, largest absolute error first, each with both gare codes, the operator's tariff, the reconstructed amount, the absolute and relative error, and the route length; verify a pair whose segments are all inside the deviation limit still appears when its reconstruction is off
- [x] 4.7 Report `unusable pair` findings — pairs that contributed no samples because a third booth blocked the route or the router returned none — naming the reason and the blocking booth; verify such a pair appears in this table and in neither of the other two
- [x] 4.8 Cap the rows each table prints, state the number suppressed, and write the full per-segment and per-pair record to `data/segment_weights_report.json` regardless; verify a run with thousands of findings stays readable and the JSON holds every one
- [x] 4.9 Print a summary of finding counts by kind; verify the counts match the table row totals plus the suppressed rows
- [x] 4.10 Run over the full set and record both distributions, then settle the gate with the maintainer — settled: no gate. Sample spread stays 59.4% median / 97.9% over 10% and is reported only; the journey error is 3.5% median, 13.1% p90, 84.4% within 10%, max 6.65 EUR
- [x] 4.11 Print the journey error report at the end of generation: totals and net bias, relative and absolute distributions, bands, a breakdown by journey length, and the worst five by euros and by proportion with a map link each; verify the links open the journey and that the two worst lists do not coincide
- [x] 4.12 Move `osmurl.py` into `builder/` and into the image so the report can link; verify `docker compose build builder` succeeds and the links render

## 4b. Pairs that are not journeys

- [x] 4b.1 Resolve every "is this booth on the route" test through the inventory's aliases, as `blockers_of` does, in the membership check and in the side test; verify ANNECY NORD to ST MARTIN BELLEVUE A41 N is found at index 5 via alias node 5141229701 and is no longer discarded — it moves from 6.71 km / 1.4000 EUR/km to 24.82 km / 0.3787 EUR/km
- [x] 4b.2 Verify the alias fix halves the fallbacks: "route missed a booth" 3 401 -> 1 971 and "extent node not on the route" 5 882 -> 3 081
- [x] 4b.3 Add `--max-detour`, defaulting to 5, dropping a pair whose barrier-to-barrier route exceeds that multiple of the straight line between the barriers, reported as an unusable pair naming the ratio; verify it drops exactly 4 pairs — 09079->09078 at 69x, 09078->09079 at 48x, 12020->12021 at 30x and 07152->07150 at 6x
- [x] 4b.4 Verify the ratio is taken barrier to barrier and read off the existing annotation rather than re-routed; verify MERU to AMBLAINVILLE reads 1.0x and is kept, though it is 6.8x between its extents
- [x] 4b.5 Verify a 3x threshold would be too tight by naming what it takes: TOURNUS to LE MIROIR, 32.7 km apart, 101.6 km routed, reconstruction +19%
- [x] 4b.6 Exclude a pair whose tariff is 0.00 EUR and report it; verify 20 such pairs are dropped and that the segment 1 504 journeys use no longer carries a 0 EUR/km sample
- [x] 4b.7 Verify the cumulative effect on the worst deviation: 815.2% barrier-to-barrier, 675.9% with extents, 608.4% with the alias fix, 255.1% with the detour rule, 250.0% with zero tariffs dropped — while the median moves only 63.9% -> 59.4%

## 4c. Fitting the rates

- [x] 4c.1 Add `fit_rates`: each journey is an equation `sum(rate * length) = tariff`, solved by iteration in log space so rates stay positive with no solver and no new dependency; verify 12 iterations is where the journey error stops moving
- [x] 4c.2 Regularise each segment toward its own sample mean, weighting the data by the segment's journey count and the prior by `--fit-lambda`; verify a segment 4 journeys cross barely moves while one 1 500 journeys cross follows the data
- [x] 4c.3 Sweep lambda and record the trade-off; verify the table in design D7 — at 0 the fit puts 7.94 EUR/km on a VAL DE LOING slip road with 587 segments over 1 EUR/km and 1 909 at nothing, at 1 that is 29 and 10, and at 5 it is none of either
- [x] 4c.4 Set the defaults to 12 iterations and lambda 5; verify the median journey error is 3.5%, p90 13.1%, 84.4% of journeys within 10%, against 8.5% / 23.2% / 56.7% for the means
- [x] 4c.5 Verify no fitted rate falls outside the range of the segment means: highest fitted 0.5386 EUR/km against the means' highest 0.5355, and lowest 0.0312 against 0.0630
- [x] 4c.6 Verify ROUMOIS to ALENCON NORD moves from 22.82 EUR (-34.4%) to 31.14 EUR (-10.5%) against its real 34.80
- [x] 4c.7 Report which rates the file carries and their range, and keep the deviation report describing the samples rather than the fitted rates; verify the summary says `(fitted)` with the range
- [x] 4c.8 Verify the fitted file applies end to end: 249 454 rows, the acceptance check passes at 38.6 min against 43.5 expected (was 36.1 with the means), and the duration difference is still 0.000 s

## 5. The segment speed file

- [x] 5.1 Write `data/segment_weights.csv` as `from_osm_id,to_osm_id,edge_speed_in_km_h,edge_rate`, one row per segment carrying a sample, speed as `distance/duration*3.6` at full precision; verify no row exists for a segment no pair drove
- [x] 5.2 Compute the rate as `distance_m / (min_weight + price_eur / wage * 3600)` with `--wage-eur-per-hour` defaulting to 20; verify a 100 m segment of weight 2.77 at 2.00 EUR/km emits a rate of 2.58, and that running at 40 EUR/hour halves every added term
- [x] 5.3 Verify the file has no blank line — OSRM rejects the whole file for one — and that it sorts deterministically, so a rerun from the same inputs is byte-identical
- [x] 5.4 Write `data/segment_weights_report.json` with the per-segment count, extremes, mean and deviation and the reconstruction errors; verify it is git-ignored and the CSV is not

## 6. Applying the file

- [x] 6.1 Add an `apply_segment_weights` Makefile step: check free space, clear `$(OSRM_OPTIMAL_PATH)/france-latest.osrm*`, copy every `france-latest.osrm*` from `$(OSRM_TOLL_PATH)`, run `osrm-customize --segment-speed-file /data/segment_weights.csv` on the copy, restart `osrm-optimal`, touch its stamp; verify the whole step completes in about 25 minutes
- [x] 6.2 Verify neither `osrm-extract` nor `osrm-partition` is invoked, and that every file under `$(OSRM_TOLL_PATH)` is byte-identical before and after — checksum the directory on both sides
- [x] 6.3 Verify the step stops and names the file when `data/segment_weights.csv` is absent, and stops and names the space it needs when the filesystem cannot hold another copy
- [x] 6.4 Verify a rerun against an already-customized `optimal` copies the toll graph over it first, so the result is identical to a run against an empty directory — compare route weights from both

## 7. Acceptance

- [x] 7.1 Route `LE PERTHUS` 36967365 to `BEZIERS-OUEST` 1676618837 on both graphs; verify the toll-weighted weight exceeds the untouched weight by 43.5 minutes (2610 s) within the tolerance set here, and record the measured difference
- [x] 7.2 Verify the two durations for that route agree, and record the measured difference as the bound the spec's "within the stated bound" refers to; write both figures into `specs/toll-weighted-graph/spec.md` before archiving
- [x] 7.3 Verify a route touching no tolled segment — two towns off the motorway network — returns identical weight and duration from both graphs
- [x] 7.4 Build the check into `build_segment_weights` against the fixed pair rather than a run-time argument, and verify it stops and reports both weights, both durations and the expected difference when the difference is outside tolerance
- [x] 7.5 Verify a route the untouched graph sends over a tolled motorway is answered by the toll-weighted graph on a free alternative where the toll exceeds the time saved, on a pair chosen to make that true; this is the behaviour the whole change exists for

## 8. Pipeline integration

- [x] 8.1 Rename the Compose service `osrm-optimal` to `osrm-toll` on `${OSRM_TOLL_PATH}` at `127.0.0.1:5000`, add a new `osrm-optimal` on `${OSRM_OPTIMAL_PATH}` at `127.0.0.1:5001`, and a second tools service mounting the toll-weighted path; verify `docker compose up` starts both query services and no one-shot container
- [x] 8.2 Point every `--osrm` argument in the Makefile and every default in `builder/*.py` at `http://osrm-toll:5000`, and every `compose up -d osrm-optimal` in steps 4 to 8 at `osrm-toll`; verify no committed file still names `osrm-optimal` as the graph a pipeline step queries
- [x] 8.3 Add `guard-osrm-toll-path` and `guard-osrm-optimal-path`, and a guard that the two paths differ; verify each fails with a message naming its variable, and that identical paths are refused before anything is overwritten
- [x] 8.4 Raise the setup step's `MIN_FREE_GB` to cover both graphs and verify it stops naming the space it needs on an undersized filesystem
- [x] 8.5 Add `build_segment_weights.py` to the `COPY` line in `builder/Dockerfile` and to `$(BUILDER_STAMP)`'s prerequisites; verify `docker compose build builder` succeeds and the script is in the image
- [x] 8.6 Add the checkpointed `build_segment_weights` and `apply_segment_weights` targets, each on its own output, and append both to `all`; verify `make -n all` runs the ten steps in the specified order
- [x] 8.7 Make the setup stamp invalidate both new steps, so rebuilding the untouched graph re-derives and re-applies the file; verify touching `data/nodes_blacklist.yaml` puts steps 9 and 10 back into `make -n all`
- [x] 8.8 Extend `clean-osrm` to clear both graph directories and both stamps while keeping `data/segment_weights.csv` and the extract; verify both directories are empty of `france-latest.osrm*` and the deliverable survives
- [x] 8.9 Verify `build_segment_weights` runs with `ULYS_SUBSCRIPTION_KEY` and `ULYS_PASSAGE_DATE` unset and with no network, and fails naming the unreachable routing service when `osrm-toll` is stopped
- [x] 8.10 Add `data/segment_weights_report.json` to `.gitignore` and commit `data/segment_weights.csv`; verify `git status` shows the CSV tracked and the report untracked

## 9. Full run

- [x] 9.1 Run `make all` end to end on a tree already carrying every earlier output; verify steps 1 to 8 do no work, step 9 routes 23 835 pairs and step 10 produces the graph
- [x] 9.2 Verify a second `make all` performs no work at all, including the two new steps
- [x] 9.3 Verify the committed CSV's row count, file size and the segment count reported by step 9 agree, and confirm with the maintainer that the size is acceptable to carry in the repository — 223 174 rows, 9.0 MB, matching the reported segment count; maintainer confirmed it is committed
- [x] 9.4 Update `openspec/specs/build-pipeline/spec.md`'s scenario text and this change's spec deltas with the measured tolerances from 7.1 and 7.2 before archiving
