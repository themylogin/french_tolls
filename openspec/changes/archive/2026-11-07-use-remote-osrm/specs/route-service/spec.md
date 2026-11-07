# Spec Delta

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

**Where `remote-routers` configures an address for a router, `web` and `bot` SHALL address that router there instead of by its service name.** The other router keeps its service name. A published host port of this deployment is still never the path.

**`osrm-toll` SHALL be started with a matching size large enough for a whole trace as `toll-equivalence` sends one.** That capability recovers the booths a foreign route crosses by matching its geometry in one request, and the server's default admits a hundred coordinates where the shortest trace worth matching runs to hundreds. Splitting the trace to fit is not an alternative: a window matched with no knowledge of the road before it produces wrong answers, which is the defect that made this requirement necessary.

The size SHALL be chosen against that measurement rather than set as high as it will go. `toll-equivalence` thins a trace before it sends it, and a size that also admits an unthinned one buys nothing: it lets a fault — a caller that skipped the thinning — reach the router as a request tens of times more expensive and, measured, less accurate. A ceiling that refuses it is the cheaper failure.

`nginx` SHALL reach the application the same way, at its service name over the Compose network, and SHALL be the only one of the six publishing a host port. `web` publishes nothing because the page and the API have to answer on one origin, and that origin is `nginx`.

`tests` SHALL depend on none of them. It SHALL NOT be given the routers' addresses and SHALL NOT mount `data/`, because the suite it runs reaches no routing service and reads no artefact. A test runner carrying a dependency its tests do not use only makes the suite unrunnable on a checkout that has no graphs.

**`integration` SHALL be the opposite, and SHALL be a separate service for exactly that reason.** It SHALL reach the routers as `web` does, by name unless an address is configured, and SHALL mount `data/`, because `drive-flow-integration-tests` drives real routes over real booths.

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

- **WHEN** the web service answers a query and no router address is configured
- **THEN** it reaches `osrm-toll` and `osrm-optimal` over the Compose network

#### Scenario: The application reaches a configured router

- **WHEN** `OSRM_OPTIMAL_URL` is configured and the bot answers a journey
- **THEN** it reaches the optimal graph at that address and `osrm-toll` over the Compose network

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

### Requirement: Configuration is read from the environment

The token, the API keys, the monthly ceiling on paid requests, the travel-time factor, the debug setting, the log level, the address route requests are sent to, the public address of the site, the address of each router, and the router access token SHALL be read from the environment, each with a documented default where a default is meaningful.

Five entries this list carried are gone from it, and none of them was ever configured:

- **The published port** is fixed at 8080 because the front end proxies to it. A variable that changes it takes the site down rather than moving it.
- **The fit threshold** is a measured value, chosen because the corpus leaves an empty band between 97.7% and 99.5%. `google-route-refinement` requires the evaluation and the drive flow to use the same one, and they already do — by reading the same constant, not the same variable.
- **The query budget** bounds how many local routing requests one journey's search may issue. It guards against a search that is looping, and a deployment that reaches it does not want a larger number, so it is a constant with its measurement beside it.
- **The reach** — how far an origin may be from a road — was a setting in one place and a literal in two others, and the bot's reply names a kilometre in prose. A value that three places have to agree on is one value, written once and read by all three.
- **The wage** belongs to `toll-weighted-graph`, which requires it to be settable there. It is a parameter of the pipeline that builds the weighted graph, and no service reads it from the environment.

The count of waypoints a link carries goes the same way: it is nine because a Google Maps URL carries nine, and a variable that raises it makes the search place points the link drops without saying so.

**The routers' addresses are settings again.** They were removed because every deployment reached the routers by service name. A deployment without graphs now reaches another deployment's routers, so the address differs between environments. Each address defaults to the service name. `remote-routers` states the rules for the addresses and the token.

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

#### Scenario: The router addresses default to the service names

- **WHEN** neither router address is configured
- **THEN** the settings hold `http://osrm-toll:5000` and `http://osrm-optimal:5000`

#### Scenario: The access token is a secret

- **WHEN** the router access token is set and a router request fails
- **THEN** neither the failure record nor any log line contains the token

### Requirement: The API serves the page from two routes and no more

The HTTP API SHALL expose place lookup and route calculation, and nothing else for the page.

**Where the router access token is set, the API SHALL also serve the router relay of `remote-routers`.** The relay serves another deployment, not the page. The page never calls it, and without the token it does not exist.

**There SHALL be no endpoint for the refinement.** `google-route-refinement` states why: a refinement describes a particular optimal route, so answering for one separately means computing that route a second time. One question from a visitor SHALL cost one request and one search.

A route query SHALL carry the refinement beside its two routes where the debug setting is on, and SHALL omit the key entirely where it is off. Omission rather than an empty value, so that a caller distinguishes "the operator did not ask for this" from "there was nothing to draw", which is a different fact and is reported inside the key as a reason.

The key SHALL sit beside `fast` and `optimal` rather than inside either. It describes the journey rather than one of its two routes, and nesting it in `optimal` would put it among keys `web-front-end` reads for every route.

Nothing that duplicates a value already in the answer SHALL be carried in it.

#### Scenario: Two routes, and the refinement is not one of them

- **WHEN** the API's routes are enumerated and the router access token is unset
- **THEN** they are place lookup and route calculation, and no path serves a refinement

#### Scenario: The relay is added only by the token

- **WHEN** the API's routes are enumerated and the router access token is set
- **THEN** they are place lookup, route calculation, and the relay under `/api/osrm/toll/` and `/api/osrm/optimal/`, and no path serves a refinement

#### Scenario: The refinement travels with the answer

- **WHEN** a journey is calculated with the debug setting on
- **THEN** the answer carries `fast`, `optimal`, and the refinement beside them

#### Scenario: The key is absent rather than empty

- **WHEN** a journey is calculated with the debug setting off
- **THEN** the answer carries `fast` and `optimal` and no refinement key at all

#### Scenario: A caller posting to the old path is not served

- **WHEN** a request is made to the refinement's former path
- **THEN** the API does not serve it
