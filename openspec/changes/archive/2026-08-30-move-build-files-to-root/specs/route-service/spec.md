## MODIFIED Requirements

### Requirement: The application, the bot, and the migration are Compose services

`docker-compose.yml` SHALL define these **six** services for the application, alongside whatever services other capabilities require of it. Five are built from one image defined at the repository root:

- `web` — the aiohttp application, publishing nothing;
- `bot` — the Telegram bot, publishing nothing;
- `migrate` — a one-shot run that applies the schema and exits;
- `tests` — a one-shot unit test run, depending on nothing;
- `integration` — a one-shot run of the recorded drive-flow suite.

The sixth is built from its own image under `www/`:

- `nginx` — the front end, serving the page and publishing the one host port.

**The application's image definition, its pinned dependency list and its schema revisions SHALL live at the repository root rather than inside the Python package.** None of them is importable and none is part of the package; they describe how the project is built and migrated, which is a property of the project. Keeping them inside `french_tolls/` is also what put the dependency list out of reach of any other image's `COPY`, and `evaluation` already builds from the root for that single reason.

**`web` and `bot` SHALL NOT start until `migrate` has completed successfully.** `runtime-store` requires that exactly one process applies the schema; two serving processes opening one SQLite file on one shared volume are what that requirement exists to keep apart.

**The application image SHALL install its Python dependencies from a pinned list rather than from the distribution.** It previously took aiohttp, PyYAML and pytest from Debian and saw them through an environment configured to draw on the system's packages. The distribution's SQLAlchemy predates the declarative style the models are written in, so that arrangement cannot serve this application, and one pinned list is the smaller thing to reason about than an environment that half-sees another.

`web` and `bot` SHALL join the Compose network and SHALL address the routers by their service names, `osrm-toll` and `osrm-optimal`. They SHALL NOT address the routers through a published host port: on a host where the published ports are not reachable, a service that used them would fail while the same query over the network succeeds.

**`osrm-toll` SHALL be started with a matching size large enough for a whole trace as `toll-equivalence` sends one.** That capability recovers the booths a foreign route crosses by matching its geometry in one request, and the server's default admits a hundred coordinates where the shortest trace worth matching runs to hundreds. Splitting the trace to fit is not an alternative: a window matched with no knowledge of the road before it produces wrong answers, which is the defect that made this requirement necessary.

The size SHALL be chosen against that measurement rather than set as high as it will go. `toll-equivalence` thins a trace before it sends it, and a size that also admits an unthinned one buys nothing: it lets a fault — a caller that skipped the thinning — reach the router as a request tens of times more expensive and, measured, less accurate. A ceiling that refuses it is the cheaper failure.

`nginx` SHALL reach the application the same way, at its service name over the Compose network, and SHALL be the only one of the six publishing a host port. `web` publishes nothing because the page and the API have to answer on one origin, and that origin is `nginx`.

`tests` SHALL depend on none of them. It SHALL NOT be given the routers' addresses and SHALL NOT mount `data/`, because the suite it runs reaches no routing service and reads no artefact. A test runner carrying a dependency its tests do not use only makes the suite unrunnable on a checkout that has no graphs.

**`integration` SHALL be the opposite, and SHALL be a separate service for exactly that reason.** It SHALL reach the routers by name and SHALL mount `data/`, because `drive-flow-integration-tests` drives real routes over real booths.

It SHALL be unable to spend money or reach a chat, and SHALL be so **by construction rather than by promise**: its Google endpoint SHALL address the suite's own replay server, and its Telegram token SHALL authenticate nothing. A real key left in the environment by accident then buys nothing, because there is nowhere for the request to go.

It SHALL be given a cache directory of its own, so a run leaves the application's count of requests spent as it found it. That directory being its own also means the run applies the schema to its own database rather than depending on `migrate`.

Merging the two runners was considered and refused. One of them exists to prove the logic runs on a bare checkout, and the other cannot run without 30 GB of graph. A single service would have to carry the union of their dependencies, which would make the unit suite unrunnable in the case it was written to cover.

`web`, `bot`, `migrate`, and `nginx` SHALL sit behind a Compose profile, so that a plain `docker compose up` continues to start the query services and nothing else. `bot` needs a Telegram token that a pipeline-only checkout has no reason to hold, and a service that crash-loops without one makes `up` useless for the pipeline.

`tests` and `integration` SHALL sit behind a profile too, since each is a one-shot run and not a service.

**Building from the root SHALL NOT mean sending the root.** The tree is tens of gigabytes, nearly all of it `data/` and the routing graphs, and what may be sent SHALL be named rather than left to what a later directory adds.

#### Scenario: Plain compose up is unchanged

- **WHEN** `docker compose up` is run
- **THEN** the two query services start, and the web application, the bot, the migration run, the front end, and both test runners do not

#### Scenario: The schema is applied before anything serves

- **WHEN** the application profile is started
- **THEN** `migrate` runs to completion first, and `web` and `bot` start only after it succeeds

#### Scenario: A failed migration does not leave a service serving

- **WHEN** `migrate` exits with a failure
- **THEN** `web` and `bot` do not start

#### Scenario: The image draws on no distribution Python package

- **WHEN** the application image's Python environment is inspected
- **THEN** every dependency comes from the pinned list, and the environment does not draw on the distribution's site packages

#### Scenario: The build files are not inside the package

- **WHEN** `french_tolls/` is listed
- **THEN** it holds Python modules and the test suites, and no image definition, no dependency list and no schema revisions

#### Scenario: The context sent from the root stays small

- **WHEN** the application image is built
- **THEN** what is sent is a few megabytes of the tree rather than the whole of it

#### Scenario: The application reaches the routers by name

- **WHEN** the web service answers a query
- **THEN** it reaches `osrm-toll` and `osrm-optimal` over the Compose network

#### Scenario: A whole trace can be matched in one request

- **WHEN** a long route's trace is sent to `osrm-toll` for matching, thinned as `toll-equivalence` thins one
- **THEN** the request is accepted rather than refused for its size

#### Scenario: The front end is the only published port

- **WHEN** the application services are running
- **THEN** `nginx` publishes a host port and `web`, `bot`, `migrate`, `tests`, and `integration` publish none

#### Scenario: Another capability's service is not one of these six

- **WHEN** a service required by another capability is defined in the same file
- **THEN** it is none of `web`, `bot`, `migrate`, `tests`, `integration`, or `nginx`, and this requirement says nothing about it

#### Scenario: One image, five services

- **WHEN** `web`, `bot`, `migrate`, `tests`, and `integration` are built
- **THEN** they are built from the same image definition, the one at the repository root

#### Scenario: The front end is built from its own image

- **WHEN** `nginx` is built
- **THEN** it comes from the image definition under `www/`, not from the application's

#### Scenario: The front end reaches the application by name

- **WHEN** a request for `/api/calculate` arrives at the front end
- **THEN** it is proxied to the web service over the Compose network

#### Scenario: The test runner reaches neither

- **WHEN** the unit test runner's configuration is inspected
- **THEN** it carries no router address and mounts no pipeline artefact

#### Scenario: The suite runs with the routers stopped

- **WHEN** the unit test runner is started with `osrm-toll` and `osrm-optimal` not running and no graph on disk
- **THEN** the suite runs to completion, and the integration runner does not, which is the difference the two services exist to keep

#### Scenario: The integration runner reaches both, and can spend nothing

- **WHEN** the integration runner's configuration is inspected
- **THEN** it carries both router addresses and mounts `data/`, and its Google endpoint addresses the replay server rather than Google
