## Context

See `proposal.md` — Why. Everything below was measured before it was decided.

- `french_tolls/refine.py` builds the application's Google request; `evaluation/fetch_google_routes.py` builds its own in `google_request_body`. They were the same terms for the same stated reason, and this change makes them differ on purpose.
- The full 2 450-journey corpus was bought under the old terms. It is what the ten-journey comparisons below are measured against.
- `french_tolls/service.py` already applies the three links outside the cache, with the reason written down. The travel-time factor is the same shape of problem.

## Goals / Non-Goals

**Goals:**

- Ask Google the question whose answer the driver receives.
- Let a journey that cannot be refined still be looked at.
- Serve a travel time that is not knowingly 7% wrong.

**Non-Goals:**

- Changing how waypoints are chosen. This change measures that they are chosen badly and does not touch it.
- Re-buying the corpus at the new terms. Its figures become a lower bound, which is stated rather than fixed.
- Moving the evaluation to the new terms. Its question is a different one.

## Decisions

### `TRAFFIC_AWARE_OPTIMAL`, and why the name is a trap

The objection to a traffic-aware setting is sound on its face: a route that depends on live conditions cannot reproduce a static one. It was tested rather than argued.

| Cluses → Mont-de-Marsan | distance | duration | overlap |
| --- | --- | --- | --- |
| `TRAFFIC_UNAWARE` | 1009 km | 10.32 h | 24.9% |
| `TRAFFIC_AWARE` | 1009 km | 10.16 h | 24.9% |
| `TRAFFIC_AWARE_OPTIMAL`, live | 866 km | 10.05 h | 62.2% |
| `TRAFFIC_AWARE_OPTIMAL`, Sunday 03:00 | 866 km | 9.84 h | 62.2% |
| `TRAFFIC_AWARE_OPTIMAL`, Friday 17:00 | 866 km | 10.22 h | 62.2% |

The geometry is identical across all three traffic conditions; only the clock moves, over 23 minutes. So the setting buys a better route search and the traffic component rides on the duration. `TRAFFIC_AWARE` alone changes nothing, which places the difference in the search rather than in the traffic data.

Over the ten least faithful journeys in the corpus, mean overlap goes 45.0% → 57.7%.

*Consequence:* Routes Pro rather than Essentials — "requests that use an advanced feature, such as the `TRAFFIC_AWARE` or `TRAFFIC_AWARE_OPTIMAL` route modifiers" — so the free allowance halves, 10 000 → 5 000 a month. `GOOGLE_DIRECTIONS_MAX_REQUEST_PER_MONTH` is already 5 000.

### Stopovers, not `via`

Measured at 57.9% against 57.7% over the same ten — a fifth of a point, mixed per journey, noise.

The decision is not made on that number. Google's URL documentation defines `waypoints` as "intermediary places to route directions through" and offers no pass-through form. The API must model what the link can carry, or the refinement measures a route the driver cannot be given.

### A fixed weekly departure slot

`trafficModel` and `departureTime` only reach the duration, so the slot is a choice about reproducibility rather than about the road. A fixed weekly slot means a cached answer's duration stays comparable with a fresh one instead of varying with the minute a journey was first asked about.

Computed per request, because Google rejects a past departure time and a constant becomes one. Anchored in `Europe/Paris` rather than UTC, so 22:00 stays 22:00 on the road across the summer time change — verified to produce `+02:00` in August and `+01:00` in November.

### The full-link case buys geometry, but only on request

The existing two-phase split already had the machinery: the second pass asks through `result.waypoints` and stores the answer. The full-link case needs only to be admitted to it.

```
budget == 0  ──►  first pass returns early, no request        (a followed link stays free)
                        │
                        └── page asks to see it ──► second pass buys the route
                                                    through the nine we already have
```

Drawing is safe here for a reason the refined path had to work for: `waypoints` and `sent_waypoints` are the same list, so every marker lies on the route drawn. That was the invariant the two phases were split to protect, and this path does not strain it.

*Alternative rejected:* buying it in the first pass. Every followed link would then pay for a route that cannot be improved.

### The factor is applied outside the cache

Beside the three links, in the same function, for a reason already written down there: it is a setting, not a property of the journey. Applying it in the stored answer would keep the old factor until eviction.

Derived from `duration_osrm` rather than from `duration`, so applying it twice scales once.

*Alternative rejected:* keeping `duration` uncorrected and adding `duration_adjusted`. Every consumer reads `duration` to answer "how long does this take", and a new consumer reading it would get the known-wrong number by default. The correction belongs on the key that answers the question.

## Risks / Trade-offs

- **Half the free allowance.** 10 000 → 5 000 requests a month, shared with the evaluation, which is still billed at Essentials. → The ceiling already matches; a sweep is what would collide, and a sweep is deliberate.
- **The corpus now describes terms the application no longer uses.** Its faithfulness figures are a lower bound. → Stated in the report's terms rather than silently; re-buying is 4 900 requests and is not part of this.
- **The factor was taken from a 29-journey sample.** The full corpus puts the faithful population at x0.9342, not the x0.9333 configured. → A 40-second difference over a twelve-hour journey; the variable is there to be changed.
- **Traffic still moves the served duration.** The 23-minute spread rides on `duration` now. → It is the road that had to be deterministic; a duration that varies with traffic is a duration that is more nearly right.
- **Cached refinements bought under the old terms are wrong.** → Cleared as part of this; they re-buy lazily, at most one request each.

## Migration Plan

1. Change the request terms and add the departure-time helper.
2. Admit the full-link case to the second pass.
3. Apply the factor outside the cache, and add `duration_osrm`.
4. Point the evaluation's two write sites at `duration_osrm`.
5. Clear cached refinements bought under the old terms.

Rollback is reverting two modules; nothing stored changes shape except the refinements that were cleared.

## Open Questions

None blocking. Whether the corpus should be re-bought at the new terms is a spending decision, not a design one, and the report says what it currently measures.
