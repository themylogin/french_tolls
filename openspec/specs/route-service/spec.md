# route-service Specification

## Purpose
Defines the answer a route query returns, how that answer is cached and when the cache stops being valid, how failures are reported, and how the web application and the Telegram bot are packaged and run beside the two routing services.

## Requirements

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

### Requirement: The answer says how faithful the link is

Each route SHALL additionally carry:

- `waypoints` — the intermediate waypoints in the link, as `[longitude, latitude]` pairs;
- `waypoints_needed` — how many the optimal route needed, which may exceed the number carried;
- `complete` — false when the link does not reproduce the optimal route in full;
- `divergences` — the stretches where no waypoint could make a fastest-path router follow the optimal route;
- `unpriced` — how many of the route's passages could not be priced.

A passage that could not be priced SHALL carry `reason` and SHALL NOT carry a `cost` of zero.

The fast route needs no waypoints, since it is by definition what a fastest-path router computes. It SHALL carry `waypoints` as an empty list and `complete` as true.

#### Scenario: An incomplete link is marked

- **WHEN** the optimal route needs eleven waypoints
- **THEN** `waypoints` holds nine, `waypoints_needed` is 11, and `complete` is false

#### Scenario: The fast route carries no waypoints

- **WHEN** the fast route is answered
- **THEN** its `waypoints` is empty and its `complete` is true

### Requirement: The cache key names everything the answer depends on

A cached answer SHALL be keyed by the origin, the destination, and a **data fingerprint**.

The fingerprint SHALL be computed at start-up from the content of every input the answer depends on: the four pipeline artefacts this service reads, and `data/segment_weights.csv`, which is what makes the toll-weighted graph differ from the untouched one.

Keying on the coordinate pair alone means a rebuilt price file never reaches a cached journey, and there is nothing in the cache to tell a stale answer from a current one. Every cached answer this service has ever written was computed against a booth model that no longer exists.

An answer written under one fingerprint SHALL never be returned under another. The service SHALL NOT need a manual cache purge after a pipeline run.

#### Scenario: A repriced pipeline invalidates the cache

- **WHEN** `data/vinci_price.yaml` is rebuilt and the service restarts
- **THEN** a journey answered before the rebuild is computed again rather than read from the cache

#### Scenario: An unchanged pipeline keeps the cache

- **WHEN** the service restarts with the artefacts unchanged
- **THEN** a journey answered before the restart is read from the cache

### Requirement: The cache is written outside the repository's data directory

Cached answers and failure records SHALL be written to a location that is not `data/`.

`data/` holds the pipeline's inputs and its committed deliverables. Writing a growing cache into it mixes runtime state with tracked artefacts, and forces the directory to be mounted writable into a service that only ever reads from it.

Where the pipeline artefacts are mounted into a service at all, they SHALL be mounted read-only. The test runner mounts them not at all.

#### Scenario: The artefacts are not writable by the application

- **WHEN** the web service runs
- **THEN** `data/` is mounted read-only, and the cache is written elsewhere

#### Scenario: The test runner has no artefacts to write to

- **WHEN** the test runner runs
- **THEN** `data/` is not mounted into it

### Requirement: A failed query says what failed

A query that cannot be answered SHALL fail with an error naming the cause, distinguishing at least:

- an origin or destination further from the road network than the reach;
- no route between the two points on one or both graphs;
- a routing service that did not answer.

The failure SHALL be recorded with the query that caused it and the cause, and the recording SHALL NOT prevent the error from reaching the caller.

A cause SHALL NOT be reported as a Python exception repr. That is what the current failure records hold, and it names the line that raised rather than the condition.

#### Scenario: An unreachable destination

- **WHEN** the destination is 4 km from the nearest road
- **THEN** the query fails naming the distance, and the failure record names the same

#### Scenario: A router that is down

- **WHEN** `osrm-optimal` is not answering
- **THEN** the query fails naming that service, and does not report an unreachable location

### Requirement: The service refuses to start without its artefacts

The application SHALL read the pipeline artefacts at start-up and SHALL fail to start, naming the missing file, when one is absent or unparseable.

A service that starts without its tariffs answers every journey at 0 EUR, and nothing in the answer distinguishes that from a free journey.

#### Scenario: A missing price file

- **WHEN** `data/vinci_price.yaml` is not mounted
- **THEN** the service exits at start-up naming that file, rather than serving

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

### Requirement: The bot's behaviour is unchanged

`french_tolls/bot.py` SHALL keep the behaviour it has: the same commands, the same two-message origin-and-destination exchange, the same reply text, and the same reach check before a location is accepted.

Only its packaging changes. The functions it imports SHALL keep their names and signatures.

#### Scenario: The reach check still exists

- **WHEN** the bot receives a location further than the reach from any road
- **THEN** it replies that the location is not within a kilometre of any road in France, as it does today

### Requirement: Configuration is read from the environment

The token, the API key, the published port, the wage, the query budget, the reach, and the routers' addresses SHALL be read from the environment, each with a documented default where a default is meaningful. `.env.example` SHALL document every one.

A secret SHALL NOT be committed and SHALL NOT appear in a failure record or a log line.

#### Scenario: Every variable is documented

- **WHEN** `.env.example` is read
- **THEN** it names the Telegram token, the LocationIQ key, and the published port of the web application, alongside the variables the pipeline already documents
