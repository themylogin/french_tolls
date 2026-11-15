# Tasks

## 1. Routers skip turn-by-turn data

- [x] 1.1 In `docker-compose.yml`, add `--disable-feature-dataset ROUTE_STEPS` to the `command` of `osrm-toll` and `osrm-optimal`, after the graph path. Verify that `docker compose config` shows the flag after `/osrm/france-latest.osrm` on both services.
- [x] 1.2 Restart both local routers on the current graph. Verify that `/nearest`, `/route` with the application's parameters, `/match` with `annotations=nodes` and `/table` answer `Ok`. Verify that `/route` with `steps=true` answers 400 `DisabledDataset`.
- [x] 1.3 Read `anon` in `memory.stat` of each router container after load. Verify that it is about 219 MB below the 6,690 MB measured without the flag.

## 2. The profile declares no excludable class

- [x] 2.1 In `builder/patch_car_profile.py`, delete the `excludable = Sequence { ... }` block on every run. Stop with an `Abort` that names `excludable` when the block is missing or appears twice. Verify with the tests of 2.2.
- [x] 2.2 In `builder/tests/test_patch_car_profile.py`, add an `excludable` block to the test profile. Add one test that the patched profile has no `excludable`, also with no blacklist and no gate. Add one test that a profile without the block is refused. Verify with `make test`.

## 3. The evaluation uses a meridian

- [x] 3.1 In `evaluation/build_test_cities.py`, remove `exclude=ferry` from the `/table` request. Exclude each candidate with a longitude above 8.4 before that request, and print the count. Update the module docstring and the progress messages. Verify that the URL the script builds has no `exclude`.
- [x] 3.2 Run `make test_cities` against the rebuilt graph of group 4 with no `data/test_cities.yaml`. Verify that it reports the meridian count and the unreachable count, and that no chosen city has a longitude above 8.4. Delete the file afterwards, because it did not exist before.

## 4. Rebuild, measure, document

- [x] 4.1 Stop the local routers and add at least 16 GB of temporary swap. Then run `make OSRM_TOLL_PATH=/osrm/toll OSRM_OPTIMAL_PATH=/osrm/optimal apply_segment_weights`. Verify that the step rebuilds the untouched graph, the segment weights and the toll-weighted graph, and that the `--verify` acceptance check passes.
- [x] 4.2 Verify with `tar -tvf` that the `cell_metrics` file of each graph holds only `exclude/0`, and that `git diff --exit-code data/segment_weights.csv` reports no change.
- [x] 4.3 Start both routers. Read `anon` in `memory.stat` of each container after load. Verify that each one is about 5,100 MB.
- [ ] 4.4 Run the integration suite against the local routers: `docker compose --profile test run --rm -e OSRM_TOLL_URL= -e OSRM_OPTIMAL_URL= integration`. Verify that it passes.
- [x] 4.5 In `README.md`, replace the 9.3 GB graph sizes with the measured sizes. Verify that the figures match `du -sh` of both graph directories.
- [x] 4.6 Remove the temporary swap. Verify with `swapon --show`.
