## Why

The bot hands a driver three Google links and no way to tell which one works. Measured across the corpus, a link through our waypoints follows our road 97.4% of the time on average — but the tail is bad, and nothing in the message says which case the driver is in.

Two facts from that measurement change what the bot should send:

- **19.7% of journeys have a toll-free optimal route.** For those, waypoints are the wrong instrument entirely; "enable Avoid tolls" reproduces the intent in one setting, and the Maps URL parameter that used to do it has not worked for years.
- **Nine waypoints is a limit of the URL, not of the algorithm.** Journeys that fit at 59% whole reach 96% and 99% when split in two, and five of twenty measured halves reached exactly 100%. Splitting is the only way past the ceiling.

## What Changes

### The bot sends one link and one button

- **BREAKING** The three direct Google links go from the message. It becomes the two route summaries, the comparison map link, and — where the optimal route pays no tolls — a bold **Please, enable Avoid tolls before driving.**
- Below it, one button: **Drive with Google**.
- The message SHALL cost no Google request. It is sent for every journey, and most are never driven.

### The button decides what the driver can actually follow

Pressed, and in this order:

- **No tolls on the optimal route** — send a link from the driver's current location. No Google request: there is nothing a waypoint could say that "avoid tolls" does not say better.
- **Budget remains** — ask Google through our waypoints. If the route it returns follows ours to **98%**, send that link. If not, spend the remaining waypoint budget on the drift and ask once more. If it still falls short, **split the route in half** and answer each half separately.
- **Budget spent** — send the unrefined link and say it was not checked against Google this month.

A half is answered the same way, and may split once more, so a journey resolves into at most **four** parts. Each part is sent as it is settled, with a button for the next; the driver is never handed four links at once.

A part that pays no tolls says so in bold instead of carrying waypoints. Every link starts from the driver's **current location** — the route's own origin is never the start, because a driver pressing the button is somewhere already.

- **Consequence:** one press costs at most 14 Google requests in the worst case (2 for the whole, 4 for two halves, 8 for four quarters). The common case is one or two.

### The requests stop using traffic

- **BREAKING** `routingPreference` returns to `TRAFFIC_UNAWARE`, and `trafficModel` and `departureTime` go.
- This reverses a decision made earlier today, on later evidence. That decision was measured when waypoints were poor, where the setting was worth **+12.7 points**. Measured again with the waypoints the search now produces, it is worth **0.8 points** — the waypoints have absorbed it.
- What it buys back: the request bills as Routes **Essentials** rather than Pro, doubling the free allowance from 5 000 requests a month to 10 000. The drive flow can spend up to 14 on one press, so the allowance matters more than it did.

### The overlay becomes a debug tool again

- **BREAKING** The orange route is drawn automatically when `DEBUG=1`, and not at all otherwise. The per-link control goes.
- Each debug page load therefore costs **two** Google requests, deliberately: seeing how well the link fits is the point of the setting.
- The orange line SHALL be **twice the width of the green** and drawn beneath it, so agreement reads as green centred on orange and divergence as orange running out alone. It carries the waypoints sent — orange for the ones the search chose, purple for the ones refinement added.

### The three link forms are removed

- **BREAKING** `url`, `url_from_current_location` and `url_from_current_location_through_start` go from the answer, and `/go/{form}` goes with them.
- Nothing uses them once the bot stops. They existed so a link sent before a refinement was bought would still arrive at the refined route; the button makes that unnecessary by refining when the driver asks.

## Capabilities

### New Capabilities

- `telegram-drive-flow`: what the bot sends, what the button does, and how the decision is separated from Telegram so it can be tested without mocking a chat.

### Modified Capabilities

- `route-service`: the three link keys leave the answer, and the bot's behaviour is no longer unchanged.
- `google-route-refinement`: the redirect endpoint goes, the request stops using traffic, and refinement gains a fit threshold and a caller that splits.
- `web-front-end`: the overlay is gated on `DEBUG`, drawn on load rather than on a click, and drawn wider than the route beneath it.

## Impact

- Modified: `french_tolls/bot.py` (rewritten around a pure decision function), `french_tolls/service.py` (the three link keys), `french_tolls/api.py` (`/go/{form}` removed), `french_tolls/refine.py` (request terms, fit threshold, splitting), `www/index.js` (debug gate, widths), `.env.example`, `docker-compose.yml`.
- Unchanged: the pipeline, the waypoint search, toll accounting, `google-route-comparison`.
- **A journey can now cost 14 Google requests instead of 2.** The monthly ceiling becomes a real constraint rather than a formality, which is part of why the requests move back to the cheaper tier.
- **`DEBUG=1` spends money on every page load.** It is already set in `.env`.
- Not addressed: whether the driver should be offered the split proactively rather than after two failed attempts, and whether a toll-free *part* of a tolled journey should be detected before the first request rather than after the split.
