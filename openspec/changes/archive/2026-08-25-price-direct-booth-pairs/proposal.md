## Why

`data/vinci_price.yaml` holds 964 enter/exit pair prices for 468 `enter` booths — about two each. A closed section charges a tariff for every entrance/exit combination its network allows, so the file covers a small fraction of what the operator publishes.

The gap is a consequence of how step 6 works. It prices only what the route set happens to drive, and the route set is built to *cover every booth once*, not to exercise every pair. A pair no route drove is a pair nobody asked about.

The pairs are enumerable without a route set. A tariff exists for an entrance and an exit when a vehicle can drive from one to the other without passing a third booth — that is what closes the ticket. OSRM can answer that question for the whole grid in about seven minutes.

## What Changes

- A seventh pipeline step, `build_vinci_direct_prices`, that walks the grid of source booths against target gare codes, asks OSRM whether a booth lies between them, and prices the pairs where none does.
- Source booths are the `enter` and `bidirectional` groups of `data/vinci_price.yaml` (516). Target booths are the `exit` and `bidirectional` groups (514). `gantry` and `passthrough` groups are never endpoints.
- A booth lies between when the route's OSM nodes meet `data/osm_toll_booths.yaml` — `toll_booths` or `aliases`, resolved through `parent_id`. That is 1556 node ids, and it includes booths with no gare, gantries, and barriers.
- Rejections go to a new SQLite database, `data/vinci_routes_rejected.sqlite3`, one row per rejected pair with the first booth in the way.
- Prices go into `data/vinci_price.yaml` under the source group's existing `prices` mapping. The file format does not change.
- The step is resumable from those two files alone and needs no cursor of its own.
- The override file's `nodes_blacklist` is honoured. A route using a connection that does not exist on the ground is not a route anyone can drive, so the step stops rather than judging the pair on it.
- The override file gains `prohibited_gare_pairs`. Such a pair is dropped from the grid before routing, so it costs neither a route nor a request and appears in neither output.
- The step aborts, rather than recording anything, when the rate service returns no amount for a pair OSRM found clean. Such a pair means the inventory is missing a booth, and that is fixed in the data.

## Capabilities

### New Capabilities

- `vinci-direct-pricing`: how the source/target grid is enumerated, how OSRM decides whether a booth lies between two booths, what is recorded for a rejected pair, how a clean pair is priced, the abort conditions, and the resume contract across `data/vinci_price.yaml` and the rejection database.

### Modified Capabilities

- `toll-booth-inventory`: the override file gains a `prohibited_gare_pairs` section, for ordered gare pairs that are not a journey however the road network reads.
- `build-pipeline`: the pipeline gains a seventh named step, so the step list, the `all` order, the resumable/checkpointed classification, and the count of steps needing network access all change.

## Impact

- **New**: `builder/build_vinci_direct_prices.py`, `data/vinci_routes_rejected.sqlite3`.
- **Modified**: `Makefile` (step 7 target, its guards, and `all`), `builder/Dockerfile` (the new script is copied in and joins the image stamp's prerequisites).
- **Reused unchanged**: the rate client, the money handling, and the gare-code checks of `builder/build_vinci_prices.py`; the blocker resolution of `builder/build_route_set.py`.
- **Unaffected**: `data/route_set.yaml`, `data/osm_toll_booths.yaml`, `data/vinci_toll_booth.yaml`, and every step that produces them. The step reads them and writes none of them.
- **Runtime**: about 7.2 hours for a full first run — 51 minutes of OSRM and 6.3 hours of rate requests at the existing one-per-second limit. Steps 1 to 4 are not re-run.
- **Dependencies**: `sqlite3` from the Python standard library. No new package in the builder image.
