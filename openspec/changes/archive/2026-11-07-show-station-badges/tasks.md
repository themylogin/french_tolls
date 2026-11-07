# Tasks

## 1. Badge rules

- [x] 1.1 In `french_tolls/refuel.py`, add `station_badge(services, address)` with the three rules of the design, and add it to `__all__`. Add unit tests in `french_tolls/tests/test_refuel.py` with the literal values of the spec: `["Automate CB 24/24", "Lavage automatique"]` gives `"24"`; `Automate CB 24/24` with the line `Autoroute A7` gives `"24"`; the lines `Autoroute A7` and `aire de l'autoroute` give `"Autoroute"`; `Aire de Beaune`, `aire des Volcans`, `aire du Poitou`, `aire d'Orange`, `aire d’Orange`, and `A71aire de ste thorette` give `"Aire"`; `38460 Saint hilaire de brens`, `Zi portuaire des mielles`, and the lines `Rue de quimper` and `29520 Chateauneuf du faou` without services give `None`. Verify with `make test`.
- [x] 1.2 Add `badge` to `_station_entry`. Give `insert_station` in `test_refuel.py` the parameters `services` and `address`, with the current values as defaults. In `test_each_listed_station_carries_its_keys`, expect `"badge": None`. Add a plan test: a station with the service `Automate CB 24/24` is listed with `"badge": "24"`. Verify with `make test`.

## 2. Page

- [x] 2.1 In `showRefuelAnswer` of `www/index.js`, add a space and `<b>` with the escaped `badge` after the name link, when `badge` is not null. Verify in the browser, with a stubbed answer: the `badge` `"24"` shows `Leclerc` **24**, and the `badge` `null` shows only the link.

## 3. Integration checks

- [x] 3.1 Run `make test` and `docker compose --profile test run --rm --no-TTY integration`. Verify that the unit suite passes. Verify that the integration suite fails no test beyond the 4 tests in `test_drive_flow.py` that failed before.
- [x] 3.2 With the agreement of the operator, run `make web`. Call `POST /api/refuel` for Paris to Marseille with the fuel `20`, and verify that each listed station carries `badge`. After a hard refresh, open the dialog on the same journey and verify that the badges show in bold after the names.
- [x] 3.3 Run `openspec validate show-station-badges --strict`. Verify that the change is valid.
