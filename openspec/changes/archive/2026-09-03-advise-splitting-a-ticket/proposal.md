## Why

A closed-section tariff is not additive. Leaving the motorway at an intermediate gare and re-entering immediately buys two short tickets instead of one long one, and the two together are often cheaper. Measured against the current price file, **19,892 of 23,414 sold pairs are cheaper if the ticket is split**, and 11,843 of them save more than 20 EUR for each hour of extra driving.

The pipeline cannot find this today, and the reason is structural. `build_segment_weights` converts each tariff into a price per kilometre and bakes it into the graph, so `osrm-optimal` optimises **geometry**. Splitting barely changes the geometry — it changes the **ticketing**, which the per-kilometre model has flattened away. Nothing in the project searches that space.

The pricing side is already correct: `french_tolls/tolls.py` pairs each `enter` with the next `exit` along the driven nodes, so a route that really does leave and rejoin is priced as two tickets without any change. The tool can price a split journey; it just cannot invent one.

## What Changes

- **A new pipeline step 12, `build_cost_cutting`**, writing `data/cost-cutting.yaml`: for every sold `(enter gare, exit gare)` pair, the stop sequences that cost less, each with the OSM booth nodes to stop at and the extra driving time in seconds.
- **The route answer gains an optional `super_optimal`** route, returned when splitting beats a configurable threshold (default 20 EUR/h) on some closed section of the optimal route.
- **The page renders it** beneath the optimal route in red, so only the junction detours show against the green.

Money is deliberately **not** stored in the file. The saving is fully determined by `data/vinci_price.yaml`; duplicating it would create a second source of truth that a repriced file silently invalidates — the failure `$(SEGMENTS)` already had before its prerequisites were made real.

## Capabilities

### New Capabilities

- `toll-split-advice`: which stop sequences make a sold ticket cheaper, how a candidate is proved to be a real re-entry rather than a drive across country, the format and rebuild contract of `data/cost-cutting.yaml`, and the threshold that decides when the advice is offered.

### Modified Capabilities

- `build-pipeline`: an twelfth step, and `data/cost-cutting.yaml` joins the artefacts carried in the repository.
- `route-service`: the answer may carry a `super_optimal` route beside `optimal` and `fast`.
- `web-front-end`: how the page draws a route that is offered with a split.

## Impact

- `builder/build_cost_cutting.py` (new), `builder/Dockerfile`, `Makefile`, `docker-compose.yml`.
- `french_tolls/` — the route service reads the new file and, when the threshold is met, re-routes through the stops and prices the result with the existing `tolls.py`.
- `www/` — one extra polyline and its z-order.
- `data/cost-cutting.yaml` (new, committed). About 2.4 MB at every pair that wins, which is a fifth of the already-committed `segment_weights.csv`.

The step needs `$(PRICES)`, `$(VINCI)`, `$(BOOTHS)` and `$(OSRM_STAMP)`. It does **not** need the segment weights or the toll-weighted graph. It costs no Ulys requests: every duration comes from the project's own `osrm-toll`.

## Non-goals

- **Changing how routes are found.** `osrm-optimal` keeps optimising geometry. The split is applied to the optimal route after the fact, not searched for jointly.
- **Modelling queues.** The extra time is driving time plus a fixed booth cost. A August afternoon at Béziers is not modelled, and the page has to say so.
- **Splits the router will not corroborate.** When the fastest way onward from a stop leaves the motorway, the candidate is dropped rather than forced. This under-reports; it does not invent.
- **More than four stops.** 96.6% of the winning splits above the threshold are a single stop, and only 3 of 11,843 use four.
