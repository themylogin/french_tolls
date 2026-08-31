## Why

The decision has tests. The thing a driver touches has none.

`telegram-drive-flow` already requires the rules to be a decision over values, tested without a chat, and they are — eighteen tests state a journey and a sequence of Google answers and read off the messages. Everything between those rules and a driver is untested: the handlers, the order the messages arrive in, the buttons and the tokens they carry, the links, and what the shell hands the decision in the first place.

Every defect found in this area lived there. A bot started with an empty token. A bot running a stale image because `--build web` does not rebuild `bot`. A bot with no Google configuration, so its ceiling read zero and every driver was told the link had not been checked. A message that called three different stretches "the first half of the route". Not one of those is reachable from a decision test, and not one would have survived a run of the exchange end to end.

The scenarios that matter are also too big to hold in the head. Driving one journey to its end can cost eight paid Google requests across three presses, and which part splits depends on answers nobody can predict. That is exactly what a recorded test is for.

## What Changes

- **A seam in the bot.** The Telegram application SHALL be constructible for a test, with its transport supplied rather than opened, and its state held per application rather than in module globals.
- **A fake Telegram.** A transport that answers the Bot API from written responses and records every call, so the assertion is the transcript a driver would have seen: the messages, in order, with their text, their links and their buttons.
- **Recorded Google answers.** Real answers to real requests, bought once and kept as JSON beside the suite. Replayed by request body, so a test spends nothing and returns the same answer every run.
- **Real OSRM, real booth data.** The routers and `data/` are cheap, local, and the thing being tested; only Google and Telegram are replaced.
- **A Compose service to run it.** The existing `tests` service is specified to depend on nothing at all, and that stays true. The integration run is a separate service with the routers, `data/`, and a scratch cache.

The scenarios pinned, all recorded under `TRAFFIC_AWARE_OPTIMAL`:

```
  optimal is free, no request made        Ancenis-Saint-Géréon -> Ploërmel   0 asks
  accepted on the first ask               Cogolin -> Apt            89.8%    1 ask
  accepted on the first ask               Cogolin -> Saint-Gaudens  97.9%    1 ask
  corrected, then accepted, nine points   Ancenis... -> Lure  82.8% -> 99.7% 2 asks
  corrected, then accepted                Luçon -> Bayeux     10.9% -> 92.2% 2 asks
  split in two, first part toll-free      Lodève -> Cluses                   4 asks
  split in two, neither part toll-free    Lure -> Menton                     6 asks
```

Two scenarios have **no example** and the change says so rather than inventing one. A journey that splits into three, and a first ask that beats the fit share *and* matches booths, both became rare under the better search: the first ask is the one made with the fewest waypoints, so it is the one traffic moves most.

## Capabilities

### New Capabilities

- `drive-flow-integration-tests`: what the recorded suite covers, what it is allowed to reach, how a Google answer is recorded and replayed, and what a test asserts.

### Modified Capabilities

- `telegram-drive-flow`: the requirement that separates the decision from the chat. It says the decision must be testable and says nothing about the shell. The shell becomes constructible for a test too, and stops holding its state in module globals.
- `route-service`: the requirement listing the Compose services. A fifth is added for the integration run.

## Impact

- `french_tolls/bot.py` — an application factory, and state moved out of module globals.
- A new suite and its recordings. The recordings are about **1.8 MB** for eleven journeys; a Google route arrives as an encoded polyline of some 60 KB.
- **Depends on `buy-googles-best-search`.** Every recording was made at `TRAFFIC_AWARE_OPTIMAL`, and under the current setting four of these seven journeys resolve differently — Cogolin → Saint-Gaudens splits into three parts and eight asks instead of being accepted outright. The recordings are only valid once that change lands.
- No paid request is made by the suite. Refreshing the recordings costs about 24.
