## 1. The inventory carries the name

- [x] 1.1 Record the OSM `name` tag on every booth entry in `builder/build_osm_toll_booths.py`, representative and alias alike, omitting the key where the node has no tag; verify the writer emits it for a named node and not for an unnamed one
- [x] 1.2 Remove `data/osm_toll_booths.yaml` and re-run `make build_osm_toll_booths`; verify the step completes and the new file parses
- [x] 1.3 Confirm the rewrite is additive — the same booths, the same ids, the same order, the same types and positions, plus `name`; verify by diffing the old and new files and finding only added `name` lines
- [x] 1.4 Confirm all twelve gare-less booths now carry a name; verify Chanas, Bernay, Hochfelden, Cholet Sud, Péage de Vienne, Rosny-sur-Seine, Cagny and Beuzeville are among them
- [x] 1.5 Record how many of the 1 295 booths have an OSM name at all; verify the count and note how many have neither an operator name nor an OSM one

## 2. Naming falls through

- [x] 2.1 Read `name` from the inventory in `french_tolls/data.py`, keeping the operator's name in its own field so the two are never confused; verify a booth with both carries both
- [x] 2.2 Make `Booth.label` fall through operator name, OSM name, node id; verify each of the three cases resolves to the expected string
- [x] 2.3 Confirm the operator's name still wins where both exist; verify against a booth whose OSM name differs from its gare name
- [x] 2.4 Confirm a ticketed section names both ends by the same rule; verify a section with one operator-named end and one OSM-named end reads `<operator> → <osm>`

## 3. What is listed

- [x] 3.1 Stop listing a `passthrough` or `gantry` that carries no tariff, while still counting it as unpriced; verify a route crossing one shows no row for it and an `unpriced` count that includes it
- [x] 3.2 Keep listing every other unpriceable passage — a missing tariff, an unknown gare, an exit with no entrance, an entrance never closed; verify each still appears with its reason
- [x] 3.3 Confirm `len(peages)` no longer equals the number of crossings, and that nothing derives one from the other; verify by searching the page, the bot, and the evaluation for such a derivation
- [x] 3.4 Confirm the journey total is unchanged by the change in what is listed; verify a route crossing an unpriced gantry costs the same before and after

## 4. The unknown amount

- [x] 4.1 Render a null cost as `X €` in `www/index.js`, keeping the reason on the row; verify a real amount still renders as currency and a genuine zero still renders `0,00 €`
- [x] 4.2 Confirm no dash remains for a cost; verify the served page carries no `—` in the cost cell

## 5. Fallout from the rewritten artefact

- [x] 5.1 Confirm the data fingerprint has moved and every cached answer and stored refinement is invalidated; verify a journey recomputes rather than reading a stale answer
- [x] 5.2 ~~Refresh the fingerprint stamp on the evaluation's corpus~~ — **no stamp exists.** `report.py` reads `data/google_routes/` directly; the fingerprint stamp belonged to the unit suite's golden fixture, removed by `unit-test-the-algorithm`. Verified the report prints unchanged after the rewrite: 20 journeys, mean multiplier x0.9239
- [x] 5.3 Confirm the unit suite is unaffected; verify 47 tests pass

## 6. Verification

- [x] 6.1 Take a real journey that crosses one of the twelve and read its passage list before and after; verify the node id is gone and the OSM name is in its place
- [x] 6.2 Take a real journey crossing an unpriced gantry; verify the row is gone, the count still reports it, and the total is unchanged
- [x] 6.3 Load the page and read a passage list end to end; verify no node ids, no dashes in the cost column, and `X €` where an amount is unknown
- [x] 6.4 Confirm the pipeline's other steps are untouched; verify `make -n all` is unchanged and no other artefact was rewritten
