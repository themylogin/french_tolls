## Why

Eight booth groups carry no gare. No route in `data/route_set.yaml` reaches them, so step 5 never asks the operator about them and step 6 never prices them. They are the booths at the Spanish and Italian borders and at the Fréjus tunnel, where the trip that would cross them ends outside France and no pair of French place nodes produces it.

The inventory therefore accounts for its 1295 representatives as 1275 mapped, 12 marked `absent_*`, and 8 unexplained. The eight are already named by hand in `data/osm_toll_booths_overrides.yaml` with `type: enter`, `type: exit`, or `type: passthrough`, and they are exactly the contents of `data/uncovered_booths.json`.

The operator does carry all eight. Nine probe requests confirmed it, and every gare returned is one the mapping does not hold today.

## What Changes

- The extraction step publishes `passage` on every booth the override file types `enter`, `exit`, or `passthrough`: the node before it and the node after it, in driven order, taken from the plaza graph the grouping already builds.
- The gare mapping step submits a three-point leg for each such booth, formed from `passage[0]`, the booth's own `latlon`, and `passage[1]`. It sends that leg to the placemark service exactly as it sends a route geometry.
- The returned placemark is matched positionally against that one booth group, under the existing 2.5 m and 10 m thresholds and the existing hand-stated-gare fallback. A leg that returns no placemark, or one that matches nothing, stops the run.
- The step records each stub in its own `routes` resume list as `{from: <booth>, to: <booth>}`, so a completed run still issues no request.
- **BREAKING** for the specs, not for any consumer: `enter`, `exit`, and `passthrough` are no longer inert. `toll-booth-inventory` currently states that they leave the inventory exactly as it would have been. That was already untrue, because `overrides.py` feeds them to `group_booths` as `one_way`, and a booth on a way tagged `oneway=no` loses its `bidirectional` type. This change states what they do.

`data/route_set.yaml` is untouched. It is a coverage set of trips a car drives, and a stub is neither.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `toll-booth-inventory`: publishes `passage` for border-typed booths; the requirement that border types are inert is replaced by one that states their two effects.
- `vinci-gare-mapping`: the step may synthesise a leg for a border-typed booth, which the current specification forbids outright; adds the matching, resume, and completeness rules for such a leg.

## Impact

Code:

- `builder/build_osm_toll_booths.py` — write `passage`
- `builder/booth_groups.py` — return the directed neighbours it already computes in `GraphBuilder.fwd` and `GraphBuilder.rev`
- `builder/build_vinci_toll_booths.py` — encode a precision-6 polyline, submit the stub, reuse `process_route`, extend the drift check and the completeness check

Data:

- `data/osm_toll_booths.yaml` — regenerated, gains `passage` on nine entries
- `data/vinci_toll_booth.yaml` — gains eight groups and five gares

No new pipeline input, no new container dependency, and no change to the Makefile targets. The extraction step already reads the carved plaza extract, and the mapping step already holds the placemark client.

Eight additional requests, issued once. A completed run continues to issue none.
