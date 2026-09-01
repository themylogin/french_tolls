## Why

Step 7 tells the toll side of a two-way booth from the free side by routing the booth against targets and reading which adjacent node each route uses. Péage de Thèze on the A 65, booth 986537073, gare 18009, does not settle: all 2 568 of its routes leave by the same side.

```
booth targets  admitted, side B                     66
booth targets  another booth in between, side B  2 484
place targets  another booth in between, side B     18
side A                                               0
```

Side A is not broken. Node 10977821568 carries no barrier, is not blacklisted, sits on a two-way `motorway_link`, and the router drives it in both directions when asked. It is simply never the fast way to any target the step offers: side A is a slow local road, side B is the A 65, and the nine places THEZE qualifies for are all reached past another barrier and discarded.

**The targets are drawn from too small a pool.** `load_places` reads `data/route_set.yaml`, which lists the 745 places the coverage search happened to use as route endpoints. The place catalogue in `data/filtered.osm.pbf` holds every `place=` node in the country. Lalonquette — `place=village`, population 257, node 1825323182 — sits 2.0 km due north of THEZE, the direction side A leads, and is not in the route set. Routed against it, the sweep settles the side immediately, in both directions, by its own rules:

```
booth -> Lalonquette   side = A   verdict = outside   1 booth on the route
Lalonquette -> booth   side = A   verdict = outside   1 booth on the route
```

That is the label the file carried before the step was last re-run. A village 2 km up the local road cannot be beaten by the motorway; the route set's places, all further off, can be.

**And an unsettled booth is silently repriced as a barrier.** `build_vinci_direct_prices.load_sides` classifies on presence alone:

```python
if not ins or not out:
    barriers.add(group)
```

THEZE has `inside_nodes` and no `outside_nodes`, so step 8 files it as a barrier and `outstanding_for` drops it — *"a barrier is a booth no journey ever enters or leaves at"* — discarding every pair that names it before any routing. Step 9 is affected too: with no `inside_nodes` for it, the extent step applies no side restriction and grows a region through the toll side.

The artefact does carry the distinction, and the capability already prescribes how to read it: an unsettled booth is *"distinguishable from a settled one by the absence of its remaining nodes from both lists, checked against the inventory's `adjacent_nodes`"*. Measured, that check separates them exactly — THEZE leaves one of two adjacent nodes in neither list, while both genuine barriers list both of theirs. No consumer performs it.

## What Changes

- Where a side receives no admitted observation from the sweep, the system SHALL retry it against places drawn from the inventory's own place catalogue rather than from the route set, and SHALL settle it by the rules already in place.
- The catalogue SHALL be used only for sides the sweep leaves unobserved. Every booth the sweep settles today settles identically, from the same targets.
- A side settled from the catalogue SHALL be reported apart from the sweep's counts, so the artefact says which sides rest on it.
- **A consumer SHALL NOT treat a booth as settled when the inventory records an adjacent node that appears in neither list.** `build_vinci_direct_prices` SHALL distinguish an unsettled booth from a barrier and SHALL report it as unsettled; `build_toll_extent` SHALL leave an unsettled two-way booth unmeasured rather than deriving a region with no side restriction.
- **Not changed**: the verdict rules, the between-booth filter, the settled states, the output format, and the sweep itself.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `bidirectional-booth-sides`: the place targets gain a catalogue fallback for unobserved sides, and the report distinguishes a side settled by it.
- `vinci-direct-pricing`: a booth with an adjacent node in neither list is unsettled, not a barrier, and is reported as such.
- `toll-road-extent`: an unsettled two-way booth is left unmeasured rather than measured without a side restriction.

## Impact

- **Modified**: `builder/build_booth_sides.py` (the catalogue fallback and its reporting), `builder/build_vinci_direct_prices.py` (`load_sides` gains the inventory check and a third return), `builder/build_toll_extent.py` (skips an unsettled two-way booth), `data/bidirectional_booth_sides.yaml` (THEZE regains `outside_nodes`).
- **New input to step 7**: `data/filtered.osm.pbf`, which step 3 already produces and step 4 already reads. It is read only when a side is unobserved.
- **Runtime**: nothing extra when every side settles. For an unobserved side, one pair of routes per catalogue place offered to it.
- **Unchanged**: every booth the sweep settles, and therefore steps 8 and 9 for all of them.
- **Working tree note**: `data/bidirectional_booth_sides.yaml` currently holds the degraded answer — THEZE lost `outside_nodes` when step 7 was re-run during the scenario 2 rebuild. The committed file has the right values, and implementing this change reproduces them.
