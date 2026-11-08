# Design

## Context

See `proposal.md` for the motivation and the specs for the behavior. The current state that shapes the approach:

- `refuel.plan` takes a `PlannedRoute` (start, end, route, split stops), walks the fuel from the origin, and routes one detour for each candidate with `routers.route_via`.
- `refuel.py` does not import `route.py`, because `route.py` reads the booth data at import and the unit suite has no `data/`. `api.py` joins the two modules and passes `route.toll_cost` in.
- `osrm._read_route_legs` joins the legs into one node list and keeps `leg_distance`, but not where each leg starts.
- `route._split_google_url` places the waypoints of the optimal route's plan and the split stops on the split route by node id, and returns None when they are more than `MAX_WAYPOINTS` (9).
- The page keeps no state for a plan. It builds the route panel once, in `calculate`, from the answer of `/api/calculate`.

## Goals / Non-Goals

**Goals:**

- The server decides where each chosen station goes on the route, the same way at each step.
- One request for each step of the plan.

**Non-Goals:**

- No change to how a single step ranks its candidates.
- No new totals in the route panel.

## Decisions

### The page sends the chosen positions, and the server routes them again

A request carries `chosen`, the positions of the stations in the order of choice. For each one, the server walks the fuel on the route so far, places the station as `detour_vias` places a candidate, and calls `route_via`. The route that it gets is the detour route that the earlier answer listed, because the router answers the same request in the same way.

The alternative is that the page sends back the full via list of the station that it chose. The server then trusts a list from the client for the place of each split stop, and the API has to carry that list in every answer. The replay costs one router request for each chosen station, and it keeps all placement in one function.

When a replay finds no search point before a chosen station, the plan did not need that station. The function raises `UnneededStation`, and `api.py` answers 400.

### `osrm.Route` keeps where each leg starts

`Route` gets `leg_start`, the node index where each leg begins. `_read_route` sets `(0,)`. `_read_route_legs` records `len(node_ids)` before it adds the nodes of each leg. Each leg after the first starts at the node of its via, because the reader drops the last node of the leg before. So via `k` of a route is at node `leg_start[k + 1]`.

The vias of the route so far are then `(location, leg_start[k + 1])` pairs, for the split stops and the chosen stations alike. `detour_vias` takes this list in place of the split stops. The distance of a candidate is the sum of the legs before it: the number of vias before the search point, plus one. `distance_from_previous` sums the same legs from the one after the last chosen via.

### The walk can start at a node with a given fuel

`fuel_walk` gets a `start` index. With chosen stations, the walk starts at the node of the last chosen station, with `tank_volume` liters. A point before that station can be at 5 L or less, but that need was the reason to choose the station, so the walk does not look there.

### `route.py` builds the link of a finished plan

`PlannedRoute` keeps `optimal`, the optimal route of the journey. A new function `link_through(routers, planned, route, kept)` builds the link of the finished route:

1. It runs `plan_waypoints` on `planned.optimal`, as `get_route` does. So the waypoints are those of the optimal route's own link.
2. It places each waypoint on the finished route by its node id, as `_split_google_url` does. A waypoint whose node the finished route does not cross is dropped.
3. `kept` gives the chosen stations and the split stops, at their `leg_start` nodes. When they alone are more than 9, the function returns None.
4. While the waypoints are more than 9, it drops the route waypoint with the shortest distance along the route to its nearest other waypoint. The distance comes from the sums of `segment_distance`.
5. It sorts the waypoints by node index and calls `google_maps_link`.

`refuel.plan` gets the function from `api.py`, as it gets `toll_cost`, and calls it only when it finishes a plan.

The waypoint search costs up to a few hundred router requests, and it runs once, on the step that finishes the plan. The alternative is that the page sends the waypoints of its link back. The page then becomes a source of routing data. The link of the split route would also need its own merge, because the answer of `/api/calculate` does not carry the split stops as waypoints.

### The page keeps the plan in three variables

- `refuelChosen` holds the positions chosen in the open dialog. `Calculate` and the closing of the dialog empty it.
- `refuelRequest` holds the car values and the fuel of the last valid `Calculate`. `Use` sends these values, so an edit of a field after `Calculate` does not change the plan.
- `finishedPlan` holds the route name and the link of a finished plan. A new route calculation empties it.

`calculate` keeps its answer in `lastAnswer`, and a new `renderRoutes` builds the route panel from `lastAnswer` and `finishedPlan`. With a finished plan, the planned route shows the icon as a plain element without the `refuel-link` class, so the click listener ignores it. The other route shows no icon, and the planned route shows the link of the plan.

The black route uses `showPath` with the width 8 of the split route. The z-order gets one more level: fast 1, Google 2, plan 3, split 4, optimal 5. So the black line is beneath the red and the green ones, and it shows where the plan leaves them. The chosen stations get `waypointDot("#000000")` markers. The dialog is 600 px wide, through the variable `--bs-modal-width`: Bootstrap's default is 500 px, and `modal-lg` is 800 px. While a request is open, the list gets `visibility: hidden`, so it keeps its place, and the spinner is centered over it with negative margins, because its rotation uses `transform`. The toll column shows `toll_difference` in the euro format of the route totals, with a sign, and stays empty at 0. The `Use` button is smaller than `btn-sm`, the smallest Bootstrap 5 size: a rule on `.stations .refuel-use` sets the button's CSS variables `--bs-btn-padding-y`, `--bs-btn-padding-x`, and `--bs-btn-font-size`. `calculate` removes the black line and its markers, as it does for the other layers.

A `Use` click on the last stop closes the dialog with `bootstrap.Modal.hide`. The listener for the closing empties `refuelChosen`, so a finished plan and a cancelled one leave the same dialog state.

## Risks / Trade-offs

- [The route panel keeps the time, the distance, and the tolls of the route without stops.] → Out of scope in the proposal. The black line and the link show the plan.
- [A link that drops route waypoints can let Google drive another road between two stations.] → Chosen by the operator. The stations stay in the link, so every stop is driven.
- [A route waypoint whose node a detour leaves is dropped.] → The station that caused the detour is a waypoint itself, so Google still goes there.
- [A step with many chosen stations costs one router request for each of them.] → At most 20 stations, so a step costs at most 20 more requests.
- [The step that finishes the plan takes a few seconds for the waypoint search.] → The dialog shows that it is busy until the answer comes.
