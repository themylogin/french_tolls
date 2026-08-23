## Why

Plaza grouping merges booths that are not alternatives. Independent evidence from the VINCI Ulys placemark service confirms it: replaying the 747 generated routes produced **17 groups that the operator identifies as two or three distinct gares**, including `02054 ST MICHEL ECHANGEUR` merged with `02056 ST MICHEL BARRIERE` and `06033 LA CIOTAT P/V` merged with `06034 LA CIOTAT ECH.`

The cause is that the grouping graph is not the graph a route sees. `GraphBuilder` is built over `ROUTABLE`, which includes `service`, `track`, `residential` and `unclassified`, and it ignores `access` entirely. So a toll plaza's internal maintenance roads become legitimate connections. At Saint-Michel-de-Maurienne the ramp gare and the mainline barrier share six "common predecessors", every one of them a `service` or `track` way inside the toll compound, reached by a 640 m path of three-metre hops across the forecourt through an `access=private` way. No car can drive it.

A second, rarer hole: the spec relies on one-way restrictions to keep opposite directions apart. On a bidirectional slip road tagged `oneway=no` there are no such restrictions, so the two gares of one interchange merge. 52 booths sit on two-way through roads.

Separately, the route set records a booth as covered without recording which way the route went through it. For a bidirectional booth those are two different tolls, and the current format cannot express the difference.

## What Changes

- Build the grouping graph over `THROUGH_CLASSES` — the same road classes `classify()` already uses to decide which booths belong in the inventory — instead of `ROUTABLE`. Measured: this resolves **all 17** operator-confirmed conflicts and drops groups containing a sequential booth pair from 66 to 2.
- Never group a booth that lies on a through road the car profile can traverse in both directions. Measured: affects exactly one group, `81055576` Broglie-Orbec, and cannot touch the Mont Blanc plaza whose four lanes are all `oneway=yes`.
- **BREAKING** — `data/osm_toll_booths.yaml` becomes a mapping of node id to details. Every entry carries `latlon`; aliases carry `parent_id`; booths on a two-way road carry `bidirectional: true`. Downstream matching needs per-lane coordinates, and the direction flag tells a consumer that this booth is two tolls rather than one.
- **BREAKING** — each `covers` entry in `data/route_set.yaml` becomes a mapping with `node_id`, plus `prev_node_id` on bidirectional booths recording the node the route arrived from. Verified sound: 51 of the 52 bidirectional booths have exactly two immediate predecessors and none has more, so the predecessor identifies the direction without ambiguity.
- **BREAKING** — a bidirectional booth becomes **two** coverage targets, one per direction. The route search covers (booth, direction) rather than booth, and `data/uncovered_booths.json` reports direction.

## Capabilities

### Modified Capabilities
- `toll-booth-inventory`: the grouping rule gains the through-road graph restriction and the two-way exclusion; the output format changes to carry coordinates, alias parents, and the bidirectional flag.
- `route-set-generation`: `covers` entries become mappings carrying direction; coverage is measured per direction for bidirectional booths; the uncovered report gains direction.

## Impact

- `builder/booth_groups.py` — grouping graph class set, two-way exclusion, two-way classification exposed to callers.
- `builder/build_osm_toll_booths.py` — new inventory format.
- `builder/build_route_set.py` — reads the new inventory, records `prev_node_id`, covers per direction, new `covers` and uncovered formats.
- `data/osm_toll_booths.yaml` — regenerated, 1231 groups becoming roughly 1303.
- `data/route_set.yaml` — regenerated; every representative id may shift, so the whole file is rebuilt.
- `data/uncovered_booths.json` — new shape, and the count is expected to rise from 9.
- `data/mk_summary.py` — reads both files.
- `openspec/changes/map-booths-to-vinci-gares` — sits downstream. Its `toll-booth-inventory` delta is superseded by this change and must be dropped; its gare-matching step must be rebased on the new `covers` shape.

Not affected: `data/excluded_booths.json` and the through-road filter that produces it, which is independent of grouping.
