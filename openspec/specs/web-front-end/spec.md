# web-front-end Specification

## Purpose
Defines the browser page this project is the back end for — where its files live, how they are built into an image and served, why the page and the API must answer on one origin, and the rules the page follows when it renders a route it was given.

## Requirements

### Requirement: The page lives in the repository and is built into an image

`www/` SHALL hold the front end and its container image definition. The page is what every part of this project exists to produce, and a deployment that has to fetch it from elsewhere can serve a version no one here can name.

The page's files SHALL be copied into the image at build time. A running container SHALL NOT depend on `www/` being present on the host, so that what ships is what was built and a deployment carries one image rather than an image and a directory that has to arrive with it.

The image SHALL be built from a definition under `www/`, separate from the application's own. A change to a stylesheet has no business rebuilding a Python image, and a Python dependency has no business being installed to serve three static files.

#### Scenario: The page is in the image

- **WHEN** the front end container runs on a host with no copy of `www/`
- **THEN** it serves `index.html`, `index.js`, and `style.css`

#### Scenario: The two images are separate

- **WHEN** a file under `www/` is edited
- **THEN** rebuilding the front end image does not rebuild the application image

### Requirement: The page and the API answer on one origin

The page requests `/api/calculate` and `/api/autocomplete` as paths relative to its own origin. Whatever serves the page SHALL therefore also answer `/api/`, by proxying those requests to the aiohttp application over the Compose network.

The page SHALL NOT be given the API's address, and SHALL NOT be made to send a cross-origin request. A page carrying the address of its back end has to be rebuilt to be deployed anywhere else, and a cross-origin arrangement adds a preflight and a CORS policy to maintain in place of a proxy rule that states the same thing once.

The front end service SHALL be the only one of the application services publishing a host port. Two public ports serving overlapping things is an arrangement that can disagree with itself, and a driver who reaches the API port directly gets a 404 for the page.

#### Scenario: The page reaches the API

- **WHEN** a browser loads the page and calculates a route
- **THEN** its request to `/api/calculate` is answered by the aiohttp application

#### Scenario: The API is not published separately

- **WHEN** the running services' published ports are listed
- **THEN** only the front end service publishes one

#### Scenario: The page carries no back end address

- **WHEN** the page's source is inspected
- **THEN** it names no host or port for the API

### Requirement: An amount is shown as money; the absence of one is not

A passage carrying an amount SHALL be rendered as a currency value. A passage carrying no amount SHALL be rendered as a marker that is plainly not a price, and the reason the API gives SHALL be available on it.

Formatting an absent amount as currency renders it `0,00 €`, which tells a driver a toll they will be charged for is free. `journey-toll-accounting` forbids the API from making that claim; a page that makes it at the last step defeats the requirement rather than satisfying it.

A route's total SHALL continue to be shown as currency, since it is always a real sum — of the passages that could be priced.

#### Scenario: A priced passage

- **WHEN** a passage carries a cost of 13.70
- **THEN** it is shown as `13,70 €`

#### Scenario: An unpriced passage

- **WHEN** a passage carries no cost
- **THEN** it is shown as a marker rather than an amount, and never as `0,00 €`

#### Scenario: The reason is available

- **WHEN** an unpriced passage is shown
- **THEN** the reason the API gave for it can be read from that row

### Requirement: The page reads a fixed set of keys from the answer

The page SHALL read, from each of the answer's two routes:

- `nodes` — to draw the route on the map, and to place the start and end markers;
- `duration`, `distance`, and `cost` — for the summary line;
- `peages`, each entry's `name` and `cost` — for the passage table;
- `url`, `url_from_current_location`, and `url_from_current_location_through_start` — for the three directions links. These address this service and redirect to Google Maps; the page neither knows nor needs to know that.

These are the keys `route-service` requires the answer to carry, and this is what depends on them. A change to any of their names or meanings breaks this page, which is the reason that requirement exists.

The page SHALL tolerate keys it does not read. The answer carries `waypoints`, `waypoints_needed`, `complete`, `divergences`, and `unpriced`; the page ignores all of them today and SHALL keep working when more are added.

#### Scenario: Every key the page reads is present

- **WHEN** the API answers a route query
- **THEN** each of the listed keys is present on both `fast` and `optimal`

#### Scenario: An unknown key is harmless

- **WHEN** the answer carries a key the page does not read
- **THEN** the page renders normally

### Requirement: A route is shareable as a link

The page SHALL put the origin and destination in the URL fragment when a route is calculated, and SHALL calculate that route on load when the fragment holds one.

This is what the Telegram bot's "Open comparison map" link uses, so the fragment's shape is a contract between the two. It SHALL hold a JSON object with `from` and `to`, each carrying a `name` and a `lonlat` pair.

#### Scenario: A calculated route becomes a link

- **WHEN** a route is calculated
- **THEN** the fragment holds the origin and destination, and reloading the page recalculates the same route

#### Scenario: The bot's link opens a route

- **WHEN** a link the bot produced is opened
- **THEN** the page fills both fields and calculates that route without further input

### Requirement: A visitor can ask what Google actually drove

Beside each of the three directions links the page SHALL offer a control that, when activated, asks this service for the refinement and draws Google's own route on the map.

The control SHALL be the icon already beside each link, made to look and behave like something clickable — a pointer cursor, and a title saying what it does. A visitor who does not press it SHALL cause no request and no spending.

Google's route SHALL be drawn in orange, above the optimal route and below the fast one, and thinner than both, so that where Google agreed the green shows along both edges and where it did not the orange runs off on its own.

The waypoints that were sent SHALL be drawn with it, as marks distinct from the endpoint pins, since they are the thing the overlay is there to judge.

The overlay SHALL be cleared when a new journey is calculated.

#### Scenario: Nothing is spent until it is asked for

- **WHEN** a journey is calculated
- **THEN** no refinement is requested, and no orange route is drawn

#### Scenario: The control draws what Google did

- **WHEN** the control beside a link is activated
- **THEN** the refinement is requested and Google's route appears in orange, over the optimal route and under the fast one

#### Scenario: The waypoints are visible

- **WHEN** the overlay is drawn
- **THEN** the waypoints sent to Google are marked on it

#### Scenario: A new journey clears it

- **WHEN** another journey is calculated
- **THEN** the orange route and its waypoint marks are removed

### Requirement: The overlay is not gated on an operator's flag

The control SHALL be available to every visitor. It SHALL NOT depend on a debug setting.

The overlay was previously drawn only when an operator set `GOOGLE_DIRECTIONS_DEBUG`, and only for journeys the evaluation had already bought — which is 2 450 of the journeys a visitor could ask for and none of the rest. It now draws the answer for the journey on screen, and it is a visitor's click rather than an operator's switch that decides whether it is asked for.

Where a budget is exhausted, the control SHALL say so rather than fail silently. Nothing to draw and nothing said is indistinguishable from a page that is broken.

#### Scenario: No flag is involved

- **WHEN** the page is served with no debug setting configured
- **THEN** the control is present and works

#### Scenario: An exhausted budget is explained

- **WHEN** the control is activated and no refinement could be made
- **THEN** the page says why rather than doing nothing
