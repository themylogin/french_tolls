# route-service Specification

## Purpose
Defines the answer a route query returns, how that answer is cached and when the cache stops being valid, how failures are reported, and how the web application and the Telegram bot are packaged and run beside the two routing services.

## Requirements

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

### Requirement: The answer says how faithful the link is

Each route SHALL additionally carry:

- `waypoints` — the intermediate waypoints in the link, as `[longitude, latitude]` pairs;
- `waypoints_needed` — how many the optimal route needed, which may exceed the number carried;
- `complete` — false when the link does not reproduce the optimal route in full;
- `unpriced` — how many of the route's passages could not be priced.

A passage that could not be priced SHALL carry `reason` and SHALL NOT carry a `cost` of zero.

The fast route needs no waypoints, since it is by definition what a fastest-path router computes. It SHALL carry `waypoints` as an empty list and `complete` as true.

#### Scenario: An incomplete link is marked

- **WHEN** the optimal route needs eleven waypoints
- **THEN** `waypoints` holds nine, `waypoints_needed` is 11, and `complete` is false

#### Scenario: The fast route carries no waypoints

- **WHEN** the fast route is answered
- **THEN** its `waypoints` is empty and its `complete` is true

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

### Requirement: The bot's behaviour is unchanged

The bot's **route calculation** SHALL keep the behaviour it has: the same commands, the same two-message origin-and-destination exchange, and the same reach check before a location is accepted.

What it **sends** for a calculated journey is no longer unchanged, and is specified by `telegram-drive-flow`. The three directions links leave the message; an action to drive replaces them.

The functions it imports SHALL keep their names and signatures.

#### Scenario: The reach check still exists

- **WHEN** the bot receives a location further than the reach from any road
- **THEN** it replies that the location is not within a kilometre of any road in France, as it does today

#### Scenario: The exchange is unchanged

- **WHEN** a driver sends an origin and then a destination
- **THEN** the bot asks for each in turn exactly as it does today, and calculates on the second

### Requirement: Configuration is read from the environment

The token, the API keys, the monthly ceiling on paid requests, the travel-time factor, the debug setting, the log level, the address route requests are sent to, and the public address of the site SHALL be read from the environment, each with a documented default where a default is meaningful.

Six entries this list carried are gone from it, and none of them was ever configured:

- **The published port** is fixed at 8080 because the front end proxies to it. A variable that changes it takes the site down rather than moving it.
- **The routers' addresses** are Compose service names on one network. The published host ports refuse connections, which this capability already requires nothing to use.
- **The fit threshold** is a measured value, chosen because the corpus leaves an empty band between 97.7% and 99.5%. `google-route-refinement` requires the evaluation and the drive flow to use the same one, and they already do — by reading the same constant, not the same variable.
- **The query budget** bounds how many local routing requests one journey's search may issue. It guards against a search that is looping, and a deployment that reaches it does not want a larger number, so it is a constant with its measurement beside it.
- **The reach** — how far an origin may be from a road — was a setting in one place and a literal in two others, and the bot's reply names a kilometre in prose. A value that three places have to agree on is one value, written once and read by all three.
- **The wage** belongs to `toll-weighted-graph`, which requires it to be settable there. It is a parameter of the pipeline that builds the weighted graph, and no service reads it from the environment.

The count of waypoints a link carries goes the same way: it is nine because a Google Maps URL carries nine, and a variable that raises it makes the search place points the link drops without saying so.

**They SHALL be declared in one place, and nothing else in the application package SHALL read the environment.** Each setting SHALL carry its name, its type, its default, and a sentence saying what it is for. A caller SHALL obtain a value by asking that one object, and SHALL receive it already of the type it is used at — a count as an integer, a distance as a number, a switch as a boolean.

The reason is not tidiness. `.env.example` is required below to document every setting, and while the settings were spread across nine modules the only way to enumerate them was to search the source for environment reads. Writing the list down for the first time found that **twelve of the twenty-one had never been configured in any environment** — container paths fixed by their mounts, a port fixed by what proxies to it, service names on a single network, two timeouts, a guard against a looping search, and values that were measured rather than chosen. A list that exists can be checked; prose about a list cannot.

**A value that several places must agree on SHALL be written once.** The reach is the example: the router enforced it, the bot compared against its own copy, and the reply text named it in prose. Two of the three ignored the setting entirely, so changing it moved one behaviour and left the other two contradicting it.

**A value nothing configures SHALL NOT be a setting.** Where every environment gives the same answer — because a container path is fixed by the mount, or a port by what proxies to it — the value SHALL be written where it is used, with a note saying who fixes it. An environment read that has never returned a value is worse than no read at all: it invites an operator to set it and to wonder why nothing moved, or why something broke.

**A value that cannot be read as its type SHALL fail at start-up rather than later.** A count or a factor set to something that is not a number SHALL stop the service, naming the value. `int` and `float` do this on their own; nothing SHALL wrap them to say it differently, because a layer of parsing exists only to reword an error that was already clear.

**An empty value SHALL count as unset.** Compose passes several of these as `${VAR:-}`, so a variable nobody set arrives as the empty string rather than absent, and a setting that read it directly would try to make a number of `""`.

A switch SHALL read the words an operator would write: `1`, `true`, `yes` and `on` are on, in any casing, and everything else is off. It SHALL NOT be on because its value was spelled in capitals, which is what `not in ("", "0", "false", "False")` did to `FALSE` and to `no`.

`URL` SHALL be required. The service SHALL fail to start, naming it, when it is unset or empty. It is the address the bot's comparison-map link is built from, and a bot that does not know it would write a link to nowhere. Starting anyway would mean sending a message whose only link is broken.

**Nothing in the declaration SHALL make a value mandatory.** A field holds what the environment gave it, or its default, and reading one never fails for want of another. That is what lets the unit suite import the routing client, the booth loader and the refinement with no environment at all, as it is specified to.

A service that cannot run without a value SHALL refuse to start, itself, naming the variable. It SHALL do so at its entry point rather than when some module it happens to import is loaded: `URL` used to stop the process from the body of a module, which is why a test could not import that module at all.

Every service that answers a route query SHALL receive it — the web application and the bot alike. The travel-time factor SHALL reach both for the same reason: a bot quoting one duration and the page another for the same journey is the same fault in a different key.

**Every service that asks Google SHALL receive the key and the monthly ceiling.** The bot did not need them while it wrote links that came back through the web application to be refined; it asks directly now, and a service missing them reads its ceiling as zero and tells every driver its link was never checked — which is indistinguishable, from outside, from a month whose budget really is spent.

The travel-time factor SHALL default to 1, which serves the router's own time unchanged.

The debug setting SHALL default to off. It causes paid requests on every page load, and a deployment that has not asked for that SHALL NOT get it.

The Google key and the monthly ceiling SHALL be optional. Without them the service answers every journey unrefined rather than failing to start. `.env.example` SHALL document every one.

A secret SHALL NOT be committed and SHALL NOT appear in a failure record or a log line.

#### Scenario: Every variable is documented

- **WHEN** `.env.example` is read
- **THEN** it names every setting the application reads

#### Scenario: The reach is one value

- **WHEN** a location further from the road than the reach is sent
- **THEN** the router's limit, the check that rejects it, and the words the driver reads all come from one constant

#### Scenario: A knob that turns nothing is not offered

- **WHEN** a value is the same in every environment the application runs in
- **THEN** it is a constant where it is used, and no environment variable names it

#### Scenario: The settings are declared in one place

- **WHEN** the application package is searched for environment reads
- **THEN** the only one is the module that declares the settings

#### Scenario: A setting arrives already typed

- **WHEN** a caller reads the monthly ceiling, the travel-time factor, and the debug setting
- **THEN** it receives an integer, a number, and a boolean, and does not convert anything

#### Scenario: A value that cannot be read stops the service

- **WHEN** a count or a factor is set to something that is not a number
- **THEN** start-up fails, naming the value, and no layer of parsing has reworded it

#### Scenario: An empty value is an unset one

- **WHEN** a variable is passed through as the empty string
- **THEN** the setting holds its default rather than trying to read `""` as a number

#### Scenario: A switch spelled in capitals is still off

- **WHEN** the debug setting is `FALSE`, `No`, `off`, or anything that is not one of the words for on
- **THEN** it is off

#### Scenario: Importing does not require configuring

- **WHEN** the routing client, the booth loader and the refinement are imported with an empty environment
- **THEN** every import succeeds, and each setting holds its default

#### Scenario: The debug setting is off unless asked for

- **WHEN** no debug setting is configured
- **THEN** the page draws no overlay and makes no Google request on load

#### Scenario: The travel-time factor defaults to serving the router's own time

- **WHEN** no factor is configured
- **THEN** `duration` equals `duration_osrm` on every route

#### Scenario: The service runs without a Google key

- **WHEN** no Google key is configured
- **THEN** the service starts and answers every journey with unrefined waypoints

#### Scenario: The service refuses to run without a public address

- **WHEN** `URL` is unset or empty
- **THEN** the service exits at start-up naming it, from its own entry point rather than from a module it imported

#### Scenario: The bot and the web application agree

- **WHEN** the same journey is answered by the bot and by the web application
- **THEN** both quote the same duration

#### Scenario: Every service that asks Google can

- **WHEN** a service that makes Google requests starts
- **THEN** it has the key and a monthly ceiling above zero where one is configured; the fit threshold travels with the code and cannot be missing

#### Scenario: A missing ceiling is not mistaken for a spent one

- **WHEN** a service configured with a Google key reports that a link was not checked
- **THEN** it is because the month's requests are actually spent, not because the ceiling never reached it

### Requirement: The API serves the page from two routes and no more

The HTTP API SHALL expose place lookup and route calculation, and nothing else.

**There SHALL be no endpoint for the refinement.** `google-route-refinement` states why: a refinement describes a particular optimal route, so answering for one separately means computing that route a second time. One question from a visitor SHALL cost one request and one search.

A route query SHALL carry the refinement beside its two routes where the debug setting is on, and SHALL omit the key entirely where it is off. Omission rather than an empty value, so that a caller distinguishes "the operator did not ask for this" from "there was nothing to draw", which is a different fact and is reported inside the key as a reason.

The key SHALL sit beside `fast` and `optimal` rather than inside either. It describes the journey rather than one of its two routes, and nesting it in `optimal` would put it among keys `web-front-end` reads for every route.

Nothing that duplicates a value already in the answer SHALL be carried in it.

#### Scenario: Two routes, and the refinement is not one of them

- **WHEN** the API's routes are enumerated
- **THEN** they are place lookup and route calculation, and no path serves a refinement

#### Scenario: The refinement travels with the answer

- **WHEN** a journey is calculated with the debug setting on
- **THEN** the answer carries `fast`, `optimal`, and the refinement beside them

#### Scenario: The key is absent rather than empty

- **WHEN** a journey is calculated with the debug setting off
- **THEN** the answer carries `fast` and `optimal` and no refinement key at all

#### Scenario: A caller posting to the old path is not served

- **WHEN** a request is made to the refinement's former path
- **THEN** the API does not serve it

### Requirement: A router request carries its own connection

A request to either routing graph SHALL open its own connection and SHALL NOT reuse one from an earlier request.

Sharing a pool across a search was measured and bought nothing: on the dearest journey — 327 requests — a connection per request came out 17% faster on one run and 1% slower on the next, with both arms interleaved in one process. The routers answer in 2 to 11 ms on the same host, so the handshakes disappear into the routing itself.

What the pool did cost was a failure mode. The server closes an idle pooled connection, and the next request over it fails for a reason that has nothing to do with the question asked. Retrying that failure — distinguishing it from a router that is genuinely down, and not counting the retry against the query budget — was the whole of the complication, and it existed only to repair what the pooling broke.

**A connection error SHALL therefore be reported as the router being unavailable on the first failure**, as every other client error already is. There SHALL be no retry.

The request timeout SHALL still apply, per request. It is the point at which something is wrong rather than slow, and that is a property of a request rather than of a session.

The query budget SHALL be unchanged in meaning and in value. It bounds the questions a search asks, and it SHALL NOT be spent on a retry, because there is none.

#### Scenario: Nothing is reused between requests

- **WHEN** a search issues several hundred router requests
- **THEN** each opens its own connection, and none is reused from a previous request

#### Scenario: A dropped connection is not retried

- **WHEN** a router request fails to connect
- **THEN** the query fails with the router reported unavailable, without a second attempt

#### Scenario: One failure counts once

- **WHEN** a router request fails to connect
- **THEN** exactly one request has been counted against the query budget

#### Scenario: A slow router still times out

- **WHEN** a router does not answer within the timeout
- **THEN** the request fails with the router reported unavailable

#### Scenario: The budget still bounds the search

- **WHEN** a search reaches the query budget
- **THEN** it stops, as it did before, and the budget's value is unchanged

### Requirement: The answer may carry a route that splits a ticket

A route query MAY return a third route under the key `super_optimal`, beside `fast` and `optimal`. It SHALL be present only when splitting a ticket somewhere on the optimal route beats the configured threshold, and absent otherwise.

`super_optimal` SHALL carry every key a route carries, with the same meanings, so that a consumer reading `distance`, `duration`, `nodes`, `peages` and `cost` needs no new handling. It SHALL additionally carry:

- `stops` — the junctions at which the driver leaves and immediately re-enters the tolled road, in driven order, each with the gare name and its position;
- `extra_duration` — seconds, the driving time it adds over `optimal`, including booth time;
- `saving` — euros, `optimal.cost` minus `super_optimal.cost`.

Its absence SHALL NOT be an error and SHALL NOT be explained. A route with nothing to save is the ordinary case.

#### Scenario: A route with nothing to save

- **WHEN** no section of the optimal route has a split above the threshold
- **THEN** the answer carries `fast` and `optimal` and no `super_optimal`

#### Scenario: A route with something to save

- **WHEN** some section has a split above the threshold
- **THEN** the answer carries `super_optimal`, whose `cost` is lower than `optimal`'s and whose `duration` is higher

#### Scenario: The third route reads like the others

- **WHEN** `super_optimal` is present
- **THEN** it carries `distance`, `duration`, `duration_osrm`, `nodes`, `peages`, `cost` and `google_url`, with the meanings those keys have on `optimal`

### Requirement: The split route is routed and priced, not asserted

`super_optimal` SHALL be produced by routing the journey through the stored booth nodes and pricing the geometry that comes back, using the same accounting that prices every other route.

The advice file names OSM booth nodes. The service SHALL resolve them to positions through the booth inventory it already loads, and SHALL route the journey through them on the toll-weighted graph, so that the road between two stops is chosen exactly as it is for `optimal`.

The price SHALL come from walking the returned geometry and pairing each entrance with the exit that follows it. It SHALL NOT be computed by subtracting the advice file's figures from the direct fare: the file says where stopping is worthwhile, and the route that comes back is what the driver would actually pay.

When the routed geometry does not cross the stops it was built from, the split SHALL NOT be offered. A route that missed a stop was not the journey the saving was computed for.

#### Scenario: The offered route is priced from its own geometry

- **WHEN** `super_optimal` is returned
- **THEN** its `cost` is the sum of its own `peages`, each of which came from pairing an entrance with the following exit on its geometry

#### Scenario: The re-route missed a stop

- **WHEN** routing through the stops returns a geometry that does not cross one of them
- **THEN** no `super_optimal` is returned

### Requirement: A split is offered at the rate the graph was weighted with

The threshold above which a split is offered SHALL be what a driver's hour is worth, read from the one setting that also weights the toll-weighted graph.

That graph carries `weight = osm_weight + price / wage * 3600`, which is what makes the router accept a detour whose toll saving beats the minutes it costs. Offering a stop asks the identical question about a different kind of detour. Two separate values would offer a driver a trade the router had already rejected as bad, or withhold one it would have taken, and nothing in the answer would show why.

It SHALL be applied per closed section of the optimal route, so a journey crossing several sections takes the splits that are worth it and leaves the ones that are not.

#### Scenario: The rate is the one the graph was built with

- **WHEN** a split is judged
- **THEN** the euros-per-hour it must clear is the same value step 10 passed as the wage

#### Scenario: Raising the rate withdraws the marginal offers

- **WHEN** the setting is raised above what a section's best split earns per hour
- **THEN** that section is no longer offered a split

#### Scenario: Sections are judged separately

- **WHEN** a route crosses two closed sections and only one has a split above the threshold
- **THEN** `super_optimal` stops only in that section

### Requirement: A split route's directions link carries its stops, or is withheld

`super_optimal` SHALL carry a `google_url` that drives the split journey, built from the optimal route's own waypoints together with a waypoint at each stop, in driven order. Where those do not fit the waypoint allowance a Maps URL takes, `google_url` SHALL be null.

Both sets are needed and neither is optional. The optimal route's waypoints are what make a fastest-path router follow the same road; a waypoint at each stop is what makes it leave the motorway and rejoin, which no shortest path does on its own. A link carrying only the first would drive the road without the manoeuvre — the ordinary route, at the ordinary price, presented as the cheap one.

Null is the honest answer when they do not fit. A consumer SHALL treat it as "no link", not as an error.

#### Scenario: The link drives the stops

- **WHEN** a split route with one stop is returned and the optimal route needed four waypoints
- **THEN** its `google_url` carries five waypoints, the stop among them

#### Scenario: The allowance is already spent

- **WHEN** the optimal route's waypoints plus the stops exceed what a Maps URL takes
- **THEN** `google_url` is null and no other key of the route changes

### Requirement: The advice file is one of the artefacts the service requires

`data/cost-cutting.yaml` SHALL be read at start-up and its absence SHALL stop the service, naming the file, exactly as a missing price file does.

It is not a mode. Step 12 runs in every build and the file is carried in the repository, so a tree without it has lost an artefact rather than opted out. Treating the absence as "no split is available anywhere" would answer every journey as though the tariff were additive, and nothing in the answer would distinguish that from a road where splitting genuinely saves nothing.

#### Scenario: A missing advice file

- **WHEN** `data/cost-cutting.yaml` is not mounted
- **THEN** the service exits at start-up naming that file, rather than serving

#### Scenario: An unparseable advice file

- **WHEN** `data/cost-cutting.yaml` is present but not valid YAML
- **THEN** the service exits at start-up naming that file
