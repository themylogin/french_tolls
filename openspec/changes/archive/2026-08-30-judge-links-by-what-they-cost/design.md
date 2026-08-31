## Context

See `proposal.md` — Why. Everything below was measured while establishing that the idea works, and most of it was found by an impossible number rather than by design.

- `french_tolls/tolls.py` prices a route from node ids, resolving lanes to plazas through the inventory's aliases. Nothing about it changes.
- `french_tolls/drive.py` decides what to send a driver, taking a `fits` predicate from its caller. The acceptance rule lives there.
- `osrm-toll` serves `/match`, which maps a foreign geometry onto the graph and returns node ids per leg.
- The corpus under `data/google_routes/` holds Google's route for 2 450 journeys, so a criterion can be scored against what Google really drives.

The headline measurements, over a 205-journey sample:

```
                                    n   same booths   no dearer
overlap 0.00-0.90                  28        16          17
overlap 0.90-0.95                  27        21          24
overlap 0.95-0.98                  45        35          38
overlap 0.98-1.01                 105       100         101
```

**72 of the 100 below the line pay identical tolls. 5 of the 105 above it do not.**

Re-measured after the work, over 500 cached journeys and with the decision itself
rather than the tests in isolation:

```
                                              share alone   tolls first
accepted on the first ask                      268 (53.6%)   409 (81.8%)
  newly accepted                                             +162
  no longer accepted                                          -21
tolls could not be established                                 30
```

None of the 162 newly accepted costs the driver more than our own route. The 21
now refused cost them €3.89 more on average, at overlaps of 98–99.6%: the share
was sending drivers down a dearer road and calling it a match.

## Goals / Non-Goals

**Goals:**

- Judge a link by what it costs the driver.
- Stop correcting and splitting journeys that were never wrong.
- Keep the geometric test as the answer when the tolls are unknown.

**Non-Goals:**

- Changing how a route is priced. This asks the existing accounting a new question.
- Changing the waypoint search. Nothing here touches where waypoints go.
- Teaching the evaluation to report toll equivalence. Worth doing, separate change.

## Decisions

### Containment, not equality

`booths(google) ⊆ booths(ours)`, not `==`.

The two errors are not symmetric. A route crossing **fewer** of our booths costs the driver less; rejecting it buys a correction nobody needed. A route crossing **one extra** costs them money they were not told about. Equality treats a cheaper route as a fault.

*Alternative rejected:* comparing totals in euros. Two different plazas can charge the same, and a comparison of totals would call that agreement — it would accept a route that takes an entirely different tolled corridor at coincidentally the same price.

*Measured afterwards:* containment never fired as a strict subset. All 162 newly accepted routes cross **exactly** our booth set, so equality would have given the same answer on this corpus. The rule stands on the asymmetry being real, not on having been observed.

*What the geometric test structurally cannot see:* 16 of the 21 journeys now refused cross one barrier — BPV SAUGNAC on the A63, €4.40 — that our route avoids by the free road running beside it. Two roads in each other's corridor are the same road to an overlap measure and different roads to a driver's wallet.

### The whole trace in one request, and why this is the whole design

This is not a tuning parameter. It is the difference between the method working and producing confident nonsense.

```
   windows of 90 tracepoints          one request for the trace
   ─────────────────────────          ────────────────────────
   each matched blind                 continuity evidence throughout
   boundary → matcher may start       one Viterbi path over the whole road
     on a ramp and rejoin
   near LEZIGNAN: a 400 m             LEZIGNAN found, 55.10 EUR exactly
     out-and-back, plaza skipped,
     13.70 EUR lost
```

The control settles it: matching our **own** routes and pricing them back gave 82/98 before and **205/205** after. Every wrong answer in the investigation came from windows, including three that I first attributed to a latent bug in the accounting, to lane aliasing, and to tracepoint density in turn. None of those was the cause.

*Consequence:* `osrm-toll` needs `--max-matching-size` raised. The default is 100 coordinates.

### How dense the trace should be, measured

Density was expected to be a latency choice and nothing more. It is not. Our own routes, matched and priced against their own bills, over 210 journeys:

```
   spacing   points   same bill   in pieces   s/match
         0     9410     206/210           4      0.39
       100     3463     210/210           0      0.14
       250     1742     210/210           0      0.08
       500      968     210/210           0      0.05
      1000      517     196/210          11      0.04
```

Thinning is not only cheaper, it is **more accurate at the dense end**. The full trace fails on four journeys and a kilometre apart on eleven, always the same way: the matcher gives up in the middle and returns the trace in two pieces, which this treats as unpriceable. 250 m sits in the middle of the band where nothing fails, at a twelfth of a second — twenty times faster than the 1.6 s measured while establishing the method.

*Consequence for the ceiling:* `--max-matching-size 10000`. About twice the longest thinned trace, and deliberately **below** the ~40 000 points an unthinned polyline carries, so a trace that reaches the router unthinned is refused rather than served slowly and wrongly.

*And one detail found by the same control:* dropping each leg's repeated head leaves that node repeated **in place** at the boundary — 2 066 of them on a 699 km route. It charges nothing twice, because the accounting dedupes consecutive nodes, but it is not a path. Squeezed, the matched sequence comes back as our own route's 10 807 nodes exactly, in order, with no step back anywhere in it. That equality is what makes the recovery checkable rather than merely plausible.

### Dropping each leg's repeated head node

An OSRM leg's node annotation begins with the node *preceding* its start, because the tracepoint snapped partway along a segment. `waypoint-route-search` already forgives exactly this when it verifies a leg.

Kept, the sequence steps back and forward across a booth, and `_crossings` — which dedupes only strictly consecutive nodes — counts one plaza twice. Measured: three phantom crossings and €3.00 on a route whose geometry was identical to ours.

Worth stating plainly because it is invisible: the answer is a plausible number, slightly too large, always in the same direction.

### Falling back rather than accepting when the tolls are unknown

The matcher can return a trace in pieces. A break between an entry and its exit leaves a ticket open and misprices everything after it.

Not knowing what a route costs is not knowing it costs the same. On the sample, 195 of 205 traces matched as one piece; the other 10 fall back to overlap, which is what the system does today anyway.

### The wording fix

"Next part", not "first half". A journey can be halved twice, so Embrun to Ancenis-Saint-Géréon sends three links, each announcing itself as the first half — about the first half, a quarter of it, and the far half.

*Alternative rejected:* numbering the parts. Splitting is lazy: when the message is written the system has not decided whether the remaining parts will split, so it does not know the total. "Next" is the strongest true claim available.

## Risks / Trade-offs

- **Latency.** ~0.08 s to match a thinned trace against `osrm-toll`, once per Google answer, at most four per press. → Small enough that it is no longer a trade-off worth naming; it also buys no paid Google request and removes some.
- **A raised matching ceiling.** `--max-matching-size` bounds what one call can cost the router, and the service is reachable from the Compose network. → Set to 10 000 from the measurement above rather than inherited: high enough for the longest thinned trace twice over, low enough to refuse an unthinned one.
- **Nine booths of 716 were missed on Google's geometry** while establishing the method. → Re-measured after the one-request match and the thinning: of 500 journeys, the 148 that ran at 99.5% or more of our road are priced as crossing *no fewer* booths than ours — not one. That is where a miss would show, and there is none left to find.
- **The corpus was bought under a different placement.** Its geometry describes links the application no longer emits, so the 72-of-100 figure is indicative rather than a promise about today's links.
- **This makes the bot depend on toll data being right.** A booth missing from the inventory is a booth neither route is charged for, and the test would call two routes equivalent that are not. That was already true of every price we quote; it now also decides whether we correct a link.

## Migration Plan

1. Raise `--max-matching-size` on `osrm-toll`.
2. Add a match request to the router client.
3. Add the booths-of-a-geometry function: match in one request, drop each leg's repeated head, price with the existing accounting.
4. Add the containment test to the drive decision, tried before the geometric one, with the fallback.
5. Fix the wording. *(Already applied, with a test.)*
6. Re-run the corpus comparison and record what the criterion accepts.

Rollback is removing the acceptance branch; the geometric test is untouched beneath it.

## Open Questions

None blocking. Whether the evaluation should report toll equivalence beside overlap is a separate change, and it is the thing that would tell us how the criterion behaves over 2 450 journeys rather than 205.
