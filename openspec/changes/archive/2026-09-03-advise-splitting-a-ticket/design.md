## Context

See `proposal.md` — Why. Three facts from the investigation shape the design.

**The tariff is not additive, and the gap is large.** `12060 ROUMOIS` sells a through ticket whose Roumois–Gacé portion costs 19.40 EUR, while the same portion sold on its own costs 10.50. Splitting pockets 8.70. The gap grows with distance and saturates: +2.00 to Gacé, +4.60 to Sées, +8.90 to everything beyond Alençon.

**A naive timing model measures the wrong journey.** Routing `EXIT[G] -> EXIT[Z]` lets OSRM abandon the motorway. For Roumois → Luigny it returned 96.7 km at 63 km/h across country against 242.4 km at 102 km/h on the A28 — *shorter and no slower*, so the split looked free while the price side charged a second motorway ticket the driver never bought.

**The turnaround is not free and not uniform.** A normal plaza has separate entrance and exit lanes and a measurable loop. A `bidirectional` booth is one node for both directions, so the router measures its turnaround as nothing, when in reality you cannot U-turn on a plaza.

## Goals / Non-Goals

**Goals:**

- Every advertised split is one the router corroborates: it re-enters the tolled road at the gare it left.
- One source of truth for money. The file carries stops and time; euros come from `vinci_price.yaml`.
- No Ulys requests, and no dependency on the toll-weighted graph.

**Non-Goals:** as in the proposal, plus — the file is not a route. It names junctions; the geometry is produced at query time.

## Decisions

### Re-entry is proved from the node annotation, and the start node does not count

A candidate leg `EXIT[G] -> EXIT[Z]` is kept only when the routed path crosses a booth of gare `G` **after** its first node.

Alternative considered: force the waypoint through the entrance booth and price whatever comes back. Rejected — that fabricates a journey the router does not think is sensible, and the resulting time would be an assertion rather than a measurement. Rejecting under-reports, which is the safe direction for advice a driver acts on.

Two failure modes are specific enough to be worth writing down, because both were live during the investigation:

- The path's **first** node *is* the exit booth of `G`. Testing the whole path makes the check pass always. It must test the path after the start.
- A plaza is several lanes and the inventory names one of them the representative; the rest are aliases. A driver re-entering through a neighbouring lane crosses an **alias** node. Ignoring aliases falsely rejected 456 real legs — 18% of all rejections.

### The turnaround cost is per booth kind

A stop costs a fixed booth time, plus a larger fixed cost at a `bidirectional` booth for the drive to the nearest roundabout and back, because the router cannot see that detour at a single-node booth.

The measured extra time is floored at the sum of those fixed costs. Concatenating two legs can measure marginally *faster* than the direct route when the stop sits on the direct path — snapping noise. Unfloored, that noise produced a 522 EUR/h entry at the top of the ranking from a drive delta of −0.36 min.

### The search keeps a Pareto frontier, not a shortest path

For each origin, labels over the price graph are grown keeping every `(fare, time)` that is not beaten on **both**. A cheapest-fare search answers a different question: for `04344 LE BOULOU -> 04224 NIMES-O` it finds a seven-stop chain saving 6.00 EUR for 22.6 minutes (16 EUR/h), while a single stop at `04335 AGDE-PEZENAS` saves 2.40 for 2.5 minutes (58 EUR/h). Ratio optimisation needs the frontier; a shortest path throws the winner away.

### The file stores time; the API derives money

Stated in the proposal. The consequence for the format: no euro amounts anywhere in `data/cost-cutting.yaml`.

### The threshold lives in the service, not the file

The file carries every pair that wins at all (~19,892). Thresholding at build time would freeze a policy into a committed artefact and force a pipeline rerun to change it. 2.4 MB against the 11 MB `segment_weights.csv` already carried.

### Geometry is produced at query time from the stored nodes

The file names OSM booth nodes. The service resolves them to coordinates through the inventory it already loads, and re-routes origin → stops → destination on `osrm-optimal`, so the segments between stops stay toll-optimal. The page receives geometry and never sees a node id.

The route that comes back is then priced by the existing `tolls.py`, which pairs each `enter` with the following `exit`. That is the check that the advice and the charge agree: if the re-routed geometry does not actually cross the booths, its price will not match and the answer must be withheld.

## Risks / Trade-offs

**The advice is only as good as the tariff file.** → The Roumois cliff was verified by hand against the operator before this was written. A rebuilt price file could introduce a cliff that is an artefact. The acceptance check should compare a sample of advertised savings against `vinci_price.yaml` arithmetic, which is cheap and catches a corrupt file.

**Queueing is not modelled.** → In August the 2-minute turnaround at a busy plaza can be 15. The page must present the time as driving time excluding queues, or the advice is dishonest.

**`MAX_STOPS` is a real cut.** → Pareto pruning loses nothing, but the stop bound does. At the default threshold 96.6% of winners are single-stop and 3 of 11,843 use four, so the bound is cheap — but it should be a named constant, not a magic number.

**Advising a manoeuvre.** → It is legal and it is what the tariff prices. The page should still show the extra time and stop count plainly, so the driver chooses rather than follows.

## Migration Plan

1. Land the step and its tests. Nothing in `data/` changes.
2. Run `make build_cost_cutting` against the existing price file. No API requests, roughly 47,000 local routes.
3. Inspect the file, then land the service and the page behind the threshold.

Rollback: revert the service and the page. Deleting `data/cost-cutting.yaml` is **not** a rollback — the file is a required artefact like the tariffs, and a service without it stops rather than answering without advice. Turning the advice off without reverting is done by raising the threshold out of reach.

## Open Questions

- The default threshold of 20 EUR/h is the user's figure. Whether the page should let a driver move it is a product question that does not change the specs or the file.
