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

### Requirement: An amount is shown as money; the absence of one is marked, not explained

A passage carrying an amount SHALL be rendered as a currency value.

A passage carrying no amount SHALL be rendered as `X €` — an amount with its figure missing.

Every passage that reaches the list is a charge the driver will pay; the only ones without an amount are the ones nobody could price. A dash reads as *nothing to pay*, which is the opposite of the truth. `X €` reads as a price nobody has filled in, which is what it is.

Formatting an absent amount as currency renders it `0,00 €`, which tells a driver a toll they will be charged for is free. `journey-toll-accounting` forbids the API from making that claim; a page that makes it at the last step defeats the requirement rather than satisfying it.

**The reason the API gives SHALL NOT be shown.** It is written to tell an operator which of six accounting states was reached — *the booth maps to no gare*, *neither neighbour is a recorded side of this barrier* — in the vocabulary of this project's own data files. A driver cannot act on it, and `X €` already says the only thing they can act on: that this charge is real and its size is not known here.

The API SHALL still carry it. `route-service` requires an unpriced passage to carry a reason and `journey-toll-accounting` requires the reasons be told apart; both stand. What changes is that the page is no longer one of its readers.

A route's total SHALL continue to be shown as currency, since it is always a real sum — of the passages that could be priced.

#### Scenario: A priced passage

- **WHEN** a passage carries a cost of 13.70
- **THEN** it is shown as `13,70 €`

#### Scenario: An unpriced passage

- **WHEN** a passage carries no cost
- **THEN** it is shown as `X €`, and never as `0,00 €` or as a dash

#### Scenario: The reason is not put in front of the reader

- **WHEN** an unpriced passage is shown
- **THEN** the reason the API gave for it appears nowhere on the page, as text or as hover text

#### Scenario: The API still carries it

- **WHEN** the answer behind that passage is read
- **THEN** it carries the reason, so an operator can still tell which accounting state was reached

### Requirement: The page reads a fixed set of keys from the answer

The page SHALL read, from each of the answer's two routes:

- `nodes` — to draw the route on the map, and to place the start and end markers;
- `duration`, `distance`, and `cost` — for the summary line;
- `peages`, each entry's `name` and `cost` — for the passage table.

These are the keys `route-service` requires the answer to carry, and this is what depends on them. A change to any of their names or meanings breaks this page, which is the reason that requirement exists.

**From the answer itself the page SHALL additionally read the refinement key, where it is present**, and from it: `nodes` to draw the orange route, `waypoints` and `added` to mark them, and `reason` to explain a drawing that did not happen. It SHALL treat the key's absence as "nothing to draw" rather than as an error, because that is how the debug setting reaches it.

The three service-addressed link keys are no longer read, because they are no longer sent. The page shows no directions link of its own.

The page SHALL tolerate keys it does not read. The answer carries `duration_osrm`, `google_url`, `waypoints`, `waypoints_needed`, `complete` and `unpriced`; the page ignores them and SHALL keep working when more are added.

#### Scenario: Every key the page reads is present

- **WHEN** the API answers a route query
- **THEN** each of the listed keys is present on both `fast` and `optimal`

#### Scenario: An unknown key is harmless

- **WHEN** the answer carries a key the page does not read
- **THEN** the page renders normally

#### Scenario: A missing refinement is not an error

- **WHEN** the answer carries no refinement key
- **THEN** the page renders the two routes normally and draws no overlay

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

Where the debug setting is on, the page SHALL draw Google's own route on the map for each journey it calculates, without being asked.

**The page SHALL make one request per journey.** It calculates, and draws the overlay from the refinement the answer carries. It used to calculate and then ask a second time for the same journey's refinement, which routed the journey again from nothing to rebuild the route the refinement describes.

The page SHALL draw the overlay when the answer carries a refinement and SHALL draw nothing when it does not. It SHALL NOT read the debug setting itself: the server decides what to send, and the presence of the key is the whole signal. Where it is off, the answer carries no refinement, so the page draws nothing and offers no control that would.

The overlay costs **two** Google requests every time one is drawn — one to find where Google left the route and one to buy the route through the corrected waypoints — and nothing is kept between drawings, so the same journey drawn twice is bought twice. That is the price of the setting and the reason it is a setting: seeing how well a link fits is the whole purpose, and it cannot be seen without asking.

Google's route SHALL be drawn in orange, **beneath** the optimal route and at **twice its width**, so that agreement reads as the green line centred on a band of orange and divergence reads as orange running out on its own. A line drawn over the top would hide the route it is being compared against; a line of the same width would disappear beneath it.

The waypoints sent SHALL be drawn with it, distinguishing those the waypoint search chose from those the refinement added, since which is which is what the overlay is there to judge.

The overlay SHALL be cleared when a new journey is calculated.

#### Scenario: One journey, one request

- **WHEN** a journey is calculated with the debug setting on
- **THEN** the page makes one request, and the orange route is drawn from what that answer carried

#### Scenario: The control draws what Google did

- **WHEN** a journey is calculated and the debug setting is on
- **THEN** Google's route appears in orange, with no control involved

#### Scenario: Nothing is spent until it is asked for

- **WHEN** a journey is calculated and the debug setting is off
- **THEN** the answer carries no refinement, no orange route is drawn, and no control offers one

#### Scenario: The same journey costs again

- **WHEN** a journey already calculated with the setting on is calculated again with it still on
- **THEN** two further Google requests are spent, because nothing about the first drawing was kept

#### Scenario: The orange is visible under the green

- **WHEN** the overlay is drawn
- **THEN** it is twice the width of the optimal route and beneath it, so the green runs down the middle of the orange where the two agree

#### Scenario: The waypoints are visible

- **WHEN** the overlay is drawn
- **THEN** the waypoints sent to Google are marked on it, and those the search chose are distinguished from those the refinement added

#### Scenario: A new journey clears it

- **WHEN** another journey is calculated
- **THEN** the orange route and its waypoint marks are removed
