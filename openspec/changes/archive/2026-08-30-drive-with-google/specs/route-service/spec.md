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
- `google_url` — a directions link from the route's own origin through its waypoints.

`duration` SHALL be the router's travel time multiplied by a configured factor. The router's clock runs slow: measured over 2 257 journeys against Google's, it predicts about 7% more travel time than Google does for the same road.

`duration_osrm` SHALL carry the uncorrected number, because the factor is measured by comparing the two clocks and comparing against the corrected one would make the next measurement come out at 1.0 by construction.

The correction SHALL be applied each time an answer is returned and SHALL NOT be read from the cache. A multiplier is a setting rather than a property of a journey, and an answer stored with it applied would keep the old factor until it was evicted. Changing the factor SHALL reach a journey already cached, without the cache being purged.

**The three service-addressed link keys are gone.** `url`, `url_from_current_location` and `url_from_current_location_through_start` are no longer returned. They addressed this service so that following one refined the waypoints before redirecting; the bot now refines when a driver asks to drive, and the page draws the refinement directly, so nothing followed them.

`google_url` remains and SHALL continue to be built from the route's own geometry and stored with the answer. It is a direct address, derivable from nothing but the route, for a consumer that would rather not depend on this service being reachable.

A caller SHALL NOT be able to tell whether an answer came from the cache. `duration` carries the same corrected number either way.

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

#### Scenario: A changed factor reaches a cached journey

- **WHEN** the factor is changed and a journey already in the cache is answered
- **THEN** its `duration` reflects the new factor, without the cache being purged

#### Scenario: The page's keys are all present

- **WHEN** the page renders an answer
- **THEN** every key `web-front-end` records it as reading is present on both routes

#### Scenario: A cache hit and a miss are indistinguishable

- **WHEN** the same journey is answered twice, the second time from the cache
- **THEN** `duration` is the same both times

#### Scenario: A changed public address reaches a cached journey

- **WHEN** `PUBLIC_SITE_URL` is changed and a journey already in the cache is answered
- **THEN** the answer is unaffected, because nothing in it is built from that address any more, and the cache needs no purge

#### Scenario: A passage carries a name and a cost

- **WHEN** a route's `peages` are read
- **THEN** each entry carries `name` and `cost`, in the order the route drives them

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

The token, the API keys, the published port, the wage, the query budget, the reach, the monthly ceiling on paid requests, the travel-time factor, the fit threshold, the debug setting, the public address of the site, and the routers' addresses SHALL be read from the environment, each with a documented default where a default is meaningful.

`PUBLIC_SITE_URL` SHALL be required. The service SHALL fail to start, naming it, when it is unset or empty. It is the address the bot's comparison-map link is built from, and a bot that does not know it would write a link to nowhere. Starting anyway would mean sending a message whose only link is broken.

Every service that answers a route query SHALL receive it — the web application and the bot alike. The travel-time factor SHALL reach both for the same reason: a bot quoting one duration and the page another for the same journey is the same fault in a different key.

**Every service that asks Google SHALL receive the key, the monthly ceiling and the fit threshold.** The bot did not need them while it wrote links that came back through the web application to be refined; it asks directly now, and a service missing them reads its ceiling as zero and tells every driver its link was never checked — which is indistinguishable, from outside, from a month whose budget really is spent.

The travel-time factor SHALL default to 1, which serves the router's own time unchanged.

The debug setting SHALL default to off. It causes paid requests on every page load, and a deployment that has not asked for that SHALL NOT get it.

The Google key and the monthly ceiling SHALL be optional. Without them the service answers every journey unrefined rather than failing to start. `.env.example` SHALL document every one.

A secret SHALL NOT be committed and SHALL NOT appear in a failure record or a log line.

#### Scenario: Every variable is documented

- **WHEN** `.env.example` is read
- **THEN** it names the Telegram token, the LocationIQ key, the Google key, the monthly ceiling, the travel-time factor, the fit threshold, the debug setting, the public address, and the published port

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

- **WHEN** `PUBLIC_SITE_URL` is unset or empty
- **THEN** the service exits at start-up naming it

#### Scenario: The bot and the web application agree

- **WHEN** the same journey is answered by the bot and by the web application
- **THEN** both quote the same duration

#### Scenario: Every service that asks Google can

- **WHEN** a service that makes Google requests starts
- **THEN** it has the key, a monthly ceiling above zero where one is configured, and the fit threshold

#### Scenario: A missing ceiling is not mistaken for a spent one

- **WHEN** a service configured with a Google key reports that a link was not checked
- **THEN** it is because the month's requests are actually spent, not because the ceiling never reached it
