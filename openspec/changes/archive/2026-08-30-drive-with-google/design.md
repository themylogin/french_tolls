## Context

See `proposal.md` — Why. The measurements it rests on, taken today:

- Over 39 toll-paying journeys measured as the site serves them, a link follows our road **97.41% mean, 99.70% median**. The placement is not the problem.
- **19.7% of journeys (482 of 2450) have a toll-free optimal route.** For those, geometric fit is measuring a question nobody asked: any toll-free road costs the driver the same €0.
- Splitting a journey that fits badly is worth a great deal — Menton to L'Aigle 59.3% whole against 95.6% and 99.3% split; five of twenty measured halves reached exactly 100%.
- `TRAFFIC_AWARE_OPTIMAL` was worth 12.7 points when waypoints were poor and **0.8 points** against the waypoints the search produces now.

`french_tolls/bot.py` is 151 lines of handlers that call `get_route` and format a reply. It has no tests. `french_tolls/refine.py` already asks Google, measures overlap, and stores answers; `_measure` returns the share this change needs.

## Goals / Non-Goals

**Goals:**

- Send a driver a link they can follow, or say plainly why they should not follow one.
- Spend nothing on a journey nobody drives.
- Make the decision testable without a chat.

**Non-Goals:**

- Changing the waypoint search or toll accounting. Neither is implicated.
- Detecting a toll-free *part* of a tolled journey before splitting. It would save requests and is left out.
- Re-buying the corpus at `TRAFFIC_UNAWARE`. It was bought that way; this change returns to it.

## Decisions

### The decision is a function over values, and the chat is a shell around it

The requirement is that this be testable without mocking a Telegram client. The way to get that is not a better mock — it is to have nothing to mock.

```
   Telegram handler                    decide(state, event) -> (state', actions)
   ─────────────────                   ────────────────────────────────────────
   receives a press          ──────►   pure: journey, cost, budget, google answers
   performs the actions      ◄──────   yields: messages to send, requests to make,
   stores state'                       whether an action follows
```

`decide` takes a value and returns values. It performs no I/O, so a test states a journey and a sequence of Google answers and asserts the messages and the requests. There is no client to substitute, no network to intercept, and no chat to simulate.

*Alternative rejected:* a handler that calls `refine` directly and is tested with a fake `aiohttp` session. That is the "ugly mocking" the request rules out, and it tests the plumbing rather than the rules — the interesting cases here are *which* messages come out in *which* order, and a session fake says nothing about that.

The Google requests are **returned as intentions**, not made. The shell makes them and feeds the answers back in. This is what lets a test drive a split: supply two answers below threshold and assert that a split and a pending part come out, with no network.

### The state between a message and its button is a value

A button press arrives with no context but what was attached to it. Telegram's callback data is 64 bytes, which is not enough for a journey, so the state lives in the store and the button carries a key.

The state SHALL be serialisable and constructible directly, so a test of "the second half of a split journey" builds that state rather than replaying the exchange that would have produced it.

### The order of the rules

```
   pressed
      │
      ├─ part pays no tolls ──────────► link + "enable Avoid tolls"        0 requests
      │
      ├─ month's budget spent ────────► unrefined link + "not checked"     0 requests
      │
      └─ ask Google through our waypoints                                  1 request
             ├─ fits ────────────────► link
             └─ does not ──► add waypoints, ask again                      1 request
                    ├─ fits ─────────► link
                    └─ does not ──► split at the midpoint by distance
                                        └─ each half: the same rules, once more
```

Toll-free is checked **first**, before the budget, because it is the cheapest answer and the most correct one. Asking Google about a route whose whole point is to pay nothing wastes a request on a question the "Avoid tolls" setting answers exactly.

*Alternative rejected:* splitting proactively for long journeys instead of after two failures. Menton to Cluses fits at 99.2% whole and *worse* split, so a length rule would damage journeys that are already right. Two failures is evidence; length is a guess.

### Splitting is bounded at four parts

Depth two. A part that still falls short is sent as the best link available.

The bound exists because the cost compounds: 2 requests for the whole, 4 for two halves, 8 for four quarters — **14 in the worst case for one press**. Unbounded recursion has an unpredictable price and hands the driver an unpredictable number of links to open in sequence.

Parts are sent **one at a time**, each with an action for the next. Four links at once is not a route, it is a puzzle.

### Back to `TRAFFIC_UNAWARE`

This reverses a decision made earlier today. The evidence for that decision was sound and is now superseded: the setting was measured at +12.7 points against the waypoints of the time and at +0.8 against the waypoints the search produces now.

What it buys back matters more than 0.8 points. Routes **Essentials** rather than **Pro** is 10 000 free requests a month rather than 5 000, and a single press can now cost 14.

*Consequence:* the evaluation and the application ask identically again, so the corpus describes the link the application emits. The re-buy that the divergence implied is not needed.

### The overlay becomes a debug tool

Removing the per-link control and drawing on load under `DEBUG` inverts a requirement written earlier today, which said the overlay must not be gated on an operator's flag. That requirement was right about the fault it addressed — the overlay used to work only for journeys already bought — and wrong about where the page sits now. The page is not where a driver decides; the bot is. The orange line is what an operator looks at to judge fit, and it costs two requests per page load.

Orange at **twice** the green's width and beneath it, rather than thinner and above: a thin line over the top hides what it is compared against, and the eye reads "green centred in orange" as agreement much faster than it reads two overlapping thin lines.

## Risks / Trade-offs

- **One press can cost 14 requests.** A handful of complex journeys could consume a day's allowance. → Bounded at four parts, and the cheaper tier doubles the allowance. The ceiling is enforced per request as it already is.
- **`DEBUG=1` spends on every page load, and it is already set in `.env`.** → Documented, defaulted off, and the page says so when the budget runs out. An operator who leaves it on in production will notice through the counter.
- **Removing `/go/{form}` breaks any link already sent by the bot.** → Those links are in Telegram history and will 404. The alternative is keeping an endpoint alive for messages nobody will re-open; the comparison map link in old messages still works.
- **A driver may not press the button.** The message is now less immediately useful than three links were. → That is the point: the three links were sent without knowing whether any of them worked.
- **Four parts is a poor experience for the worst journeys.** → It is better than one link that goes somewhere else, and those journeys are rare.
- **The pure decision is more code than a handler that just calls `refine`.** → The request asked for testability without mocking, and this is what that costs.

## Migration Plan

1. Add the fit share and threshold to what a refinement reports.
2. Return the Google request to `TRAFFIC_UNAWARE`, and align the evaluation.
3. Write the decision function and its state, with tests, before touching the bot.
4. Rewrite the bot's handlers as a shell over it.
5. Remove the three link keys and `/go/{form}`.
6. Gate the overlay on `DEBUG`, draw on load, widen the orange.

Steps 3 and 4 are the substance; 5 and 6 are removals that depend on 4 having landed.

Rollback is per step. Step 5 is the only one that breaks anything already sent.

## Open Questions

None blocking. Whether a toll-free half of a tolled journey should be detected before the first request rather than after the split is a cost optimisation the measurement has not been taken for, and is recorded in the proposal as not addressed.
