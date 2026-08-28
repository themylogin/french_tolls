## Context

See proposal.md — Why.

The fingerprint is not one thing in one place. It is a digest in `data.py`, a field on `BoothData`, a column in the primary key of two tables in `db.py`, the first parameter of four functions there and of five in `refine.py`, and half of `_generation()` in `service.py`.

The other half of `_generation()` is what makes this more than a deletion:

```python
def _generation():
    return BOOTHS.fingerprint + ":" + hashlib.sha256(
        PUBLIC_SITE_URL.encode()).hexdigest()[:8]
```

That second hash guards a real failure. The cached answer carries three links built as `{PUBLIC_SITE_URL}/go/{form}?from=…&to=…`, so a service whose address changed would serve links to its old one forever.

But the links do not have to be in the cache. `_describe` builds them from `endpoints=(from_, to)` — and `from_` and `to` *are* the cache key. Anything derivable from the key does not need to be stored under it. That observation is what lets the whole key collapse to the coordinate pair rather than to the pair plus a configuration hash.

One thing blocks it today. `service.py:129` branches: with no `PUBLIC_SITE_URL`, the three keys hold Google Maps addresses instead of `/go/` paths. So the config decides the *kind* of link, not just its prefix, and a link rebuilt after the cache read would have to know which branch the answer was written under. The operator has settled this: `PUBLIC_SITE_URL` is required and the `/go/` form is the only form. With one shape, the branch disappears and the derivation holds.

## Goals / Non-Goals

**Goals:**

- Remove the fingerprint from every place it reaches.
- Reduce both cache keys to the origin and the destination.
- Keep the answer's observable shape exactly as it is, including the three links as absolute addresses.
- Leave `bot.py` and `www/index.js` untouched.

**Non-Goals:**

- Making the three links relative. The bot puts them in Telegram messages, which have no origin to resolve a relative path against. They stay absolute; only where they are assembled moves.
- Preserving paid refinements across the schema change. The operator chose to drop them.
- Any new mechanism for noticing a stale cache. There is deliberately none. `make clean-cache` is the whole story.
- Touching the `autocomplete` or `google_requests` tables.

## Decisions

### The three links are attached after the cache read, not stored

`get_route` returns the cached mapping directly on a hit. The three links are added to both `fast` and `optimal` on the way out, on a hit and a miss alike, so the two paths cannot drift.

`_describe` stops taking `endpoints`. What it returns is what is cached.

The alternative — keeping the `PUBLIC_SITE_URL` hash as the surviving half of the key — was rejected because it keeps a column, a helper, and a parameter alive to store something the key already determines. It also has a worse failure mode: changing the address silently strands every cached answer rather than updating it.

`google_url` is the exception and stays in the cached answer. It is built from the route's own geometry, not from the endpoints, so it is not a function of the key.

### `PUBLIC_SITE_URL` is checked at import, next to the artefacts

`service.py` already does `BOOTHS = load_or_exit()` at module scope, and `data.load_or_exit` raises `SystemExit` with a readable line. The address check goes beside it and fails the same way. Both entry points reach it — the web service through `api`, the bot through `service` — which is the reason that guard lives there rather than in each.

`docker-compose.yml` passes `PUBLIC_SITE_URL: "${PUBLIC_SITE_URL:-}"` to `web` and `bot`. That empty default now means a service that will not start. The default is removed so Compose itself reports the unset variable, rather than passing an empty string that the application then rejects one layer later.

### The old rows are dropped by detecting the column, not by a version number

`CREATE TABLE IF NOT EXISTS` will not alter a table that already exists, so a database written under the old schema would keep a `fingerprint` column that the new statements do not mention. Every read would miss and every write would fail on the NOT NULL column.

At init, before the schema is applied: if `routes` or `refinements` exists and `PRAGMA table_info` reports a `fingerprint` column, drop that table. The `CREATE TABLE IF NOT EXISTS` that follows recreates it empty.

The condition is false ever after, so this is one-shot without a version table to carry. `db.py` already has `_rename_legacy` and `_adopt_legacy_table` doing exactly this kind of one-time repair, so the shape is the module's own.

A migration that kept the rows was considered and rejected by the operator. It would collapse several fingerprints of one journey to one row, which needs a rule for which survives, and the code to do it runs once and is read forever.

### `refine()` loses the parameter rather than ignoring it

`refine`, `_first_pass`, `_second_pass`, `_store`, and the two `db` calls drop `fingerprint`. Keeping it as an unused first argument would leave every call site explaining a value nothing reads.

## Risks / Trade-offs

**A stale answer is a wrong toll total that looks exactly like a right one.** → This is the change's whole cost, and it cannot be mitigated in code without rebuilding what is being removed. It is mitigated in prose, where the operator will meet it: the `clean-cache` comment stops saying the purge is unnecessary and starts saying it is what a pipeline rebuild requires. The spec carries the same statement so it is not merely a comment.

**Every stored refinement is lost, and each cost up to two paid Google requests.** → Accepted on the operator's instruction. It happens once, on the first start after the change. Journeys are re-refined lazily as they are asked for, within the monthly ceiling that already bounds spending.

**A deployment with no `PUBLIC_SITE_URL` stops starting.** → Intended, and the readable exit is the mitigation. `.env` sets it and `.env.example` documents it, so the current deployment is unaffected. Removing the empty Compose default is what keeps the failure from arriving as an empty string.

**The evaluation service also receives `PUBLIC_SITE_URL`.** → It has a non-empty default at `docker-compose.yml:234`, so it is unaffected. Confirm during implementation that the evaluation image does not import `service` under an empty value.

**Nothing in the test suite covers the cache.** → `test_cost.py`, `test_waypoints.py`, and `test_refine.py` reach neither the database nor the network, and that is a property worth keeping. The cache changes are verified by inspection and by one real journey answered twice, not by a new test that would need a database.

## Migration Plan

There is no separate step. Deploying the code performs the drop on first start.

Rollback is reverting the code, which restores the fingerprint columns by the same mechanism in reverse: the old `CREATE TABLE IF NOT EXISTS` will not add a column to the new tables, so a rollback needs the tables dropped again. `make clean-cache` does that and is the documented answer either way.
