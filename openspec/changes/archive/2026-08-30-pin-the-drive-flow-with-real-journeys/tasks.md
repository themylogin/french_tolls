## 0. Before anything

- [x] 0.1 `buy-googles-best-search` is landed and archived. Verified by driving all eleven journeys through the shipped code: **Cogolin → Saint-Gaudens resolves in one ask** at 97.9%, and the eleven cost 24 paid requests against 37 before

## 1. The seam in the bot

- [x] 1.1 `bot.build(token, request=..., get_updates_request=...)` returns the application with its handlers and its state; `main()` is now one line calling it, so the factory is not a test-only path
- [x] 1.2 `ChatState` holds the origins awaited, the parts owed and the token counter, and lives in `application.bot_data`. Verified two states in one process share nothing: each issues `d1` as its first token into its own `pending`. The three module globals are gone
- [x] 1.3 Unit suite passes unchanged, **111 tests**

## 2. Answering Telegram

- [x] 2.1 `integration/telegram_transport.py` — a `BaseRequest` answering all seven endpoints the flow calls, and refusing loudly on any eighth. `Sent` exposes the text, the links and the buttons
- [x] 2.2 Payloads the library parses into real objects; verified by the flow working — it replies with a message, edits that message into the answer, and deletes another, none of which is possible against a payload the library rejected
- [x] 2.3 No socket is opened. The token authenticates nothing, the container has no route to Telegram, and `test_no_socket_is_opened_to_telegram` asserts the bot's request object is the transport
- [x] 2.4 Nothing patches or substitutes the messaging library — the only seam is the transport under it, and the suite imports no private name from `telegram`

## 3. Replaying Google

- [x] 3.1 `refine.ROUTES_ENDPOINT` reads `GOOGLE_ROUTES_ENDPOINT`, defaulting to Google. Production is untouched
- [x] 3.2 `integration/google_replay.py` runs a real aiohttp server on `127.0.0.1:8099` and the application's own client posts to it — so the body, the field mask, the JSON encoding, the status handling and the decoding all run. Verified by 46 passing tests that never patch `_ask_google`
- [x] 3.3 A request with no recording raises `Missing` naming the journey, the waypoint count and the preference, and is never forwarded. `test_an_unrecorded_question_is_not_asked`
- [x] 3.4 Each cassette records its `preference`; `load()` refuses one bought under another. `test_a_recording_knows_what_bought_it` feeds it a `TRAFFIC_UNAWARE` cassette and asserts the refusal names both settings
- [x] 3.5 `python3 -m french_tolls.integration.record` is a separate service behind its own `record` profile. Verified: the suite ran 46 tests with a key that authenticates nothing, and the application's own request counter was **unchanged at 818** while the suite's scratch counter reached 26

## 4. The pinned journeys

Recorded at `TRAFFIC_AWARE_OPTIMAL`, one per outcome. Each asserts the transcript **and** the paid request count.

- [x] 4.1 **Optimal is free** — Ancenis-Saint-Géréon → Ploërmel. 1 part, **0 requests**, the avoid-tolls instruction in bold
- [x] 4.2 **Accepted on the first ask** — Cogolin → Apt. 1 part, 1 request, no "route is complex" and no "not checked"
- [x] 4.3 **Corrected, then accepted** — Ancenis-Saint-Géréon → Lure. 1 part, 2 requests, and the second ask provably carries more waypoints than the first
- [x] 4.4 **Split in two, one part toll-free** — Lodève → Cluses. 2 parts, 4 requests; exactly one part carries the avoid-tolls instruction and it is the one driven first
- [x] 4.5 **Split in two, neither part toll-free** — Lure → Menton. 2 parts, 6 requests, two presses with a fresh token each
- [x] 4.6 Verified across all five, parameterised: every link starts `origin=Current+Location`, every part carries a link to drive, every part but the last offers the next, and every token pressed was one the bot itself offered
- [x] 4.7 No part of any journey contains "first half"

## 5. Running it

- [x] 5.1 `integration` added: both routers by name, `./data:ro`, a `tmpfs` cache that dies with the run (see 6.2 for why it is not a volume), `GOOGLE_ROUTES_ENDPOINT` at `127.0.0.1:8099`. Verified the application's counter stayed at **818** across a full run. A `recorder` service was added beside it, behind a separate `record` profile, since it is the one that spends
- [x] 5.2 The `tests` service has **no diff at all** — no router address, no `data/` mount — and its 111 tests still pass
- [x] 5.3 `docker compose config --services --profiles ""` lists only `osrm-optimal` and `osrm-toll`. `tests` and `integration` are behind `test`, `recorder` behind `record`

## 6. Recorded, not fixed

- [x] 6.1 **Two outcomes have no journey**, named in `journeys.UNPINNED` with the reason for each, and `test_the_outcomes_with_no_journey_are_named` asserts both are still declared. Nothing synthetic was added to cover them
- [x] 6.2 **A graph rebuild invalidates every recording at once**, because the request body carries the waypoints and the waypoints come from the graph. Measured: a 1 cm shift of one waypoint takes the key from `0f717f3d…` to `68db43e2…`. It fails as a wall of `Missing`, each naming the journey it could not answer, and the fix is `docker compose run --rm recorder` at 13 paid requests. The alternative — a looser key that survives a rebuild — is rejected in `key_of` for answering a question that was not asked

  **This only holds because the suite's cache is cold.** A cached route answer holds the waypoints the search produced when it was stored, and nothing detects that the graph beneath it changed. Kept between runs, a rebuilt graph would never reach the request: the old waypoints would be replayed, the recordings would still match, and the suite would pass while testing a graph it no longer uses. The cache is therefore `tmpfs` and dies with the run. Verified: a second run starts with 0 cached answers and 0 requests counted. It costs about six seconds — 16.1 s against 11.7 s
- [x] 6.3 **The recordings freeze one moment of traffic.** The suite pins how the flow handles that answer, not that Google would still give it. Recorded in the module docstring of `journeys.py`
- [x] 6.4 Only the five pinned journeys are kept: **928 KB**, from 13 paid requests rather than the 24 estimated. The probe's eleven cassettes stay in the cache volume and are not in the source tree
