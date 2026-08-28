## MODIFIED Requirements

### Requirement: The application and the bot are Compose services

`docker-compose.yml` SHALL define four further services. Three are built from one image under `french_tolls/`:

- `web` — the aiohttp application, publishing nothing;
- `bot` — the Telegram bot, publishing nothing;
- `tests` — a one-shot test run.

The fourth is built from its own image under `www/`:

- `nginx` — the front end, serving the page and publishing the one host port.

`web` and `bot` SHALL join the Compose network and SHALL address the routers by their service names, `osrm-toll` and `osrm-optimal`. They SHALL NOT address the routers through a published host port: on a host where the published ports are not reachable, a service that used them would fail while the same query over the network succeeds.

`nginx` SHALL reach the application the same way, at its service name over the Compose network, and SHALL be the only one of the four publishing a host port. `web` publishes nothing because the page and the API have to answer on one origin, and that origin is `nginx`.

`tests` SHALL depend on none of them. It SHALL NOT be given the routers' addresses and SHALL NOT mount `data/`, because the suite it runs reaches no routing service and reads no artefact. A test runner carrying a dependency its tests do not use only makes the suite unrunnable on a checkout that has no graphs.

`web`, `bot`, and `nginx` SHALL sit behind a Compose profile, so that a plain `docker compose up` continues to start the query services and nothing else. `bot` needs a Telegram token that a pipeline-only checkout has no reason to hold, and a service that crash-loops without one makes `up` useless for the pipeline.

`tests` SHALL sit behind a profile too, since it is a one-shot run and not a service.

#### Scenario: Plain compose up is unchanged

- **WHEN** `docker compose up` is run
- **THEN** the two query services start, and the web application, the bot, the front end, and the test runner do not

#### Scenario: The application reaches the routers by name

- **WHEN** the web service answers a query
- **THEN** it reaches `osrm-toll` and `osrm-optimal` over the Compose network

#### Scenario: The front end is the only published port

- **WHEN** the application services are running
- **THEN** `nginx` publishes a host port and `web`, `bot`, and `tests` publish none

#### Scenario: The front end reaches the application by name

- **WHEN** a request for `/api/calculate` arrives at the front end
- **THEN** it is proxied to the web service over the Compose network

#### Scenario: The test runner reaches neither

- **WHEN** the test runner's configuration is inspected
- **THEN** it carries no router address and mounts no pipeline artefact

#### Scenario: The suite runs with the routers stopped

- **WHEN** the test runner is started with `osrm-toll` and `osrm-optimal` not running and no graph on disk
- **THEN** the suite runs to completion

#### Scenario: One image, three services

- **WHEN** `web`, `bot`, and `tests` are built
- **THEN** they are built from the same image definition under `french_tolls/`

#### Scenario: The front end is built from its own image

- **WHEN** `nginx` is built
- **THEN** it comes from the image definition under `www/`, not from the application's

### Requirement: The answer keeps the shape its consumers already read

A route query SHALL return a mapping with the keys `fast` and `optimal`, each holding one route.

Each route SHALL carry, with the meanings they have today:

- `distance` — metres;
- `duration` — seconds;
- `nodes` — the route's coordinates in order, as `[longitude, latitude]` pairs;
- `peages` — the passages in driven order, each a mapping with `name` and `cost`;
- `cost` — euros, the sum of the priced passages;
- `url` — a Google Maps directions link from the route's own origin;
- `url_from_current_location` — the same link with `Current Location` as the origin;
- `url_from_current_location_through_start` — the same, with the route's origin kept as the first waypoint.

New information SHALL be added as new keys and SHALL NOT change the meaning of an existing one. The Telegram bot and the page under `www/` read this mapping, and `web-front-end` records exactly which of these keys the page reads. A renamed or repurposed key breaks one or both of them.

The entry point SHALL keep its present signature: it takes an origin and a destination, each a `[longitude, latitude]` pair, and returns this mapping.

#### Scenario: An existing consumer still works

- **WHEN** the bot formats an answer
- **THEN** it reads `duration`, `cost`, `distance`, and the three link keys from `optimal` and `fast`, and each holds what it held before

#### Scenario: The page's keys are all present

- **WHEN** the page renders an answer
- **THEN** every key `web-front-end` records it as reading is present on both routes

#### Scenario: A passage carries a name and a cost

- **WHEN** a route's `peages` are read
- **THEN** each entry carries `name` and `cost`, in the order the route drives them
