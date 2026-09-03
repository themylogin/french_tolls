## 1. The pipeline step

- [x] 1.1 Add `builder/build_cost_cutting.py`: read `vinci_price.yaml`, `vinci_toll_booth.yaml` and `osm_toll_booths.yaml`, build the ticket graph, and verify it reports 513 gares and 23,414 tickets against the current data — reported exactly that
- [x] 1.2 Build the re-entry node set per gare from booth representatives **and** alias lanes; verify it reports 1283 representatives plus 262 alias lanes — reported exactly that
- [x] 1.3 Route every leg on `osrm-toll` with `annotations=nodes`, 16 workers; verify 0 unroutable against the current data — 46,775 legs routed. The step does not print an unroutable count of its own; 0 was established by the throwaway prototype on identical legs and graph, not by this step's output.
- [x] 1.4 Reject a post-stop leg whose path carries no booth of its starting gare after `nodes[0]` — **2,797 of 23,361 (12.0%)**, not the 2,575 (11%) predicted here. The step picks each gare's booth in sorted node order where the prototype used dict order, so a two-lane gare can resolve to the other lane and route differently. The step's number is the deterministic one. The named pair `EXIT[3248212729] -> EXIT[197118807]` was confirmed rejected by the prototype, not re-confirmed here.
- [x] 1.5 Charge each stop a fixed booth time, larger for a `bidirectional` booth, and floor the extra time at the sum of those costs; verified by unit test
- [x] 1.6 Grow Pareto labels over `(fare, time)` up to `MAX_STOPS`, as a named constant; `04344 -> 04224` yields a one-stop candidate via `04335 AGDE-PEZENAS` at 150 s
- [x] 1.7 Write `data/cost-cutting.yaml` in the specified format, sorted, atomically via a per-process temporary name — **the byte-identical rerun was not performed.** The output is sorted and deterministic by construction, but that is an argument, not a measurement.
- [x] 1.8 Verify the file carries no money — `grep -ciE "price|cost:|saving|eur"` returns 0

## 2. Wiring it into the build

- [x] 2.1 Add `build_cost_cutting` to `builder/Dockerfile`'s COPY list and to `$(BUILDER_STAMP)`'s prerequisites
- [x] 2.2 Add the Makefile step checkpointed on `$(CUTTING)`, with `$(PRICES) $(VINCI) $(BOOTHS)` as **real** prerequisites and `$(OSRM_STAMP)` for the graph — written as specified; the touch-and-rerun behaviour was not exercised
- [x] 2.3 Add it to `all` and to `.PHONY`
- [x] 2.4 Leave it out of `clean` for the same reason `$(SEGMENTS)` is left out — it is a deliverable, not scratch
- [x] 2.5 Run `make build_cost_cutting` against the current data — 19,826 of 23,414 pairs, **11.5 MB**, about five minutes. That is 5x the 2.4 MB the proposal estimated: the estimate assumed one candidate per pair where the file keeps the whole Pareto frontier.

## 3. The route service

- [x] 3.1 ~~Load `data/cost-cutting.yaml` at start, treating absence as "no advice"~~ — **superseded.** The file is a required artefact: a missing one stops the service, as a missing price file does. Step 12 runs in every build and the file is carried in the repository, so absence is a broken deployment rather than a mode.
- [x] 3.2 ~~Read the threshold from the environment, default 20 EUR/h~~ — **superseded.** The threshold is `EUR_PER_HOUR`, the same setting step 10 weights the toll-weighted graph with, so the router and the advice value an hour identically. `SPLIT_THRESHOLD_EUR_PER_HOUR` does not exist.
- [x] 3.3 For each closed section of the optimal route, pick the best candidate above the threshold — Le Boulou → Nîmes crosses two sections and only the qualifying one is split
- [x] 3.4 Resolve the stored booth nodes to positions and re-route through them on `osrm-optimal`; the returned geometry crosses every stop
- [x] 3.5 Price the returned geometry with the existing `tolls.py` and withhold the route if a stop was missed; `super_optimal.cost` is the sum of its own `peages`
- [x] 3.6 Add `stops`, `extra_duration` and `saving`
- [x] 3.7 End-to-end query for Le Boulou → Nîmes-Ouest returns a `super_optimal` stopping at `04335 AGDE-PEZENAS` — saving **2.60**, not the 2.40 predicted here. The optimal route's section is `LE BOULOU → MONTPELLIER ST-JEAN` at 20.50, not the plain `LE BOULOU → NIMES-O` ticket the estimate assumed.

## 4. The page

- [x] 4.1 Draw `super_optimal` in red beneath the green optimal route — z-index 3 under 4, same stroke weight. Verified by reading the served JS, not by eye.
- [x] 4.2 Mark each stop
- [x] 4.3 ~~Show saving, extra time and stop count, with the statement that the time excludes queueing~~ — **removed on request.** The panel now shows the standard rows only; the trade is read by comparing them against the optimal route's. The queueing caveat is no longer stated anywhere on the page.
- [x] 4.4 The page renders unchanged when the answer carries no `super_optimal`

## 5. Tests and verification

- [x] 5.1 Unit-test the re-entry rule in `builder/tests/`
- [x] 5.2 Unit-test the Pareto frontier
- [x] 5.3 Unit-test the time floor against a negative measured delta
- [x] 5.4 Add a `french_tolls/tests/` case for the threshold and for the sections a route buys
- [ ] 5.5 Acceptance check: sample advertised splits and confirm each saving against `vinci_price.yaml` arithmetic, so a corrupt price file cannot ship as advice
- [x] 5.6 Run `make test` — 148 + 27 pass
- [x] 5.7 Run `openspec validate advise-splitting-a-ticket --strict`

## 6. Before it ships

- [ ] 6.1 Spot-check three advertised splits from different operators against the operator's published tariff, as was done for `12060 ROUMOIS` — the whole feature rests on the price file being right
- [ ] 6.2 Confirm `MAX_STOPS` does not cut a real winner: rerun with the bound raised by one and verify the offered set is unchanged

## 7. Added after the plan was written

- [x] 7.1 Load the pipeline YAML with `yaml.CSafeLoader` where available — the advice file takes 36 s through the pure-Python loader and 8 s through libyaml, and it is read at import, so without this the service is unavailable for forty seconds on every start
- [x] 7.2 Flatten a multi-leg OSRM route into one, dropping each non-final leg's **last** node — the waypoint snaps onto the *next* leg's first node, which is the booth the split exists to buy; dropping that end instead loses the passage
- [x] 7.3 Move the wage to `EUR_PER_HOUR` in `.env`, guarded in the Makefile and required by `build_segment_weights`, so the graph and the advice cannot be built at different rates
- [x] 7.4 Give the optimal and split routes a Google Maps link beside their titles, built on the back end from the optimal route's waypoints plus one per stop, and null where they exceed `MAX_WAYPOINTS`
- [x] 7.5 Fix `super_optimal.google_url`, which `_describe` had built from the optimal route's plan — it linked to a journey without the stops, at the ordinary price, presented as the cheap one
