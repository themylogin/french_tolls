## Why

Nine routes in `data/route_set.yaml` drive through both carriageways of one toll plaza and therefore pay one gare twice. No car can do that. Each of the nine has an endpoint that OSRM snaps onto a road the endpoint has no access to — five onto a motorway mainline, one onto a motorway link inside a plaza, the rest onto a local road hundreds of metres away.

Endpoint eligibility is today a pure tag test: a node is a candidate if `place` is one of six values. Nothing checks whether a car can start a trip there. A `place=locality` in France names a field, a wood, or a farm plot, and 97.7 % of them sit more than 10 m from any routable way. When the nearest way is the autoroute, the generated trip begins mid-motorway, leaves at the next interchange, and re-enters the opposite carriageway. The toll it records is not the toll a real trip pays, so every downstream consumer of the route set inherits the error.

## What Changes

- **BREAKING** Route endpoint eligibility gains a reachability test. A `place` node is a candidate only when its nearest routable segment is within 50 m and is not `motorway`, `motorway_link`, or `trunk_link`. Roughly 53 % of the current candidate catalogue becomes ineligible.
- **BREAKING** `data/route_set.yaml` is regenerated. 553 of its 787 routes use an endpoint that is no longer eligible, and 783 of its 1340 coverage targets must be found again.
- The route search drops a resumed route whose endpoints have become ineligible, instead of keeping it because it still covers something.
- Step 3 persists the `highway` value of each candidate's nearest routable segment, because `/nearest` returns a way name and not its class, and 6 of the 16 endpoints in the report snapped onto unnamed ways.
- Step 5 asserts that no route's `covers` resolves two booths to one gare, and fails the build with a table of violations when it does.
- The distance threshold is a single named constant, and the design records 100 m and 200 m as a fallback ladder for the case where 50 m leaves previously covered targets uncoverable.

## Capabilities

### New Capabilities

None. The behaviour lands as new requirements on three existing capabilities.

### Modified Capabilities

- `toll-booth-inventory`: the "Route endpoint candidates" requirement gains a reachability condition alongside the existing tag test, and a new requirement covers persisting the nearest-segment class.
- `route-set-generation`: a new requirement states that endpoints are places a car can start and finish a trip; the resume behaviour is narrowed to drop routes whose endpoints are no longer eligible.
- `vinci-gare-mapping`: a new requirement forbids a route from paying one gare twice and makes a violation fail the step.

## Impact

- `builder/build_osm_toll_booths.py` — persists the nearest-segment class map.
- `builder/build_route_set.py` — applies the eligibility test to `PlaceCollector` output; narrows `load_existing`.
- `builder/build_vinci_toll_booths.py` — adds the duplicate-gare assertion.
- `Makefile` — step 3 gains an output; step 4 gains an input. Step 3 does not gain a dependency on the OSRM graph.
- `data/route_set.yaml`, `data/uncovered_booths.json`, `data/vinci_toll_booth.yaml` — all regenerated.
- A full rebuild of the route set is required. Resuming from the existing file is not useful at 30 % survival.
