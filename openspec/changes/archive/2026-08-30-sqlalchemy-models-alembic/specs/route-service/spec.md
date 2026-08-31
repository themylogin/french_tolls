## ADDED Requirements

### Requirement: The answer keeps the shape its consumers already read, and is computed fresh

A route query SHALL return a mapping with the keys `fast` and `optimal`, each holding one route.

Each route SHALL carry, with the meanings they have today:

- `distance` — metres;
- `duration` — seconds, the travel time this service stands behind;
- `duration_osrm` — seconds, the router's own travel time before correction;
- `nodes` — the route's coordinates in order, as `[longitude, latitude]` pairs;
- `peages` — the passages in driven order, each a mapping with `name` and `cost`;
- `cost` — euros, the sum of the priced passages;
- `google_url` — a directions link from the route's own origin through its waypoints.

**Every answer SHALL be computed when it is asked for.** No answer is stored and none is read back, so nothing an answer carries can describe a route that the current artefacts and the current configuration would no longer produce.

`duration` SHALL be the router's travel time multiplied by a configured factor. The router's clock runs slow: measured over 2 257 journeys against Google's, it predicts about 7% more travel time than Google does for the same road.

`duration_osrm` SHALL carry the uncorrected number, because the factor is measured by comparing the two clocks and comparing against the corrected one would make the next measurement come out at 1.0 by construction.

The correction SHALL be applied each time an answer is returned. It was applied after the store rather than before it so that a changed factor reached a journey already held; with nothing held, a changed factor reaches every journey on the next query and there is nothing to purge for it.

**The three service-addressed link keys are gone.** `url`, `url_from_current_location` and `url_from_current_location_through_start` are no longer returned. They addressed this service so that following one refined the waypoints before redirecting; the bot now refines when a driver asks to drive, and the page draws the refinement directly, so nothing followed them.

`google_url` remains and SHALL continue to be built from the route's own geometry. It is a direct address, derivable from nothing but the route, for a consumer that would rather not depend on this service being reachable.

New information SHALL be added as new keys and SHALL NOT change the meaning of an existing one. The page under `www/` reads this mapping, and `web-front-end` records exactly which of these keys it reads.

The entry point SHALL keep its present signature: it takes an origin and a destination, each a `[longitude, latitude]` pair, and returns this mapping.

#### Scenario: An existing consumer still works

- **WHEN** the bot formats an answer
- **THEN** it reads `duration`, `cost` and `distance` from `optimal` and `fast`, and each holds what it held before

#### Scenario: The links address this service

- **WHEN** a route is read
- **THEN** no key of it addresses this service; `url`, `url_from_current_location` and `url_from_current_location_through_start` are absent, and the only Google address it carries is `google_url`, which addresses Google directly

#### Scenario: The direct link is still available

- **WHEN** the answer is read
- **THEN** it carries the unrefined Google Maps link under `google_url`

#### Scenario: The travel time served is corrected

- **WHEN** a route is answered
- **THEN** its `duration` is `duration_osrm` multiplied by the configured factor, on both `fast` and `optimal`

#### Scenario: The uncorrected time is still available

- **WHEN** something measures the router's clock against Google's
- **THEN** it reads `duration_osrm`, which the correction has not been applied to

#### Scenario: A changed factor reaches the next answer

- **WHEN** the factor is changed and a journey answered before is answered again
- **THEN** its `duration` reflects the new factor, and nothing had to be purged for it to

#### Scenario: A rebuilt pipeline reaches the next answer

- **WHEN** `data/vinci_price.yaml` is rebuilt and the service restarts
- **THEN** a journey answered before the rebuild is answered at the new price, with no purge and no operator action

#### Scenario: The page's keys are all present

- **WHEN** the page renders an answer
- **THEN** every key `web-front-end` records it as reading is present on both routes

#### Scenario: The same journey answers the same twice

- **WHEN** the same journey is answered twice with nothing changed between
- **THEN** both answers carry the same `duration`, `cost` and `peages`

#### Scenario: A passage carries a name and a cost

- **WHEN** a route's `peages` are read
- **THEN** each entry carries `name` and `cost`, in the order the route drives them

### Requirement: The application, the bot, and the migration are Compose services

`docker-compose.yml` SHALL define these **six** services for the application, alongside whatever services other capabilities require of it. Five are built from one image under `french_tolls/`:

- `web` — the aiohttp application, publishing nothing;
- `bot` — the Telegram bot, publishing nothing;
- `migrate` — a one-shot run that applies the schema and exits;
- `tests` — a one-shot unit test run, depending on nothing;
- `integration` — a one-shot run of the recorded drive-flow suite.

The sixth is built from its own image under `www/`:

- `nginx` — the front end, serving the page and publishing the one host port.

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
- **THEN** they are built from the same image definition under `french_tolls/`

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

## MODIFIED Requirements

### Requirement: The cache is written outside the repository's data directory

The autocomplete cache, the count of paid requests, and failure records SHALL be written to a location that is not `data/`.

The two tables SHALL live in one database rather than in a mixture of files and databases. The count of what has been spent has to be transactional against the record of what the money bought, and two stores cannot be made to agree; one store is also one thing to find, to inspect, and to back up. `runtime-store` states what those tables are and how their schema is versioned.

**Route answers and refinements are no longer among them.** Neither is stored at all, so neither has a location.

`data/` holds the pipeline's inputs and its committed deliverables. Writing a growing cache into it mixes runtime state with tracked artefacts, and forces the directory to be mounted writable into a service that only ever reads from it.

Where the pipeline artefacts are mounted into a service at all, they SHALL be mounted read-only. The test runner mounts them not at all.

#### Scenario: One database holds it all

- **WHEN** the application's writable storage is inspected
- **THEN** the autocomplete cache and the monthly request count are tables of one database, and no route answer or refinement is stored anywhere

#### Scenario: The artefacts are not writable by the application

- **WHEN** the web service runs
- **THEN** `data/` is mounted read-only, and the store is written elsewhere

#### Scenario: The test runner has no artefacts to write to

- **WHEN** the test runner runs
- **THEN** `data/` is not mounted into it

## REMOVED Requirements

### Requirement: The cache key is the journey, and nothing else

**Reason**: There is no cached answer and no stored refinement to key. Both tables are removed, so every statement this requirement makes — what the key holds, what it deliberately leaves out, that a rebuilt pipeline reaches a stored journey, that an operator must purge by hand, that the old fingerprinted rows are dropped rather than migrated — is about something that no longer exists.

The requirement's whole subject was the risk it managed: a stale toll total that is indistinguishable from a correct one, which nothing detects. Storing no answer removes the risk rather than managing it. The price is stated in the proposal and in `google-route-refinement`: a repeat journey is routed again, and a repeat refinement is bought again.

**Migration**: Delete the `cache:` volume before the first run of this change. The `routes` and `refinements` tables are not migrated and are not recreated. The operator command that purged the cache after a pipeline rebuild is no longer needed; a rebuilt pipeline reaches the next query with no action taken. `runtime-store` states what remains stored and how its schema is versioned.

### Requirement: The answer keeps the shape its consumers already read

**Reason**: The requirement is kept in full and restated as **The answer keeps the shape its consumers already read, and is computed fresh**, which adds that nothing is stored between queries. Every key, every meaning, and the travel-time correction are unchanged.

It is restated rather than amended because three of its scenarios described a cache hit — that a changed factor reaches a journey already stored, that a hit and a miss are indistinguishable, and that a changed public address reaches a stored journey — and there is no longer a state in which any of them can occur. A scenario whose precondition cannot arise is not a passing test; it is a test that never runs.

**Migration**: None for a consumer. The mapping returned is identical, key for key. What changes is that a second query for the same journey does the routing again, which costs about a second of local work and no money.

### Requirement: The application and the bot are Compose services

**Reason**: The requirement is kept in full and restated as **The application, the bot, and the migration are Compose services**. A sixth service is added, `migrate`, and `web` and `bot` gain a dependency on it; the application image stops taking Python packages from the distribution. Everything else — the router addressing, the matching size, the published port, the two test runners, the profiles — is unchanged.

It is restated rather than amended because two of its scenarios counted the services in their names, "Another capability's service is not one of these four" and "One image, three services", and both counts are now wrong.

**Migration**: Run `docker compose --profile <application> up` as before. The new `migrate` service runs first and exits; a deployment that starts `web` or `bot` directly, without Compose resolving the dependency, will now open a database whose schema has never been applied.
