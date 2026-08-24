## Why

The pipeline resolves every OSM booth group to an operator gare code, but a gare code is not a price. The Ulys `tollstation/v1/rate` service takes a list of gare passages and returns what that journey costs — a single amount for a barrier passed in open flow, and one amount per entrance/exit pair for a closed section. Replaying the gare codes the existing route set already carries turns the inventory into a priced one, with no routing work and no second placemark request.

## What Changes

- Add a sixth pipeline step, `build_vinci_prices`, which submits the gares of every route in `data/route_set.yaml` to the Ulys `tollstation/v1/rate` service and writes `data/vinci_price.yaml`, classifying each OSM booth group as `passthrough`, `enter`, `exit`, or `bidirectional` and recording what it charges.
- **BREAKING** — `data/osm_toll_booths.yaml` replaces `bidirectional: true` with a `type` field, and adds `gantry` to it. Both name a booth whose role belongs to the journey rather than to the booth: a two-way booth is an entrance driven one way and an exit driven the other, and a free-flow gantry starts a section when another follows and is a charge of its own when none does. Such a group keeps the inventory's type in the price file and carries the charges of every role it was seen in, rather than splitting the file's key by journey.
- **BREAKING** — `covers` in `data/route_set.yaml` becomes ordered by traversal position rather than by node id. The rate service pairs passages by their position in the request, so the driven order is now part of the file's contract rather than an accident of how it was written. Every existing `covers` list is rewritten by `make update_route_set`; the contents do not change, only the order.
- The new step contacts no routing service and no placemark service. It derives the gares from `data/route_set.yaml` and `data/vinci_toll_booth.yaml` alone, so it is the first step that needs neither the OSRM graph nor the extract.
- Add `ULYS_PASSAGE_DATE` to `.env` and to the builder service environment. Every passage is submitted with that one timestamp, so the whole file is priced against a single tariff date.
- A route that traverses a booth marked `absent_enter` or `absent_exit` is not submitted at all. Omitting one passage of a closed section would make the service pair the remaining gare with the wrong partner and return a real price for a journey nobody drove. An `absent_passthrough` forms no pair and is simply left out of the request.
- A price stated by hand for an `absent_passthrough` booth is copied into the output, so a consumer reads one file rather than two.
- Add a `nodes_blacklist` section to the override file. A route the router builds through a connection that does not exist on the ground is not a route anyone can drive, and pricing it produces a charge for a journey nobody makes. Listing the node discards those routes at the source, in step 4, until the extract carries the upstream OSM fix.
- Unlike `build_vinci_toll_booths`, a booth left without a price does not fail the step. It is reported. The gap is a consequence of the skipped routes, and the route set is the place to fix it.

## Capabilities

### New Capabilities
- `vinci-price-mapping`: how OSM booth groups are priced from the VINCI Ulys rate service — the request contract, the rule that attributes a returned amount back to a booth group, the classification of a group as `passthrough`, `enter`, or `exit`, the conditions that stop the step, and the format and resume contract of `data/vinci_price.yaml`.

### Modified Capabilities
- `route-set-generation`: `covers` becomes ordered by traversal position, reproducibility is stated over the sequence rather than the set, and a `nodes_blacklist` override discards any route through a node the map gets wrong.
- `toll-booth-inventory`: `bidirectional: true` becomes `type: bidirectional`, and `type: gantry` is added for `highway=toll_gantry` booths. A booth may hold only one type.
- `build-pipeline`: a sixth named step is added; the `.env` contract gains the passage date; two steps now require network access rather than one.

## Impact

- `builder/build_osm_toll_booths.py` — writes `type` instead of `bidirectional`, and types gantries.
- `builder/build_route_set.py` — `covers` is built and written in traversal order; reads the inventory's `type`.
- `data/osm_toll_booths.yaml` — 49 entries change key, 56 gain one. Positions and grouping unchanged.
- `builder/build_vinci_prices.py` — new script.
- `data/route_set.yaml` — every `covers` list is reordered. Contents unchanged.
- `data/vinci_price.yaml` — new committed deliverable.
- `Makefile` — new `build_vinci_prices` step and a `guard-ulys-passage-date` target.
- `docker-compose.yml` — `ULYS_PASSAGE_DATE` on the `builder` service.
- `.env.example` — names the new variable.
- External dependency on `api-ulys.azure-api.net/tollstation/v1/rate`, reached with the subscription key the gare mapping step already uses.
