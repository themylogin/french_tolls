## Why

A blacklisted node is a connection that is not there on the ground. Today every consumer of the router filters such routes out afterwards — the route set discards the candidate, the booth sides discard the observation, the direct pricing step stops outright.

Filtering afterwards answers the wrong question. It establishes that the fastest route is undrivable; it does not ask what the fastest *drivable* route is. So a booth whose only approach in the graph crosses a defect becomes unreachable rather than reached another way. In the last direct pricing run that cost 211 of 335 findings on one booth, BLOIS, whose approach crosses node `2127208202`.

If the node is impassable in the graph instead, the router simply routes around it. The question every step asks becomes answerable again, and three separate filters disappear.

There is also a live regression to close. `data/nodes_blacklist.yaml` now holds the list and the override file no longer does, but `overrides.py` still reads it from the override file — so `ov.nodes_blacklist` is empty and all three consumers are currently applying no blacklist at all.

## What Changes

- The OSRM setup step copies `/opt/car.lua` out of the routing image and patches it so that every node listed in `data/nodes_blacklist.yaml` is treated as an impassable barrier. `osrm-extract` runs the patched profile.
- The setup stamp depends on `data/nodes_blacklist.yaml`. Editing the list invalidates the graph and the next `make` re-runs extract, partition and customize — roughly 30 to 40 minutes.
- `data/nodes_blacklist.yaml` becomes the file of record, read only by the setup step. It is no longer a booth override.
- **BREAKING** `overrides.py` drops the `nodes_blacklist` section, and the override file's permitted top-level keys shrink from three to two.
- The route search, the booth sides step and the direct pricing step stop filtering on it. A route the router returns is drivable by construction.
- **BREAKING** the direct pricing step loses its `blacklisted route` stop condition, and the route set loses its blacklist report.

## Capabilities

### Modified Capabilities

- `build-pipeline`: the OSRM setup step patches the profile and keys its stamp to the blacklist; the blacklist is configuration in its own file.
- `toll-booth-inventory`: the override file no longer carries `nodes_blacklist`.
- `route-set-generation`: candidates are no longer filtered against the blacklist, because the router cannot produce one.
- `vinci-direct-pricing`: a blacklisted route is no longer a stop condition.
- `bidirectional-booth-sides`: an observation is no longer discarded for touching a blacklisted node.

## Impact

- **New**: a patch step and the patched profile under `$(OSRM_OPTIMAL_PATH)`.
- **Modified**: `Makefile`, `builder/overrides.py`, `builder/build_route_set.py`, `builder/build_booth_sides.py`, `builder/build_vinci_direct_prices.py`.
- **Cost**: one full re-preprocessing to adopt it, and one per blacklist edit thereafter. Nothing is asked of the operator.
- **Consequence**: routes that were previously discarded now exist and are judged on their merits, so the route set, the sides and the prices all change. Every downstream artefact needs regenerating, and the 335 `blacklisted route` findings should become ordinary results.
- **Not in scope**: whether the nodes currently listed are the right ones. This changes how the list is enforced, not what is on it.
