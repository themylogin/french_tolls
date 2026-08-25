## 1. Read the sides

- [x] 1.1 Load `data/bidirectional_booth_sides.yaml` in `builder/build_vinci_direct_prices.py` and pass it through the Makefile; verify the step reports 45 entrance/exit and 2 barrier booths at startup — reports 45 two-way booths with a toll side and 2 barriers excluded, at startup
- [x] 1.2 Stop with a clear message when a `bidirectional` group in the price file has no entry in the sides file; verify by removing one entry — load_sides names the booths and says to run build_booth_sides

## 2. Exclude barriers from the grid

- [x] 2.1 Drop a barrier from the source list and from the target list before routing, alongside self-pairs, same-gare pairs and prohibited pairs; verify sources fall 516 to 514 and targets 513 to 511 — sources 516, targets 513, the 2 barriers dropped from both lists before routing
- [x] 2.2 Verify no route and no rate request is issued for any pair naming a barrier — outstanding_for returns nothing for a barrier source and never offers a barrier target

## 3. The side test

- [x] 3.1 Reject a pair whose two-way source is departed by a node in its `outside_nodes`; verify against a synthetic route leaving by each side — a source left by its free side is rejected, by its toll side is kept
- [x] 3.2 Reject a pair whose two-way target is arrived at from a node in its `outside_nodes`; verify the same — a target reached from its free side is rejected
- [x] 3.3 Apply no side test to a one-way booth at either end; verify a one-way pair is judged exactly as before — a one-way pair is not side-tested
- [x] 3.4 Verify the node tested is the one immediately beside the booth, the same one the sides were established from — the node tested is the one immediately beside the booth, both ends

## 4. The rejection record

- [x] 4.1 Add `reason` to the `rejected` table and make `blocker` nullable; verify a fresh database carries both and that an old one is refused with a message saying to delete it — reason added, blocker nullable; the old database was refused naming the column and the remedy
- [x] 4.2 Record `booth` with the blocking group for a pair with something in the way, and `wrong side` with no blocker otherwise; verify one row of each — one row of each reason, blocker null for a wrong side; a booth in the way wins and names the booth
- [x] 4.3 Verify the resume path still skips every recorded pair whatever its reason — resume skips a recorded pair whatever its reason

## 5. Re-derive the affected prices

- [x] 5.1 Discard every price whose source is a `bidirectional` group or whose target gare is carried by one; verify 4 027 of 23 148 go and 19 121 remain — 4 027 discarded of 23 148, 19 121 remain, 0 surviving prices touch a two-way booth
- [x] 5.2 Verify a price with a one-way booth at both ends is untouched and is not re-asked — one-way pairs kept exactly: 19 121 of 19 121, types unchanged
- [x] 5.3 Verify step 6 reloads the trimmed file under `load_state` without an `Abort` — step 6 reloads the trimmed file: 1267 booths, 774 routes

## 6. Run it

- [x] 6.1 Rebuild the rejection database, run the step under `--survey`, and record pairs routed, rejected by booth, rejected by side, and priced — 242 623 routed, 238 158 rejected (238 141 booth, 17 wrong side), 4 130 priced, 71.4 min
- [x] 6.2 Verify the 15 two-way `unexpected answer` findings are gone; for any that survives, record what the route does instead — all 15 two-way `unexpected answer` findings gone; the 335 that remain are all `blacklisted route`
- [x] 6.3 Compare the priced count per two-way booth against the discarded 4 027; a booth that loses nearly all of its pairs is a signal its sides are wrong, and SHALL be reported rather than accepted — no booth lost nearly all its pairs; largest loss 2 of 4 (BROGLIE/ORBEC SENS 2). MER 110->110, CHATENOIS 110->110, ARLAY 118->117
- [x] 6.4 Verify the final price file reloads under step 6 and that step 6 reports no contradiction — step 6 reloads: 23 251 prices, no wrong-typed entry, no contradiction
