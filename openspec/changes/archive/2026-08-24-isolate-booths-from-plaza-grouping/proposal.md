## Why

Booths `25315120` and `26024647` sit 222 m apart on the A8. They share a predecessor and a successor within the reach radius, so the grouping rule makes them one group — and it is right: they are alternative lanes of one plaza. But the operator charges them as two different gares, `06013 ANTIBES EST` and `06024 SOPHIA`, confirmed by querying the placemark service at each node.

One group is one coverage target and one gare. Two gares cannot fit in it. Whichever lane a route happens to use decides the group's gare, and the next route that uses the other lane makes the mapping step fail with a conflict it has no way to resolve.

The grouping is topologically correct and its consequence is still wrong. Nothing in the override file can say that: `parent_id` merges a booth into a group, and `toll-booth-inventory` states outright that a group cannot be split by fiat.

## What Changes

- `parent_id: null` in the override file keeps a booth in a group of its own, exempt from the topological pairing rule. It is the inverse of `parent_id: <id>`.
- **BREAKING** The rule that a group cannot be split by hand is removed. A group can now be split, in one direction only: a named booth is held out, and the rest of its group stays together.
- An isolated booth is excluded from the pairing relation in both positions rather than unpicked afterwards. Grouping is a transitive closure, so a booth left in the relation still chains its neighbours together even if it is later detached.
- Stating `parent_id: null` for a booth that another booth names as its `parent_id` target is an error, whichever end states it.
- Isolated booths are checked against the extract like every other override.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `toll-booth-inventory`: the "Forced group membership" requirement gains the null spelling and drops the claim that a group cannot be split by fiat.

## Impact

- `builder/overrides.py` — new `isolated` set; `parent_id: null` no longer lands in `forced` as a null parent, which today fails with "names parent None, which is not in the inventory".
- `builder/booth_groups.py` — `group_booths` takes `isolated` and skips those booths when pairing.
- `builder/build_osm_toll_booths.py` — passes `ov.isolated`.
- `data/osm_toll_booths_overrides.yaml` — carries the first such entry, for `26024647`.
- `data/osm_toll_booths.yaml` — 1295 groups and 261 aliases, was 1294 and 262. `26024647` moves from `aliases` to `toll_booths` and becomes a coverage target.
- `data/route_set.yaml` — regenerates incrementally. Existing routes are re-queried, so `covers` recomputes against the new grouping; only the new target needs a fresh search.
- `data/vinci_toll_booth.yaml` — the `25315120` record is stale, having been derived from the `26024647` lane, and must be removed so it is re-derived.
