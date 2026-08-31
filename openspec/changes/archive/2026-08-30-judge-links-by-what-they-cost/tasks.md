## 1. The router will match a whole trace

- [x] 1.1 Start `osrm-toll` with a matching size a real trace fits in; verify a real trace is accepted in one request and that the default 100 refuses it — a 699 km route thins to 2 068 points and matches in one piece; the default of 100 refuses it. **Changed from the original wording**: a 36 000-point trace is now refused on purpose, see 1.2
- [x] 1.2 Choose the number deliberately rather than inheriting it, and record why; it bounds what a single call can cost the router — `--max-matching-size 10000`, about twice the longest thinned trace and deliberately below what an unthinned polyline carries, so an unthinned trace is refused rather than served slowly. Recorded in `docker-compose.yml`; measurements in `equivalence.TRACE_SPACING_M`
- [x] 1.3 Verify nothing else about the service changes: routing, snapping and the table service answer as before — `data/check_service.py`: snap 42.9 m, route 699.3 km / 10 807 nodes, table answers both directions

## 2. Turning a geometry into the booths it crosses

- [x] 2.1 Add a match request to the router client, asking for node annotations and no geometry; verify it goes to the untouched graph — `Routers.match`, covered by `test_the_trace_is_matched_on_the_untouched_graph`
- [x] 2.2 Send the whole trace in one request, never in windows; verify by a test that a windowed variant is not reachable from the public function — `test_the_whole_trace_goes_in_one_request` counts the requests and the coordinates in the one that was made
- [x] 2.3 Drop each leg's leading node except the first; verify a leg boundary beside a booth charges that booth once — `test_a_repeated_leg_head_does_not_become_a_second_charge`, plus `test_the_matched_nodes_are_a_path` for the node left repeated in place
- [x] 2.4 Price the matched sequence with the existing accounting, unchanged, so aliases and booth sides behave as they do for our own routes — `tolls.py` gains `booths_crossed` and nothing else; `account` is untouched
- [x] 2.5 **The control**: matching our own route SHALL price back to our own bill — **210/210** over 210 journeys, same bill and same booth set, at 0.08 s a match (`data/control_match.py`). The matched node sequence is our own route's node sequence exactly: 10 807 nodes, in order, no step back
- [x] 2.6 Report when the matcher returned the trace in more than one piece, so a caller can tell an answer from a guess — `Match.pieces` / `Match.whole`; `matched_nodes` returns None rather than a guess

## 3. The acceptance rule

- [x] 3.1 Accept a Google route that crosses no booth the optimal route does not; verify a route crossing a strict subset is accepted and one crossing an extra booth is not — `drive.accepts`, `test_a_route_paying_fewer_of_our_tolls_is_not_a_fault`, `test_a_route_that_adds_a_toll_is_not_accepted_however_well_it_followed`
- [x] 3.2 Try the toll test before the geometric one; verify a route below the fit share with identical booths is sent with no waypoint added and no split — `test_a_route_on_a_different_road_but_the_same_tolls_is_sent_as_it_is`, `test_the_tolls_are_asked_before_the_road`
- [x] 3.3 Fall back to the geometric test where the tolls could not be established; verify a broken trace is judged on overlap and is not called equivalent — `test_a_route_whose_tolls_are_unknown_is_judged_on_the_road`, and on our side `test_a_part_whose_own_tolls_are_unknown_is_judged_on_the_road`
- [x] 3.4 Record which test accepted a route; verify a caller can tell "drove our road" from "pays our tolls" — `Message.basis` is `TOLLS`, `ROAD`, or None; asserted in every acceptance test and logged by `bot.send_outcome`
- [x] 3.5 Keep the rule in the decision and out of the refinement; verify nothing in `refine.py` compares booth sets — `refine.ask_once` returns `Asked`, which carries Google's geometry and no opinion about it; the word "booth" does not appear in `refine.py`
- [x] 3.6 Cover the branches with tests that supply booth sets as values, as the existing decision tests supply Google answers — eight tests, booth sets written as plain integers

## 4. The wording

- [x] 4.1 Describe a part as the next one rather than the first half; verify a journey halved twice sends three links and none claims to be the first half — done, `COMPLEX` now reads "This route is complex. Here is the next part of the route.", covered by `test_the_message_does_not_call_every_part_the_first_half`, suite 89 passing
- [x] 4.2 Confirm numbering is not available as an alternative: splitting is lazy, so the total is unknown when the message is written — recorded in `design.md`

## 5. Verification

- [x] 5.1 Re-run the corpus comparison with the criterion in place and record what it accepts — `data/corpus_criterion.py` and `data/corpus_summary.py` over **500 cached journeys**, no paid request. Accepted on the first ask: **53.6% under the share alone, 81.8% with the tolls first**. 162 newly accepted, and **none of the 162 costs the driver more than our own route**. 21 no longer accepted, at €3.89 more on average. 30 could not be priced and fall back to the share
- [x] 5.2 Measure what the criterion costs in latency per part, and what it saves in paid Google requests per journey — **0.08 s** a match, twenty times cheaper than the 1.6 s measured while establishing this, and unpaid. It removes a paid request on 28.2% of journeys net (162 that no longer need a correcting ask, less 21 that now do), before counting the split cascades it avoids, which cost up to twelve more each
- [x] 5.3 Verify the journeys the criterion still rejects are rejected for a reason — `data/check_rejected.py`: Embrun to Ancenis-Saint-Géréon, Google pays **€72.00 against our €37.80** at 58.1% overlap, crossing 7 booths ours avoids (A48/A6/A71/A85 instead of the A75 corridor). Rejected on its tolls, corrected, then split. The same journey driven the other way is 99.6% overlap, an identical booth set, and is now accepted on its tolls
- [x] 5.4 Confirm the unit suite passes and that the waypoint search, the pipeline and toll accounting are untouched — **111 passing**, up from 89. `search.py` and `builder/` have no diff at all; `tolls.py` gains `booths_crossed` and changes nothing else
- [x] 5.5 Check the booths missed on Google's geometry across a wider sample, and confirm none of them causes a route to be accepted that should not be — of the 500, **148 journeys ran at 99.5% or more of our road, and not one of them is priced as crossing fewer booths than ours**. At that overlap a difference would be a booth the matcher missed rather than a road the driver took, so this is where a miss would show, and there is none. The 9-of-716 measured while establishing the method was before the trace was matched in one request and thinned

## 6. Recorded, not fixed

- [x] 6.1 The corpus was bought under an earlier waypoint placement, so its geometry describes links the application no longer emits. The 162-of-232 figure is indicative rather than a promise about today's links
- [x] 6.2 This makes the drive flow depend on the toll inventory being complete. A booth missing from it is a booth neither route is charged for, and two routes that are not equivalent would be called equivalent. That was already true of every price quoted; it now also decides whether a link is corrected
- [x] 6.3 Containment never fired as a strict subset on the corpus: all 162 newly accepted routes cross *exactly* our booth set. Equality would have given the same answer here. Containment is kept because the asymmetry is real — a cheaper route is not a fault — not because it was observed
- [x] 6.4 **Worth a look, out of scope here.** 16 of the 21 journeys the criterion newly rejects cross one barrier: BPV SAUGNAC on the A63, a €4.40 passthrough. Our route avoids it and Google's does not, at 98–99% overlap — the free road and the tolled one run in each other's corridor there, which is precisely why the geometric test cannot see the difference. Whether our route is right to avoid it is a question about the graph, not about this criterion
