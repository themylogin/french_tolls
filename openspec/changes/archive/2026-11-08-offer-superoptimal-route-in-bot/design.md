# Design

## Context

See `proposal.md` for the motivation and the specs for the behavior. The current state that shapes the approach:

- `route.get_route` returns `super_optimal` when a split wins. `_super_optimal` builds it:
  - `google_url` comes from `_split_google_url`. It keeps every waypoint of the optimal route that lies on the split route, and every stop, or it is None.
  - `waypoints` is a copy of the optimal route's plan. Nothing reads it.
  - `stops` has `name` and `latlon` only.
- `route.link_through` (refuel) already selects waypoints around fixed vias. It keeps the vias and drops the optional waypoint that is nearest along the route to another waypoint, until all fit.
- `bot.part_of` builds a `drive.Part` from `answer["optimal"]` only.
- `bot.perform(AskGoogle)` runs `get_route` again for every ask. It needs only the optimal nodes, as the corridor. `bot.perform(AskRoute)` runs `get_route` for a half and reads its optimal route.
- `drive.accepts` accepts on tolls when Google's booths are a subset of the part's booths. It accepts on the road when the share fits.
- `ChatState.pending` maps a token to a list of parts. The drive button handler matches `^d\d+$`. The car dialog matches `^car:`.
- Integration harness:
  - `Telegram.messages` ignores `editMessageReplyMarkup`;
  - `Chat.press_offered` presses the last button of the messages sent since the last press;
  - `test_every_token_pressed_came_from_the_bot` collects offered buttons from `messages`.
- The archived change `plan-several-fuel-stops` recorded 4 tests in `test_drive_flow.py` that failed before it. That is the baseline.
- The integration suite routes with the real routers and `data/`. This planning did not run it: the Python packages are not installed outside Docker. So it is not known which pinned journeys carry `super_optimal` today.

## Goals / Non-Goals

**Goals:**

- The drive rules stay in `drive.py`, and a superoptimal part is a value like an optimal part.
- A press on a choice makes no Google request and no route request.
- A journey that chooses "Optimal" makes the same Google requests as before. Its cassette stays valid.

**Non-Goals:**

- No change to `google_url` of `super_optimal`, or to the page.
- No change to how the split is found or priced.

## Decisions

### The choice is one token, and the chat state keeps both parts

`handle_route` builds two parts and stores them, with the answer's text, under one token in a new `ChatState.choices`. The buttons carry `r<n>:optimal` and `r<n>:super_optimal`. A new handler matches `^r\d+:`. A press pops the token, so both buttons are spent at once. An unknown token gets the expired message of the drive handler.

Alternative: two tokens in `pending`, one per button. Rejected: a press on one leaves the other alive, and the driver could then drive both routes from one answer.

### The press edits the same message

The handler calls `edit_message_text`. The text is the answer as sent, an empty line, and "Optimal route chosen" or "Superoptimal route chosen". The markup is one "Drive with Google" button, or none where `settle` answers the part. The button's token is `state.remember([part])`, so the existing drive handler answers it with no change.

The choice state keeps the HTML text the bot sent, in a `Choice(text, parts)` value. The message a press arrives on carries the text and its entities, not the HTML. Sending that text back would drop the bold titles and the links.

Alternative: send a new message with the button. Rejected: the request is that the keyboard changes. A new message also repeats nothing useful.

### One function settles a route without a request

Add `drive.settle(part, maps_link)`. It returns the `Message` of rule 1 or rule 2, or None. `handle_route` uses it for a journey without a choice. The choice handler uses it for the chosen part. When it returns a message, the choice handler removes the buttons and sends the link with the label "Drive this route", as `send_outcome` does for a whole journey.

`_part` uses the same function for rules 1 and 2, so the rules have one definition. `settle` takes the text prefix that `_part` adds to a later part of a split journey.

### A part keeps its stops as values

```
Stop(location, booths, index)
    location   (lon, lat) of the exit booth: the via the route was built with
    booths     frozenset of the exit and entrance booth ids
    index      position in Part.nodes where the route reaches the exit booth

Part.stops     tuple of Stop, () for an optimal part
AskRoute.stops the stops of that half, () for an optimal half
AskGoogle.nodes the corridor: the nodes of the part being driven
```

- `accepts`:
  - a part without stops: as today;
  - a part with stops: `TOLLS` only when Google's booths are a subset of the part's booths and contain the booths of every stop. Never `ROAD`.
- `_part` splits at the index of the midpoint. A stop at or before that index goes to the near half. The other stops go to the far half.
- `perform(AskGoogle)` uses `request.nodes` and no longer calls `get_route`. For an optimal part these are the nodes that the call returned before, so the request body, the share, and the added waypoints do not change.

Alternative for the corridor: `AskGoogle` carries the route name, and `perform` routes again. Rejected: it repeats the waypoint search and the split search for every ask. For a half of a superoptimal part, there is also no name to route again.

### `drive_waypoints` is a new key, from the selection that `link_through` uses

Extract the selection loop of `link_through` into `_fit_waypoints(route, optimal, plan, fixed)`. It returns the `(index, location)` pairs in route order, or None when `fixed` alone is more than `MAX_WAYPOINTS`. `link_through` keeps its behavior.

`_super_optimal` calls it with each stop as fixed and writes `drive_waypoints`. Each stop entry gets `booths` and `index`.

Alternative: change `waypoints` or `google_url`. Rejected: `route-service` adds new information as new keys and keeps the meaning of existing keys. Also, a trimmed `google_url` would change the page.

### A half with stops is routed through them

Add `route.stretch_through(from_, to, stops)`:

1. Snap both ends. Route `fast` and `optimal`, and plan the waypoints of `optimal`.
2. Route on `osrm-optimal` through the exit booth of each stop, as `_split_journey` does.
3. When the route does not cross the booths of each stop, return None.
4. Return `{"fast": ..., "super_optimal": ...}` in the shape of `get_route`, with `drive_waypoints` and `stops`.

`perform(AskRoute)` calls it when the request has stops, and `get_route` when it has none. `bot.part_of` takes the key to read: `"optimal"` or `"super_optimal"`.

Alternative: call `get_route` for each half and read its `super_optimal`. Rejected: the midpoint cuts a closed section. The half then buys other tickets, and the split search can move or drop the stop.

Alternative: never split a superoptimal part. Rejected: split routes are long, and long routes are the ones that Google leaves. The driver would get a link that drifts.

### The bot treats a route it cannot drive as absent

The bot lists `super_optimal` only when `drive_waypoints` is not null. A route whose stops alone do not fit in one link has no link that keeps them.

### The harness sees offers in every call

- `Chat.press_offered` reads the `sent` calls since the last press, not `messages`. A call with buttons is an offer: `sendMessage`, `editMessageText`, or `editMessageReplyMarkup`. A spent button is removed by an edit without buttons, so it is not an offer.
- When the latest offer has a button with the label of the journey's choice, the harness presses that button. Otherwise it presses the last button, as today.
- `Journey` gets `choice`, default None. None means that the answer offers no choice. A pinned journey that offers one sets `"Optimal"` or `"Superoptimal"`, so the field also pins whether the choice is offered. `driven()` and `record.record` pass it to `Chat.drive`.
- `test_every_token_pressed_came_from_the_bot` collects offered buttons from every `sent` call.

### The new pinned journey

Key `superoptimal`, chosen `"Superoptimal"`. Start from the example in the design of `advise-splitting-a-ticket`: Le Boulou to Nîmes on the A9, with one stop at AGDE-PEZENAS (2.40 EUR for 2.5 min). Keep it only when the answer carries `super_optimal` and Google's first route makes the stop. Otherwise try another A9 or A28 journey.

Its cassette costs paid requests. The operator records it alone:

```
docker compose --profile record run --rm recorder python3 -m french_tolls.integration.record superoptimal
```

## Risks / Trade-offs

- [A pinned journey gains a superoptimal route] → It chooses "Optimal" by default, so its Google requests and its cassette do not change. Only its press count grows by one.
- [A zero-request journey gains a choice] → It no longer pins the outright answer. Replace it with a journey that offers no choice. Its recording costs nothing, because it makes no request.
- [Google puts the stop waypoint on the motorway, not on the exit plaza] → The stop booths are not crossed, so the route is refused and corrected or split. The pinned journey measures this case.
- [More requests where Google's booths are unknown] → A part with stops cannot be accepted on the road, so it goes on to the correction and the split. Matching failed for about 5% of stored Google routes (2314 of 2450 matched whole).
- [The midpoint falls inside a stop detour] → The stop goes to the near half, whose route then misses the entrance booth. The part is not split and is sent as the best link. This is rare: a detour is a few hundred metres of a long route.
- [Two waypoint sets for one route] → `google_url` and `drive_waypoints` differ only when everything does not fit. The `route-service` delta states why.
- [A driver presses once more when the optimal route needs no request] → This is the requested flow. The link comes on the choice press, so there is no third press.

## Migration Plan

1. Land the change with the unit tests and the harness changes. Run the integration suite with the existing cassettes.
2. With the agreement of the operator, record the `superoptimal` cassette.
3. Restart the bot. No data or schema changes.

Rollback: revert the change and restart the bot. The page and the API for the page do not change, so a rollback does not touch them.
