# Proposal

## Why

Each router holds 6.69 GB of resident memory after it loads the France graph. On the 15 GB development host, the two routers do not fit in RAM together. Part of that memory holds data that no consumer of this project reads.

## What Changes

- **BREAKING** The routing profile declares no excludable class. Today it declares `toll`, `motorway` and `ferry`, so `osrm-customize` stores four metric sets in `cell_metrics`: one with no exclusion and one for each class. Each set is 457 MB. One set remains. This saves 1,371 MB per graph, on disk and in RAM. A request with `exclude=` fails.
- **BREAKING** Both routers start with `--disable-feature-dataset ROUTE_STEPS`. They then do not load the intersection bearings. Measured on the current graph, this saves 219 MB of resident memory per router and needs no rebuild. A request with `steps=true` fails with `DisabledDataset`. All other answers stay byte-identical.
- `make test_cities` stops sending `exclude=ferry`. A candidate east of the meridian 8.4°E is not mainland. That meridian lies between Lauterbourg (8.23°E), the easternmost point of the mainland, and the Sanguinaires (8.53°E), the westernmost land of Corsica.
- The README states the new size of each graph.

Together, the two changes cut the resident memory of each router from 6.69 GB to about 5.10 GB. The two routers together save about 3.2 GB.

Not in this change:

- `osrm-routed --mmap`. The user decided against it.
- No street names in the profile. Measured on the full France extract, it saves 0.15 GB of the 27.9 GB extract peak and 37 MB per router.
- The peak memory of `osrm-extract`. Neither change above lowers it.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `build-pipeline`: the patched profile declares no excludable class, and both routers skip the intersection bearings.
- `google-route-comparison`: a fixed meridian decides what is mainland. Ferry exclusion no longer decides it.

## Impact

- `builder/patch_car_profile.py` and its tests in `builder/tests/`. A changed patch script invalidates the graph, so the next `make` rebuilds both graphs. That rebuild takes about 30 minutes, and on this host it needs temporary swap.
- `docker-compose.yml`: the commands of `osrm-toll` and `osrm-optimal`.
- `evaluation/build_test_cities.py`.
- `README.md`: graph sizes.
- The relay forwards requests unchanged. A borrower that sends `exclude=` or `steps=true` now gets an error from the router. No consumer in this repository sends either one after this change.
