# Tasks

## 1. Baseline

- [x] 1.1 Run `make test` and `docker compose --profile test run --rm --no-TTY integration` before any change. Write down which tests fail. Later tasks compare against this list, not against zero. Verify that the list names each failing test.

  Baseline on 2026-11-08: the unit suite passes 425 tests and the builder suite passes 27. The integration suite fails 4 of 115, all on `split-all-tolled`, which now resolves into 1 unchecked link:
  - `test_a_journey_that_splits_is_driven_by_pressing_for_each_part`
  - `test_a_pinned_journey_costs_what_it_is_pinned_to_cost[split-all-tolled]`
  - `test_a_pinned_journey_resolves_into_the_parts_it_is_pinned_to[split-all-tolled]`
  - `test_a_split_journey_arrives_one_part_at_a_time`

## 2. The drive decision

- [x] 2.1 In `french_tolls/drive.py`, add `settle(part, maps_link, prefix="")`. It returns the `Message` of rule 1 or rule 2, or None. Make `_part` use it for rules 1 and 2. Add tests in `french_tolls/tests/test_drive.py`: a part with cost `0` gives a message with `AVOID_TOLLS`; a part whose `booths` equal its `fast_booths` gives a link with no waypoints and basis `AGREED`; a part that needs Google gives None. Verify with `make test`.
- [x] 2.2 Add `Stop(location, booths, index)`, `Part.stops` (default `()`), `AskRoute.stops` (default `()`), and `AskGoogle.nodes`. `_part` puts `part.nodes` in each `AskGoogle`. Add a test: each `AskGoogle` of a part carries that part's nodes. Verify with `make test`.
- [x] 2.3 Change `accepts` for a part with stops, as in the design section "A part keeps its stops as values". Add tests with part booths `{1, 2, 3, 4}` and one stop with booths `{3, 4}`: Google booths `{1, 2, 3, 4}` give `TOLLS`; `{1, 2}` give None; `{1, 2, 3, 4, 9}` give None; unknown booths with share `1.0` give None. Keep the tests of a part without stops unchanged. Verify with `make test`.
- [x] 2.4 In `_part`, divide the stops at the index of the midpoint: a stop at or before it goes to the near `AskRoute`, the others to the far one. Add tests on the 201-node route: stops at 40 and 160 go to the near and the far half; a stop at the midpoint index goes to the near half; a part without stops asks for halves without stops; with budget `0`, the link of a part whose waypoints hold the stop location carries it. Verify with `make test`.

## 3. The route service

- [x] 3.1 In `french_tolls/route.py`, extract the selection loop of `link_through` into `_fit_waypoints(route, optimal, plan, fixed)`, as in the design. Do not change the behavior of `link_through`. Verify that the `link_through` tests in `french_tolls/integration/test_refuel_endpoint.py` pass with `docker compose --profile test run --rm --no-TTY integration`.
- [x] 3.2 In `_super_optimal`, add `drive_waypoints` from `_fit_waypoints`, with each stop as fixed. Add `booths` (exit and entrance booth ids) and `index` (`route.index_of` of the exit booth) to each stop entry. Add tests in a new `french_tolls/integration/test_split_route.py`, with built `Route` values and a patched plan: 8 plan waypoints and 2 stops give 9 `drive_waypoints` with both stops, and a null `google_url`; 4 plan waypoints and 1 stop give the 5 waypoints of `google_url`, in its order; 10 stops give null `drive_waypoints`; each stop's `booths` are in the route's `booths`, and `nodes[index]` is the exit booth. Verify with the integration suite.
- [x] 3.3 Add `stretch_through(from_, to, stops)` with the four steps of the design section "A half with stops is routed through them". Each stop is a `(location, booths)` pair. Add it to `__all__`. Add tests in `test_split_route.py` with a fake router that answers `route_via` from its vias: one stop gives a `super_optimal` whose `drive_waypoints` hold the stop location and whose `stops` carry its booths; a via route that does not cross the entrance booth gives None. Verify with the integration suite.

## 4. The integration harness

- [x] 4.1 In `french_tolls/integration/chat.py`, make `press_offered` read the `sent` calls since the last press. A call with buttons is an offer, including `editMessageReplyMarkup`. Give `Chat.drive` and `press_offered` a `choice` label: when the latest offer has a button with that label, press it; otherwise press the last button, as today. In `test_drive_flow.py`, make `test_every_token_pressed_came_from_the_bot` collect the offered buttons from every `sent` call. Verify that the integration suite fails only the baseline tests of 1.1.
- [x] 4.2 In `french_tolls/integration/journeys.py`, add `choice` to `Journey`, default None: None means the answer offers no choice. Pass `journey.choice` to `Chat.drive` in `driven()` in `test_drive_flow.py` and in `record.record`. Verify that the integration suite fails only the baseline tests of 1.1.

## 5. The bot

- [x] 5.1 In `french_tolls/bot.py`, give `part_of` the key to read, `"optimal"` by default. For `"super_optimal"` it reads `drive_waypoints` as the waypoints and builds a `Stop` from each stop entry. `perform(AskGoogle)` uses `request.nodes` as the corridor and no longer calls `get_route`. `perform(AskRoute)` calls `route.stretch_through` when the request has stops and reads `"super_optimal"`; otherwise it works as today. Verify that the integration suite fails only the baseline tests of 1.1, so the cassettes still replay.
- [x] 5.2 In `handle_route`, when `super_optimal` is present and its `drive_waypoints` is not null: list `Superoptimal route:` first, in the format of the others; send the comparison map link; offer one row `Optimal`, `Superoptimal` with a token in a new `ChatState.choices`. Otherwise, keep the message of today and use `drive.settle` for the outright link. Verify with the tests of 5.4.
- [x] 5.3 Add the choice handler on `^r\d+:`, as in the design sections "The choice is one token" and "The press edits the markup of the same message". When `settle` answers the chosen part, remove the buttons and send its link labelled `Drive this route`. Otherwise, replace the buttons with one `Drive with Google` button for that part. An unknown token gets the expired message. Verify with the tests of 5.4.
- [x] 5.4 Find a journey whose answer carries `super_optimal`, starting with Le Boulou to Nîmes. Keep its locations in `journeys.py` outside `JOURNEYS`, because it has no cassette yet. Add tests in `test_drive_flow.py` that stop before `Drive with Google`, so they make no Google request: the answer lists `Superoptimal route:`, `Optimal route:`, `Fastest route:` in that order; it offers one row with `Optimal` and `Superoptimal` and no `Drive with Google`; it carries the comparison map link; a press on `Superoptimal` edits the markup to one `Drive with Google` button, and the replay spent `0`; a second press on the same choice gets `That route has expired. Please send the locations again.` Verify with the integration suite.
- [x] 5.5 Look for a journey with `super_optimal` whose fastest route crosses the optimal route's booths, starting with Perpignan to Béziers. When one exists, add a test: a press on `Optimal` removes the buttons, sends a `Drive this route` link with no waypoints, offers no button, and spends `0`. When none exists, write the journeys tried in the docstring of `test_drive_flow.py`, and leave the case to the test of `settle` in 2.1. Verify with the integration suite.
- [x] 5.6 Run the integration suite. For each pinned journey that now offers a choice, set `choice="Optimal"` and check that its `asks` and `parts` do not change. When `toll-free` or `routes-agree` now offers a choice, replace it with a journey that offers none, and record its empty cassette with the recorder (it makes no request). Make the press assertions count the choice press: `test_every_token_pressed_came_from_the_bot` expects a press when `journey.choice` is set, and `test_a_journey_that_splits_is_driven_by_pressing_for_each_part` adds one press for a choice. Add a test that the answer offers the choice exactly when `journey.choice` is set. Verify that the integration suite fails only the baseline tests of 1.1.

- [x] 5.7 When a choice is pressed, edit the answer message: append an empty line and `Optimal route chosen` or `Superoptimal route chosen`, and keep its HTML. Keep the sent text in a `Choice(text, parts)` value in `ChatState.choices`. Add tests in `test_drive_flow.py`: a press on `Superoptimal` edits the answer to its own text plus `\n\nSuperoptimal route chosen` with `parse_mode` `HTML`; a press on `Optimal` that `settle` answers ends the answer with `Optimal route chosen`. Verify that the integration suite fails only the baseline tests of 1.1.

## 6. The pinned superoptimal journey

- [x] 6.1 Move the journey of 5.4 into `JOURNEYS` with the key `superoptimal`, `choice="Superoptimal"`, and an outcome text. With the agreement of the operator, record its cassette: `docker compose --profile record run --rm recorder python3 -m french_tolls.integration.record superoptimal`. Set `asks` and `parts` from the output. Verify that the recorder prints no `<<< expected` flag, and that `french_tolls/integration/cassettes/superoptimal.json` exists.

  Recorded on 2026-11-08 for 2 paid requests and 1 part. The journey was pinned at 1 request before the run, so the recorder flagged the difference; `asks` is now 2. The first ask through the 3 drive waypoints was refused, and the corrected ask was accepted. Both asks carry the AGDE-PEZENAS stop.
- [x] 6.2 Add a test for the scenario "A superoptimal journey is driven through its stops": the summaries are in order; the choice comes first; `Drive with Google` comes after the press on `Superoptimal`; every stop of `get_route`'s `super_optimal.stops`, as `lat,lon` with six decimals, is a waypoint of a link sent; the spend is `asks`. Verify with the integration suite.

## 7. Integration checks

- [x] 7.1 Run `make test` and `docker compose --profile test run --rm --no-TTY integration`. Verify that no test fails beyond the baseline of 1.1.
- [x] 7.2 With the agreement of the operator, run `make bot` and use the real bot. Send Le Boulou, then Nîmes. Verify the three summaries, the choice, `Drive with Google` after `Superoptimal`, and a Maps link that leaves the motorway at the stop. Send Ancenis-Saint-Géréon, then Ploërmel. Verify that the answer is the one of today, with no choice.
- [x] 7.3 Run `openspec validate offer-superoptimal-route-in-bot --strict`. Verify that the change is valid.
