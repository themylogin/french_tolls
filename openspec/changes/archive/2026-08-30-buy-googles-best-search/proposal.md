## Why

The cheap search invents manoeuvres no driver makes. Asked at `TRAFFIC_UNAWARE`, Google returns routes that leave a motorway at a junction and rejoin it a few hundred metres later — a sixteen-kilometre excursion to advance nine hundred metres on one measured journey. The excursion crosses two barriers our route does not, so `toll-equivalence` refuses the link, spends a correcting request on it, and splits the journey into parts nobody needed.

Overlap could not see this. The setting was chosen on a measurement that the higher quality was worth **0.8 points of faithfulness**, and that is true: a sixteen-kilometre detour inside a four-hundred-kilometre route is three per cent of its length. It is one hundred per cent of the difference between "pays what we quoted" and "does not", which is what now decides whether a driver gets one link or three.

## What Changes

- The refinement request SHALL ask at `TRAFFIC_AWARE_OPTIMAL` rather than `TRAFFIC_UNAWARE`.
- This moves the refinement to the **Pro** tier, whose free allowance is 5 000 requests a month rather than 10 000. The configured ceiling is already 5 000, so nothing needs changing and nothing has headroom.
- The route returned now depends on traffic at the moment of asking. Two answers for one journey are no longer comparable across time.
- **Not** changed: `google-route-comparison`. The evaluation buys routes to compare durations against OSRM's, and `TRAFFIC_UNAWARE` is the only setting under which the two durations answer the same question. It builds its own request and keeps it.
- **Not** changed: waypoints stay stopovers. Measured — re-asking one request with `via: true` on every intermediate returned the identical route, two seconds apart. Pass-through waypoints were not the cause and are not the cure.

Measured over eleven journeys driven to their end, every ask recorded:

```
                              TRAFFIC_UNAWARE        TRAFFIC_AWARE_OPTIMAL
  Cogolin -> Saint-Gaudens    3 parts, 8 asks   →    1 ask,  97.9%, accepted
  Ancenis... -> Cluses        2 parts, 6 asks   →    2 asks, 98.2%, accepted
  Lure -> Menton              3 parts, 10 asks  →    2 parts, 6 asks
  Solesmes -> Mayenne         refused, 13.80    →    accepted, 14.90 exactly
  total across all eleven     37 asks           →    24 asks
```

Four journeys refused for a phantom barrier become exact matches — same booths, same total to the cent. The one journey that genuinely disagrees, Lure → Menton at €28.90 against our €10.50, stays refused under both.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `google-route-refinement`: the requirement that fixes the routing preference. It currently mandates `TRAFFIC_UNAWARE` and states, as its reason, a measurement made in units that cannot see the defect this fixes. Both the setting and the reasoning change.

## Impact

- `french_tolls/refine.py` — `_request_body`, one field, and the paragraph explaining it.
- Paid Google requests: **fewer**, by about a third on the measured set, because a route that is accepted costs no correcting ask and no split cascade.
- Billing tier: Essentials → Pro. The bill is per request either way; what changes is the free allowance.
- `evaluation/` — untouched. It builds its own request body.
- The corpus under `data/google_routes/` was bought at `TRAFFIC_UNAWARE`. It stays valid as a record of what was asked and answered; it stops being a prediction of what the application will now receive.
