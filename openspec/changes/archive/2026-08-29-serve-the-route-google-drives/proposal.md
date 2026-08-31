## Why

Three faults, all the same shape: what we show is not what the driver gets.

The link opens Google Maps, which routes at its highest search quality. We asked at its lowest. On Cluses to Mont-de-Marsan that sent the driver 143 km further via the A9 while our route and the web site both avoid it — 24.9% faithful where the same request at the better setting is 62.2%.

A link already full at nine waypoints refused to draw anything, so the journeys with the most waypoints were the only ones nobody could look at.

OSRM's clock runs about 7% slow against Google's, measured over 2 257 journeys, and every answer served that unadjusted number.

## What Changes

### The refinement asks for the route the driver will actually be given

- **BREAKING** `routingPreference` becomes `TRAFFIC_AWARE_OPTIMAL`, with `trafficModel: OPTIMISTIC` and a `departureTime` of the next Saturday 22:00 in `Europe/Paris`.
- The name is misleading for the purpose it serves. Measured across live traffic, a quiet Sunday 03:00 and a Friday 17:00 rush hour, the geometry is **identical**: 866 km at 62.2% in all three, with only the predicted duration moving over a 23-minute spread. What this buys is a better route search; the traffic model and the departure slot describe the clock, not the path.
- Over the ten least faithful journeys in the corpus it lifts mean overlap from 45.0% to 57.7%.
- The departure time SHALL be computed per request. Google rejects one in the past, and any constant becomes one.
- **Consequence:** the request is billed as Routes Pro rather than Essentials, halving the free allowance from 10 000 requests a month to 5 000.
- Intermediates stay **stopovers**. Measured, `via: true` is worth 0.2 points — noise — and a Google Maps URL cannot express a pass-through waypoint at all, so the API must model what the link can carry.
- `google-route-comparison` deliberately does **not** follow. It keeps `TRAFFIC_UNAWARE` so Google's clock stays free-flow and comparable with OSRM's, which is what makes its travel-time multiplier reproducible. The two request bodies stop being the same terms for the same reason.

### A link that is full is still worth looking at

- A journey already needing nine waypoints SHALL buy its route when the page asks to see it, and SHALL be drawn.
- Nothing is refined — there is still nowhere to put a waypoint — and the answer still says the waypoint budget was full.
- Safe to draw because the waypoints and the waypoints sent are the same list, so every marker shown is one Google demonstrably reached.
- Still gated on the page asking. A followed link buys nothing: a full link cannot be improved, and paying per redirect to rediscover that buys nothing.

### The travel time served is corrected against Google's

- **BREAKING** `duration` in an answer becomes OSRM's own seconds multiplied by `TIME_MULTIPLIER`. The router's number moves to a new `duration_osrm`.
- Applied outside the cache, beside the links and for the same reason: a multiplier is a setting, not a property of the journey, and an answer stored with it applied would keep the old value until it was evicted.
- `google-route-comparison` reads `duration_osrm`. Storing the corrected number would make the next measurement of this multiplier come out at 1.0 by construction.

## Capabilities

### Modified Capabilities

- `google-route-refinement`: the terms of the Google request, and what a journey with no waypoint budget is owed.
- `route-service`: the meaning of `duration` in an answer, and one new configuration variable.

## Impact

- Modified: `french_tolls/refine.py` (request terms, departure time, the full-link path), `french_tolls/service.py` (the multiplier, applied outside the cache), `evaluation/fetch_google_routes.py` (reads `duration_osrm`), `docker-compose.yml`, `.env.example`.
- Unchanged: the pipeline, the unit suite, `make all`, the page, the bot's formatting — both read `duration` and get the corrected number without knowing it changed.
- **The application is billed at a higher SKU.** Its 5 000/month ceiling already matches the Pro free cap, but the evaluation shares the key and is still billed at Essentials.
- **The 2 450-journey corpus was bought at `TRAFFIC_UNAWARE`.** Its faithfulness figures now describe a route the application no longer asks for, and are a lower bound. Re-buying is 4 900 requests.
- Cached refinements computed under the old terms are stale; they were cleared.
- Not addressed: the waypoint budget is spent badly. On Cluses to Mont-de-Marsan seven of nine waypoints fall in the first 181 km of an 823 km route, leaving a 428 km gap and a 210 km gap with nothing steering Google — and 734 km of the 758 km of drift lies in those two gaps. Named here because this change measures it and does not fix it.
