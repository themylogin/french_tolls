## Context

See proposal.md — Why.

The grouping rule pairs two booths when they share a predecessor and a successor within `MAX_REACH_M` (1000 m), and takes the transitive closure. For `25315120` and `26024647` the shared nodes are exactly one each:

```
  shared predecessor  26024921
  shared successor    4060409828
  neither booth is on a two-way road, so the two-way exemption does not apply
```

That is a correct reading of the road network. Both are lanes a car can choose between. The operator nonetheless charges them separately, which was confirmed by querying the placemark service at each node's position — 0.5 m and 0.1 m matches on the two comparable cases, so this is not positional ambiguity.

Two other groups have members more than 150 m apart. Both were checked against the operator and both are a single gare:

```
  27509156 / 31415199   214 m   both 09125 DIJON SUD
  35675144 / 1801078049 249 m   both 09101 FLEURY-EN-BIERE
```

So distance does not predict the defect and cannot be the rule.

## Goals / Non-Goals

**Goals:**

- Let a booth be held out of grouping by hand, stated once in the file that already holds every other hand-made decision.
- Keep the statement narrow: one booth out, the rest of its group intact.
- Fail loudly on a contradictory pair of overrides.

**Non-Goals:**

- Detecting this case automatically. There is no signal in OSM for "the operator bills these lanes separately"; it is only observable by asking the operator, which costs a request per route.
- A general group-editing facility. There is no way to state arbitrary partitions, only to remove one booth.
- Changing how the gare mapping resolves a conflict. That remains an error; this change removes the cause in this instance rather than adding a resolution rule.

## Decisions

### The spelling is `parent_id: null`

It reads as the inverse of `parent_id: <id>` and needs no new key. `overrides.py` already branches on the presence of `parent_id`, so the null case is one condition rather than a new field with its own validation.

*Alternative considered:* a new `type: isolated` value. Rejected because `type` is about what a booth *is* — ignored, absent from the operator, a border crossing — while this is about where it sits in the grouping, which is what `parent_id` already governs.

### Isolation happens inside the pairing loop, not after it

The isolated booth is skipped in both positions of the pair test. Removing it from the result afterwards would not work: grouping is a transitive closure, so `A—X—B` still leaves `A` and `B` in one group after `X` is detached. Skipping `X` in the relation means the chain never forms.

This matters for wide plazas, where the rule deliberately merges outer lanes only through the ones between them.

### Forced membership stays a post-pass; isolation does not

`forced` is applied after the rules run, because its target must be a representative *in the grouping the rules produced*. Isolation cannot wait for that, per the previous decision. The two are therefore checked against each other explicitly, in `overrides.load` for the file-level spelling and again in `group_booths` for the case where a caller passes both directly.

## Risks / Trade-offs

**A hand-held-out booth is one more thing that can go stale.** → It is checked against the extract like every other override, so a retagged or deleted node stops the step rather than silently doing nothing.

**Isolation is invisible in the output.** → The inventory records the result, not the reason. Mitigated by the override file being the single place such decisions live, and by the step printing the count of booths held out.

**Someone isolates a booth that is a genuine lane-mate.** → The consequence is a spurious extra coverage target: the route search must then find a route through that specific lane, and may fail. It shows up as an uncovered target rather than as silent wrongness.

## Migration Plan

1. Run step 3. The inventory becomes 1295 groups and 261 aliases; `26024647` moves from `aliases` to `toll_booths`.
2. Run `make update_route_set`. Existing routes are re-queried, so every `covers` recomputes against the new grouping. Only the new target `26024647` needs a fresh search.
3. Remove the `25315120` entry from `data/vinci_toll_booth.yaml`. It records `06024 SOPHIA`, which was read from the `26024647` lane and is wrong for the group as it now stands. The route that covers `25315120` in the current route set has not been queried yet, so the correct gare is re-derived without discarding anything else.
4. Run step 5. It resumes from its own output and queries only outstanding routes.

Rollback is `git checkout` of the builder sources and the override entry, then step 3 again.
