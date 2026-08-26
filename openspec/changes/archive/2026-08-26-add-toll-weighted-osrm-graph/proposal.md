## Why

`data/vinci_price.yaml` holds 23 376 entrance/exit tariffs across 522 source booths, worth 519 345 EUR of toll. Nothing consumes them. The router still answers every question as if the toll network were free, so a route it calls fastest can be the one that costs a driver forty euros to save five minutes.

A router cannot be told about a ticket. It knows edges, and it costs each one. So the tariffs have to be spread over the edges the ticket covers: a price per kilometre for every directed segment the priced routes drive, converted into the extra weight a driver carries for using it.

OSRM already accepts exactly that input. `--segment-speed-file` takes a CSV of `from_osm_id,to_osm_id,edge_speed_in_km_h,edge_rate`, sets the segment's duration from the speed and its weight from `length / rate`, and `osrm-customize` folds it into an MLD graph without re-running extract or partition. Keeping the speed at its original value and moving only the rate leaves durations alone and puts the toll into the weight, which is the quantity the search minimises.

The instance naming has to change with it. The project has one OSRM instance, `optimal`, and every step queries it. Once a second graph exists, the name has to say which one is which: `toll` is the untouched graph every existing step keeps using, and `optimal` becomes the toll-weighted one that answers what a driver should actually do.

## What Changes

- **BREAKING** `OSRM_OPTIMAL_PATH` is replaced by two variables. `OSRM_TOLL_PATH` holds the untouched graph that `setup_osrm` builds and that steps 4, 5, 7 and 8 query. `OSRM_OPTIMAL_PATH` holds the toll-weighted graph, and is no longer where preprocessing writes. An existing tree migrates by moving the graph directory and adding the second variable.
- **BREAKING** the Compose service `osrm-optimal` is renamed `osrm-toll` and keeps `127.0.0.1:5000`. A new `osrm-optimal` service serves the toll-weighted graph on `127.0.0.1:5001`. Every existing pipeline step switches to `http://osrm-toll:5000`.
- A ninth step, `build_segment_weights`, that routes all 23 835 priced booth pairs against the `toll` graph and writes `data/segment_weights.csv`.
- Each priced pair contributes one price-per-kilometre sample, `price / route length`, to every directed segment its route drives.
- A segment's rate is **fitted** so that the rates reproduce the tariffs, and held toward the mean of its own samples in proportion to how few journeys constrain it. Measured, that takes the median journey error from 8.5% to 3.5% and the share of journeys priced within 10% from 56.7% to 84.4%, while leaving the highest rate at 0.5386 EUR/km against the means' own highest of 0.5355 — so no segment is priced outside what some real journey paid.
- A pair that is not a journey contributes nothing: one whose barrier-to-barrier route exceeds `--max-detour` (default 5) times the straight line between the barriers, one priced at 0.00 EUR, and one whose route does not cross its own booths. Measured, that is 24 pairs of 23 376, worth 0.01% of the toll, and dropping them takes the worst segment deviation from 815% to 250%.
- **No deviation gate.** An earlier design stopped the run when any segment's samples spread more than 10%. Measured, 97.9% do after every correction, because two journeys on different concessions genuinely pay different rates for the same distance. That is a fact about French tolls, not a defect a pipeline can fix, and the fit is what stops it reaching the driver. The spread is still reported, worst first, with the way carrying each segment — it is how four measurement errors were found — but nothing about it stops the run.
- Generating the file ends by reporting the **journey error**: every tariff against what the rates charge for it, with totals, distributions, a breakdown by journey length, and the worst journeys named twice over — by euros and by proportion — each with a link to itself on the map.
- A `--survey` mode that does everything except write the file.
- Weight is the OSM weight plus the time a driver earning `--wage-eur-per-hour` (default 20) works to pay the segment's toll: `weight = osm_weight + segment_price_eur / wage * 3600`. A 100 m segment at 2 EUR/km costs 0.20 EUR and adds 36 seconds.
- Duration is preserved. Every emitted row carries the segment's original speed, so `osrm-customize` recomputes the same duration it had.
- The original per-segment weight, duration and distance come from OSRM's own `annotations=nodes,distance,duration,weight` on those same routes. No Lua patch is needed: the router already publishes the numbers.
- A tenth step, `apply_segment_weights`, that copies the `toll` graph over the `optimal` one and runs `osrm-customize --segment-speed-file data/segment_weights.csv` against the copy.
- `data/segment_weights.csv` is committed, alongside the booth inventory, the route set, the gare mapping, the price file and the booth sides.
- An acceptance check on the pair LE PERTHUS (36967365) to BEZIERS-OUEST (1676618837), priced at 14.50 EUR: the `optimal` graph's route weight must exceed the `toll` graph's by about 43.5 minutes, and its duration must match to within a stated bound.
- Measured over all 23 352 priced journeys: median error 3.5%, p90 13.1%, 84.4% priced within 10%, net bias -0.20%, and no journey wrong by more than 6.65 EUR.

## Capabilities

### New Capabilities

- `toll-weighted-graph`: how a tariff becomes a price per kilometre on each directed segment, how the samples are aggregated and validated, how the segment speed file is derived from OSRM's own annotations, what the file contains, how it is applied to a second graph, and what the two graphs must then agree and disagree about.

### Modified Capabilities

- `build-pipeline`: two OSRM instances instead of one, with the graph path split into two variables and the service renamed; two further named steps and their place in `all`; the checkpointed/resumable classification of both; the disk the two graphs need; and the segment weight file joining the committed deliverables.

## Impact

- **New**: `builder/build_segment_weights.py`, `data/segment_weights.csv` (committed), `data/segment_weights_report.json` (untracked diagnostic).
- **Modified**: `.env.example` and `.env` (`OSRM_TOLL_PATH` added, `OSRM_OPTIMAL_PATH` redefined), `docker-compose.yml` (`osrm-toll`, the new `osrm-optimal`, a second tools service), `Makefile` (paths, guards, the service every step brings up, steps 9 and 10, `all`, `clean-osrm`), `builder/Dockerfile` (the new script and the image stamp), `.gitignore` (the report is ignored, the CSV is not).
- **Reused unchanged**: the inventory, sides and blocker helpers of `builder/build_vinci_direct_prices.py`; the price file loader of `builder/build_vinci_prices.py`; the bordered `table` helper the other steps report with.
- **Unaffected**: every artefact the first eight steps produce. Step 9 reads them and writes none of them. The `toll` graph is byte-identical to today's `optimal` graph, so no earlier step's answers change.
- **Disk**: two graphs of 9.2 GB each. The old 40 GB guard was sized from a stale 25 GB estimate of a single graph; measured, the two graphs plus the transient extract copy peak near 23 GB, so the guard becomes 25 GB with a second 12 GB check before the copy.
- **Runtime**: about 10 minutes for step 9 (23 835 local routes with full annotations, against the 51 minutes 256 580 unannotated routes took in step 8), plus step 10 (a 9.2 GB copy and one `osrm-customize`).
- **Dependencies**: no new package in the builder image.
