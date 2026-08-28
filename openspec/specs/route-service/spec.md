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
- `url` — a directions link from the route's own origin;
- `url_from_current_location` — the same link with `Current Location` as the origin;
- `url_from_current_location_through_start` — the same, with the route's origin kept as the first waypoint.

Those three SHALL address this service rather than Google, in every case and with no fallback. Following one refines the waypoints where budget allows and redirects to Google Maps, so a link that was sent before the refinement was bought still arrives at the refined route. They remain links to a driving route from the named origin to the named destination, which is what every consumer reads them for; only the host changes.

The three SHALL be computed from the origin and the destination each time an answer is returned, and SHALL NOT be read from the cache. They are a function of the two coordinates and the service's public address, and the coordinates are the cache key itself; storing them would put the public address into what is cached and make a configuration change serve links to an address that is no longer the service's.

A caller SHALL NOT be able to tell whether an answer came from the cache. The three keys carry the same absolute addresses either way.

The direct Google link SHALL be returned as well, under its own key, for a consumer that would rather not depend on this service being reachable. Unlike the three, it is built from the route's own geometry rather than from the endpoints, so it is not derivable from the cache key and SHALL be stored with the answer.

New information SHALL be added as new keys and SHALL NOT change the meaning of an existing one. The Telegram bot and the page under `www/` read this mapping, and `web-front-end` records exactly which of these keys the page reads. A renamed or repurposed key breaks one or both of them.

The entry point SHALL keep its present signature: it takes an origin and a destination, each a `[longitude, latitude]` pair, and returns this mapping.

#### Scenario: An existing consumer still works

- **WHEN** the bot formats an answer
- **THEN** it reads `duration`, `cost`, `distance`, and the three link keys from `optimal` and `fast`, and each holds what it held before

#### Scenario: The page's keys are all present

- **WHEN** the page renders an answer
- **THEN** every key `web-front-end` records it as reading is present on both routes

#### Scenario: The links address this service

- **WHEN** the three link keys are read
- **THEN** each addresses this service, and following one redirects to Google Maps

#### Scenario: A cache hit and a miss are indistinguishable

- **WHEN** the same journey is answered twice, the second time from the cache
- **THEN** the three link keys carry the same absolute addresses both times

#### Scenario: A changed public address reaches a cached journey

- **WHEN** `PUBLIC_SITE_URL` is changed and a journey already in the cache is answered
- **THEN** its three links carry the new address, without the cache being purged

#### Scenario: The direct link is still available

- **WHEN** the answer is read
- **THEN** it carries the unrefined Google Maps link under its own key

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

### Requirement: The cache key is the journey, and nothing else

A cached answer SHALL be keyed by the origin and the destination, and by nothing else.

The same key SHALL govern a stored refinement. A refinement describes a particular optimal route, so it is stale exactly when that route is, and the two SHALL therefore be purged together and never separately.

Nothing in the key SHALL describe the pipeline artefacts. A rebuilt price file therefore reaches a cached journey, and the cache SHALL be purged by hand after a pipeline run. This is a deliberate trade: automatic invalidation cost a digest computed at start-up, a field carried on the booth model, a column in the primary key of two tables, and a parameter threaded through every cache call and through the whole of the refinement, to spare an operator one command run a few times a year.

The consequence SHALL be stated where an operator will meet it. The command that purges the cache SHALL describe itself as what a pipeline rebuild requires, and SHALL NOT describe itself as a way to reclaim disk that a rebuild has already made stale. A stale answer is a wrong toll total that is indistinguishable from a right one, and nothing detects it.

Nothing in the key SHALL describe the service's configuration either. The answer SHALL carry no value derived from configuration, which is what makes the coordinate pair sufficient.

Rows written under a key that carried a fingerprint SHALL be dropped rather than migrated. The tables holding paid autocomplete answers and the month's count of paid requests SHALL NOT be touched.

#### Scenario: A repriced pipeline does not invalidate the cache

- **WHEN** `data/vinci_price.yaml` is rebuilt and the service restarts
- **THEN** a journey answered before the rebuild is still read from the cache, and the operator must purge it to see the new price

#### Scenario: An unchanged pipeline keeps the cache

- **WHEN** the service restarts with the artefacts unchanged
- **THEN** a journey answered before the restart is read from the cache

#### Scenario: A refinement is purged with the route it describes

- **WHEN** a journey's cached answer is purged
- **THEN** its stored refinement goes with it, because the two share a key

#### Scenario: The old rows are dropped rather than migrated

- **WHEN** the service starts against a database whose answers and refinements were keyed by a fingerprint
- **THEN** those two tables are recreated empty, and the autocomplete cache and the month's request count keep every row

#### Scenario: The drop happens once

- **WHEN** the service starts again against the same database
- **THEN** nothing is dropped, and every answer written since the first start survives
### Requirement: The cache is written outside the repository's data directory

Cached answers, stored refinements, the autocomplete cache, the count of paid requests, and failure records SHALL be written to a location that is not `data/`.

They SHALL live in one SQLite database rather than in a mixture of files and databases. The count of what has been spent has to be transactional against the record of what the money bought, and two stores cannot be made to agree; one store is also one thing to find, to inspect, and to back up.

`data/` holds the pipeline's inputs and its committed deliverables. Writing a growing cache into it mixes runtime state with tracked artefacts, and forces the directory to be mounted writable into a service that only ever reads from it.

Where the pipeline artefacts are mounted into a service at all, they SHALL be mounted read-only. The test runner mounts them not at all.

#### Scenario: One database holds it all

- **WHEN** the application's writable storage is inspected
- **THEN** the route answers, the refinements, the autocomplete cache, and the monthly request count are tables of one database

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

`docker-compose.yml` SHALL define these four services for the application, alongside whatever services other capabilities require of it. Three are built from one image under `french_tolls/`:

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

#### Scenario: Another capability's service is not one of these four

- **WHEN** a service required by another capability is defined in the same file
- **THEN** it is none of `web`, `bot`, `tests`, or `nginx`, and this requirement says nothing about it

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

The token, the API keys, the published port, the wage, the query budget, the reach, the monthly ceiling on paid requests, the public address of the site, and the routers' addresses SHALL be read from the environment, each with a documented default where a default is meaningful.

`PUBLIC_SITE_URL` SHALL be required. The service SHALL fail to start, naming it, when it is unset or empty. The three link keys address this service, and a service that does not know its own address cannot produce them; starting anyway would mean answering with links of a different shape, which is a silent change to a contract two consumers read.

Every service that answers a route query SHALL receive it — the web application and the bot alike. A deployment that gave it to one and not the other made the same three keys mean different things to the page and to Telegram, and nothing reported the difference.

The Google key and the monthly ceiling SHALL be optional. Without them the service answers every journey unrefined rather than failing to start: refinement is an improvement to a link, not a condition of producing one. `.env.example` SHALL document every one.

A secret SHALL NOT be committed and SHALL NOT appear in a failure record or a log line.

#### Scenario: Every variable is documented

- **WHEN** `.env.example` is read
- **THEN** it names the Telegram token, the LocationIQ key, the Google key, the monthly ceiling, the public address, and the published port of the web application, alongside the variables the pipeline already documents

#### Scenario: The service runs without a Google key

- **WHEN** no Google key is configured
- **THEN** the service starts and answers every journey with unrefined waypoints

#### Scenario: The service refuses to run without a public address

- **WHEN** `PUBLIC_SITE_URL` is unset or empty
- **THEN** the service exits at start-up naming it, rather than serving links of another shape

#### Scenario: The bot and the web application agree

- **WHEN** the same journey is answered by the bot and by the web application
- **THEN** both carry the same three links, each addressing this service
