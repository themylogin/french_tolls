## Context

See `proposal.md` — Why.

- `french_tolls/bot.py` builds its `Application` inside `main()`, from `os.environ`, and calls `run_polling`. There is no way in.
- `users_from`, `pending` and `_next_token` are module globals.
- `french_tolls/refine.py` posts to `ROUTES_ENDPOINT`, a module constant, through `_ask_google`.
- `db.CACHE_DIR`, `refine.API_KEY`, `refine.MONTHLY_CEILING`, `service.BOOTHS` and `service.PUBLIC_SITE_URL` are all read at **import**. A harness cannot set them after importing the package, which is why the runner is a Compose service with its own environment rather than a fixture.
- python-telegram-bot is 21.11. `telegram.request.BaseRequest` has one abstract call worth anything: `do_request(url, method, request_data) -> (int, bytes)`.

## Goals / Non-Goals

**Goals:**

- Assert the transcript a driver would have seen, for each way a journey can resolve.
- Spend nothing per run, and buy real answers when refreshing.
- Replace exactly two things: the service that costs money, and the one that needs a chat.

**Non-Goals:**

- Testing the waypoint search or the accounting. `route-algorithm-tests` does that against a hand-built graph, and does it better.
- Testing Google. Its answers are input.
- Covering every journey. Five outcomes, one journey each.

## Decisions

### The Telegram seam is the transport, not the library

`ApplicationBuilder().request(fake).get_updates_request(fake).updater(None)`, then `await application.process_update(update)`.

The fake answers seven endpoints with payloads the library parses into its own objects, so `Message`, `CallbackQuery` and the markup are all built as they are in production. Nothing above the transport can tell.

*Alternatives rejected:*

- **Substituting a `Bot`.** Then `Message.reply_text`, `edit_text`, `delete` and the markup construction are all fake, which is most of what the shell does.
- **Patching methods.** The spec `telegram-drive-flow` already forbids substituting objects for the messaging library, and patching is that with extra steps.

*What it requires from `bot.py`:* one factory that takes the transport, and state in `application.bot_data`. Both are small, and the second fixes a real defect — two applications in one process currently share `pending`, so the second test would answer the first test's button.

### The Google seam is the endpoint, not the function

`ROUTES_ENDPOINT` becomes configurable. The suite runs a small HTTP server that answers `computeRoutes` from the recordings, and points the application at it.

This is the decision I am least likely to be talked out of. Patching `refine._ask_google` would skip the field mask, the JSON encoding, the status handling and the error path — the parts most likely to break silently. Pointing the real client at a local server exercises all of them, and the client does not know.

It is also what makes "cannot spend money" structural rather than a promise. With the endpoint at localhost, a real key in the environment by accident still buys nothing.

*Consequence:* `API_KEY` must be non-empty or `ask_once` returns None before it asks. The runner sets a placeholder. The safety comes from the endpoint, not from the key, and the spec should say so in those terms.

### A recording is keyed by the whole request body, and a miss is an error

```
  key = sha256(canonical json of the request body)
```

A request with no recording fails the test and names itself. It is never forwarded.

The cost is real: the body carries the waypoints, the waypoints come from the search, and the search reads the graph. **Rebuild the graph and every recording misses at once.** The fix is a re-record, about 24 paid requests.

*Alternative rejected:* keying on `(origin, destination, ask index)` and asserting the waypoints separately. It survives a rebuild, and it answers a question that was not asked — a moved waypoint would return the old route and the test would pass while asserting nothing. A suite that fails loudly on a graph rebuild is telling the truth; one that quietly replays a stale answer is not.

*Provenance to store with each recording:* the routing preference it was bought under, because `buy-googles-best-search` changes what the same journey resolves into. There is no version string for the graph, so a rebuild is detectable only as a wall of misses. That is acceptable — it is loud.

### The runner is a fifth Compose service

`tests` is specified to run with the routers stopped and no `data/` mounted, and that requirement is the point of it: it proves the logic runs on a bare checkout. This suite cannot run without 30 GB of graph. One service carrying both sets of dependencies would make the unit suite unrunnable in exactly the case it exists to cover.

### What a test asserts

The recorded calls, in order: text, links, buttons — and the number of paid requests the flow would have made. The request count is the operator's bill, and nothing else in the suite would notice it doubling.

## Risks / Trade-offs

- **A graph rebuild invalidates every recording.** → Loud, not silent, and a re-record is 24 requests. Recorded here so it is not a surprise.
- **The recordings freeze one moment of traffic.** `TRAFFIC_AWARE_OPTIMAL` moves with traffic, and the first ask moves most: one journey measured 91.0% of our road at the old setting and 10.9% at the new. The suite tests that the flow handles *that* answer correctly, not that Google still gives it. → Correct, and worth stating: this pins our behaviour, not Google's.
- **Two outcomes have no journey.** A split into three, and a first ask that beats the fit share with matching booths. Both got rare under the better search. → Named in the spec as unpinned. A synthetic journey would pin an outcome the application does not produce.
- **1.8 MB of recordings for eleven journeys.** A route is a 60 KB polyline. → Only the pinned journeys need keeping; the rest can be dropped.
- **The bot gains a factory it would not otherwise have.** → It is four lines, and `main()` uses it too, so it is not a test-only path.

## Migration Plan

1. Land `buy-googles-best-search`. Nothing here is valid before it.
2. Add the factory and move the state to `bot_data`; the unit suite still passes.
3. Make `ROUTES_ENDPOINT` configurable.
4. Add the fake Telegram transport and the replay server.
5. Keep the recordings for the five pinned journeys; drop the rest.
6. Add the Compose service and run it.

Rollback is deleting the suite and the service. The factory and `bot_data` stay — they are improvements on their own.

## Open Questions

None blocking. Whether to pin a sixth journey for the fallback path — where the trace will not match and the geometric test decides — is worth doing when a real one turns up; one appeared during recording and was refused for other reasons.
