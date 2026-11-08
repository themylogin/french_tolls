# Tasks

## 1. Legs and the fuel walk

- [x] 1.1 In `french_tolls/osrm.py`, add `leg_start` to `Route`, with the default `()`. `_read_route` sets `(0,)`, and `_read_route_legs` sets the node index where each leg begins, as in the design section "`osrm.Route` keeps where each leg starts". In `french_tolls/tests/test_osrm_client.py`, extend `test_a_route_through_a_via_keeps_the_distance_of_each_leg` to expect `leg_start` `(0, 2)` for the legs with the nodes `[1, 2, 3]` and `[3, 4]`. Verify with `make test`.
- [x] 1.2 In `french_tolls/refuel.py`, give `fuel_walk` a `start` index with the default `0`. Add tests in `french_tolls/tests/test_refuel.py`: with `tank_volume` `50`, 1 L per segment, and a walk that starts at node 3 with 50 L, the search point is node 48; a start at a node after which the fuel lasts gives `None`. Verify with `make test`.

## 2. Chosen stations in the plan

- [x] 2.1 In `refuel.py`, make `detour_vias` and `detours` take the vias of the route so far as `(location, node index)` pairs, built from `leg_start`, as in the design. The distance of a candidate is the sum of the legs before it. Keep the existing tests passing. Add tests: a chosen station C before the search point and a split stop B after it give the vias C, station, B; with legs of 220 km to C and 310 km from C to the station, the `distance` is `530000`. Verify with `make test`.
- [x] 2.2 Add the replay of the design section "The page sends the chosen positions, and the server routes them again", and `UnneededStation`. `plan` gets the parameter `chosen`. Add tests with a fake router that answers `route_via` from the via list: `"chosen": [A]` makes the planned route the detour route listed for A, and the walk restarts at A with `tank_volume`; `"chosen": [A, B]` routes A first, then B, with one request each; a chosen station after the fuel already lasts raises `UnneededStation`. Verify with `make test`.
- [x] 2.3 When `chosen` is not empty and the fuel lasts, add `route` with `nodes` and the `google_url` of the link function that the caller gives. Add tests: the answer has `stop_needed` false, `fuel_left`, and `route`; the link function gets the finished route, the chosen stations, and the split stops at their `leg_start` nodes; without chosen stations, the answer has only `stop_needed` and `fuel_left`, and the link function is not called. Verify with `make test`.
- [x] 2.4 Add `distance_from_previous` to each station entry: the sum of the detour legs after the last chosen via, or `distance` without chosen stations. Add tests: legs of 220 km to C and 310 km from C give `310000`; 150 km from C to a split stop and 180 km on to the station give `330000`; without chosen stations it equals `distance`. Verify with `make test`.

## 3. The link of a finished plan

- [x] 3.1 In `french_tolls/route.py`, add `optimal` to `PlannedRoute`, and add `link_through(routers, planned, route, kept)` with the five steps of the design. Add it to `__all__`. Verify with the tests of 3.2.
- [x] 3.2 In `french_tolls/integration/test_refuel_endpoint.py`, add tests of `link_through` with a patched `plan_waypoints`: 5 route waypoints and 2 stations give a link with 7 waypoints in route order; 8 route waypoints and 2 stations give 9, keep both stations, and drop the route waypoint nearest along the route to another waypoint; a route waypoint whose node the finished route does not cross is not in the link; 10 kept stations give `None`. Verify with `docker compose --profile test run --rm --no-TTY integration`.

## 4. Endpoint

- [x] 4.1 In `french_tolls/api.py`, read `chosen`: a missing key is an empty list; a value that is not a list, more than 20 entries, or an entry without two finite numbers gives 400 before the first router request. Pass `chosen` and a link function built on `route.link_through` to `refuel.plan`. `UnneededStation` gives 400. Verify with the tests of 4.2.
- [x] 4.2 Add endpoint tests in `test_refuel_endpoint.py`: a request without `chosen` passes an empty list to the plan; 21 entries, `{"latitude": 45.34}`, and `"chosen": "A"` each give 400 and call no router; `UnneededStation` gives 400; a valid `chosen` reaches the plan in its order. Verify with `docker compose --profile test run --rm --no-TTY integration`.

## 5. Page

- [x] 5.1 In `www/index.js`, add the fifth column with a green `Use` button, `btn btn-success btn-sm`, to each row. Keep `refuelRequest` from the last valid `Calculate`, and `refuelChosen`. A click on `Use` adds the station and sends one request with `refuelRequest` and `chosen`. While it is open, disable `Calculate` and all `Use` buttons. Show a new list in place of the old one. Verify in the browser: the first `Use` sends `"chosen": [A]`; a second `Use` sends `"chosen": [A, B]`; the row shows `Leclerc`, `235 km`, `1,799 €/L`, `+7 min`, and a green `Use`.
- [x] 5.2 Keep the answer of `/api/calculate` in `lastAnswer`, and build the route panel with a new `renderRoutes` from `lastAnswer` and `finishedPlan`. On a finished plan, close the dialog, draw the black route at the width 8 and the z-order of the design, mark each chosen station with a black dot, show the icon of the planned route as a plain element, hide the icon of the other route, and show the link of the plan. Add the style of the plain icon to `www/style.css`. Verify in the browser: the black line is beneath the green and the red ones; each chosen station has a black dot; a click on the plain icon opens no dialog; the split route shows no icon; the Maps link of the planned route goes through the stations; a null link hides it.
- [x] 5.3 Empty `refuelChosen` when the dialog closes and on `Calculate`. Remove the black route and its dots in `calculate`, and empty `finishedPlan`. Verify in the browser: `Cancel` after one `Use` draws nothing, and the next `Calculate` sends no `chosen`; a new route calculation removes the black route and the dots, and the optimal route has a clickable icon again.
- [x] 5.4 Show `distance_from_previous` in the distance column. Make the `Use` button smaller with the CSS variables of the design. Verify in the browser: after one `Use`, the next list shows the distance from the chosen station; the `Use` button is lower than a `btn-sm` button.
- [x] 5.5 Add a toll column before `Use` that shows `toll_difference` as `+1,15 €` or `-1,25 €`, and nothing when it rounds to 0. Verify in the browser: a station with a toll change shows it with its sign; a station without one shows an empty cell.
- [x] 5.6 Make the dialog 600 px wide. While a `Use` request is open, keep the old list in place with `visibility: hidden`, and center the spinner over it. Verify in the browser: after a click on `Use`, the list area keeps its size, the spinner turns at its center, and the dialog is wider than before.

## 6. Integration checks

- [x] 6.1 Run `make test` and `docker compose --profile test run --rm --no-TTY integration`. Verify that the unit suite passes. Verify that the integration suite fails no test beyond the 4 tests in `test_drive_flow.py` that failed before.
- [x] 6.2 With the agreement of the operator, run `make web`. Plan Paris to Marseille on the optimal route with the tank `30`, `Diesel`, `5.5`, `7.2`, and the fuel `10`, so that the plan needs at least two stops. Verify that each `Use` shows the list of the next stop, that the last `Use` closes the dialog and draws the plan, and that the Maps link opens a route through the chosen stations. Repeat on the split route of Lyon to Montpellier.
- [x] 6.3 Run `openspec validate plan-several-fuel-stops --strict`. Verify that the change is valid.
