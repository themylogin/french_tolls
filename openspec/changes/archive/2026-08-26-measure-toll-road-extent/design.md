## Context

See proposal.md — Why. Three facts shape the approach, and all three were measured before this was written.

**The convergence method works, and it finds the node a human would pick.** Routing AMBLAINVILLE (288919803) to its 24 nearest places gives 24 successful routes sharing a 64-node prefix that ends at node 240997497 — the node named independently from the map. The same run in reverse for MERU (288926127) converges at 5122294120. Neither needed a tolerance or a threshold: the prefix simply stops.

**The error it corrects is large.** MERU to AMBLAINVILLE is 1.5 km booth to booth and 10.0 km between the extents (0.41 km before MERU plus 1.5 plus 8.11 past AMBLAINVILLE). Its EUR/km falls from 1.2422 to about 0.19 — from the largest sample in the whole segment table to an ordinary one.

**Everything it needs is already committed.** `data/route_set.yaml` carries 771 places with node ids and coordinates. `data/bidirectional_booth_sides.yaml` carries the inside/outside nodes for all 47 two-way booths. `data/osm_toll_booths.yaml` carries the booth and alias node ids the bound rule needs. `data/osm_toll_booths_overrides.yaml` carries 33 hand-stated booths.

## Goals / Non-Goals

**Goals:**

- One extent node per priced booth end, derived from the router and recorded in the file the tariffs already live in.
- A per-kilometre price measured over the distance the driver was charged for.
- A report that shows the extent distances, so a convergence that ran too far is visible rather than merely counted.

**Non-Goals:**

- Deciding whether a way is tolled from its OSM tags. `toll=yes` is not reliably mapped on the French network and a wrong tag would silently shorten an extent. The convergence asks the router what every journey does, which is the same question with a better source.
- Re-pricing anything. No tariff is re-requested and the operator is not contacted.
- Changing which pairs are priced. This changes only the distance a price is divided by.
- Settling the deviation gate of `add-toll-weighted-osrm-graph`. This change was the deferral that decision was waiting on, and D5 records what the corrected measurement says; choosing the default remains the maintainer's.

## Decisions

### D1: Convergence, not tags, and no threshold

The extent is the last node every route shares. Not "the node where 90% of routes still agree", and not "the node where the road stops being tagged `toll=yes`".

*Alternative considered:* a share threshold, so one odd route cannot cut the prefix short. Rejected for now — the measured runs had 24 of 24 routes agree for 64 and 28 nodes respectively, so there was nothing for a threshold to rescue. A threshold is also the kind of knob that hides a real problem: a route that leaves early is either a genuine early exit, which should bound the extent, or a routing defect, which should be seen. The minimum-successful-routes rule (D3) covers the case where there is simply not enough evidence.

*Alternative considered:* reading `toll=yes` from the extract. Rejected as above, and it would add a 4.8 GB scan to a step that otherwise needs only the router.

### D2: The sequence starts at the booth node

OSRM snaps the query coordinate onto a lane, so the returned node annotation can begin one node *before* the booth — the measured AMBLAINVILLE routes all start `[2587186119, 288919803, ...]`. That first node is upstream of the barrier and belongs to no journey through it.

So the shared sequence is taken from the index of the booth node onward for an exit, and up to it for an entrance. A route whose annotation does not contain the booth node at all is discarded rather than guessed at.

### D3: Twenty-four nearest places, with a floor on how many must route

Twenty-four was measured, not chosen. It reaches 10.9 to 73.0 km from AMBLAINVILLE, which is far enough that the places genuinely lie in different directions, and it keeps the whole inventory to about 30 000 routes — the same order as the 23 835 that take 1.6 minutes in `build_segment_weights`.

A booth where fewer than a floor of those routes succeed is left unmeasured and reported. Convergence over three routes is not convergence; it is three routes that happen to start the same way. The floor is settable and defaults to 8.

Places lying *on* the toll road need no special handling. The prefix is an intersection, so one route that leaves the network early bounds it however many others stay on.

### D4: The extent stops at the next booth

A corridor whose nearby places all sit beyond a second barrier would otherwise converge past that barrier, and the extent would run into a section this tariff does not pay for. Truncating at the next booth group makes the failure impossible rather than merely unlikely.

Booth identity uses the same map the rest of the pipeline uses — `toll_booths` plus `aliases` resolved through `parent_id`, which `build_vinci_direct_prices.load_inventory` already returns.

This is a bound, not the usual case: it should fire rarely, and the step reports how often it did so that "rarely" is checked rather than assumed.

### D5: The deviation gate of the other change was deferred until this landed, and the answer is that it does not help

`add-toll-weighted-osrm-graph` was complete except for one decision: what its `--max-deviation` default should be, given that 220 033 of 223 174 segments exceeded 10%. Its worst case, at 815%, was MERU to AMBLAINVILLE — a denominator error this change removes.

It has now been re-measured, together with three further corrections found along the way (alias resolution, the detour rule and zero tariffs, all recorded in that change's design as D14 to D16):

| | booth to booth | + extents | + alias fix | + detour 5x | + zero tariffs |
|---|---|---|---|---|---|
| deviation max | 815.2% | 675.9% | 608.4% | 255.1% | 250.0% |
| deviation p90 | 122.6% | 101.7% | 101.1% | 100.9% | 100.2% |
| deviation median | 63.9% | 59.9% | 59.4% | 59.4% | 59.4% |
| price error median | 9.0% | 8.6% | 8.5% | 8.5% | 8.5% |

Four real measurement errors are gone and the worst deviation is down 3.3 times, but **the median has not moved** beyond the denominator's own 63.9% to 59.4%. Every correction removed extremes and left the middle alone.

That is the answer the deferral was for: the remaining spread is the tariff structure, not the pipeline. Different concessions charge different rates for the same distance — VILLEFRANCHE-NORD sells 6.1 km for 0.40 EUR and 10.3 km for 3.20 — and no uniform per-journey spreading reconciles that.

The maintainer settled it: **the gate is removed**. A limit on the spread would stop every run for something no pipeline can fix. What the pipeline can do is stop that disagreement reaching the driver, which is what the fitted rates of that change's D7 do — journey error 3.5% median against the spread's 59.4%.

### D6: The two roles of a two-way booth are separated by side, not by direction of query

A `bidirectional` booth is an entrance one way and an exit the other, and both roles are measured from routes that *touch the same node*. Direction of query alone does not tell them apart: a route from the booth to a place could be leaving the network (the exit's road) or could be a journey that entered there and is being routed backwards.

`data/bidirectional_booth_sides.yaml` already settles this. `inside_nodes` is the toll network side. Leaving the booth for a place means departing to the outside, so a route that departs by an `inside_nodes` node is on the wrong side and is discarded — the same test `build_vinci_direct_prices.wrong_side` applies to pairs.

### D7: The fields live in the price file, not a new one

They belong to a booth, and the price file is the per-booth record every consumer of the tariffs already opens. A separate file would have to be joined to it by every reader and kept in step with it by every writer.

The cost is that `build_vinci_prices` and `build_vinci_direct_prices` both rewrite that file and must carry fields they do not produce. Their loader and writer are one function each (`load_state`, `write_state`) and both already round-trip fields they do not set, so this is a small change to a single place — but it is a real one, and the spec has a scenario for it.

The key order within an entry is fixed (`type`, `price`, `first_toll_node_id`, `last_toll_node_id`, `prices`) for the reason the file's existing ordering rules exist: a rerun that learns nothing must produce no diff.

### D8: Where the step sits

After `build_vinci_direct_prices`, because it reads the `enter`/`exit` roles that step settles and writes into the same file. Before `build_segment_weights`, which consumes what it writes.

That makes it step 9 and pushes the segment weight and apply steps to 10 and 11.

## Risks / Trade-offs

- **A convergence that runs too far** — every nearby place lies the same way, so the prefix extends past where the toll road really ends → Bounded by the next booth (D4), and the report lists extents largest first so a 40 km "slip road" is seen rather than counted.
- **A convergence that stops too short** — one nearby place is reached by an immediate turn-off → The extent is short, the priced distance is closer to today's booth-to-booth figure, and the result is no worse than the current behaviour. Visible as a near-zero extent in the report.
- **8.11 km is a long way past a barrier** → It is what the router says every journey does, and it is what the maintainer independently identified from the map. But it is the first case examined, and the report exists so the next fifty are examined too before the numbers are trusted.
- **The fields are optional, so a half-measured file prices pairs two different ways** → Deliberate: an unmeasured end falls back to the booth node, so a partial run still prices everything, and the step counts the fallbacks. The alternative — refusing to price until every booth is measured — would make the step a barrier rather than an improvement.
- **Two other steps rewrite the price file** → They must not drop fields they do not produce. One spec scenario and one task cover it, and the round-trip is testable without routing.

## Migration Plan

No migration. The two fields are additive and optional, and a price file without them is valid and prices every pair exactly as it does today.

The order of work is:

1. Land `add-toll-weighted-osrm-graph` — this change edits `builder/build_segment_weights.py`, which that change introduces.
2. Land this change, and re-measure the deviation and reconstruction distributions.
3. Settle the `--max-deviation` default with the maintainer, on the corrected numbers.

Rollback is deleting the two fields from the price file; the consumers fall back to booth nodes on their own.

## Open Questions

- Whether 24 places is right everywhere. It was measured on two booths in one interchange. The report's extent distances over the whole inventory are what answers it, and the number is a flag so it costs nothing to revisit.
- Whether a `gantry` carrying `prices` needs an extent. A gantry charges per section travelled rather than closing a ticket, so its "extent" may not mean the same thing. There are 7 of them with prices; they are left unmeasured by this change and reported, and the answer comes from looking at what the report says about them.
