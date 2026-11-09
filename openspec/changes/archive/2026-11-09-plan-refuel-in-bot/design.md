# Design

## Context

See `proposal.md` for the motivation, and the specs for the texts, the limits, and the scenarios.

- `bot.handle_route` offers `Drive with Google` (`state.remember([part])`, callback `d<n>`) only when `drive.settle` returns None and no choice is offered. `choice_button_handler` does the same after a choice. A settled answer carries its link and has no markup.
- `drive_button_handler` resolves a list of `drive.Part`. A `Part` with `stops` is a superoptimal part. `perform(AskRoute)` routes a half with stops through `route.stretch_through`, and `part_of(answer, name="super_optimal")` reads `stops` and `drive_waypoints` from its answer.
- `drive.settle` builds rule 1 and rule 2 links with no waypoints. `drive.accepts` refuses the road test for any part with stops.
- `route.stretch_through` routes through `(location, booths)` stops on the optimal graph. It finds each stop index by its booths, and takes its `fast` route without the stops.
- `refuel.plan(routers, planned, parameters, fuel, toll_cost, chosen, link_through)` gives the answer of `POST /api/refuel`. `_through_chosen` gives the route through the chosen stations and its `Via` list in route order. A `Via` of a split stop has no booths. `route.SplitStop` has no booths either.
- `refuel.fuel_walk` walks in liters against `parameters.reserve`.
- `car.CarParameters` has `reserve` and an optional `gauge_steps`. `save_car` writes `dataclasses.asdict`, so each field is a column. The head revision is `68910fca5c86`.
- Gasolinera holds the gauge keyboards in `gasolinera/journey.py` (`GAUGES`, `gauge_mark`, `parse_range`) and its `range_walk` in `gasolinera/refuel.py`.
- The integration suite has no gas stations and no fake routers for the bot. `test_refuel_endpoint` replaces `api.planned_route` and `refuel.plan` with `monkeypatch`.

## Goals / Non-Goals

**Goals:**

- One planner for the page and the bot, in liters or in km.
- One drive decision for a route with split stops, gas stations, or both.
- The dialog rules of the bot are testable without Telegram, as `car.py` and `drive.py` are.

**Non-Goals:**

- No opening hours alert. This project stores no opening hours.
- No `Plan refuel` on the parts of a split journey.
- No summary of the planned route (time, cost, km) in the bot.
- No conversion between km and liters.
- No change to `/help` or to the command menu.

## Decisions

### The walk takes either liters or km

`plan` takes `fuel=None` or `range_km=None` as keywords, as `search` does in gasolinera. Exactly one is set. `range_walk(route, range_km, reserve_km, start=0)` subtracts each segment distance in km, and stops at `reserve_km` or less. It is the gasolinera walk with a `start`.

- `_through_chosen` walks by the range before the first chosen station, and by the fuel from each chosen station with `tank_volume` liters. A range that lasts before the first chosen station raises `UnneededStation`.
- The liters of a stop after a range walk are `tank_volume - reserve`.
- With no chosen station, a range that lasts gives `{"stop_needed": false, "range_left": ...}`.

Alternative: convert the range to liters with a consumption. Gasolinera rejects this, because the range of the car already holds its own consumption estimate.

### The car gets `reserve_km`

`CarParameters` gets `reserve_km: float`, required, after `reserve`. `Car.reserve_km` is a float column, not null, with the `server_default` `"50"`. A new revision after `68910fca5c86` adds it in one `op.batch_alter_table`, and its downgrade drops it.

- `CarDialog` gets `reserve`. The `reserve` step keeps it and asks the new `reserve_km` step, which saves the car.
- `parse_reserve_km(text)` accepts a decimal from 0 to 500.
- `parse_car` reads `reserve_km` with the same limits, and refuses a bool, NaN, and a missing key.

The name `reserve_km` is the name gasolinera uses for the same value. `reserve` stays without a suffix, as the liters of the tank do.

### The API reads `fuel` or `range`

`api.refuel` refuses a body that has both keys or neither. `range` must be a finite number from 0 to 3000. It calls `plan` with `fuel=` or `range_km=`.

### The page adds two rows and one rule

- `www/index.html` gets `Range reserve` (`refuel-reserve-km`, unit `km`) after `Reserve`, and `Range now` (`refuel-range`, unit `km`) after `Fuel in the tank now`. Each row copies the markup of the fuel row.
- `readRefuelForm` reads both fields. With both empty or both filled, it marks both with the message of the spec. It checks the filled one against its limits. It adds `reserve_km` to `car`, and returns `fuel` or `range`.
- `storeCar` stores `reserve_km`. `openRefuelDialog` fills it with `50` when the storage has no number there, and empties `refuel-range`.
- `sendRefuel` sends the `fuel` key or the `range` key, never both.
- `showRefuelAnswer` reads `range_left`. The "no station" message names `reserve_km` when the request had a range and no station is chosen yet.

### A gas station is a `Stop` with no booths

The drive decision gets no new type. A chosen station becomes `Stop(location, booths=frozenset(), index)`. This needs three changes in `drive.py`:

- `settle` passes the locations of the stops without booths to `link_from_here`. So rules 1 and 2 keep the stations, and a superoptimal part keeps its current links.
- `accepts` applies the stop rule only when a stop has booths. A part with only stations uses the tests of an optimal part, the road test too.
- The `Stop` docstring states that empty booths mean a gas station. Code tells the two kinds apart only by the booths.

The split code already sends each stop to the half that drives it, by its index. It needs no change.

Alternative: a separate `stations` field on `Part` and `AskRoute`. It repeats the split, the routing, and the link code for a second list.

### `stretch_through` routes the stations too

`stretch_through` takes stations as `(location, ())` stops in route order, mixed with the split stops.

- The index of a station stop is the start of the route leg after it, as `_through_chosen` finds it. A booth stop keeps `_stop_entry`.
- The `fast` route goes through the stations only, on the fast graph, with `route_via`. Without stations it stays `routers.fast`. So rule 2 compares the fastest route through the same stations.
- The booth check passes for a station, because its booth set is empty.

The bot then builds the part of a finished plan with the code that builds a superoptimal half: `part_of(await stretch_through(from_, to, stops), from_, to, name="super_optimal")`. Its `drive_waypoints` are None when the stops do not fit in one link. The bot then sends the "too many stops" message.

### The bot gets the stop order from the planner

`_through_chosen` becomes the public `through_chosen`. `Via` gets `booths`, and `SplitStop` gets the exit booth and the entrance booth that `planned_route` already reads. At the end of a plan, the bot calls `through_chosen` and turns its vias into the stops of `stretch_through`.

This routes the chosen stations a second time. The routers are local, so the cost is small. The API answer keeps its keys.

Alternative: add the vias to the answer of `plan`. This changes the JSON of `POST /api/refuel` for a need of the bot only.

### The dialog rules live in a new module

`french_tolls/refuel_chat.py` holds what needs no Telegram and no router: the gauge keyboards, `gauge_mark`, `parse_range`, the station list in HTML, the rows of the number keyboard, and the texts. The keyboards and `gauge_mark` are copied from gasolinera, and the texts are English. `bot.py` holds the handlers and the state.

`bot.py` reaches the planner through one function, `plan_stops(offer, parameters, start, chosen)`. It returns the answer of `plan`, and the `Part` of a finished plan. The integration tests replace it with `monkeypatch`, as `test_refuel_endpoint` replaces `refuel.plan`.

### The state is explicit and per application

`ChatState` gets three maps:

- `refuel_offers`: by the token of `Plan refuel` (`p<n>`). An offer holds the origin, the destination, the route name, the `Part` that `Drive with Google` drives, and the token of that button or None. A press on either button pops both.
- `fuel_questions`: by user id, because a typed range must find the question. It holds the gauge token (`g<n>`), the offer, the car, and the chat and message ids of the question, so a typed range can edit it.
- `station_lists`: by the list token (`s<n>`). A list holds the offer, the car, the start (liters or km), the chosen stations, the listed stations, and the HTML of the list.

A station press, a gauge press, and a typed range pop their entry before they plan. So a second press finds nothing and gets the expired text. A shared location and `/reset` pop the fuel question of the user.

The handlers use the patterns `^p\d+$`, `^g\d+:\d+$`, and `^s\d+:\d+$`. They do not match the drive, choice, or car buttons.

### The answer asks for the route, then for the action

These decisions come from the first test in Telegram, on 2026-11-08.

- `handle_route` offers the route buttons that differ: `Super` where a drivable split route is listed, `Optimal`, and `Fastest` where the fast nodes are not the optimal nodes. With one route only, it offers the action buttons at once. The summary of the split route is titled `Superoptimal:`, and the choice still writes `Superoptimal route chosen`.
- The action buttons are always `Drive with Google` and `Plan refuel`, also for a settled route. So `handle_route` no longer calls `settle`, and the answer carries no directions link.
- `Choice.parts` gets a `fast` part: `part_of(answer, ..., name="fast")`. Its `booths` and `fast_booths` are the booths of the fast route, so rule 1 or rule 2 always settles it, and `Drive with Google` makes no request. Its waypoints are empty.
- `drive_button_handler` calls `settle` first. A settled part gets its link at once, without `⏳ Checking with Google...`.

Alternative: a link in the answer for a settled route, as before. The driver could then not plan a refuel before the link.

### The fastest route has its own plan

`planned_route` accepts `fast`, for the bot only. The API still refuses it, because the page offers no gas station icon on the fastest route.

- `PlannedRoute` gets `router_url`: the URL of the graph of its route. `detours` and `through_chosen` route on it, in place of the fixed `config.osrm_optimal_url`.
- A finished plan on the fastest route does not go through `stretch_through`, which routes on the toll-weighted graph. The bot builds its `Part` from the route of `through_chosen`. The stations are stops without booths, and `booths` and `fast_booths` are the booths of that route. So `settle` always sends one link through the stations, and makes no request.
- More than `MAX_WAYPOINTS` stations give the "too many stops" message, as on the other routes.

### Fewer messages in the refuel dialog

- A gauge press or a valid typed range deletes the fuel question. `fuel_text` and `range_text` go.
- A station press edits the list message into the paragraph of that station. `station_list` gives the paragraph for one station, with its number, so the bot keeps the paragraphs of each list in `StationList`.
- A finished plan deletes `⏳ Finding gas stations...` and adds `Drive with Google` to the message of the last chosen station. `plan_and_answer` gets that message from the station press. `ready_text` goes.

### Errors end the plan

`RouteError`, `NoRoute`, `RouterUnavailable`, `UnneededStation`, a None planned route, and a None `stretch_through` all give `Error finding gas stations. I am very sorry for that 😞`. The other errors of the bot do the same.

## Risks / Trade-offs

- [A page that the browser loaded before the deploy sends no `reserve_km`, and gets 400.] → The dialog shows its error message. A reload fixes it.
- [Google can snap a station waypoint on a motorway service area to the carriageway, and pass the station.] → The link carries the exact position of the station. The tolls test cannot see this, as for any waypoint.
- [Typed coordinates during the fuel question get the range error, as in gasolinera.] → A shared location or `/reset` closes the question.
- [The `/car` dialog gets a seventh question.] → Every driver must answer it once on the next change. Stored cars get 50 km, so nothing breaks.
- [The bot routes the chosen stations a second time at the end of a plan.] → The routers are local, and a plan has few stations.
- [A plan on a superoptimal route can lose a split stop when it adds a station.] → `stretch_through` returns None, and the bot sends the error text.

## Migration Plan

1. Deploy the application image and the `www` image together. `migrate` applies the revision before `web` and `bot` start. Each stored car gets a range reserve of 50 km.
2. To roll back, run the downgrade of the revision, and deploy the old images.
