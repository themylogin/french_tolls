## Context

See proposal.md — Why.

Every number below was measured against `data/plazas.osm.pbf` and the 1231-group inventory, or against one full replay of the 747-route set through the Ulys placemark service. The operator data is used as independent evidence about grouping; it is not an input to the pipeline this change touches.

## Goals / Non-Goals

**Goals:**

- Make the grouping graph the graph a route between two place nodes actually sees.
- Stop merging booths that serve opposite directions of a two-way road.
- Record which way a route went through a booth, and treat the two directions of a bidirectional booth as separate things to cover.

**Non-Goals:**

- The gare mapping. That is `map-booths-to-vinci-gares`, downstream of this.
- Changing which booths enter the inventory. `classify()` and the through-road filter are untouched, and `data/excluded_booths.json` is unchanged.
- Reducing the uncovered count. It is expected to rise, and that is information rather than regression.

## Decisions

### Build the grouping graph over `THROUGH_CLASSES`

`group_booths` builds its graph over `ROUTABLE`, which adds `unclassified`, `residential`, `living_street`, `service`, `road` and `track` to the through classes. `GraphBuilder.way` reads only `highway`, `oneway` and `junction`, so `access=private` and `motor_vehicle` are ignored outright.

At Saint-Michel-de-Maurienne the ramp booth `5923855974` and the mainline booth `5923855978` share six predecessors. All six are `service` or `track`. The 640 m path between them is roughly twenty three-metre hops across the toll forecourt, passing an `access=private` way, before joining the ramp. The real car route is kilometres.

The project already has a definition of "a road a route between two places uses" — `THROUGH_CLASSES`, used by `classify()` to drop 282 booths as car-park barriers and forestry gates, and backing the inventory requirement of the same name. Grouping then contradicted it by using the wider set. Restricting the graph closes the gap.

Measured:

| | current | through-roads only |
|---|---|---|
| groups | 1231 | 1302 |
| multi-member groups | 161 | 118 |
| groups containing a mutually reachable pair | 44 | 2 |
| groups containing a one-way sequential pair | 22 | 0 |
| **operator-confirmed conflicts still merged** | **17 of 17** | **0 of 17** |

Of the 66 groups that split, 18 mix a link-only booth with a mainline booth, 41 are same-class and within 50 m, and 7 are same-class and further apart. The same-class-and-close category is not suspicious: it is the signature of an entry gare beside an exit gare, and four of its members are operator-confirmed two-code cases (`09119 MACON SUD`, `09064 MONTMARAULT`, `05960 VIVY`, `04535 NIORT-S`), split exactly on the boundary the operator draws.

Alternatives considered and rejected:

- **Refuse to group any mutually reachable pair.** Rejected on evidence. The Mont Blanc plaza is four `trunk_link oneway=yes` lanes 5–15 m apart — genuine alternatives that must group — and every pair is mutually reachable through a turnaround loop at the portal. Broglie-Orbec is two gares 660 m apart that must not group, and is also mutually reachable. Reachability does not discriminate.
- **Refuse to group a link-only booth with a mainline booth.** Catches 4 of the 17. It was pattern-matching on a symptom of the service-road defect, and becomes unnecessary once the graph is restricted.
- **Filter on `access` as well.** Would be more correct in general, but `service` and `track` disappear from the graph anyway, so it buys nothing here. Worth revisiting only if a case appears on a through-class way.

### Never group a booth on a two-way through road

The inventory spec keeps opposite carriageways apart by relying on one-way restrictions:

> the one-way restrictions give them no common predecessor and successor

On a bidirectional slip road tagged `oneway=no` there are no restrictions to rely on, and the two gares of one interchange merge. `81055576` and `1042834566`, both named `Broglie-Orbec`, are 660 m apart on `motorway_link oneway=no` and are mutually reachable in both directions.

The rule is expressed against what `GraphBuilder` already computes at lines 154-165 — the branch where `fwd_ok and rev_ok` — rather than against the `oneway` tag, so it also covers ways with no `oneway` tag that are not one-way by class.

Measured: 52 booths qualify, 46 by an explicit `oneway=no` and 6 untagged and two-way by class. After the graph restriction, exactly **one** multi-member group contains such a booth, and it is Broglie-Orbec. Mont Blanc contains none.

The rule is blunt. A genuinely bidirectional plaza — several lanes all tagged `oneway=no` — would be split into singletons and its coverage targets would become unreachable. No such case exists in France today. This is a stated limitation, not a general truth.

### `prev_node_id` identifies the direction

For a bidirectional booth, `covers` records the node the route arrived from. Measured over the through-class graph:

```
 bidirectional booths                                     52
   with exactly 2 distinct immediate predecessors         51
   with exactly 1                                          1
   with more than 2                                        0
```

No bidirectional booth has a third approach, so the predecessor never conflates two directions and never splits one direction into two. 51 booths yield two directions and one yields a single direction.

Alternatives considered:

- **A boolean or a compass bearing.** A bearing is geometric and unstable on a curved approach; a boolean needs an arbitrary choice of which side is "forward".
- **The next node instead of the previous one.** Equivalent. The predecessor is chosen because it is what the route search already has in hand when it walks the traversed node list.

### A bidirectional booth is one coverage target per drivable direction

The coverage unit becomes `(booth, prev_node_id)` for bidirectional booths and `(booth, null)` for the rest. This is the point of recording direction at all: passing a bidirectional gare northbound does not pay the southbound toll.

Consequences, accepted deliberately:

- The set-cover core of `build_route_set.py` changes its universe from group representatives to direction-qualified targets: 1354 rather than 1303.
- `data/uncovered_booths.json` must express direction, so its shape changes.
- The uncovered count rises above the current 9. Some directions of some bidirectional booths are not reachable by any generated endpoint pair, which is the same class of result the existing uncovered report exists to record.

The alternative — record the direction descriptively and keep coverage per booth — was rejected because it would leave the file claiming a bidirectional gare is covered when only one of its two tolls has ever been driven.

### The inventory format carries `latlon`, `parent_id` and `bidirectional`

`toll_booths` and `aliases` become mappings from node id to a detail block. Every entry carries its **own** position, aliases included: group members lie a median 15 m and up to 735 m apart, and any consumer matching against individual lanes needs the lane, not its representative.

This supersedes the format change previously drafted in `map-booths-to-vinci-gares`; that change's `toll-booth-inventory` delta is dropped, and it rebases on this one.

## Risks / Trade-offs

- **99 booths change group and every representative may shift**, invalidating every `covers` id in `data/route_set.yaml`. → The route set is regenerated in full rather than extended. The regeneration is also the correctness test below.
- **A split may be wrong — two real lanes of one barrier separated.** → Then no route can cover both, because a route through a plaza passes exactly one lane, and those targets stay uncovered forever. So an uncovered count far above 9 is the signal. 17 of the 66 splits are already confirmed correct by operator data; the other 49 rest on the rule alone.
- **Direction-qualified coverage may be unachievable for some booths.** → Reported in `data/uncovered_booths.json` rather than hidden, which is what that file is for.
- **The two-way exclusion is blunt.** → Stated above. One group affected today.
- **Two unarchived changes touched `toll-booth-inventory`.** → Resolved by moving format ownership here and dropping the delta from `map-booths-to-vinci-gares`.

## Migration Plan

1. Change `booth_groups.py`; regenerate `data/osm_toll_booths.yaml`; check the group count lands near 1303 and that the 17 known conflicts are split.
2. Change `build_route_set.py`; regenerate `data/route_set.yaml` from scratch; compare the uncovered count against 9 and read the difference before accepting it.
3. Drop the `toll-booth-inventory` delta from `map-booths-to-vinci-gares` and rebase its gare-matching step on the new `covers` shape.

Rollback is `git revert` plus a regeneration; both artifacts are committed, so the previous pair is always recoverable.

## Outcome

Regeneration produced 1303 groups and 786 routes covering 1340 of 1353 targets. Uncovered went from 9 to 13, and every difference is accounted for:

| | |
|---|---|
| the same 9 booths as before | international borders and private sites; unchanged |
| `7795369636` | split from Arc 1800, 54 m away, which was already uncovered |
| `1154852457` | a slip road 585 m from its old siblings, merged into them by the service-road artefact. Both directions uncovered: no route ever passed it, and the old grouping hid that |
| `13719126553` | a real plaza lane 41 m from its sibling, split because its only inbound edge is a `service` way. The one false positive, and the only booth in 1565 with no through-class predecessor |
| `1581498325` | an **OSM data error**, not a pipeline defect. Beaurepaire is two booths 14 m apart on two parallel one-way carriageways: `2199932050` on way `209825479` (`oneway=yes`) and `1581498325` on way `209825480`, tagged `oneway=no` when the carriageway is one-way. The bad tag makes the booth look bidirectional, so it claims two targets while only one direction is drivable. Correcting the tag upstream removes the flag and the phantom target together. |

A filter that dropped approaches unreachable except through their own booth was written and then **removed**: it closed this one case, but it was compensating in code for a single mis-tagged way rather than fixing the data, and it changed no other booth's target count. The uncovered report showing the phantom direction is the honest reading of the extract as it stands.

49 of the 52 two-way booths have both directions driven. No evidence of widespread wrong splits: the 66 groups that split produced one bad outcome, and 17 of them are confirmed correct by operator data.

## Open Questions
- Whether the 2 residual groups containing a reachable pair — Mont Blanc, correctly grouped, and one other — need any further treatment. Neither blocks this change.
- `13719126553`, `7795369636` and `1154852457` are left as they are. They are individually diagnosed above and deliberately deferred to later proposals rather than patched with ad hoc rules here.
