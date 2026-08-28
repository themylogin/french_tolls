## MODIFIED Requirements

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

Those three SHALL address this service rather than Google. Following one refines the waypoints where budget allows and redirects to Google Maps, so a link that was sent before the refinement was bought still arrives at the refined route. They remain links to a driving route from the named origin to the named destination, which is what every consumer reads them for; only the host changes.

The direct Google link SHALL be returned as well, under its own key, for a consumer that would rather not depend on this service being reachable.

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

#### Scenario: The direct link is still available

- **WHEN** the answer is read
- **THEN** it carries the unrefined Google Maps link under its own key

#### Scenario: A passage carries a name and a cost

- **WHEN** a route's `peages` are read
- **THEN** each entry carries `name` and `cost`, in the order the route drives them

### Requirement: The cache key names everything the answer depends on

A cached answer SHALL be keyed by the origin, the destination, and a **data fingerprint**.

The same key SHALL govern a stored refinement. A refinement describes a particular optimal route, so it is stale exactly when that route is.

The fingerprint SHALL be computed at start-up from the content of every input the answer depends on: the four pipeline artefacts this service reads, and `data/segment_weights.csv`, which is what makes the toll-weighted graph differ from the untouched one.

Keying on the coordinate pair alone means a rebuilt price file never reaches a cached journey, and there is nothing in the cache to tell a stale answer from a current one. Every cached answer this service has ever written was computed against a booth model that no longer exists.

An answer written under one fingerprint SHALL never be returned under another. The service SHALL NOT need a manual cache purge after a pipeline run.

#### Scenario: A refinement is invalidated with the route it describes

- **WHEN** the fingerprint changes
- **THEN** neither the cached answer nor the stored refinement for a journey is used

#### Scenario: A repriced pipeline invalidates the cache

- **WHEN** `data/vinci_price.yaml` is rebuilt and the service restarts
- **THEN** a journey answered before the rebuild is computed again rather than read from the cache

#### Scenario: An unchanged pipeline keeps the cache

- **WHEN** the service restarts with the artefacts unchanged
- **THEN** a journey answered before the restart is read from the cache

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

### Requirement: Configuration is read from the environment

The token, the API keys, the published port, the wage, the query budget, the reach, the monthly ceiling on paid requests, the public address of the site, and the routers' addresses SHALL be read from the environment, each with a documented default where a default is meaningful.

The Google key and the monthly ceiling SHALL be optional. Without them the service answers every journey unrefined rather than failing to start: refinement is an improvement to a link, not a condition of producing one. `.env.example` SHALL document every one.

A secret SHALL NOT be committed and SHALL NOT appear in a failure record or a log line.

#### Scenario: Every variable is documented

- **WHEN** `.env.example` is read
- **THEN** it names the Telegram token, the LocationIQ key, the Google key, the monthly ceiling, the public address, and the published port of the web application, alongside the variables the pipeline already documents

#### Scenario: The service runs without a Google key

- **WHEN** no Google key is configured
- **THEN** the service starts and answers every journey with unrefined waypoints
