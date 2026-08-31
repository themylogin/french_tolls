## REMOVED Requirements

### Requirement: The refinement is reachable as an answer and as a redirect

**Reason**: The redirect half has no caller left. It existed so that a link written long before anyone followed it would still arrive at the refined route — the bot wrote three links per journey and could not afford to refine them all in advance. The bot now sends no directions link at all; it sends an action, and the refinement happens when the driver presses it. A redirect that nothing points at is an endpoint that spends money for whoever finds it.

**Migration**: The **answer** form survives unchanged and is restated below as a requirement in its own right — the page and the drive flow both call it. `/go/{form}` and the three link keys it served are removed by `route-service`. Nothing that a driver or a visitor can do today stops working: the page's overlay and the bot's button both reach Google through the answer form.

## ADDED Requirements

### Requirement: The refinement is reachable as an answer

Given an origin and a destination, the system SHALL return the refined waypoints, a directions link carrying them, Google's route geometry where it was asked for, how faithfully that route followed the optimal route, and which budgets applied.

This is what the page draws and what the drive flow decides on. Both need the same thing — what Google actually did — and neither needs a redirect.

The geometry returned SHALL be Google's route through the waypoints the link carries, so that every one of those waypoints lies on it. Returning the route through a different set puts the markers visibly off the line they were computed for.

Where a budget prevented the refinement, the answer SHALL say which budget, and SHALL still carry the unrefined waypoints. A caller that cannot tell "Google agreed" from "nobody could afford to ask" cannot decide what to tell a driver.

#### Scenario: The page asks and draws

- **WHEN** the page requests the refinement for the journey on screen
- **THEN** the reply carries geometry it can draw and the waypoints that geometry was driven through

#### Scenario: The geometry matches the waypoints it is drawn with

- **WHEN** geometry is returned
- **THEN** it is Google's route through the waypoints the link carries, so every one of those waypoints lies on it

#### Scenario: A caller can tell agreement from an exhausted budget

- **WHEN** a budget prevented the refinement
- **THEN** the answer names that budget and carries the unrefined waypoints

### Requirement: How faithfully Google followed is part of the answer

The system SHALL report, with a refinement, the share of Google's route by length that ran within the corridor of the optimal route.

A configured threshold SHALL define what counts as following it. The system SHALL NOT decide what to do about a route that falls short — that belongs to the caller — but SHALL make the judgement available so that every caller applies the same one.

The threshold SHALL default to the share `google-route-comparison` already uses to separate a route Google drove from one it did not, so that what the evaluation calls faithful and what the bot calls followable are the same thing.

#### Scenario: The share is reported

- **WHEN** a refinement is returned
- **THEN** it carries the share of Google's route that ran within the corridor

#### Scenario: One threshold, two readers

- **WHEN** the evaluation and the drive flow judge the same route
- **THEN** both use the same configured share

## MODIFIED Requirements

### Requirement: Google is asked for the route the driver will be given

For a journey whose optimal route and waypoints have been computed, the system SHALL ask Google for a driving route between the same two points through exactly those waypoints, in that order.

The request SHALL describe an empty road: `travelMode: DRIVE`, `routingPreference: TRAFFIC_UNAWARE`, no traffic model, no departure time, no alternative routes, no waypoint reordering, and tolls not avoided.

The higher-quality search was used for a time, on the measurement that it was worth **12.7 points** of faithfulness. That measurement was taken when the waypoints were poor. Measured again against the waypoints the search now produces, the same setting is worth **0.8 points** — a well-placed waypoint decides the road, and there is little left for the search quality to decide. What the cheaper setting buys back is the **Essentials** tier rather than **Pro**, and with it a free allowance of 10 000 requests a month rather than 5 000. A single drive request can now cost up to fourteen, so the allowance is no longer a formality.

Removing the departure time also removes the only part of the request that varied with when it was made, so two answers for the same journey are comparable however far apart they were asked.

Intermediate waypoints SHALL be sent as stopovers rather than as pass-through points. A Google Maps directions URL cannot express a pass-through waypoint, so a request that used one would measure a route the link cannot produce.

The system SHALL request only the fields it uses: the route's geometry, its distance, and its duration.

#### Scenario: The request asks at the highest routing quality

- **WHEN** a refinement request is built
- **THEN** it no longer does: it sets `TRAFFIC_UNAWARE`, because the higher tier is worth 0.8 points against the waypoints the search now produces and costs half the free monthly allowance

#### Scenario: The path does not move with traffic

- **WHEN** the same journey is asked about under different traffic conditions
- **THEN** the route returned is identical, because nothing in the request consults traffic at all

#### Scenario: The departure time is computed rather than fixed

- **WHEN** a request is built at any moment
- **THEN** it carries no departure time, so there is none to compute and none to go stale

#### Scenario: The slot survives a summer time change

- **WHEN** a request is built on a date in winter and one in summer
- **THEN** both are identical, because no local hour is named

#### Scenario: The evaluation does not follow

- **WHEN** the evaluation builds its own Google request
- **THEN** it asks the same way, so the two no longer differ and its measurements describe the link the application emits

#### Scenario: Two requests a month apart are comparable

- **WHEN** the same journey is asked about on different days
- **THEN** nothing in the request differs, and the routes returned are comparable

#### Scenario: Waypoints are sent as stopovers

- **WHEN** the intermediates of a request are read
- **THEN** none is marked as a pass-through point, because a directions URL cannot carry one

#### Scenario: The waypoints asked about are the ones computed

- **WHEN** the optimal route carries seven waypoints
- **THEN** Google is asked to drive through those seven, in that order

