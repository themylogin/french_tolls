## 1. The accounting

- [x] 1.1 In `french_tolls/tolls.py`, keep the last `gantry` crossed with no ticket open and no flat price of its own; on an `exit` reached with no ticket open, price the passage at that gantry's fare for the exit's gare, and take back the unpriced crossing recorded for the gantry
- [x] 1.2 Apply the same look-back in `closed_sections`, which pairs entrances with exits for the split advice, so the advice and the charge describe the same section
- [x] 1.3 Hold one gantry, not a list — an earlier one belongs to a section already settled
- [x] 1.4 Leave the flat-gantry and passthrough branches untouched, so a gantry that collects where it stands is not also billed a section

## 2. The tariff lookup

- [x] 2.1 In `french_tolls/booths.py`, gather tariffs under the gare code across every group carrying it, built once with the booth table
- [x] 2.2 Use it for a gantry only. An entrance the route crossed keeps reading its own mapping, so no fare that is correct today can move
- [x] 2.3 Verify the amounts agree where two groups of a gare both hold a pair: 210 shared pairs, 0 contradictions
- [x] 2.4 Put the rule in one function, `tolls.fare`. `account`, `route._ticket_price` and `route._plan_split` all call it. Before this, `route` read `entrance.prices` directly and skipped in silence every section `closed_sections` opened at a gantry — the disagreement 1.2 exists to prevent, half-fixed
- [x] 2.5 Record why the two lookups differ: `vinci-direct-pricing` never enumerates a gantry as a source (`SOURCE_TYPES = (ENTER, BIDIRECTIONAL)`), so a gantry is priced only by the routes that cross it — 0 rejections and 3 tariffs against the neighbouring booth's 538 and 27. A group that *is* enumerated can still be blocked pair by pair: Corze's two entrances hold 29 and 5 after 534 and 560 rejections

## 3. Tests

- [x] 3.1 Add the look-back cases to `french_tolls/tests/test_cost.py`: an exit priced from the gantry behind it, the tariff found under a sibling of the gantry's gare, an exit with no gantry behind it, and a flat gantry not billed a section
- [x] 3.2 Keep the case that a crossed entrance reads only its own tariffs
- [x] 3.3 Add the section-from-a-gantry case to `french_tolls/tests/test_splits.py`, so `closed_sections` agrees with `account`
- [x] 3.4 Add `test_every_reported_section_has_a_fare`, asserting `closed_sections`, `fare` and `account` agree on one section; verify it fails when the gantry branch is removed from `fare`
- [x] 3.5 Run `make test` — 157 service tests, 27 builder tests
- [x] 3.6 Run the integration suite; confirm the 4 `split-all-tolled` failures are on `master` too and predate this change
- [x] 3.7 Build the test images before trusting a run. `docker-compose.yml` gives `tests` `build: .` with no bind mount, so `compose run tests` reuses a baked image and reports the previous commit's result. A run taken this way hid a wrong assertion in `test_a_gantry_that_charges_flat_is_not_also_billed_as_a_section`: `reasons()` returns every passage, including a priced one with `reason` None

## 4. The journey that started this

- [x] 4.1 Query Le Boulou → Annecy: the last passage reads `CHAMBERY NORD → ANNECY CENTRE` at 5.60 EUR
- [x] 4.2 `optimal.unpriced` falls from 2 to 0
- [x] 4.3 `optimal.cost` moves 47.60 → 53.20, and the optimal route is unchanged
- [x] 4.4 The superoptimal route carries the same section at the same fare, so the split advice and the charge agree
- [x] 4.5 Rebuild the app images and recreate the containers; `web`, `bot`, `nginx` and both routers up, no errors logged

## 5. What it reaches

- [x] 5.1 Count the gantries the look-back can use: 6 of 56 carry tariffs and no flat price
- [x] 5.2 Count what the gare-wide lookup adds: Chambéry Nord 3 → 27 tariffs; the five A79 gantries are 1 → 1, so the widening reaches one plaza
- [x] 5.3 Confirm no priced passage can change — the look-back is reached only on the branch that previously recorded "exit without an entrance"
- [x] 5.4 Name the other consumers of a gantry's tariffs, so the blast radius is known: `build_segment_weights` already takes any group with `prices` as a source, with no type filter, and `build_cost_cutting.load_prices` already merges by gare. `build_toll_extent` reads `ENTER` and `BIDIRECTIONAL` only and is unaffected

## 6. Not done

- [ ] 6.1 A section between two gantries is still not one passage. The A79 chain prices portal to portal, and the second portal is a `gantry` rather than an `exit`, so the look-back never fires there. Out of scope: it is a second journey shape, and no reported route needs it
- [ ] 6.2 The frontend still shows a bare `× €` for a passage it cannot price. The API carries `reason` and the frontend discards it. Separate from this change, which removes one cause rather than the display
