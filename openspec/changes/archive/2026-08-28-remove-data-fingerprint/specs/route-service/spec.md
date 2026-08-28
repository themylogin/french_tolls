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

## REMOVED Requirements

### Requirement: The cache key names everything the answer depends on

**Reason**: Its name and every one of its scenarios assert automatic invalidation, which is precisely what this change removes. Kept as a MODIFIED block it would have carried a scenario named "A repriced pipeline invalidates the cache" whose outcome is now the opposite of its name.

**Migration**: Replaced by "The cache key is the journey, and nothing else" below, which states the reduced key, the manual purge that now follows a pipeline run, and what happens to rows written under the old key. The one behaviour that survives unchanged — an unchanged pipeline keeps the cache — is restated there.

## ADDED Requirements

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
