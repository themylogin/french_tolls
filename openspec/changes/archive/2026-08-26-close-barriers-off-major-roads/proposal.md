## Why

The stock car profile treats `barrier=gate` and `barrier=lift_gate` as passable for a 60-second penalty, wherever the gate stands. On a service road, a driveway or a track that gate is locked in reality. The router does not know it, so it drives through: a route that leaves the toll network by an access track is scored as drivable, and every step that trusts the router — the route search, the booth sides probe, the direct pricing survey — trusts a road nobody can take.

The cost is visible in `data/nodes_blacklist.yaml`. That file exists for connections the map is wrong about, but entries were being added to it to close one gate at a time where a route escaped through a service road. Seven of its nine ids have just been removed as excessive; the two that remain are real map defects. Closing the gates by class removes the reason those seven were ever written.

## What Changes

- The patched routing profile keeps the gate penalty only where an allowed highway class carries the gate. Every other `barrier=gate` and `barrier=lift_gate` node becomes an impassable barrier, which is what the stock profile already does with every barrier value it does not whitelist.
- The allowed classes are `motorway`, `trunk`, `primary`, `secondary`, `tertiary`, `unclassified`, `residential`, `living_street`, and the `_link` form of the first five. A gate on `service`, `track`, `driveway`, `path` or any other class is closed.
- A gate node carried by ways of several classes is open when at least one of them is allowed, so a gate tagged on the junction of a driveway and a residential street does not cut the street.
- A gate node with a resolvable access tag keeps stock behaviour. `access=private` closes it as before, `access=yes` opens it as before, and the class rule does not reach it. This change touches the `barrier_penalties` path alone.
- The OSRM setup step gains a pass over `data/france-latest.osm.pbf` to work out which gates an allowed class carries, and hands that set to `builder/patch_car_profile.py`. No new file enters the repository: the set is derived from the extract and lives only in the patched profile under `$(OSRM_OPTIMAL_PATH)`.
- The OSRM setup stamp additionally depends on `builder/patch_car_profile.py`. The class policy is compiled into the graph exactly as the blacklist is, so editing it must invalidate the graph for the same reason.
- `data/nodes_blacklist.yaml` keeps `675137755` and `980135734` and loses the seven ids that only closed a gate escape.
- The route set, the gare mapping, the prices, the booth sides and the direct prices are regenerated against the new graph. The expectation is that none of them changes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `build-pipeline`: the setup step's profile patch gains a second rule — a gate is passable only where an allowed highway class carries it — and the setup stamp keys to the patch script as well as to the blacklist.

## Impact

- **Modified**: `builder/patch_car_profile.py` (a second injected rule and the gate scan), `Makefile` (the stamp prerequisite and the scan's inputs), `data/nodes_blacklist.yaml` (seven ids removed).
- **Cost**: one full re-preprocessing — 30 to 40 minutes — plus a few minutes for the PBF pass, and a run of every downstream step. Nothing is asked of the operator: steps 5, 6 and 8 are resumable and issue no request while their outputs are complete.
- **Consequence**: routes that escaped a toll road through a locked gate cease to exist, so the router answers with the fastest genuinely drivable route instead. If any downstream artefact does change, the run stops and reports the difference before any Ulys request is issued.
- **Not in scope**: gates that carry an explicit access tag; barrier values other than `gate` and `lift_gate`; which of the two remaining blacklist ids are still needed.
