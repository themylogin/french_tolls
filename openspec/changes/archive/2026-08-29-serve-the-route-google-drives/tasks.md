## 1. The request asks for the route the driver is given

- [x] 1.1 Set `routingPreference` to `TRAFFIC_AWARE_OPTIMAL` with `trafficModel: OPTIMISTIC`; verify a built request carries both
- [x] 1.2 Establish that the setting does not make the path depend on traffic before relying on it; verified on Cluses to Mont-de-Marsan across live traffic, Sunday 03:00 and Friday 17:00 — **866 km and 62.2% in all three**, only the duration moving over a 23-minute spread
- [x] 1.3 Confirm the gain is real over more than one journey; verified over the ten least faithful in the corpus, mean overlap **45.0% → 57.7%**
- [x] 1.4 Decide stopover against `via` on what the link can carry, not on the measurement; measured 57.9% against 57.7% over the same ten, and Google's URL documentation offers no pass-through form, so stopovers stay
- [x] 1.5 Compute the departure time per request as the next Saturday 22:00 in `Europe/Paris`; verify Saturday before 22:00 gives today, Saturday at 22:00 exactly gives next week, and a November date gives `+01:00` where August gives `+02:00`
- [x] 1.6 Confirm the evaluation does not follow; verify `google_request_body` still sets `TRAFFIC_UNAWARE` and that the two bodies are built independently

## 2. A full link is still worth looking at

- [x] 2.1 Admit the no-waypoint-budget case to the second pass when the geometry is asked for; verify a journey needing nine waypoints returns a drawable route
- [x] 2.2 Keep a followed link free; verify `/go/start` on such a journey makes no request and leaves the month's count unchanged
- [x] 2.3 Keep the reason reported; verify the answer still says the waypoint budget was full while carrying the route
- [x] 2.4 Record the measurements this path is the only source of; verify `before_overlap` and `drift` are filled rather than left empty, and that the refined path keeps its own values
- [x] 2.5 Confirm every marker drawn lies on the route drawn; verify all nine waypoints sit within a few metres of it

## 3. The travel time served is corrected

- [x] 3.1 Read `TIME_MULTIPLIER` from the environment, defaulting to 1; verify an unset value serves the router's own time
- [x] 3.2 Apply it outside the cache beside the links, deriving `duration` from `duration_osrm`; verify a computed answer and a cache hit carry the same ratio and that applying it twice scales once
- [x] 3.3 Confirm the cache stores the uncorrected time; verify a stored row carries the router's seconds and neither `duration_osrm` nor the links
- [x] 3.4 Point the evaluation's two write sites at `duration_osrm`; verify the report over the existing corpus is unchanged
- [x] 3.5 Carry the variable to both services and document it; verify `docker-compose.yml` sets it on the web application and the bot, and that `.env.example` describes it

## 4. Verification

- [x] 4.1 Run the unit suite; **66 passed**, unchanged
- [x] 4.2 Verify the corrected duration end to end; Cosne-Cours-sur-Loire to Dunkerque serves `duration=17419.7` against `duration_osrm=18664.6` on `fast` and `18007.2` against `19294.1` on `optimal` — **ratio 0.9333 on both, computed and cached alike**
- [x] 4.3 Verify the full-link case end to end; Cluses to Mont-de-Marsan through `/api/refine` returns **866 km at 62.2% faithfulness with nine waypoints and none added**, against 1009 km at 24.9% under the old terms
- [x] 4.4 Verify the report over the unchanged corpus still reads `FAITHFUL n=1229 x0.9342`, `DIVERGING n=1028 x0.9489`, `MIXED x0.9409`
- [x] 4.5 Clear cached refinements bought under the old terms; **6 rows cleared**, re-bought lazily at one request each
- [x] 4.6 Record what this change measures and does not fix: on Cluses to Mont-de-Marsan seven of nine waypoints fall in the first 181 km of an 823 km route, and **734 km of the 758 km of drift lies in the 428 km and 210 km gaps** left after them. The routing mode is worth 37 points on that journey; the remaining 38 is the waypoint distribution
- [x] 4.7 Record the billing consequence: the application moves from Routes Essentials to Routes Pro, halving the free allowance from 10 000 requests a month to 5 000, which its configured ceiling already matches
