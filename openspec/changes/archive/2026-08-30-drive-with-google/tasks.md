## 1. The refinement reports how well it fits

- [x] 1.1 Report the share of Google's route running within the corridor of the optimal route as part of a refinement; verify it is present on a refined answer, on an unrefined one, and on one Google already agreed with — verified: `overlap` on a refined answer and on an AGREED one, `before_overlap` on a first-pass result; a refinement that never reached Google reports no share, which is correct
- [x] 1.2 Add a configured fit threshold defaulting to the share `google-route-comparison` uses; verify both read the same value and that changing it changes what the drive flow calls followable — `FIT_THRESHOLD` in `refine.py`, read by `report.py` as `CLOSE_OVERLAP`; verified both are 0.98 and are the same value
- [x] 1.3 Keep the decision out of the refinement: it reports the share, callers judge it; verify nothing in the refinement branches on the threshold — verified: nothing in `refine.py` compares against it; the drive decision takes a `fits` predicate from its caller

## 2. The Google request stops using traffic

- [x] 2.1 Set `routingPreference` to `TRAFFIC_UNAWARE` and remove `trafficModel` and `departureTime`; verify a built request carries none of the three — verified: `TRAFFIC_UNAWARE`, no `trafficModel`, no `departureTime`
- [x] 2.2 Remove the departure-time helper and its timezone handling, now that nothing computes a slot; verify no reference remains — `_departure_time`, `ROAD_TZ`, `DEPARTURE_WEEKDAY`, `DEPARTURE_HOUR` and the `datetime`/`zoneinfo` imports removed; no reference remains
- [x] 2.3 Verify two requests built at different times are byte-identical, which is what makes two answers for one journey comparable — verified: two bodies built a second apart are byte-identical
- [x] 2.4 Align the evaluation's own request body so the corpus describes the link the application emits; verify the two bodies match field for field — verified: the evaluation was already on `TRAFFIC_UNAWARE`; the two bodies now match field for field, names and values
- [x] 2.5 Record what the change costs in faithfulness on a sample, against the 0.8 points measured; if it is materially worse than that, stop and say so before continuing — **0.55 points of mean** (97.41% → 96.85%), median 99.70% → 99.60%, over the same 39 toll-paying journeys. Better than the 0.8 predicted, so not materially worse. 9 journeys lost ground and the worst lost **16.9 points**

## 3. The decision, before the bot

- [x] 3.1 Write the decision as a function over values — journey, toll cost, budget, Google answers in, messages and requests out — performing no I/O; verify by calling it with no network configured — `french_tolls/drive.py`: a generator that yields `AskGoogle`/`AskRoute` and returns an `Outcome`; performs no I/O
- [x] 3.2 Make the state between a message and its press serialisable and directly constructible; verify a test can build "the second half of a split journey" without replaying the exchange — `Part` is a frozen dataclass of plain values; `test_the_pending_part_is_a_value_a_test_can_build` builds one directly
- [x] 3.3 Order the rules toll-free, then budget, then ask; verify a toll-free journey makes no request even when budget is available — verified by `test_toll_free_is_decided_before_the_budget`: a toll-free journey with zero budget still gets the avoid-tolls answer and makes no request
- [x] 3.4 Return Google requests as intentions the caller performs; verify a test supplies answers and asserts messages with nothing intercepted — requests are yielded, never made; the test harness is eleven lines and patches nothing
- [x] 3.5 Cover every branch with tests and no substituted objects: toll-free; budget spent; fits first ask; fits after waypoints added; splits; a half that is toll-free; a half that splits again; the four-part bound — 17 tests in `french_tolls/tests/test_drive.py` covering every branch, including the queue defect that dropped a quarter of a journey
- [x] 3.6 Verify the worst case costs 14 requests and no more, and that the common case costs one or two — verified by `test_the_worst_case_is_bounded` (14 across four presses) and `test_a_route_google_follows_is_sent_after_one_ask` (1)

## 4. The bot becomes a shell

- [x] 4.1 Reduce the answer message to the two summaries and the comparison map link; verify no directions link remains and no Google request is made when it is sent — the message is the two summaries plus the comparison map link; verified no directions link is built in `bot.py` and the message makes no Google request
- [x] 4.2 Add the bold avoid-tolls instruction where the optimal route costs nothing; verify it appears at zero cost and not otherwise — verified: the bold notice is appended when `optimal.cost <= 0` and not otherwise
- [x] 4.3 Add the single action, and a handler that performs what the decision returns and stores the state it returns; verify the handler holds none of the rules — `drive_button_handler` and `perform` — the handler performs `AskRoute`/`AskGoogle` and stores `outcome.pending`; the rules live in `drive.py`
- [x] 4.4 Send parts one at a time, each with an action for the next and the last with none; verify a two-part journey sends one message then the other, never both — `send_outcome` attaches the action to the last message only, and only when something is pending
- [x] 4.5 Build the comparison map address from the configured public address rather than the literal in the source; verify changing it changes the link — `comparison_map` builds from `PUBLIC_SITE_URL`; verified no site address is written into `bot.py`, including the help text
- [x] 4.6 Keep the exchange and the reach check exactly as they are; verify both against their existing behaviour — verified: `handle_location`, the two-message exchange and the reach-check text are untouched

## 5. Removing what nothing uses

- [x] 5.1 Remove `url`, `url_from_current_location` and `url_from_current_location_through_start` from the answer; verify no consumer reads them and that `google_url` remains — verified: the answer's only url key is `google_url`; the three are gone from a live `/api/calculate`
- [x] 5.2 Remove `/go/{form}` and the link-form handling behind it; verify the endpoint is gone and the refinement's answer form still serves the page and the drive flow — verified: `/go/start` now answers **404**; `/api/refine` still serves the page and the drive flow. `refined_link` lost its `form` argument with them
- [x] 5.3 Verify the cache is unaffected: nothing stored depended on the public address, so no purge is needed — verified: the newest stored answer carries only `google_url`; nothing cached was built from `PUBLIC_SITE_URL`, so no purge is needed
- [x] 5.4 Record that links already sent by the bot will no longer resolve, and that the comparison map links in those messages still do — recorded: links already sent by the bot addressed `/go/{form}` and will 404. The comparison map link in those same messages still resolves

## 6. The overlay becomes a debug tool

- [x] 6.1 Gate the overlay on the debug setting, defaulting off; verify a page served without it draws nothing, requests nothing, and offers no control — `DEBUG` read in `api.py`; off, `/api/refine` returns `{"nodes": []}` and the page renders nothing. Verified `''`, `'0'`, `'false'` are off and `'1'`, `'yes'` are on
- [x] 6.2 Draw it automatically on calculation when the setting is on; verify two Google requests per journey and an orange route on the map — the page asks on every calculation and draws what comes back; with `DEBUG=1` a live `/api/refine` returned **19 416 nodes**
- [x] 6.3 Draw the orange beneath the optimal route at twice its width; verify the green runs down the middle of the orange where they agree — orange at weight **16** and z-index 2, against the optimal route's 8 at z-index 3 — twice the width, beneath it
- [x] 6.4 Keep the two kinds of waypoint distinguishable and keep clearing the overlay on a new journey; verify both — unchanged: `added` are purple and the rest orange, and the overlay is still cleared when a new journey is calculated
- [x] 6.5 Say so when the budget is exhausted rather than drawing nothing; verify the message appears — the page shows `data.reason` where the server gave one, and nothing where it did not — an exhausted budget is explained, an overlay that is simply off is not

## 7. Verification

- [x] 7.1 Run the unit suite and record the count; the decision's tests are the substance of this change and should be a visible share of it — **88 passed**, up from 66. 17 of the 22 new tests are the decision's, in `test_drive.py`; the other 5 are `test_geometry.py`
- [x] 7.2 Exercise the drive flow end to end against the real service for one toll-free journey, one that fits first ask, one that needs waypoints, and one that splits; record the requests each cost — toll-free: 0 requests, one link, avoid-tolls notice. Tolled and followable: 1-2 requests, one link. Hendaye to Cognac: 6 requests, 4 parts. Wissembourg to Menton driven to the end: **3 presses, 10 requests, 3 links**
- [x] 7.3 Verify the bot's message costs nothing, by sending one and reading the month's counter before and after — verified: the month's counter was 649 before the message and 649 after; the message carries 0 directions links and one action
- [x] 7.4 Confirm `.env.example` documents the debug setting and the fit threshold, and that both default safely — both documented in `.env.example`; `DEBUG` empty (off) and `GOOGLE_FIT_THRESHOLD=0.98`. Verified `''`, `'0'`, `'false'` read as off
- [x] 7.5 Confirm the pipeline, the waypoint search, toll accounting and `google-route-comparison` are untouched — verified: `search.py`, `osrm.py`, `tolls.py`, `builder/` and the `Makefile` are untouched. `report.py` changed only to read `FIT_THRESHOLD`; the evaluation still imports and still asks at `TRAFFIC_UNAWARE`

## 8. Recorded, not fixed

- [x] 8.1 **A third of toll-paying journeys split.** Measured over 39: 13 (33%) sit below the 0.98 threshold and resolve into two or four links. Wissembourg to Menton takes 3 presses, 10 requests and 3 links; Hendaye to Cognac splits into 4 despite scoring 98.3% before traffic was dropped. Shipped as specified: every link sent is one Google follows, and the alternative is sending one link that goes somewhere else
- [x] 8.2 Dropping traffic cost **0.55 points of mean** and moved some journeys across the threshold that were above it before. Nine of 39 lost ground and the worst lost 16.9 points
- [x] 8.3 **The bot was given the Google calls and not the configuration they need.** `GOOGLE_DIRECTIONS_API_KEY`, `GOOGLE_DIRECTIONS_MAX_REQUEST_PER_MONTH` and `GOOGLE_FIT_THRESHOLD` were never passed to the `bot` service, so it read a ceiling of 0 and told every driver the link was unchecked. Found by using it, not by the suite: the decision's tests take the budget as a value, which is the property that makes them good tests and also why they could not catch this. Fixed in `docker-compose.yml`, and the spec now requires it
- [x] 8.4 `bot` and `web` build separate images from one context, so `--build web` leaves the bot on old code. A `--force-recreate` then produces a bot that starts cleanly and behaves like yesterday's
