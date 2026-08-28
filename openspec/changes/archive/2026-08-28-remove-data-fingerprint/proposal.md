## Why

The data fingerprint exists so that a rebuilt pipeline never reaches a cached answer. It buys that automatically, and it costs a SHA-256 over five artefacts at start-up, a field on `BoothData`, a column in the primary key of two tables, a parameter threaded through every cache call and through the whole of `refine.py`, and a `_generation()` helper that mixes it with a second hash.

The operator does not want it bought automatically. A pipeline rebuild is a deliberate act, and `make clean-cache` already exists to follow it. Paying for automatic invalidation in code that is read every day, to avoid one command run a few times a year, is the wrong trade.

Removing it exposes a second thing in the same key. `_generation()` also hashes `PUBLIC_SITE_URL`, because the answer carries three links built from it. That is only necessary because the links are stored in the cached answer, and they need not be: they are a pure function of the two coordinates, which are the cache key itself. Building them after the cache read removes the second half of the key for the same reason as the first.

## What Changes

### The fingerprint goes

- **BREAKING** `data.fingerprint()`, `FINGERPRINTED`, `FINGERPRINT_CHARS`, and `BoothData.fingerprint` are removed. Nothing computes a digest of the artefacts, and the start-up log line stops reporting one.
- **BREAKING** The `fingerprint` column leaves the primary key of `routes` and `refinements`. A cached answer and a stored refinement are keyed by the origin and the destination alone.
- **BREAKING** Rows already stored under the old schema are dropped, not migrated. On the first start after this change, `routes` and `refinements` are recreated empty if they still carry the column. The `autocomplete` and `google_requests` tables are untouched: autocomplete rows each cost a paid LocationIQ request, and the month's count is what stops this service spending money.
- The cost of that: every stored refinement is lost, and each cost up to two paid Google requests. Accepted deliberately — the alternative is migration code that runs once and is then read forever.
- `refine()` and its four helpers lose their first parameter.
- `make clean-cache` becomes the only way a rebuilt pipeline reaches the cache. Its comment stops claiming it is unnecessary.

### The links are built after the cache, not stored in it

- `_generation()` is removed outright. `db.read_answer` and `db.write_answer` take the two points.
- **BREAKING** The three link keys — `url`, `url_from_current_location`, `url_from_current_location_through_start` — are no longer part of what is written to the cache. They are attached to both routes on the way out, on a cache hit and a miss alike. What a caller receives is unchanged: the same three keys, the same absolute addresses.
- `google_url` stays in the cached answer. It is built from the route's own geometry rather than from the endpoints, so it is not derivable from the key.

### `PUBLIC_SITE_URL` becomes required

- **BREAKING** A service started without `PUBLIC_SITE_URL` exits with a readable line, as it already does for a missing artefact. It does not start and serve something else.
- **BREAKING** The fallback that returns Google Maps addresses in the three link keys when no public address is configured is removed. The `/go/` form is the only form.
- This is what lets the links be rebuilt after the cache read: with one shape and a required address, the three links are a function of the two coordinates and nothing else.

### A defect the requirement exposed

Making the variable required surfaced that the `bot` service never received it. `docker-compose.yml` passed `PUBLIC_SITE_URL` to `web` and not to `bot`, so the bot took the fallback branch on every answer and sent **direct Google Maps addresses** in the three link keys, while `web` sent `/go/` addresses. The two consumers have disagreed about what those keys mean since `refine-waypoints-with-google` landed.

That change's own proposal states the intent it did not achieve: "The Telegram bot needs no edit — it reads the same three keys." True of the bot's code, and false in deployment. Every link the bot sent went straight to Google unrefined, which is the outcome that change existed to prevent.

- **BREAKING** `PUBLIC_SITE_URL` is added to the `bot` service. Telegram users now receive `/go/` links that refine before redirecting, rather than direct Google links.
- Two things kept this invisible. The bot has never started in this checkout — `TELEGRAM_BOT_TOKEN` is unset, so it crash-loops before reaching any of it. And `.env.example` documented the variable under the evaluation's section, describing it as read "only to build the links the report prints", which is what it was believed to do. That entry moves to the web application's section and says what it is.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `route-service`: the cache key requirement names a fingerprint that will not exist; the configuration requirement does not currently make `PUBLIC_SITE_URL` mandatory; the link requirement admits a Google-address fallback that is being removed.
- `google-route-refinement`: it requires a refinement to be invalidated by the same data fingerprint that invalidates a route answer. There will be no such fingerprint.

## Impact

- Modified: `french_tolls/data.py` (the digest and the field), `french_tolls/db.py` (two schemas, the key, four functions, a one-shot drop), `french_tolls/service.py` (`_generation`, the link fallback, the failure record, the two cache calls, link assembly moved after the read), `french_tolls/refine.py` (the parameter, five signatures), `french_tolls/tests/booths.py`, `french_tolls/tests/test_refine.py`, `Makefile` (the `clean-cache` comment).
- Unchanged: `french_tolls/bot.py` and `www/index.js`. Neither needs an edit; both read the three link keys. The page receives exactly what it receives today. The bot receives `/go/` links where it used to receive direct Google ones, which is what it was always meant to receive.
- Data: `/cache/database.db` keeps its autocomplete rows and its month counter. Route answers and refinements are dropped once, on the first start.
- Operationally: after `make all` or any artefact rebuild, run `make clean-cache`. Nothing detects a stale answer any more, and a stale answer is a wrong toll total that looks exactly like a right one.
