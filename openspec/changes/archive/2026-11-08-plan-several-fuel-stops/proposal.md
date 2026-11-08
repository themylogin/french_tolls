# Proposal

## Why

The gas station dialog plans one fuel stop. On a long route, or with a small tank, one full tank does not reach the destination. The driver then has to guess the next stop. The page also forgets the plan: the map, the route panel, and the Maps link do not show the chosen stations.

## What Changes

- Each row of the station list gets a green `Use` button on the right.
- A click on `Use` chooses the station. The page then asks `POST /api/refuel` again, with the chosen stations of this plan in order. The service routes through them, fills the tank at each one, and walks the fuel from the last one:
  - when the tank reaches 5 L again before the destination, the answer is a new list for the next stop, and the dialog shows it;
  - when the fuel lasts, the plan is finished.
- A driver can choose any number of stops in this way, up to 20.
- When the plan is finished, the dialog closes and the page shows the plan:
  - the map draws the route through the chosen stations in black, with the width of the red split route, beneath the green and red routes;
  - the map marks each chosen station with a black dot;
  - the planned route keeps its gas station icon, but the icon no longer opens the dialog;
  - the other route loses its icon;
  - the Google Maps link of the planned route goes through the chosen stations.
- The Maps link keeps every chosen station. When the waypoints of the route and the stations are more than the 9 that a link carries, the link drops route waypoints until it fits. Google can then drive another road between two stations.
- `Cancel` during a plan drops the stations chosen so far. `Calculate` starts a new plan without chosen stations.
- A new route calculation clears the plan.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `refuel-planning`:
  - the request takes the chosen stations;
  - the fuel walk restarts with a full tank at the last chosen station;
  - the detours and the distances go through the chosen stations;
  - the answer of a finished plan carries the route and its Maps link.
- `web-front-end`:
  - the list gets the `Use` button;
  - a finished plan closes the dialog and is drawn on the map and in the route panel;
  - `Calculate` and `Cancel` reset the chosen stations;
  - the no-stop message applies only when no station is chosen.

## Impact

- Changed files:
  - `french_tolls/osrm.py`: `Route` keeps where each leg starts;
  - `french_tolls/refuel.py`: the walk, the vias, the detours, and the plan take the chosen stations;
  - `french_tolls/route.py`: `PlannedRoute` keeps the optimal route, and a new function builds the Maps link through the stations;
  - `french_tolls/api.py`: the endpoint reads and checks `chosen`;
  - their tests;
  - `www/index.js` and `www/style.css`.
- Router load: for each chosen station, a request routes it again, which is one more request per step. The step that finishes the plan also runs the waypoint search once, for the Maps link. This costs up to a few hundred requests, as one `/api/calculate` does.
- The request gets one optional key, so a request without it works as before.
- Unchanged: `/api/calculate`, the ranking rules, the badges, and the bot.
- Not in scope:
  - new totals of time, distance, or tolls in the route panel for the planned route;
  - a way to undo one chosen station while the dialog is open;
  - keeping the plan after a reload.
