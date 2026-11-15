# Design

## Context

See proposal.md for the motivation. The gasolinera changes `list-cheaper-stations-earlier` and `list-destination-stations-on-no-stop` are the model. This design ports them to the planner and the dialog of french_tolls.

`refuel.plan` serves two callers: `POST /api/refuel` and `bot.plan_stops`. It runs `through_chosen`, walks the route, and returns early when no stop is needed. Otherwise it takes 30 `candidates` near the search point, routes one detour per candidate through `detours`, and prices each one with the fuel, the toll change, and the time. A detour goes through the split stops and the chosen stations. `detour_vias` places the station after the vias before the search point.

`through_chosen` rebuilds the route through the chosen stations. It places each chosen station at the search point of the route so far. A chosen station is `(latitude, longitude)`. When the fuel lasts before a chosen station, it raises `UnneededStation`, and the API answers 400.

The `Drive with Google` handler pops its `pending` token and removes every button of its message. It also pops the `RefuelOffer` that has its token, so `Plan refuel` and `Drive with Google` spend each other.

The bot keeps each open stop list as a `StationList` in `ChatState.station_lists`, by the token of its number buttons, `s<n>:<number>`. A press pops the list and plans again. Integration tests replace `bot.plan_stops` with a fake that returns answer dicts.

A station price is the lowest of `station.prices` for the fuels of `car.station_fuels(fuel_type)`. `candidates` holds the only copy of this rule today.

## Goals / Non-Goals

**Goals:**

- Keep one code path for the detours and the prices of the stop list, the destination list, and the cheaper list.
- Keep the answer of `POST /api/refuel` and its router load as they are.
- Route nothing through a cheaper station before a press. Route no planned route again on a press.
- Keep one rule for the price of a station.

**Non-Goals:**

- No change to the web page, and no change to the chosen stations that the API accepts.
- No cost shown for a cheaper station. Its cost only orders the list.

## Decisions

### The bot asks `plan` for the extra lists with one keyword

`plan` gets a keyword `for_bot=False`. `bot.plan_stops` passes `for_bot=True`. With it, two things change:

1. A no-stop answer without chosen stations lists the stations at the destination. The answer gets `liters` and `stations`. `fuel_left` or `range_left` stays.
2. A stop answer or a no-stop answer with stations gets `cheaper_share`, an int, and `cheaper_query`, a `CheaperQuery`.

`api.py` passes no keyword, so its answer stays JSON and makes no new request.

Alternatives:

- Always list the destination stations and count the share. The page shows neither, and every no-stop request of the page would route 30 detours. Rejected.
- A second plan function for the bot. It would copy the walk, `through_chosen`, and the pricing loop. Rejected.

### The destination is the last route point

The walks return `len(route.segment_distance)` as the index of the destination. On a no-stop walk with `for_bot`, `plan` uses that index as the search point. The liters follow the rule that already exists: `tank_volume - left` after a fuel walk, and `max(0, tank_volume - reserve_fuel(...))` after a range walk. At the destination, the reserve fuel is `reserve_km` at `consume_130`.

Each destination entry gets `route_index`, the index of the destination. A choice of it then places the station as its detour did.

A finished plan with chosen stations does not change. It already ends with `Drive with Google` and no `No need to refuel` text.

### One pricing helper places each station at its own index

`detours(routers, planned, vias, placed)` takes `(candidate, index)` pairs. `index` places the station among the vias, through `detour_vias`. The pricing loop of `plan` moves into a helper over the same pairs. It computes `station_leg` and `after_chosen` from the index of each pair, not from one search index. It returns the priced entries in input order, without the unreachable ones.

The stop list and the destination list pass the search index for every candidate. The cheaper list passes the route point of each station. `plan` sorts by `(cost, station id)` and keeps 10, as today.

### `CheaperQuery` keeps what a press needs

`CheaperQuery` is a frozen dataclass with these fields:

- `planned`: the `PlannedRoute`, for the router URL and the snapped ends.
- `route` and `vias`: the route through the chosen stations, and its vias.
- `walk_start`: the index where the walk starts, the origin or the last chosen station.
- `search_index`, `liters`, and `reference`: the search point, the liters, and the lowest price of the list. For a destination list, the search point is the destination.

`refuel.cheaper_stations(routers, query, parameters, toll_cost)` runs on a press. It finds the route stations, keeps the cheaper ones, and prices them with the helper. It returns entries in the form of `stations`. Each entry also has `route_index`, the index of its route point.

Alternative: run `planned_route` and `through_chosen` again on a press. For `super_optimal`, `planned_route` runs the split search again. A new route can also disagree with the share on the button. Rejected.

### Route stations from one box and a grid of route points

This is the method of gasolinera:

1. Take the route points up to `search_index`, from the origin or from the point after the last chosen station. `detour_vias` places a station after the vias with a lower index only, so a station at the point of the chosen station would go before it.
2. Read `stations_in_area` once, for the box of these points plus 5 km on each side. The half width uses the cosine of the largest latitude.
3. Put the points in a grid of 0.1° × 0.1° cells.
4. For each station with a price for the fuel, measure the great-circle distance to the points in its cell and the 8 cells around it. The nearest point within 5 km is its route point.

At 51.1° N, the north end of France, a 0.1° cell is 6.98 km wide. So the 3 × 3 cells hold every point within 5 km of a station.

The selection keeps the stations with `price < reference`. It sorts them by `(-route index, price, station id)` and keeps 10. Route distance grows with the index, so the index orders the stations along the route. After the detours, the helper's entries sort by `(cost, station id)`.

Alternative: compare each station with every point. A long route has tens of thousands of points, and its box holds thousands of stations. That is too slow in Python. Rejected.

### One rule for the price of a station

A new `gas_stations.fuel_price(prices, fuel_type)` gives `(price, fuel)` for the lowest price among the station fuels of the car, or None. `candidates`, the route stations, and the share use it.

### The share comes from one store query

`gas_stations.count_below(fuel_type, price)` reads only the `prices` column of every station. It applies `fuel_price` to each, and gives two counts: the stations below the price, and all stations with a price. The share is `(100 * below + total - 1) // total`. Integer arithmetic rounds up with no float error. `total` is at least 1, because the listed stations come from the store.

Alternative: SQL with `json_each`. It would hold a second copy of the price rule. Rejected.

### A chosen destination or cheaper station carries its route index

A chosen station is `(latitude, longitude)` or `(latitude, longitude, route_index)`. `through_chosen` places a three-part entry at `route_index`, with no walk. So it never raises `UnneededStation` for it, and a destination station is accepted when the fuel lasts. A two-part entry keeps the walk, the search point, and `UnneededStation`. The route at that step is the route that the list saw, so the index is valid.

The bot builds the three-part entry from `route_index` of a destination entry or a cheaper entry. The API and the stop list keep two parts, so the API still answers 400 for a station that the plan does not need, and their tests do not change.

Alternatives:

- Place every chosen station at its nearest route point. That changes the placement of stop list stations, which the spec ties to the search point. Rejected.
- Let `for_bot` turn off `UnneededStation` for every station. A stop list station would then need a search point that the walk does not give. Rejected.

### The cheaper list shares the token of its list

`StationList` gets `cheaper: tuple = ()`. The cheaper list buttons carry `s<n>:c<number>`, with the token of its stop list or destination list. The cheaper button carries `s<n>:cheaper`. A number press on either list pops the one `StationList`, so it closes both lists.

Alternative: a second token, and a link between the two lists. Two entries can drift apart. Rejected.

When the list closes during the cheaper search, the bot sends the cheaper list without buttons.

### The destination list is a `StationList` with a drive token

The no-stop answer with stations goes through the same path as a stop list. Its `StationList` also gets `drive_token`, the `pending` token of its `Drive with Google`. Its keyboard is the number rows, the cheaper row when the share is above 0, and `Drive with Google`.

- A number press on the destination list or its cheaper list pops `state.pending[drive_token]`. That spends `Drive with Google`.
- `drive_button_handler` pops the `StationList` that has its token, and the cheaper offer of that list. This follows how it already pops the `RefuelOffer` with its token.

Alternative: a separate dataclass for the destination list. The number handler, the cheaper handler, and the closing rules would need a second copy. Rejected.

### The bot keeps one cheaper query for each driver

`ChatState.cheaper_offers` maps a user id to a `CheaperOffer`: the token of the list, and the `CheaperQuery`. `plan_and_answer` gets the user id as a parameter, because after a station press its `message` is a bot message. Each stop list or destination list of the driver replaces the offer. The bot stores no offer when the share is 0. A number press on that list, or its `Drive with Google`, drops the offer.

The cheaper handler expires the press when the offer is missing, has another token, or its list is closed. Else it pops the offer and edits the list keyboard to its rows without the cheaper row. It then shows `⏳ Finding gas stations...` and calls `bot.cheaper_stops(query, parameters)`. That function wraps `refuel.cheaper_stations` with `Routers()` and `toll_cost`. Integration tests replace it, as they replace `plan_stops`.

### Texts

`refuel_chat.no_stop_text(answer)` adds the destination header and the list, the singular header, or the empty-list line after the sentence. The cheaper label and `None of them is within 5 km of your route.` each have one use, so they stay inline in `bot.py`.

## Risks / Trade-offs

- [A no-stop answer takes longer: up to 30 detours, four at a time] → The stop list makes the same requests today.
- [A router failure now fails a no-stop answer that worked before] → The driver gets the error text and can plan again.
- [Each driver keeps one `CheaperQuery`, with up to three routes of tens of thousands of points] → One per driver, replaced by the next list and dropped on a choice or on `Drive with Google`. If memory grows, keep only the router URL and the snapped ends in place of `planned`.
- [The bot and the API now differ on a station that the plan does not need] → Only the bot sends a route index, and only for stations that its own lists placed. The API keeps its 400.
- [The router can answer differently between the list and the choice, after an OSRM rebuild] → The index then places the station at another point. The plan still routes through the station.
- [The cost of a cheaper station uses the liters of the stop list, and an earlier stop buys less] → The cost only orders the list. The message shows the price, the detour, and the toll change.
- [The reference price comes from a list ranked by cost] → A station with a low price and a long detour sets a low reference. This matches gasolinera.
- [Each stop list reads the prices of every stored station] → The rows are small JSON lists, and the count needs no geometry. If it becomes slow, cache the counts by the latest update of the store.

## Migration Plan

No data change. Deploy with `make bot`. Old buttons from before the restart already expire, because the bot keeps its state in memory. Rollback is a revert and a restart.
