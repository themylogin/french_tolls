# Proposal

## Why

The web page shows a "Superoptimal route" above the optimal one when splitting a ticket saves money. The Telegram bot does not. Its answer lists only the optimal and fastest routes, and "Drive with Google" always drives the optimal route. A driver who uses the bot cannot see or drive the cheaper split route.

## What Changes

- When the answer carries a superoptimal route, the bot lists it first, as the page does:
  - `Superoptimal route: <time>, <cost> €` and its distance;
  - then `Optimal route`, then `Fastest route`, as today.
- In that case the answer message offers a choice instead of "Drive with Google". The keyboard is one row: `[Optimal] [Superoptimal]`.
- A press on a choice spends the choice. The bot then edits the same message:
  - an empty line and `Optimal route chosen` or `Superoptimal route chosen` are added at the end;
  - the keyboard becomes one `[Drive with Google]` button for the chosen route;
  - when the chosen route needs no Google request (the fastest route crosses the same booths), the bot sends the drive link at once and offers no button, as the answer message does today.
- "Drive with Google" for the superoptimal route uses the existing drive rules on that route:
  - every link keeps a waypoint at each stop;
  - Google's route is accepted only when it crosses every booth of each stop and no booth outside the route;
  - a route that is split in halves keeps each stop in its half.
- The comparison map link is also sent when a superoptimal route is listed, because the map shows where the stops are.
- The route answer gives the bot what it needs to drive the split route:
  - `super_optimal.drive_waypoints`: each stop, and as many of the optimal route's waypoints as fit beside them;
  - `booths` and `index` on each entry of `super_optimal.stops`.
- When the answer has no superoptimal route, the bot behaves as today.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `telegram-drive-flow`:
  - the answer message lists the superoptimal route and offers the choice;
  - a choice leads to "Drive with Google" or to the link;
  - the drive rules apply to a superoptimal route through its stops.
- `route-service`: the `super_optimal` route carries `drive_waypoints`, and each stop carries `booths` and `index`.
- `drive-flow-integration-tests`:
  - the suite presses buttons that a markup edit offers;
  - each pinned journey states which route it chooses;
  - one new pinned journey drives a superoptimal route.

## Impact

- Changed files:
  - `french_tolls/drive.py`: a part keeps its stops, the acceptance test reads them, and a split divides them;
  - `french_tolls/bot.py`: the summary, the choice keyboard, its handler, and the parts for the superoptimal route;
  - `french_tolls/route.py`: the new keys, and a function that routes a stretch through given stops;
  - `french_tolls/tests/test_drive.py`;
  - `french_tolls/integration/`: the chat harness, the transport, the journeys, the recorder, and a new cassette.
- Google cost: a choice costs no request. The superoptimal route costs the same number of requests as an optimal one, because the rules are the same.
- Router load: each half of a split superoptimal route needs one more routed request, through its stops.
- A new cassette needs paid Google requests. The operator records it on purpose, with `record`.
- Unchanged: the page, `/api/calculate` for the page, `/api/refuel`, and the link `google_url` of the superoptimal route.
- Not in scope:
  - the stop names, the saving, or the extra time in the bot message;
  - a way to change the choice after the press;
  - the stale `waypoints` key of `super_optimal`, which repeats the optimal route's waypoints. Nothing reads it.
