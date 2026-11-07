# Design

## Context

See `proposal.md` for the motivation. The specs `refuel-planning` and `web-front-end` give the required behavior.

The current state that shapes the approach:

- `route.get_route` builds three routes. The optimal route costs three router requests: two snaps and one route. The waypoint search `plan_waypoints` costs up to several hundred requests. The split route needs the optimal route and one `route_via` request. `_super_optimal` takes the waypoint plan only to build `google_url` and the `_describe` dictionary.
- `osrm.Route` carries `segment_distance` and `segment_duration` for each node pair. These are the raw router values. `_for_delivery` applies `TIME_MULTIPLIER` to the totals only.
- `gas_stations.stations_in_area` returns the stations in a latitude and longitude box through the R*Tree index. Each row has `prices` as `[fuel, date, price text]` triples.
- `car.FUEL_TYPES` and `car.station_fuels` map a fuel type to the station fuel names.
- `tolls.account(BOOTHS, node_ids).cost` gives the toll cost of a node sequence.
- The page already loads the Bootstrap 5 bundle and Bootstrap Icons. The page has no JavaScript tests.
- nginx proxies every path under `/api`, so `/api/refuel` needs no proxy change.

## Goals / Non-Goals

**Goals:**

- One click costs a bounded number of router requests: 4 to rebuild the route and at most 30 for the detours.
- The planned route is the same route that the page shows.
- The server makes every calculation. The page only collects the values and shows the answer.

**Non-Goals:**

- No change to the answer of `/api/calculate`.
- No shared car values between the page and the bot.
- No JavaScript test setup.

## Decisions

### The server rebuilds the route from the journey and the route name

The page sends `from`, `to`, and `route`. The server routes the journey again. The alternative is that the page sends the route geometry back. The page does not have the segment durations, and the server must not trust a geometry from the client for its toll accounting. Two snaps and one route are cheap. Only the waypoint search is expensive, and the refuel plan does not need it.

`route.py` gets one new public function that returns the planned route without the waypoint search. It takes the routers, the origin, the destination, and the route name. It returns the snapped start, the snapped end, the route, and the split stops in route order. The stops are an empty list for `optimal`. It raises `RouteError` with the same causes and the same failure record as `get_route`.

To share the split logic, `_super_optimal` splits into two parts:

- a part that needs no plan. It runs `_plan_split`, routes through the stops, and checks the missed stops and the saving. It returns the route and the stops, or `None`;
- a part that describes the result. It uses the plan for `_describe` and `_split_google_url`, as it does now.

`get_route` keeps its signature and its answer. The existing tests and cassettes cover it.

When `route` is `super_optimal` and the first part returns `None`, the endpoint answers 404. The page shows the icon only on a split route that it received, so a 404 happens only when the data changed between the two requests.

### `refuel.py` does not import `route.py`

`route.py` reads the booth data files from `/data` at import. `route-service` keeps `data/` out of the unit test runner. So a module that imports `route.py` cannot be tested in the unit suite.

`refuel.plan` takes the routers, the planned route, the car, the fuel, and a toll cost function. `api.py` joins the two modules. It calls `route.planned_route`, and then it calls `refuel.plan` with `route.toll_cost`. `refuel.plan` lets `RouterUnavailable` go out unchanged, and `api.py` turns it into 502.

The tests of `refuel.py` are in the unit suite. The tests of `route.planned_route` and of the endpoint are in `integration/test_refuel_endpoint.py`, because the integration suite has `data/` mounted. These tests use fake routers and send no router request.

The alternative is a `route.py` that reads the data at first use. Today a bad data file stops the service at start, and a change to that rule is outside this change.

### The fuel walk uses the node segments

The walk starts with `fuel` at node 0. For each segment `i`, the speed is `segment_distance[i] / (segment_duration[i] * TIME_MULTIPLIER)` in m/s, converted to km/h. The fuel that the segment uses is `segment_distance[i] / 1000 * consumption(speed) / 100`. The search point is the first node where the fuel left is 5 L or less.

A segment with a duration of 0 has a distance of 0 in practice, so it uses no fuel. The walk gives it the consumption at 80 km/h to prevent a division by zero.

The first and the last segments are partial when an endpoint snaps into a segment. Their annotation values are what the router gives, so the walk uses them unchanged. The error is less than one segment.

The OSRM car profile sets a road with a tagged speed limit to 80% of that limit. The plan does not undo this. `TIME_MULTIPLIER` is the measured correction between the OSRM travel time and the real travel time, so the corrected speed is the speed to use.

At 80 km/h and above, the consumption function is `consume_80 + (consume_130 - consume_80) * (v² - 80²) / (130² - 80²)`. This is the curve `a + b·v²` through the two car values. Air drag grows with the square of the speed, and rolling resistance is almost constant per km. So this curve fits steady driving better than a straight line. For 6 and 8 L/100 km, a straight line gives 7.0 at 105 km/h, and the curve gives 6.88.

The curve continues above 130 km/h, where drag keeps growing. `consume_130` is never less than `consume_80`, so the curve never falls. At 80 km/h and above, the consumption is never less than `consume_80`.

Below 80 km/h, the curve falls under `consume_80`. Town driving with stops uses more fuel than that, so the walk keeps `consume_80` there. This also gives the refuel plan a safe margin.

### The candidates come from the R*Tree box and a distance filter

The box around the search point is 50 km in each direction: `50 / 111.2` degrees of latitude, and `50 / (111.2 * cos(latitude))` degrees of longitude. `stations_in_area` returns the stations in the box. The new module then keeps the stations with a price for a fuel of the car and a great-circle distance of 50 km or less. It sorts them by distance and keeps the first 30.

The alternative is a fixed count without a radius. In an empty area, the nearest 30 stations can be 100 km away, which is past the range of 5 L. The 50 km radius stops the search there, and the dialog then says that no station is near.

### Each detour is one `route_via` request on the toll-weighted graph

The detour is `route_via(config.osrm_optimal_url, start, vias, end)`. For `optimal`, `vias` is the station only. For `super_optimal`, `vias` are the stop positions with the station inserted at its place. The stop positions are the exit booth positions, as `_super_optimal` uses them. The place of the station is the number of stops whose exit booth node index on the route is less than the index of the search point.

The baseline for the detour time and the toll difference is the planned route itself. The cost uses the toll cost of the real detour nodes. When a station makes the detour miss a split stop, the toll difference shows the price of that.

The detour requests run at the same time, with at most 4 open at once. This is the limit of the gas station run. It keeps the load on a remote router low. Thirty requests at 4 at once take about eight request times.

`NoRoute` for one detour leaves out that station. `RouterUnavailable` for one detour fails the whole request with 502. A list without the failed stations can hide the cheapest one, and the driver cannot know that.

### The distance to a station comes from the legs of its detour

`osrm.Route` gets `leg_distance`, the router's distance of each leg. Both readers fill it: `_read_route` with one leg, and `_read_route_legs` with one entry per leg. The station is via number `k` of the detour, where `k` is the number of split stops before the search point. Its `distance` is the sum of the first `k + 1` legs.

The alternative is to find the node nearest to the station in the flat node list. A route into a station and back out on the same road passes that node twice, so the sum up to it can be wrong by the length of the access road.

### The answer rounds money to cents and liters to two decimals

`fuel_cost`, `toll_difference`, and `cost` are rounded to two decimals. `liters` and `fuel_left` are rounded to two decimals. `price` is the stored text as a float. `detour_duration` is in seconds after the multiplier, not rounded. The sort uses the unrounded cost, then the station id when two costs are equal.

### `car.py` validates the JSON values

A new function in `car.py` takes the `car` object of the request and returns `CarParameters` or `None`. It checks the types and the limits of `car-parameters`, and it refuses a `consume_130` below `consume_80`. A boolean is not a valid number, because JSON `true` becomes the Python integer 1. A consumption must be finite. The endpoint checks `fuel` against `tank_volume` and `route` against the two names. Any failure, a body that is not JSON included, gives 400 before the first router request.

The bot parsers take text. They stay unchanged.

### The bot checks the order of the two consumptions in the dialog

`car.answer_text` checks the new rule at the `consume_130` step, after `parse_consumption` accepts the text. A value below `dialog.consume_80` gets the error message of `car-parameters`, with the 80 km/h value in the format of `describe`. The dialog stays at the `consume_130` step and has no `save`. `bot.py` needs no change, because it sends the reply text and keeps the dialog of the reply.

### The page keeps the journey of the last answer

Typing in the `From` or `To` field sets the global `from` or `to` to `null`. The dialog must not read them. The page keeps the `lonlat` pairs of the journey when `/api/calculate` succeeds, and the dialog sends these pairs.

`showRoute` gets the route name as a parameter. The icon is `<i class="bi bi-fuel-pump">` inside a link with the class `refuel-link` and a `data-route` attribute. One click listener on `#routes` handles both icons, because `#routes` is filled with `innerHTML` on each answer.

### The dialog is static markup in `index.html`

The modal markup is in `index.html`. `index.js` opens it with `bootstrap.Modal.getOrCreateInstance`. The Bootstrap bundle is a classic script, so it runs before the module `index.js`. `Cancel` uses `data-bs-dismiss="modal"`.

Each field is a Bootstrap grid row, with the label on the left and the field on the right. The message of a field spans the row below them. The unit of a number field is a grey text on the right inside the field, and the field has a right padding that keeps a typed value clear of it. Bootstrap draws its invalid icon in the same place, so a marked field shows the red border without the icon. The label keeps the unit as hidden text for a screen reader. The fuel type is three inline radio buttons. `95` is selected when the storage has no valid fuel type, so the fuel type always has a value and needs no check.

The numeric fields are text fields with `inputmode="decimal"` or `inputmode="numeric"`. A `type="number"` field reads a decimal comma differently in each browser. The page checks the values with the same regular expressions as `car.parse_tank_volume` and `car.parse_consumption`, so `6,5` is valid. The page sends numbers in the JSON body.

The page keeps the four car values in `localStorage` under the key `car`, as one JSON object. A value that does not parse is treated as no value.

When the dialog closes, the page aborts an open request with an `AbortController`. A late answer then does not appear in the next dialog. When the dialog opens, it clears the old result.

The page escapes the station name with `encodeHTML`. The name comes from a scraped public page.

## Risks / Trade-offs

- [A station beside a motorway can snap onto the carriageway. The detour is then near zero, but the driver cannot reach the station there.] → Accept for this version, and check some motorway stations during the manual test. A later change can compare the snap distance of the station.
- [Old prices can rank a station first. A closed station keeps its last prices.] → Out of scope by the proposal. The `date` of each price stays in the store, so a later filter needs no schema change.
- [The detour of a split route can miss a split stop.] → The toll difference shows the real cost of the detour, so the ranking stays correct.
- [A detour can cross a toll that the data cannot price. `toll_cost` counts it as 0 €, so the station can look cheaper than it is. Example: Lyon to Montpellier, where a detour joins the motorway at Chanas. That booth is absent from `vinci_price.yaml`, so the ticket to NIMES-O counts as 0 € in place of about 27 €.] → Accepted by the operator for this version. The ranking uses the priced tolls only. A later change can leave out these stations or rank them last.
- [The fuel that the detour uses is not in the cost.] → Out of scope by the proposal. For a detour of 10 km at 6 L/100 km, the error is 0.6 L, about 1.10 €.
- [One click costs up to 34 router requests.] → The radius and the count limit the requests. The concurrency limit protects a remote router.
- [A car that the bot saved before this change can have a `consume_130` below its `consume_80`.] → No code reads the `car` table yet. The next save through `/car` applies the rule.
- [The page has no automatic tests.] → `tasks.md` has a manual check for each scenario of the page.

## Migration Plan

1. Deploy the application image and the front end image together. The new page calls an endpoint that the old application does not have.
2. Run `docker compose run --rm gas-stations PT23H` once if the store has no stations. An empty table gives the empty-list message.
3. To roll back, deploy the old images. No schema changes, and the `car` key in `localStorage` does no harm to the old page.
