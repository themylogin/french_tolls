## REMOVED Requirements

### Requirement: Google is asked what it would actually drive

**Reason**: Its normative core — that the request SHALL describe an empty road at `TRAFFIC_UNAWARE` with no departure time — asked Google a question whose answer no driver ever receives. A link opens Google Maps, which routes at its highest search quality; the request asked at its lowest. On Cluses to Mont-de-Marsan the two disagree by 143 km and by 37 points of faithfulness, and the road the requirement bought was not the road the link produced.

**Migration**: Replaced by "Google is asked for the route the driver will be given" below, which keeps the waypoint-order and requested-fields obligations word for word and restates only the terms of the request. `google-route-comparison` does not follow and is unchanged: it keeps `TRAFFIC_UNAWARE` for its own stated reason, which is that a free-flow clock is what makes its travel-time multiplier comparable with OSRM's.

## ADDED Requirements

### Requirement: Google is asked for the route the driver will be given

For a journey whose optimal route and waypoints have been computed, the system SHALL ask Google for a driving route between the same two points through exactly those waypoints, in that order.

The request SHALL ask at Google's highest routing quality: `travelMode: DRIVE`, `routingPreference: TRAFFIC_AWARE_OPTIMAL`, no alternative routes, no waypoint reordering, and tolls not avoided. This is the setting a Google Maps link is answered at, and the route it returns is therefore the road the driver is actually sent down.

The choice SHALL NOT be read as making the answer depend on traffic. Measured on one journey across live traffic, a Sunday at 03:00 and a Friday at 17:00, the returned geometry is identical — the same distance and the same faithfulness to a tenth of a point — while only the predicted duration moves. What the setting buys is a better route search.

The request SHALL carry a `trafficModel` and a `departureTime`, which describe the clock rather than the path. The departure time SHALL be a fixed weekly slot rather than the moment of the request, so a stored answer's duration stays comparable with a fresh one. It SHALL be computed at request time and SHALL lie in the future: Google rejects a departure time in the past, and any constant eventually becomes one. It SHALL be anchored to the timezone of the roads being driven, so the slot does not shift by an hour across a summer time change.

Intermediate waypoints SHALL be sent as stopovers rather than as pass-through points. A Google Maps directions URL cannot express a pass-through waypoint, so a request that used one would measure a route the link cannot produce. The two settings were measured a fifth of a point apart, which is not a reason to break that correspondence.

The system SHALL request only the fields it uses. Unlike the evaluation, which buys an answer once and keeps it whole against future questions, this asks a question it already knows: the route's geometry, its distance, and its duration.

#### Scenario: The request asks at the highest routing quality

- **WHEN** a refinement request is built
- **THEN** it sets `TRAFFIC_AWARE_OPTIMAL`, and does not ask to avoid tolls or to reorder the waypoints

#### Scenario: The path does not move with traffic

- **WHEN** the same journey is asked about under different traffic conditions
- **THEN** the route returned is the same road, and only its predicted duration differs

#### Scenario: The departure time is computed rather than fixed

- **WHEN** a request is built at any moment
- **THEN** its departure time is the next occurrence of the configured weekly slot, in the roads' own timezone, and lies in the future

#### Scenario: The slot survives a summer time change

- **WHEN** a request is built on a date in winter and one in summer
- **THEN** both name the same local hour, with the offset that applies on that date

#### Scenario: Waypoints are sent as stopovers

- **WHEN** the intermediates of a request are read
- **THEN** none is marked as a pass-through point, because a directions URL cannot carry one

#### Scenario: The waypoints asked about are the ones computed

- **WHEN** the optimal route carries seven waypoints
- **THEN** Google is asked to drive through those seven, in that order

#### Scenario: The evaluation does not follow

- **WHEN** the evaluation builds its own Google request
- **THEN** it still asks at `TRAFFIC_UNAWARE`, so its clock stays free-flow and its travel-time multiplier stays reproducible

## MODIFIED Requirements

### Requirement: Two budgets, and the answer says which one stopped it

Refinement SHALL proceed only when both budgets allow it.

The **waypoint budget** is nine — what a Google Maps directions URL carries — less the number the optimal route already needs. A journey already needing nine SHALL NOT be refined, because there is nowhere to put the result.

The **request budget** is `GOOGLE_DIRECTIONS_MAX_REQUEST_PER_MONTH` less the number of Google requests already made in the current calendar month. A journey SHALL NOT be refined when that is exhausted.

Where either budget is exhausted, the journey SHALL still be answered and the link SHALL still work, carrying the unrefined waypoints. The answer SHALL say which budget stopped it, so an operator can tell a route Google agreed with from one nobody could afford to ask about.

A journey with no waypoint budget SHALL still be shown on request. Nothing can be refined — there is nowhere to put a waypoint — but the route Google drives through the waypoints the link already carries is the route that link produces, and it SHALL be bought and drawn when a caller asks to see it. Refusing left the journeys carrying the most waypoints as the only ones that could not be looked at. This is safe to draw because the waypoints and the waypoints sent are the same list, so every marker shown is one Google demonstrably reached.

That purchase SHALL happen only when the geometry is asked for. Following a link SHALL buy nothing, because a full link cannot be improved and paying per redirect to establish that again buys nothing.

The system SHALL NOT contact Google when a stored refinement already answers the question being asked, and that SHALL NOT count against either budget.

#### Scenario: No room for another waypoint

- **WHEN** the optimal route already needs nine waypoints
- **THEN** no waypoint is added, the link carries those nine, and the answer says the waypoint budget was full

#### Scenario: A full link is drawn when the geometry is asked for

- **WHEN** the page asks to see a journey whose optimal route already needs nine waypoints
- **THEN** Google's route through those nine is bought and returned, every one of them lying on it, and the answer still says the waypoint budget was full

#### Scenario: A full link followed buys nothing

- **WHEN** a link for such a journey is followed rather than looked at
- **THEN** no Google request is made and the month's count is unchanged

#### Scenario: The month is spent

- **WHEN** the month's requests have reached the configured maximum
- **THEN** no Google request is made, the link carries the unrefined waypoints, and the answer says the monthly budget was spent

#### Scenario: A journey asked about twice

- **WHEN** a journey whose stored refinement answers the question is requested again
- **THEN** the stored refinement is returned, no request is made, and the month's count is unchanged

#### Scenario: An unconfigured maximum

- **WHEN** `GOOGLE_DIRECTIONS_MAX_REQUEST_PER_MONTH` is unset or zero
- **THEN** no refinement is attempted and every journey is answered unrefined
