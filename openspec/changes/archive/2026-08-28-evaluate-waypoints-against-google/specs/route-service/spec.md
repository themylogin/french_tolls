## MODIFIED Requirements

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
