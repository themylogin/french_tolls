## MODIFIED Requirements

### Requirement: Google is asked for the route the driver will be given

For a journey whose optimal route and waypoints have been computed, the system SHALL ask Google for a driving route between the same two points through exactly those waypoints, in that order.

**The request SHALL ask at the highest routing quality: `travelMode: DRIVE`, `routingPreference: TRAFFIC_AWARE_OPTIMAL`**, no traffic model, no departure time, no alternative routes, no waypoint reordering, and tolls not avoided.

The cheaper search was used for a time, on the measurement that the higher quality was worth **0.8 points** of faithfulness against the waypoints the search now produces. That measurement is correct and it is in the wrong units. It counts length outside a corridor, and what a driver pays does not vary with length.

At `TRAFFIC_UNAWARE` the search returns routes that leave a motorway at a junction and rejoin it shortly after. Measured on one journey: a **sixteen-kilometre excursion to advance nine hundred metres**, crossing two barriers our route does not, which breaks one long ticket into two short ones. That is three per cent of a four-hundred-kilometre route's length, and it is the whole of the difference between a link `toll-equivalence` accepts and one it corrects and splits.

The manoeuvre appeared on four separate motorways and operators in the recorded set. At `TRAFFIC_AWARE_OPTIMAL` every one of those four journeys came back crossing **exactly** our booth set, for the same total to the cent, on a route that was both shorter and faster. The one journey that genuinely takes a dearer road stayed refused under both settings, so the higher quality removes the artefacts without papering over real disagreement.

The system SHALL accept, as the price of this:

- **The Pro tier**, whose free allowance is 5 000 requests a month rather than the 10 000 of Essentials. Fewer requests are made: over eleven journeys driven to their end the count fell from 37 to 24, because a route that is accepted costs no correcting ask and no split.
- **A route that moves with traffic.** The first ask of a journey — made with the fewest waypoints — varies most: one measured journey returned 91.0% of our road at the cheaper setting and 10.9% at the higher one. Corrected asks converge regardless, so the outcome is stable where the geometry is not.

The system SHALL NOT carry a departure time. It is the one part of the request that would be computed rather than fixed, and a stale one asks about a journey nobody is taking. This is what keeps the request free of any local hour or calendar date.

The evaluation SHALL NOT follow. `google-route-comparison` buys routes to compare Google's duration against OSRM's, and `TRAFFIC_UNAWARE` is the only setting under which those two durations answer the same question. It builds its own request and keeps it.

Intermediate waypoints SHALL be sent as stopovers rather than as pass-through points. A Google Maps directions URL cannot express a pass-through waypoint, so a request that used one would measure a route the link cannot produce. Measured: re-asking one request with every intermediate marked pass-through returned the identical route, two seconds apart. Pass-through waypoints are not an alternative to this requirement.

The system SHALL request only the fields it uses: the route's geometry, its distance, and its duration.

#### Scenario: The request asks at the highest routing quality

- **WHEN** a refinement request is built
- **THEN** it sets `TRAFFIC_AWARE_OPTIMAL`, because the cheaper search invents junction manoeuvres that change what a driver pays

#### Scenario: A phantom exit and re-entry is not bought

- **WHEN** a journey is asked about whose cheaper answer left a motorway and rejoined it a few hundred metres later
- **THEN** the answer crosses the booths the optimal route crosses and no others

#### Scenario: The path does not move with traffic

- **WHEN** the same journey is asked about under different traffic conditions
- **THEN** it no longer holds: the route returned may differ, and this is accepted, because what a caller decides rests on the booths it crosses and the corrected ask settles those either way

#### Scenario: The departure time is computed rather than fixed

- **WHEN** a request is built at any moment
- **THEN** it carries no departure time, so there is none to compute and none to go stale

#### Scenario: The slot survives a summer time change

- **WHEN** a request is built on a date in winter and one in summer
- **THEN** both name no local hour, because neither carries a departure time

#### Scenario: The evaluation does not follow

- **WHEN** the evaluation builds its own Google request
- **THEN** it asks at `TRAFFIC_UNAWARE`, because it compares durations against OSRM's empty road and this one does not

#### Scenario: Two requests a month apart are comparable

- **WHEN** the same journey is asked about on different days
- **THEN** it no longer holds: the routes may differ with traffic, and a caller that needs two comparable answers asks the evaluation, which still holds the road empty

#### Scenario: Waypoints are sent as stopovers

- **WHEN** the intermediates of a request are read
- **THEN** none is marked as a pass-through point, because a directions URL cannot carry one

#### Scenario: The waypoints asked about are the ones computed

- **WHEN** the optimal route carries seven waypoints
- **THEN** Google is asked to drive through those seven, in that order
