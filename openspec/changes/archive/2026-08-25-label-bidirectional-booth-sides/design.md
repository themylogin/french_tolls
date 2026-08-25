## Context

See proposal.md — Why.

Measured, read-only, against the current data:

```
bidirectional booths                                    47
  that are an alias, or the parent of one                0
  adjacent set of 2 nodes, both two-way                 35
  adjacent set of 3 nodes, two one-way and one two-way  12
110 booth/neighbour edges, none whose onewayness disagrees between ways
```

The 12 are not intersections. A two-way stub through the lane meets one-way ramps forking past it, so the third node is reachable in one direction only.

## Goals / Non-Goals

**Goals:**

- Tell the toll side of a two-way booth from the free side.
- Separate the two populations hiding under one word: interchange ramps, and barriers you simply pay at.
- Fail loudly on a route that cannot be driven, rather than absorbing it.

**Non-Goals:**

- Step 7 consuming the sides. That follows once they exist.
- Re-typing the barriers. This identifies them; what `type` they should carry is a later question.
- Any use of OSM's `toll` tag.

## Decisions

### Direction of travel was the wrong quantity, and the first attempt used it

The first implementation classified during step 4: the node a route arrived from became an entrance side, the node it departed to an exit side, and a node seen both ways became both. It ran, converged, and reported zero contradictions.

It was measuring traffic flow. An ordinary interchange ramp is driven both ways, so 35 of 47 booths landed in the both-ways bucket and the output told step 7 nothing it did not already know. Zero contradictions was not evidence of correctness; the question it answered was simply easy.

That code is reverted rather than kept alongside. Two mechanisms claiming to name the sides, one of them measuring something else, is worse than one.

### The probe, and why both kinds of target are needed

```
targets   every enter/exit booth, and places spread over 12 bearing sectors within 60 km
admit     the route traverses the booth, nothing else lies between it and the target,
          and no node on it is blacklisted
side      the node immediately beyond the booth, in the direction of travel

arriving at an exit booth      -> inside      departing from an enter booth -> inside
arriving at an enter booth     -> outside     departing from an exit booth  -> outside
reaching a place, no booth     -> outside
```

Neither kind of target works alone, and this is not a tuning detail.

**Booth targets can only ever exercise the inside sides.** Booths sit on the motorway, so the router leaves by a ramp to reach any of them. Measured on CHATENOIS: all 1870 routes to booth targets left by one of the two ramps, and the two-way stub was never once the side observed. Booth-only probing left 16 of 47 booths unresolved, every one of them with `outside` empty.

**Place targets reach the free side**, because places are off the motorway. 746 place routes on top of 87 890 booth routes — under 1% more work — resolved all 16.

### The sign of the two directions

Arriving at an exit means you were holding a ticket. Departing from an exit means you have just surrendered one. The verdicts are opposites, and applying the arrival rule to both directions makes every node collect both labels.

That is exactly what happened: the first run of the probe produced 42 contradicted booths and 0 resolved, with the inside and outside sets identical on every node. It is worth stating in the spec because the failure looks like a broken premise rather than a sign error.

### A contradiction is a defect report, not noise to outvote

When the probe first ran correctly, 15 booths were contradicted — always a lone dissenter against a clear majority, 161 to 1 in one case. Three booths produced the minority observation on eleven of the fifteen: ST ROMAIN SUR CHER on six, CHARTRES-EST on three, LONGUE on two.

They were map defects. Blacklisting the nodes those routes used took the result from 42 entrance/exit and 3 contradicted to **45 and 0**. A majority rule would have reached the same classification while burying six defects.

So the step stops and names the minority routes. That is the mechanism by which the defects were found, not a safety margin around it.

### Its own step, and its own file

The probe needs `enter`/`exit` roles, which exist only in `data/vinci_price.yaml`. That is a pricing-step output, so this cannot run inside step 4 — the earlier design put it there only because direction of travel needed nothing.

It writes `data/bidirectional_booth_sides.yaml` rather than extending the inventory or the route set. Writing into another step's output would break the checkpoint model: regenerating the inventory while the route set still exists silently drops whatever a later step had added to it, which is a hazard this pipeline has already met.

## Risks / Trade-offs

**The probe depends on the operator's roles being right** → a target whose `enter`/`exit` role is wrong produces a wrong verdict. It shows up as a contradiction rather than as a silent error, and the report names the target, which is how CHARTRES-EST and ST ROMAIN SUR CHER surfaced. It is a dependency, not a hidden one.

**89 000 route requests for 47 booths** → about two minutes against the local router and nothing against the operator. The booth half is 87 890 of those and could be cut by only probing nearby booths, at the cost of the long-range observations that settle sparse regions. Not cut, because two minutes is not worth optimising.

**A booth added to the inventory invalidates the file** → the step is checkpointed on its output, so a new two-way booth needs `data/bidirectional_booth_sides.yaml` deleted before it will be considered. The same is true of every checkpointed step here.

**Zero contradictions is not proof** → it was reported by the direction-of-travel design too, which was wrong. What supports this one is that its two barriers, THOUARCE and LESTELLE ST MARTORY, are exactly the two booths carrying a flat price and no pair prices in data produced independently of it.

## Open Questions

None that change the specs, the approach, or the tasks.
