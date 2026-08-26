## Context

See proposal.md — Why.

What the stock profile does with a barrier node, in `process_node`:

```lua
local barrier_penalty = profile.barrier_penalties[barrier]   -- gate = 60, lift_gate = 60

if not profile.barrier_whitelist[barrier]
          and not rising_bollard
          and not flat_kerb
          and not highway_crossing_kerb
          and not audible_fence
          and not barrier_penalty        -- <-- the gate's exemption
          or restricted_by_height then
  obstacle_map:add(node, Obstacle.new(obstacle_type.barrier))
end

if barrier_penalty then
  obstacle_map:add(node, Obstacle.new(obstacle_type.gate,
                                      obstacle_direction.both, barrier_penalty, 0))
end
```

Every other barrier value the profile does not whitelist is already impassable. `gate` and `lift_gate` are exempt because they have a penalty, and the exemption is unconditional.

The extract carries 435 955 such nodes. Under the rule this change adopts:

```
on an allowed class only         15 004
on both an allowed and a disallowed class      9 804   -> open:   24 808
on a disallowed class only      351 802
on no highway way at all         59 345               -> closed: 411 147
```

The `barrier` branch is reached only when the node's access tag does not resolve; `access=private` and `access=yes` are decided above it and stay that way.

## Goals / Non-Goals

**Goals:**

- A gate off the through-road network is impassable, so no route can leave a toll road through one.
- A gate on the through-road network behaves exactly as it does today.
- The rule is compiled into the graph, and editing it cannot be silently ignored.
- Every downstream artefact is reproduced against the new graph and compared, before any Ulys request is spent.

**Non-Goals:**

- Any change to how a route is judged once returned. Blockers, sides and tariffs are untouched.
- Any change to `barrier_whitelist`, to barrier values other than `gate` and `lift_gate`, or to the access-tag branch above them.
- Deciding which of the two remaining blacklist ids are still needed.

## Decisions

### The class cannot be decided inside the profile, so it is precomputed

`process_node` receives a node and nothing else. OSRM's Lua API offers no way from a node to the ways that carry it, and the two facts this rule needs are on opposite sides of that boundary.

Three ways round it were tried against the real image (`ghcr.io/project-osrm/osrm-backend:26.8-debian`) on a hand-built extract:

- `way:get_nodes()` exists and returns the way's nodes, and `obstacle_map:add()` accepts one from inside `process_way` — the obstacle is collected. But those objects are node *references*: `n:id()` works, `n:get_value_by_key("barrier")` fails with `attempt to call a nil value (method 'get_value_by_key')`. The way pass can see which nodes a service road carries; it cannot see which of them is a gate.
- Recording gate ids in `process_node` and reading them back in `process_way` fails for a second reason: osrm-extract holds one Lua state per thread, so a table filled on one thread is not the table another thread reads. The result would depend on how the parser sharded the file.
- `exclude=` classes and location-dependent GeoJSON are both about ways and areas, not about a node's neighbourhood.

So the answer is computed before extraction and handed to the profile as data — the mechanism already in place for `data/nodes_blacklist.yaml`.

### The open gates are listed, not the closed ones

The injected table holds the 24 808 nodes an allowed class carries. A gate that the scan does not reach — because it is on no way, because a class is unknown, because the scan is wrong — is closed.

That is the safe direction for this change: "these gates are locked" is the fact being encoded, so a miss should leave a gate shut rather than open a road that is not there. It is also, by a factor of seventeen, the smaller table: about 500 KB of Lua against 8 MB, which matters because osrm-extract parses the profile once per thread.

### The check goes on the penalty, not on the barrier

The injected line clears the penalty for a node that is not in the open set:

```lua
local barrier_penalty = profile.barrier_penalties[barrier]
-- >>> gates_on_through_roads, injected
if barrier_penalty and not open_gate_nodes[node:id()] then
  barrier_penalty = nil
end
-- <<< gates_on_through_roads
```

Everything after it is the stock profile. A closed gate falls through the `not barrier_penalty` arm and becomes the same impassable barrier the profile already makes of a `barrier=block`, and the `Obstacle.new(obstacle_type.gate, ...)` line below is skipped because the penalty is gone. Nothing new decides what a barrier means; the change is only which gates keep the exemption.

The alternative — adding `Obstacle.new(obstacle_type.barrier)` in a separate injected block at the top of `process_node`, as the blacklist does — would leave the gate obstacle to be added below as well, and the node would carry two contradictory obstacles.

The anchor line is matched rather than assumed, and the patch aborts when it is absent or appears more than once, exactly as the existing patch does with `function process_node(...)`.

### The gate values come from the profile's own table

The patch reads the keys of `barrier_penalties` out of the pristine `car.lua` rather than restating `gate` and `lift_gate`. If a future image penalises a third value, the scan covers it; if the table is gone, the patch aborts instead of injecting a rule that governs nothing.

### The scan reads the extract, in one pass, inside the setup step

`patch_car_profile.py` gains `--pbf` and does the scan itself. It already owns the question "what must the profile say"; splitting the scan into a separate step would add an intermediate file that nothing else reads and that can go stale against the extract beside it.

One pass, not two. A sorted PBF carries all nodes before any way, so a handler that collects gate ids from nodes and tests way members against that set as the ways arrive is complete when the pass ends. The measurement above cost about twenty minutes as two passes; one pass halves it. The file's sort order is declared in its header and is checked before the pass, because an unsorted file would silently produce a short list — and a short list means gates closed, which is the direction that does not announce itself.

Rejected: carving a small intermediate with `osmium tags-filter` first (the carve is the same pass, plus a file); a committed list of node ids (400 KB of ids in git that drift against the extract with every download).

### The stamp keys to the patch script

`$(OSRM_STAMP)` already depends on `data/nodes_blacklist.yaml` by content. The class list and the scan now live in `builder/patch_car_profile.py`, so that file joins it. Editing either changes what the graph means, and a graph that disagrees with the tree it came from is the failure this dependency exists to prevent.

The extract is not added: it stays order-only, as it is today. Re-downloading France is a deliberate act with its own consequences, and keying half an hour of preprocessing to a 4.8 GB file's timestamp is the trap the order-only rule was written for.

### Nothing downstream changes shape, so nothing downstream is edited

No consumer of the router learns about gates. The route search, the sides probe and the direct pricing survey all ask the router a question and trust the answer; this change alters the answer, not the question. The work downstream is regeneration and comparison, which is where the risk in this change actually sits.

## Risks / Trade-offs

**A gate that is genuinely open closes a road** → 411 147 nodes become impassable, and some of them carry a road a car really can drive: a residential street mistagged `highway=service`, a gate marked but unlocked. The mitigations are the any-allowed-way rule for junction nodes, the untouched access branch (`access=yes` still opens a gate on any class), and the fact that these are barriers on ways the profile already discourages. The blunt check is the one the tasks run: 781 routes reproduced, and every booth still reachable.

**A booth becomes unreachable** → a booth approached only through a gated service road loses its approach, and the route set drops it. The route set reports uncovered booths (8 today) and that number is the detector; the tasks compare it before anything downstream runs.

**The comparison itself can cost requests** → the direct pricing step prices a pair as soon as it judges it clean, so a pair that flips from rejected to clean on the new graph is asked about immediately. A rebuilt rejection database re-judges roughly 238 000 pairs. The tasks therefore rebuild it against copies and under `--limit`, count the flips, and report before a full run.

**Twenty minutes become a permanent part of the setup step** → the scan runs on every graph rebuild, on top of 30 to 40 minutes of preprocessing. Halved by the single pass, and paid only when the graph is rebuilt.

**A second Lua table in the profile** → the patched profile grows to about half a megabyte of node ids, parsed once per extract thread. Measured against the 435 955-node total rather than assumed; the closed-set alternative would have been sixteen times larger.

## Migration Plan

1. Patch and scan land; `make setup_osrm` rebuilds the graph because the stamp's new prerequisite is newer than it.
2. `data/nodes_blacklist.yaml` is already reduced to the two ids that are real map defects, so the same rebuild adopts both changes at once.
3. The route set is regenerated into a copy and diffed. If it differs, the run stops there and reports — steps 5, 6 and 8 are not started, and no Ulys request is issued.
4. If it matches, the gare mapping and the pricing step run and must ask for nothing, the sides are reproduced, and the direct pricing comparison runs against copies under `--limit`.

Rollback is `git revert` plus one more `make setup_osrm`: the graph is derived, and the committed artefacts are what they were.

## Open Questions

None.
