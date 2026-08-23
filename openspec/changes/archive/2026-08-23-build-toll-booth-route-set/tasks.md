## 1. Project scaffolding

- [x] 1.1 Add `.env.example` with `OSRM_OPTIMAL_PATH` and a `.gitignore` covering `.env` and `data/`; verify a fresh `cp .env.example .env` gives a working configuration and `git status` shows no large artifacts tracked
- [x] 1.2 Create the `Makefile` skeleton: `include .env`, `export`, a guard that aborts naming `OSRM_OPTIMAL_PATH` when it is unset or empty, and the four phony step targets plus `all`; verify `make -n all` lists `download_pbf`, `setup_osrm`, `build_osm_toll_booths`, `build_route_set` in that order, and that `OSRM_OPTIMAL_PATH= make setup_osrm` fails with the named-variable message
- [x] 1.3 Create `docker-compose.yml` with the `osrm-optimal` service (service name and `container_name` both `osrm-optimal`, `osrm-routed --algorithm mld`, no `-t` flag), plus `osrm-tools` and `builder` under `profiles: ["tools"]`, mounting `${OSRM_OPTIMAL_PATH}:/osrm` and `./data:/data`; verify `docker compose config` resolves the paths and `docker compose up -d` starts only `osrm-optimal`

## 2. Step 1 — download_pbf

- [x] 2.1 Implement `download_pbf` fetching `france-latest.osm.pbf` from Geofabrik into `data/`, writing to a temporary name and renaming on success so an interrupted download is never mistaken for a complete one; verify the file arrives at ~4.7 GB and that killing the download mid-transfer leaves no `data/france-latest.osm.pbf`
- [x] 2.2 Verify the step is existence-based: re-running `make download_pbf` with the file present performs no network access

## 3. Step 2 — setup_osrm

- [x] 3.1 Add a free-space precheck at the top of `setup_osrm` that fails immediately with a clear message when `$OSRM_OPTIMAL_PATH` has less than ~40 GB available; verify by pointing `OSRM_OPTIMAL_PATH` at a small tmpfs and confirming the step aborts before any container starts
- [x] 3.2 Implement the preprocessing recipe: remove any stale `.osm.pbf` under `$OSRM_OPTIMAL_PATH`, copy the extract in (`cp -l … || cp …`), then run `osrm-extract -p /opt/car.lua`, `osrm-partition`, and `osrm-customize` via `docker compose run --rm osrm-tools`; verify the three commands exit 0 and the `.osrm.*` files appear under `$OSRM_OPTIMAL_PATH`
- [x] 3.3 Unlink the extract copy after `osrm-customize` succeeds and write `$(OSRM_OPTIMAL_PATH)/.setup.stamp` as the final action; verify no `.osm.pbf` remains under `$OSRM_OPTIMAL_PATH`, `data/france-latest.osm.pbf` is still present, and the stamp exists
- [x] 3.4 Declare the stamp target with an order-only prerequisite on the extract; verify that `touch data/france-latest.osm.pbf` followed by `make setup_osrm` re-runs nothing, and that deleting the stamp re-runs the step from the copy step onward
- [x] 3.5 Verify a mid-recipe failure leaves no stamp: interrupt during `osrm-partition` and confirm the next `make setup_osrm` restarts the step rather than skipping it

## 4. Builder image

- [x] 4.1 Write `builder/Dockerfile` on a Debian base installing `osmium-tool`, `pyosmium`, `pyyaml`, and an HTTP client; verify `docker compose run --rm builder osmium --version` and a `python -c "import osmium, yaml"` smoke check both succeed
- [x] 4.2 Wire the image build into the Makefile as an internal prerequisite of steps 3 and 4 so `make all` still presents exactly four steps; verify `make -n all` shows no fifth top-level step and that a cold `make build_osm_toll_booths` builds the image first

## 5. Step 3 — build_osm_toll_booths

- [x] 5.7 Restrict the inventory to booths on through-road classes and record every exclusion with its reason in `data/excluded_booths.json`; verify inventory and exclusions are disjoint, together account for every booth in the extract, and no excluded booth sits on a through road

- [x] 5.1 Implement the `osmium tags-filter` stage selecting `n/barrier=toll_booth`, `n/highway=toll_gantry`, and `n/place=city,town,village` into a retained intermediate PBF that serves as the hand-off to step 4; verify the output is a few MB, survives the step, and that a way tagged `barrier=toll_booth` in the source does not appear in it
- [x] 5.2 Implement the pyosmium pass over the filtered file writing `data/osm_toll_booths.yaml` with `toll_booths` (ascending, duplicate-free group representatives) and `aliases` (member id -> representative); verify every booth appears exactly once across the two keys, each representative is the smallest id in its group, and no alias target is itself an alias
- [x] 5.3 Confirm the filtered PBF carries node id, coordinates, and `name` for every eligible `place` node; verify by reading it back with pyosmium that a known `place=suburb` node is absent while known `place=town` and `place=hamlet` nodes are present with plausible coordinates and their names
- [x] 5.4 Group plaza lanes topologically: carve the road network around booths, build directed adjacency honouring one-way (including the implicit one-way of motorway/motorway_link/trunk_link), weight edges by real segment length, contract degree-2 geometry nodes summing their length, search 1 km of road back/forward stopping at any other booth, and take the transitive closure of the shared-(P,S) relation; verify booths in sequence and on opposite carriageways stay separate, a known multi-lane plaza's two barriers stay apart while each groups its own lanes, and no route traverses two booths of one group
- [x] 5.6 Emit the group-size distribution on stdout; verify it totals to the booth count
- [x] 5.5 Verify the step needs no network: run it with the extract present and networking disabled and confirm it completes

## 6. Step 4 — build_route_set

- [x] 6.1 Implement the OSRM client: bounded connection retry (~60 s) against `http://osrm-optimal:5000`, requests using `annotations=nodes&overview=false&steps=false`, and a parallel request pool; verify a single known city pair returns a node list, and that starting the step before the server is ready succeeds rather than aborting on the first refused connection
- [x] 6.2 Verify the failure path: with `osrm-optimal` stopped, the step exits non-zero within the retry window with a message naming the unreachable service
- [x] 6.3 Load the endpoint candidate catalogue from the filtered PBF produced by step 3 (id, coordinates, name), converting to OSRM's `{lon},{lat}` order at query time; verify the catalogue holds hundreds of thousands of eligible places and that a spot-checked candidate's coordinates place it in France
- [x] 6.4 Implement Wave A candidate generation — select ~100 geographically dispersed place nodes and route all ordered pairs; verify the candidate count matches `n·(n−1)` and that A→B and B→A are kept as distinct candidates
- [x] 6.11 Add an asymmetric near x far endpoint strategy for interchange ramp tolls: pair the closest places to the booth with distant ones, in both orders; verify a symmetric band provably cannot generate those pairs and that the strategy converts groups no symmetric band reached
- [x] 6.5 Implement Wave B candidate generation — for each uncovered booth take its K≈20 nearest place nodes and keep pairs whose bearings to the booth differ by more than ~120°; verify on a hand-picked isolated booth that the generated pairs bracket it geographically
- [x] 6.6 Implement the greedy selection loop taking the candidate with the largest marginal gain and stopping when Wave B yields nothing new; verify no selected route contributes zero new booths at the time it is chosen
- [x] 6.7 Write `data/route_set.yaml` with `routes:` holding `{from, to, covers}` mappings and `places:` holding `{name, node_id, latlon}` entries sorted by `node_id` for exactly the endpoints the routes reference, with `latlon` in latitude-longitude order and `name: null` for unnamed nodes; verify the file parses, every `from`/`to` resolves to exactly one `places` entry, no `places` entry is unreferenced, all `covers` ids appear under `toll_booths` in `data/osm_toll_booths.yaml`, and no route has `from == to`
- [x] 6.8 Verify `places` is the referenced subset and not the catalogue: assert its length is at most twice the route count and far below the candidate catalogue size, and that regenerating an unchanged route set yields a byte-identical file
- [x] 6.9 Implement the verification pass and coverage report: resolve traversed lanes to representatives, recompute the union of `covers`, compare it to the representative set, write `data/uncovered_booths.json` (empty list on full coverage, overwritten every run), and print covered/uncovered/total to stdout; verify by deleting a route from an intermediate result that the uncovered list and the counts both reflect it
- [x] 6.10 Verify `covers` reproducibility: re-query a sample of ~20 emitted `from`/`to` pairs against the same instance and assert the returned booth sets equal the recorded `covers` lists

- [x] 6.12 Widen the endpoint set to include `hamlet`, `isolated_dwelling`, and `locality`; verify a booth whose only nearby settlements are small is reachable, and record that it was unreachable by any `city|town|village` pair before
- [x] 6.13 Solve endpoints from network distance using the routing engine's table service (`d(u,v) == d(u,b) + d(b,v)`) rather than straight-line geometry alone; verify solved pairs are still routed and their traversed booths recorded from the response

## 7. End-to-end

- [ ] 7.1 Run `make all` from a clean checkout on a host with only Docker and Compose installed; verify all four steps complete and the three `data/` deliverables are produced
- [x] 7.2 Re-run `make all` with every output in place; verify no step re-executes its work and no container performs real work
- [x] 7.3 Delete only `data/route_set.yaml` and re-run `make all`; verify only step 4 re-executes
- [x] 7.4 Record the final numbers — booth count, route count, uncovered count, and wall-clock per step — and confirm the route count is smaller than the number of groups covered as required by the route-set-size requirement

### Final numbers (task 7.4)

| | |
|---|---|
| booths in the France extract | 1847 |
| excluded (not on a through road) | 282 |
| retained | 1565 |
| groups | 1231 (334 aliases) |
| covered | 1222 (99.3%) |
| uncovered | 9 |
| routes | 747 |
| places referenced | 773 |
| endpoint candidate pool | ~1.02M eligible place nodes |

Wall-clock, all in Docker: download 3m25s; OSRM MLD build ~6 min (9.2 GB);
extraction, carve and grouping ~6 min; route search ~15 min. The route count
(747) is below the number of groups covered (1222), as the
route-set-size requirement demands.
