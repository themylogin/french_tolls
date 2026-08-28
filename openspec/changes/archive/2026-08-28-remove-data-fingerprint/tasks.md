## 1. The links move out of the cache

Done first, because the cache key cannot lose its configuration half until nothing configuration-shaped is stored under it.

- [x] 1.1 Make `PUBLIC_SITE_URL` required in `french_tolls/service.py`: check it beside `BOOTHS = load_or_exit()` and raise `SystemExit` with a readable line naming the variable when it is unset or empty; verify the web service and the bot each exit at start-up with that line and no traceback — `french_tolls: cannot start: PUBLIC_SITE_URL is not set`, one line, no traceback, for both
- [x] 1.2 Remove the fallback at `service.py:129-137` that returns Google Maps addresses in the three link keys when no public address is configured; verify the `/go/` form is the only form `_go_url` can produce and that no branch remains on `PUBLIC_SITE_URL` — the branch is gone and the guard at import makes it unreachable
- [x] 1.3 Stop building the three links in `_describe`: drop its `endpoints` parameter and the `ours` mapping, keeping `google_url`, which is built from the route's geometry and is not derivable from the cache key; verify what `_describe` returns no longer carries `url`, `url_from_current_location`, or `url_from_current_location_through_start`
- [x] 1.4 Attach the three links to both `fast` and `optimal` in `get_route`, on the cache-hit path and the computed path alike, so a caller cannot tell the two apart; verify by answering one journey twice and comparing the two replies key for key — Lyon to Paris, 0.483 s then 0.022 s, and the two replies compare equal as whole objects. Both routes carry all three keys
- [x] 1.5 Confirm a changed `PUBLIC_SITE_URL` now reaches a journey already in the cache; verify by answering a journey, restarting with a different address, and reading the three links again without purging — restarted with `https://changed.example` and the cached journey (0.017 s, a hit) returned `https://changed.example/go/start?...`
- [x] 1.6 Remove the empty Compose default so an unset variable is reported by Compose rather than passed on as an empty string: `PUBLIC_SITE_URL: "${PUBLIC_SITE_URL:?set PUBLIC_SITE_URL in .env}"` for `web` and `bot`; verify `docker compose --profile app config` fails with that message when the variable is unset and succeeds when `.env` sets it — unset exits 15 with `required variable PUBLIC_SITE_URL is missing a value: set PUBLIC_SITE_URL in .env`; with `.env` it exits 0
- [x] 1.7 Confirm the evaluation service is unaffected; verify its own non-empty default at `docker-compose.yml:234` still applies and that its image starts — it imports only `french_tolls.geometry`, never `service`, so the guard cannot fire there. Its default is untouched
- [x] 1.8 Give the `bot` service `PUBLIC_SITE_URL`, which it never had — added scope, agreed with the user after 1.1 exposed it. See group 6

## 2. The fingerprint goes

- [x] 2.1 Remove `fingerprint()`, `FINGERPRINTED`, `FINGERPRINT_CHARS`, and the now-unused `hashlib` import from `french_tolls/data.py`; verify the module imports and that `ARTEFACTS` is still what `load` reads — `data/segment_weights.csv` was named only by `FINGERPRINTED`, so it is no longer read by this module at all
- [x] 2.2 Remove the `fingerprint` field from `BoothData` and drop it from the start-up log line; verify the line still reports the booth, lane, gare, priced, and sides counts
- [x] 2.3 Remove `_generation()` from `french_tolls/service.py` and pass the two points to `db.read_answer` and `db.write_answer`; verify no caller of either supplies a third key component
- [x] 2.4 Remove the `fingerprint` field from the failure record written by `_record_failure`; verify a recorded failure still carries `from`, `to`, `cause`, and `message`
- [x] 2.5 Drop the first parameter from `refine`, `_first_pass`, `_second_pass`, and `_store` in `french_tolls/refine.py`, and from the `db.read_refinement` and `db.write_refinement` calls; verify `service.py:238` calls `refine` with the endpoints and the optimal route alone — eleven call sites and signatures, each replaced once and checked
- [x] 2.6 Update `french_tolls/tests/booths.py` to build `BoothData` without a fingerprint, and `FakeDB.write_refinement` in `french_tolls/tests/test_refine.py` to the new signature; verify `make test` passes with the same count it has today — 66 pass, unchanged

## 3. The store

- [x] 3.1 Remove the `fingerprint` column from the `routes` and `refinements` schemas in `french_tolls/db.py`, leaving `PRIMARY KEY (from_lon, from_lat, to_lon, to_lat)` on both; verify both statements parse against a fresh database
- [x] 3.2 Reduce `_key` to the two points and update the four read and write statements; verify each names four key columns and no fifth
- [x] 3.3 Add the one-shot drop before the schema is applied: where `routes` or `refinements` exists and `PRAGMA table_info` reports a `fingerprint` column, drop that table so the `CREATE TABLE IF NOT EXISTS` below recreates it empty; verify against a copy of a real `/cache/database.db` that both tables come back empty and that `autocomplete` and `google_requests` keep every row — run against a copy of the live volume holding 10 answers and 4 refinements. Both came back with 0 rows and no `fingerprint` column; `google_requests` kept its row, and a seeded paid `autocomplete` row survived
- [x] 3.4 Confirm the drop is one-shot; verify a second start against the migrated database drops nothing and keeps the answers written since — wrote one answer and one refinement, re-ran init, both survived and read back intact; a key that was never written still misses
- [x] 3.5 Confirm the shape of the change to the store is the module's own; verify it sits with `_rename_legacy` and `_adopt_legacy_table` and introduces no version table — `_drop_fingerprinted` sits beside them and carries no version state

## 4. What an operator is told

- [x] 4.1 Rewrite the `clean-cache` comment in the `Makefile`: it is what a pipeline rebuild requires, not a way to reclaim the disk of superseded fingerprints; verify the comment no longer claims a rebuild already invalidates the cache — it now opens `RUN THIS AFTER ANY PIPELINE REBUILD` and states what the purge costs: every paid refinement and every paid autocomplete row
- [x] 4.2 Confirm `.env.example` documents `PUBLIC_SITE_URL` as required rather than optional; verify its entry says the service will not start without it — the entry was in the evaluation's section, describing the variable as read "only to build the links the report prints", which is how the bot's missing copy went unnoticed. Moved to the web application's section, marked REQUIRED, and it now names all three readers

## 5. Verification

- [x] 5.1 Run `make test`; verify the suite passes and the count is unchanged, since no test reaches the database — 66 pass
- [x] 5.2 Answer one real journey twice through the running service; verify the second is served from the cache, that both replies are identical key for key, and that the three links are absolute `/go/` addresses both times — Lyon to Paris, 505 km, 16.90 EUR. 0.483 s then 0.022 s, replies equal, all three `http://127.0.0.1:8090/go/…`
- [x] 5.3 Rebuild one artefact and answer the same journey again; verify it is still served from the cache — the behaviour this change is buying — and that `make clean-cache` followed by the same query recomputes it — touched `data/vinci_price.yaml`, restarted, still a hit at 0.021 s. Dropped the cache volume: recomputed at 0.566 s, then 0.022 s, same 16.90 EUR and same 504 601 m
- [x] 5.4 Follow one link from the page and one from the bot; verify each redirects to Google Maps and that neither consumer needed an edit — all three `/go/` forms return 302 to `google.com/maps/dir/`. `bot.py` and `www/index.js` are untouched. The bot cannot be run end to end here (`TELEGRAM_BOT_TOKEN` is unset, and it has been crash-looping on that since before this work), so its half was verified by running `get_route` inside the bot's own container: all three keys are now `/go/` addresses
- [x] 5.5 Confirm the codebase is smaller; verify `git diff --stat` shows a net deletion across `data.py`, `db.py`, `service.py`, and `refine.py`, and that no file outside those, the two test helpers, the `Makefile`, `docker-compose.yml`, and `.env.example` changed — **the file scope holds; the net-deletion claim does not, as stated.** `git diff --stat` names exactly the nine expected files and no others. But the totals are **+138 / −118**, a net gain of 20 lines. Excluding comments and blank lines the code is **+82 / −93**, a net loss of 11:

  | file | +code | −code | net |
  |---|---:|---:|---:|
  | `french_tolls/data.py` | 2 | 18 | −16 |
  | `french_tolls/service.py` | 26 | 39 | −13 |
  | `french_tolls/refine.py` | 11 | 11 | 0 |
  | `french_tolls/db.py` | 37 | 20 | **+17** |

  `db.py` grows because `_drop_fingerprinted` is new. That function is transitional: once every deployment has started once, its condition is false forever and it could be deleted. The prose is the rest of the gain — the `clean-cache` warning, the schema comments explaining that nothing detects a stale answer, and the `.env.example` entry. Those were required by the specs, and they are the point of the trade rather than an overrun.

## 6. The defect making the variable required exposed

- [x] 6.1 Add `PUBLIC_SITE_URL` to the `bot` service in `docker-compose.yml`; verify the bot gets past the start-up guard — it does, and now fails on `TELEGRAM_BOT_TOKEN`, which is unset in this checkout and is a separate pre-existing condition
- [x] 6.2 Record what the omission caused; verify the proposal and the `route-service` delta both state it — the bot took the removed fallback on every answer and sent **direct Google addresses** in the three link keys while `web` sent `/go/` ones, so every link the bot sent went to Google unrefined. That is the outcome the archived `refine-waypoints-with-google` change existed to prevent, and its proposal claims "the Telegram bot needs no edit — it reads the same three keys": true of the code, false in deployment
- [x] 6.3 Add the requirement that keeps it from recurring; verify the delta says every service answering a route query receives the address, with a scenario asserting the bot and the web application agree
