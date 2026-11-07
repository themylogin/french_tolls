# Proposal

## Why

The store holds the fuel prices of about 9,400 stations, and the bot collects the car parameters. Nothing uses them yet. A driver on a long route must choose where to refuel. The cheapest choice depends on the fuel price, the toll change, and the time of the detour.

## What Changes

- The page shows a gas station icon beside the title of the optimal route and of the split route. The icon comes after the Google Maps link when that link is shown. The fastest route gets no icon.
- A click on the icon opens a compact modal dialog with five required fields. Each label is on the same line as its field:
  - the tank volume in liters;
  - the fuel type: Diesel, 95, or 98, as radio buttons with 95 selected by default;
  - the consumption at 80 km/h in liters per 100 km;
  - the consumption at 130 km/h in liters per 100 km;
  - the fuel in the tank now, in liters.
- The first four fields use the limits of the bot `/car` dialog. The page keeps them in LocalStorage and fills them in the next time. The page does not keep the fuel in the tank. The driver enters it each time.
- The dialog has two buttons. `Cancel` closes it. `Calculate` checks the fields and sends one request.
- A new endpoint, `POST /api/refuel`, plans the fuel stop:
  - it routes the selected route again from the same origin and destination;
  - it follows the route segment by segment and subtracts the fuel that each segment uses. The speed of a segment comes from the OSRM duration multiplied by `TIME_MULTIPLIER`. The consumption comes from the curve `a + b·v²` through the two car consumptions. Below 80 km/h, it is `consume_80`;
  - the search point is the first point where the tank holds 5 L or less. When the fuel at the start is 5 L or less, the search point is the start;
  - it takes the 30 nearest stations within 50 km of the search point that sell a fuel of the car;
  - it routes start, station, end for each candidate on the same graph, through the same split stops;
  - it gives each station a cost: the fuel to fill the tank, plus the toll difference, plus the extra time at `EUR_PER_HOUR`;
  - it returns the 10 stations with the lowest cost.
- The dialog lists these 10 stations, cheapest first. Each row shows the name as a Google Maps link, the road distance from the origin, the price per liter, and the detour time with its sign, for example `+4 min`.
- When the tank holds more than 5 L at the destination, the dialog shows the fuel left at the destination and lists no station.
- The bot `/car` dialog, the page, and the endpoint refuse a consumption at 130 km/h that is less than the consumption at 80 km/h. An equal value is valid. Without this rule, the curve falls above 130 km/h and can give a negative consumption.

## Capabilities

### New Capabilities

- `refuel-planning`: how the service finds the point on a route where the driver must refuel, which stations it considers, how it prices a stop at each one, and what `POST /api/refuel` accepts and returns.

### Modified Capabilities

- `car-parameters`: a new requirement says that the consumption at 130 km/h is not less than the consumption at 80 km/h. The scenario "Values inside the limits" then names the question at 80 km/h only.
- `web-front-end`: new requirements for the gas station icon, the car dialog, the LocalStorage values, and the list of stations. The requirement "The page and the API answer on one origin" names the endpoints that the page requests. It changes to name `/api/refuel` as a third endpoint.

## Impact

- New files: `french_tolls/refuel.py`, `french_tolls/tests/test_refuel.py`, and `french_tolls/integration/test_refuel_endpoint.py`.
- Changed files:
  - `french_tolls/api.py` gets the new endpoint;
  - `french_tolls/route.py` exposes the parts that build the optimal route and the split route, so the new module can rebuild them without the waypoint search;
  - `french_tolls/car.py` gets a validation function for the values that the endpoint receives, and the order rule for the two consumptions of the bot dialog;
  - `french_tolls/tests/test_car.py` gets the tests of both;
  - `www/index.html`, `www/index.js`, and `www/style.css` get the icon, the dialog, and the list.
- Router load: one click costs about 34 router requests. These are 4 to rebuild the route and 1 for each of up to 30 candidates. The waypoint search does not run again.
- No new dependency. The page uses the Bootstrap modal and the Bootstrap icon `bi-fuel-pump`. The page loads both already.
- No new table. The car values of the page stay in the browser. They do not reach the `car` table of the bot.
- Unchanged: the answer of `/api/calculate`, the bot drive flow, the gas station run, and the build pipeline.
- Not in scope:
  - the same search in the Telegram bot;
  - station markers on the map;
  - more than one fuel stop on a route;
  - the fuel that the detour itself uses;
  - a filter on old prices.
