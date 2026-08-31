## MODIFIED Requirements

### Requirement: The answer keeps the shape its consumers already read

A route query SHALL return a mapping with the keys `fast` and `optimal`, each holding one route.

Each route SHALL carry, with the meanings they have today:

- `distance` — metres;
- `duration` — seconds, the travel time this service stands behind;
- `duration_osrm` — seconds, the router's own travel time before correction;
- `nodes` — the route's coordinates in order, as `[longitude, latitude]` pairs;
- `peages` — the passages in driven order, each a mapping with `name` and `cost`;
- `cost` — euros, the sum of the priced passages;
- `url` — a directions link from the route's own origin;
- `url_from_current_location` — the same link with `Current Location` as the origin;
- `url_from_current_location_through_start` — the same, with the route's origin kept as the first waypoint.

`duration` SHALL be the router's travel time multiplied by a configured factor. The router's clock runs slow: measured over 2 257 journeys against Google's, it predicts about 7% more travel time than Google does for the same road. Serving that unadjusted told every driver the trip was longer than it is. `duration` keeps its name and its unit because every consumer reads it to answer the same question — how long the journey takes — and that answer is now a better one.

`duration_osrm` SHALL carry the uncorrected number. The factor is measured by comparing the router's clock with Google's, so anything that measures it SHALL read this key; comparing against the corrected number would make the next measurement come out at 1.0 by construction.

The correction SHALL be applied each time an answer is returned and SHALL NOT be read from the cache, exactly as the three links are and for the same reason: a multiplier is a setting rather than a property of a journey, and an answer stored with it applied would keep the old factor until it was evicted. Changing the factor SHALL reach a journey already cached, without the cache being purged.

Those three links SHALL address this service rather than Google, in every case and with no fallback. Following one refines the waypoints where budget allows and redirects to Google Maps, so a link that was sent before the refinement was bought still arrives at the refined route. They remain links to a driving route from the named origin to the named destination, which is what every consumer reads them for; only the host changes.

The three SHALL be computed from the origin and the destination each time an answer is returned, and SHALL NOT be read from the cache. They are a function of the two coordinates and the service's public address, and the coordinates are the cache key itself; storing them would put the public address into what is cached and make a configuration change serve links to an address that is no longer the service's.

A caller SHALL NOT be able to tell whether an answer came from the cache. The three keys carry the same absolute addresses either way, and `duration` carries the same corrected number either way.

The direct Google link SHALL be returned as well, under its own key, for a consumer that would rather not depend on this service being reachable. Unlike the three, it is built from the route's own geometry rather than from the endpoints, so it is not derivable from the cache key and SHALL be stored with the answer.

New information SHALL be added as new keys and SHALL NOT change the meaning of an existing one. The Telegram bot and the page under `www/` read this mapping, and `web-front-end` records exactly which of these keys the page reads. A renamed or repurposed key breaks one or both of them.

The entry point SHALL keep its present signature: it takes an origin and a destination, each a `[longitude, latitude]` pair, and returns this mapping.

#### Scenario: An existing consumer still works

- **WHEN** the bot formats an answer
- **THEN** it reads `duration`, `cost`, `distance`, and the three link keys from `optimal` and `fast`, and each holds what it held before

#### Scenario: The travel time served is corrected

- **WHEN** a route is answered
- **THEN** its `duration` is `duration_osrm` multiplied by the configured factor, on both `fast` and `optimal`

#### Scenario: The uncorrected time is still available

- **WHEN** something measures the router's clock against Google's
- **THEN** it reads `duration_osrm`, which the correction has not been applied to

#### Scenario: A changed factor reaches a cached journey

- **WHEN** the factor is changed and a journey already in the cache is answered
- **THEN** its `duration` reflects the new factor, without the cache being purged

#### Scenario: The page's keys are all present

- **WHEN** the page renders an answer
- **THEN** every key `web-front-end` records it as reading is present on both routes

#### Scenario: The links address this service

- **WHEN** the three link keys are read
- **THEN** each addresses this service, and following one redirects to Google Maps

#### Scenario: A cache hit and a miss are indistinguishable

- **WHEN** the same journey is answered twice, the second time from the cache
- **THEN** the three link keys carry the same absolute addresses both times, and `duration` is the same both times

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

The token, the API keys, the published port, the wage, the query budget, the reach, the monthly ceiling on paid requests, the travel-time factor, the public address of the site, and the routers' addresses SHALL be read from the environment, each with a documented default where a default is meaningful.

`PUBLIC_SITE_URL` SHALL be required. The service SHALL fail to start, naming it, when it is unset or empty. The three link keys address this service, and a service that does not know its own address cannot produce them; starting anyway would mean answering with links of a different shape, which is a silent change to a contract two consumers read.

Every service that answers a route query SHALL receive it — the web application and the bot alike. A deployment that gave it to one and not the other made the same three keys mean different things to the page and to Telegram, and nothing reported the difference. The travel-time factor SHALL reach both for the same reason: a bot quoting one duration and the page another for the same journey is the same fault in a different key.

The travel-time factor SHALL default to 1, which serves the router's own time unchanged. It is a correction measured against an external service, so a deployment that has not measured it SHALL NOT be given one by default.

The Google key and the monthly ceiling SHALL be optional. Without them the service answers every journey unrefined rather than failing to start: refinement is an improvement to a link, not a condition of producing one. `.env.example` SHALL document every one.

A secret SHALL NOT be committed and SHALL NOT appear in a failure record or a log line.

#### Scenario: Every variable is documented

- **WHEN** `.env.example` is read
- **THEN** it names the Telegram token, the LocationIQ key, the Google key, the monthly ceiling, the travel-time factor, the public address, and the published port of the web application, alongside the variables the pipeline already documents

#### Scenario: The travel-time factor defaults to serving the router's own time

- **WHEN** no factor is configured
- **THEN** `duration` equals `duration_osrm` on every route

#### Scenario: The service runs without a Google key

- **WHEN** no Google key is configured
- **THEN** the service starts and answers every journey with unrefined waypoints

#### Scenario: The service refuses to run without a public address

- **WHEN** `PUBLIC_SITE_URL` is unset or empty
- **THEN** the service exits at start-up naming it, rather than serving links of another shape

#### Scenario: The bot and the web application agree

- **WHEN** the same journey is answered by the bot and by the web application
- **THEN** both carry the same three links, each addressing this service, and both quote the same duration
