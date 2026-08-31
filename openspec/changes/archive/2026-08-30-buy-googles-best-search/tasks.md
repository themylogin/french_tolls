## 1. The request

- [x] 1.1 Set `routingPreference: TRAFFIC_AWARE_OPTIMAL` in the refinement's request body — verified against a built body: preference set, no `trafficModel`, no `departureTime`
- [x] 1.2 Rewrite the paragraph that explains the setting — `_request_body` now names what the old measurement cannot see (three per cent of length, all of the difference in what is paid), the four motorways it was measured on, and the two things paid for it
- [x] 1.3 Verify the intermediates are still stopovers — no `via` on any intermediate, and the measurement that pass-through waypoints return the identical route now sits beside them
- [x] 1.4 Verify the evaluation is untouched — `evaluation/fetch_google_routes.py` builds its own body, imports only `MAX_WAYPOINTS`, `drift_sections` and `waypoints_for` from `refine`, and keeps `TRAFFIC_UNAWARE`. Its docstring now says the divergence is deliberate, so nobody later "fixes" the mismatch

## 2. What the stored answers now mean

- [x] 2.1 **Decided: invalidate by provenance, do not purge by hand.** A refinement now records the routing quality that bought it, and one bought under another is ignored — the row stays as a true record of what was asked, and stops being served as an answer. This matches how the answer cache already treats an entry with no booth set. Verified: a stored row with no `preference` reads back as `None` and is discarded
- [x] 2.2 Verified a journey looked at after the change draws a route consistent with the drive flow — the stale refinement is not served, and the next look buys a fresh one at the new quality. The cost falls only on the operator: `refine()` is reached only through `/api/refine`, which answers nothing unless `DEBUG` is on

## 3. Verification

- [x] 3.1 Re-drove all eleven journeys through the shipped code. **Cogolin → Saint-Gaudens resolves in one ask** (97.9%, accepted) rather than three parts and eight asks; **Ancenis-Saint-Géréon → Cluses in two** (86.5% → 98.2%) rather than two parts and six
- [x] 3.2 The artefact is gone on all four journeys it was measured on, and two of them improved further than predicted — **Solesmes → Mayenne is now accepted on the first ask** at 99.1% with exactly our two booths (it crossed MARQUION twice and split into three parts before), and **Dieppe → Bayeux on the first ask at 100.0%**. Cogolin → Saint-Gaudens and Ancenis-Saint-Géréon → Cluses come back crossing exactly our booth set
- [x] 3.3 Lure → Menton is still corrected and split — 2 parts, 6 asks, refused on the whole at 56.6% and 82.4% for four booths ours avoids. The real disagreement survives the change
- [x] 3.4 **24 paid requests over the eleven journeys, against 37 before.** Measured through the shipped code, not the probe
- [x] 3.5 Unit suite passes, **111 tests**. Outside the request body, the only change is the provenance field decided in section 2; `evaluation/` keeps its own body and gained only a comment

## 4. Recorded, not fixed

- [x] 4.1 **The free allowance halves**, 10 000 to 5 000, because this moves the refinement to the Pro tier. `GOOGLE_DIRECTIONS_MAX_REQUEST_PER_MONTH` is already 5 000, so the ceiling needs no change — and it now sits exactly at the allowance rather than half of it, with no headroom left to raise it into. Recorded in `.env.example`, where an operator reads it. One stale sentence there ("one request per journey, ever") was corrected in the same breath, because it contradicted the note
- [x] 4.2 **Two answers for one journey are no longer comparable across time.** The first ask varies most: Luçon → Bayeux measured 91.0% of our road at the cheaper setting and 10.9% at this one. Anything wanting two comparable answers asks the evaluation, which still holds the road empty — and `evaluation/fetch_google_routes.py` now says the divergence is deliberate so nobody closes it
- [x] 4.3 **The corpus under `data/google_routes/` was bought at `TRAFFIC_UNAWARE`.** It remains a valid record of what was asked and answered. It stops predicting what the application will receive: of the eleven journeys re-driven, six resolved differently under the new setting. Any analysis that used the corpus to forecast the drive flow is indicative only
