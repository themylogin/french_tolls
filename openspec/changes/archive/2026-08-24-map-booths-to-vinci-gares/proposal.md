## Why

The pipeline produces an OSM toll booth inventory and a route set that covers it, but OSM node ids are useless to a tariff consumer. Toll operators identify a gare by their own code, and the VINCI Ulys `placemark` service returns those codes for a driven route. Replaying the existing route set against that service resolves the whole inventory to operator codes in one pass, with no new routing work.

## What Changes

- Add a fifth pipeline step, `build_vinci_toll_booths`, which replays every route in `data/route_set.yaml` against the Ulys `placemark/v2/legs` service and writes `data/vinci_toll_booth.yaml`, mapping each OSM booth group to the operator gare it corresponds to.
- Depends on `fix-booth-grouping-and-direction`, which owns the inventory format this step reads — per-node `latlon`, `parent_id`, and the `bidirectional` flag — and the direction-carrying `covers` shape. That change must land first.
- **BREAKING** — the pipeline grows from four named steps to five, and the new step always executes rather than being skipped when its output exists. The step is resumable: it records the routes it has already queried and re-queries none of them, so a completed run performs no requests.
- Add `ULYS_SUBSCRIPTION_KEY` to `.env` and to the `builder` service environment, with a guard that fails before any work when it is unset.
- **BREAKING** — a booth is never recorded as having no gare. Every booth a processed route drove through must map to one, or the step fails and tabulates those that did not, with the evidence needed to decide what to do about each. Booths the override file marks `absent_*`, and booths an override has since removed from the inventory, are exempt.
- Read the override file for gares stated by hand, so a gare the operator places beyond any usable threshold can be resolved by operator number rather than by distance.

## Capabilities

### New Capabilities
- `vinci-gare-mapping`: how OSM booth groups are resolved to VINCI Ulys gare codes — the request contract, the spatial correspondence rule, the resume contract, and the format of `data/vinci_toll_booth.yaml`.

### Modified Capabilities
- `build-pipeline`: a fifth named step is added; the skip-when-output-exists requirement is reworded so a resumable step may always execute; the `.env` contract gains the Ulys subscription key.

## Impact

- `Makefile` — new `build_vinci_toll_booths` step in `all`, new guard target.
- `docker-compose.yml` — `environment:` block on the `builder` service.
- `builder/build_vinci_toll_booths.py` — new script.
- `data/vinci_toll_booth.yaml` — new committed deliverable.
- External dependency on `api-ulys.azure-api.net`, reached with a subscription key. The step needs network access; no other step does.
