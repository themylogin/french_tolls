## Why

The waypoint search is measured and found wanting. Over ten long journeys it makes Google drive the intended road for a median 87.7% of the distance, and on the worst — Bayeux to Apt — for 74.4%: Google covered in 1 009 km what our route does in 959 km, spending 134 km on a single detour our route skips in 86.

The search cannot do better on its own, because it is arguing about a road network it cannot see. It verifies each leg against OSRM's graph, which is the honest contract it was built to, and OSRM's graph is not Google's. No amount of care on our side reveals that Google prefers a different road between two of our waypoints.

But Google will say so, if asked. A route request through our waypoints comes back with the road Google actually chose, and the stretches where it left ours are exactly the places a further waypoint would help. Measured on Bayeux to Apt: seventeen such stretches, and placing one waypoint in the middle of each of the two longest is a concrete, computable improvement to a link that today sends a driver 50 km out of their way.

Asking costs money, so it is asked at most twice per journey — once to find the detours, and once more only if someone wants to see the corrected route — and never more than a stated number of times a month.

## What Changes

### The links become ours

- **BREAKING** `url`, `url_from_current_location`, and `url_from_current_location_through_start` stop being `google.com` addresses and become addresses of this service. Following one computes the journey, refines the waypoints if there is budget for it, and redirects to Google with the improved set. The Telegram bot needs no edit — it reads the same three keys — and the page's three links change with them.
- The cost of that: a link that used to reach Google directly now depends on this service being up. The raw Google link is returned alongside, under its own key, so a consumer that would rather not depend on us has one.

### Waypoints get a second pass

- A new endpoint takes an origin and a destination, computes the optimal route and its waypoints as today, and — where both budgets allow — asks Google to drive it, finds the stretches where Google left a corridor around our route, and inserts a waypoint at the middle of the worst of them, on **our** route rather than on Google's.
- The number inserted is whatever the nine-waypoint ceiling of a Maps URL leaves free. Bayeux to Apt has seven, so it gets two.
- At most two Google requests per journey, ever, and one if nobody looks at it. The first finds where Google went its own way and produces the refined waypoints, which is all a link needs. The second is bought only when someone asks to see the result, because the route through the refined waypoints does not exist until it is asked for — the first request's whole purpose is to find where that route will differ. Both are stored, so the bot's link, the page's button, and a second visitor never re-buy a phase.

### Everything is cached in one database

- **BREAKING** `/cache/autocomplete.sqlite` becomes `/cache/database.db`, and stops being only the autocomplete cache. It gains a table counting Google requests per month keyed on `YYYY-MM`, a table of route answers, and a table of refinements.
- **BREAKING** Route answers move out of the per-fingerprint JSON files into that database. One store, one place to look, one thing to back up — and the counter has to be transactional against the same store that records what the money bought, or the count and the corpus can disagree.

### The page shows what Google did, on request

- The turn-right icon beside each of the three links becomes a button. Clicking it asks for the refinement and draws Google's own route on the map in orange, over the optimal route and under the fast one.
- **BREAKING** `GOOGLE_DIRECTIONS_DEBUG` is removed. The overlay is now something a visitor asks for by clicking, not something an operator switches on, and it draws the live answer rather than whatever the evaluation happened to have bought.

## Capabilities

### New Capabilities

- `google-route-refinement`: the endpoint and the redirect, the two budgets and what happens when either is exhausted, how a drift stretch becomes a waypoint, and what is stored.

### Modified Capabilities

- `route-service`: the answer's three link keys change what they point at; the cache moves from files to SQLite; the service now makes a paid outbound request, which its configuration requirement does not currently admit.
- `web-front-end`: the page gains a control that spends money on a click, and the keys it reads change meaning.
- `google-route-comparison`: it states that the evaluation is the only service permitted to make a paid outbound request and the only one needing the Google key. Both are about to be false.

## Impact

- New: the refinement module, the Google client for the application, the database module, two endpoints.
- Modified: `french_tolls/service.py` (links, cache), `french_tolls/api.py` (two routes — the first change to it in this project's history), `french_tolls/autocomplete.py` (the renamed database), `www/index.js` (the button), `docker-compose.yml`, `.env.example`, `Makefile` if a migration needs invoking.
- Removed: `french_tolls/google_debug.py` and `GOOGLE_DIRECTIONS_DEBUG`.
- Unchanged: `french_tolls/bot.py`, the waypoint search itself, the toll accounting, the pipeline, the unit suite.
- Data: existing cached answers under `/cache/<fingerprint>/` are not migrated. They are recomputable in under a second each, and carrying a file format forward into the store meant to replace it is worth less than deleting them.
- Money: bounded by `GOOGLE_DIRECTIONS_MAX_REQUEST_PER_MONTH`, already set in `.env`. Beyond it the service keeps working and stops refining.
- The evaluation's corpus of 20 bought journeys measures the algorithm **before** this change. That is what makes it a baseline rather than something invalidated by it.
