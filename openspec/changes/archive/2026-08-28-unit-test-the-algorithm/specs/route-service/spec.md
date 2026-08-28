## MODIFIED Requirements

### Requirement: The application and the bot are Compose services

`docker-compose.yml` SHALL define three further services, all built from one image under `french_tolls/`:

- `web` — the aiohttp application, publishing a host port;
- `bot` — the Telegram bot, publishing nothing;
- `tests` — a one-shot test run.

`web` and `bot` SHALL join the Compose network and SHALL address the routers by their service names, `osrm-toll` and `osrm-optimal`. They SHALL NOT address the routers through a published host port: on a host where the published ports are not reachable, a service that used them would fail while the same query over the network succeeds.

`tests` SHALL depend on neither. It SHALL NOT be given the routers' addresses and SHALL NOT mount `data/`, because the suite it runs reaches no routing service and reads no artefact. A test runner carrying a dependency its tests do not use only makes the suite unrunnable on a checkout that has no graphs.

`web` and `bot` SHALL sit behind a Compose profile, so that a plain `docker compose up` continues to start the query services and nothing else. `bot` needs a Telegram token that a pipeline-only checkout has no reason to hold, and a service that crash-loops without one makes `up` useless for the pipeline.

`tests` SHALL sit behind a profile too, since it is a one-shot run and not a service.

#### Scenario: Plain compose up is unchanged

- **WHEN** `docker compose up` is run
- **THEN** the two query services start, and the web application, the bot, and the test runner do not

#### Scenario: The application reaches the routers by name

- **WHEN** the web service answers a query
- **THEN** it reaches `osrm-toll` and `osrm-optimal` over the Compose network

#### Scenario: The test runner reaches neither

- **WHEN** the test runner's configuration is inspected
- **THEN** it carries no router address and mounts no pipeline artefact

#### Scenario: The suite runs with the routers stopped

- **WHEN** the test runner is started with `osrm-toll` and `osrm-optimal` not running and no graph on disk
- **THEN** the suite runs to completion

#### Scenario: One image, three services

- **WHEN** the three services are built
- **THEN** they are built from the same image definition under `french_tolls/`

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
