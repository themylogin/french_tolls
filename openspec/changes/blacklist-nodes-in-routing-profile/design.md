## Context

See proposal.md — Why.

What exists today:

```
data/nodes_blacklist.yaml     9 node ids under a `nodes_blacklist` key
overrides.py                  still parses the section from the override file,
                              which no longer has it -- ov.nodes_blacklist is empty
three consumers               build_route_set, build_booth_sides,
                              build_vinci_direct_prices, all currently filtering
                              against that empty set
```

So the blacklist is presently enforced nowhere. The route set, the sides and the prices in the tree were all produced when it *was* enforced, by the old post-filter.

The routing image carries the profile at `/opt/car.lua`. In 26.8 the relevant hook is:

```lua
function process_node(profile, node, result, relations)
  local access = resolve_access(find_access_tag(node, profile.access_tags_hierarchy), profile)
  if access then
    if profile.access_tag_blacklist[access] and not profile.restricted_access_tag_list[access] then
      obstacle_map:add(node, Obstacle.new(obstacle_type.barrier))
    end
  ...
```

## Goals / Non-Goals

**Goals:**

- A blacklisted node is impassable in the graph, so no route over one can be returned.
- One place enforces it, and the three post-filters go.
- A changed blacklist cannot be silently ignored.

**Non-Goals:**

- Revisiting which nodes are on the list.
- Any change to how routes are judged once returned. Blockers, sides and tariffs are untouched.

## Decisions

### Patch the profile rather than filter the result

A filter over a returned route answers "is the fastest route drivable". The question every step is actually asking is "what is the fastest drivable route". Those differ exactly when the fastest route is undrivable, which is the only case the blacklist exists for.

The consequence is not academic. The last direct pricing survey stopped on 335 pairs, 211 of them reaching BLOIS, whose approach crosses node `2127208202` about 175 m from the booth. Under a filter the booth is unreachable. Under an impassable node the router takes another approach and the pairs are priced or rejected on their merits.

### `obstacle_map:add(node, Obstacle.new(obstacle_type.barrier))`

The same mechanism the profile already uses for a `barrier=*` node it does not whitelist, applied at the top of `process_node` before any tag is read. It makes the node impassable rather than merely expensive, which is what "not there on the ground" means.

Alternatives considered and rejected: giving the node a huge penalty, which makes it a last resort rather than an impossibility; and `exclude=`, which is class-based and would need the class baked into ways rather than nodes.

### The stamp depends on the blacklist's content

Every other prerequisite of the OSRM setup step is order-only — presence matters, modification time does not — because re-touching an upstream file must never trigger half an hour of preprocessing.

The blacklist is the exception, and deliberately. Once compiled in, the graph *is* the blacklist. A stale graph would keep routing over a node the file says is impassable, and nothing downstream could detect it, because every step now trusts the router instead of checking. Thirty to forty minutes is the price of that guarantee, and the step announces it before starting so it is never a surprise.

### Read by the setup step alone

The blacklist stops being a booth override because it never was one. It says the map is wrong at a node; it says nothing about tolls. `overrides.py` drops the section, the override file's permitted keys fall to two, and a leftover `nodes_blacklist` there stops the step like any unknown section — which is what catches a half-finished migration.

## Risks / Trade-offs

**Every downstream artefact changes** → routes previously discarded now exist, so the route set, the booth sides and the prices are all affected. They must be regenerated in order rather than patched, and the direct pricing step will re-ask for whatever the new routes make askable. This is the intended effect, not a side effect, but it is not a small run.

**An accidental edit costs 30 to 40 minutes** → the automatic invalidation was chosen over a manual `make clean-osrm` precisely so a stale graph cannot happen. The announcement before preprocessing is the mitigation.

**A stale blacklist entry is harder to notice** → the route set used to warn when the blacklist caught nothing. Once the nodes are impassable there are no discarded candidates to count, so that warning has no data. The setup step can report how many listed nodes it actually found in the extract, which catches a typo or an id that no longer exists, but not an entry that is simply no longer needed.

**Two graphs can disagree** → anyone with a graph built before this change gets different answers from the same repository. The blacklist file is committed so the graph is reproducible, and the stamp dependency means a rebuild happens automatically, but a graph outside `$(OSRM_OPTIMAL_PATH)` is not covered.

## Open Questions

None that change the specs, the approach, or the tasks.
