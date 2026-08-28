# google-route-refinement Specification

## Purpose
Asks Google to drive the route this project computed, finds where it went its own way instead, and spends the remaining waypoint budget on pulling it back — at most twice per journey, and no more often each month than the operator allows.

## Requirements

### Requirement: Google is asked what it would actually drive

For a journey whose optimal route and waypoints have been computed, the system SHALL ask Google for a driving route between the same two points through exactly those waypoints, in that order.

The request SHALL describe an empty road: `travelMode: DRIVE`, `routingPreference: TRAFFIC_UNAWARE`, no departure time, no alternative routes, no waypoint reordering, and tolls not avoided. These are the terms under which Google's answer is comparable to the route it is being compared against, and the terms `google-route-comparison` already establishes for the same reason.

The system SHALL request only the fields it uses. Unlike the evaluation, which buys an answer once and keeps it whole against future questions, this asks a question it already knows: the route's geometry, its distance, and its duration.

#### Scenario: The request describes an empty road

- **WHEN** a refinement request is built
- **THEN** it sets `TRAFFIC_UNAWARE`, carries no departure time, and does not ask to avoid tolls or to reorder the waypoints

#### Scenario: The waypoints asked about are the ones computed

- **WHEN** the optimal route carries seven waypoints
- **THEN** Google is asked to drive through those seven, in that order

### Requirement: A stretch Google went its own way becomes a waypoint

The system SHALL find every stretch of Google's route lying outside a corridor of the optimal route, measured as `google-route-comparison` measures it.

The system SHALL rank those stretches by their length weighted by where they begin. For a stretch whose bypassed portion of the optimal route begins `dist` metres from the origin along an optimal route of `total` metres, the rank SHALL be the stretch's length multiplied by `1.0 - (dist / total) / 2`.

Both `dist` and `total` SHALL be measured along the **optimal route**, not along Google's. The driver follows the optimal route, so it is the only route along which "how far in" describes what the driver experiences. Where the bypassed portion is located by two ends, `dist` SHALL be the nearer of them to the origin.

A stretch at the origin therefore counts for its full length, and a stretch at the destination for half. The purpose is that a driver follows a link from its beginning: a correction near the origin is reached by everyone who follows the link at all, while a correction near the destination is reached only by a journey that is driven to the end rather than abandoned, interrupted, or re-requested from a new position. Ranking by raw length spends a scarce budget as though every kilometre were equally likely to be driven.

For each of the highest-ranked stretches, up to the waypoint budget, the system SHALL place one new waypoint **on the optimal route**, at the midpoint by distance of the portion of the optimal route that the stretch bypassed.

The waypoint SHALL NOT be placed on Google's own path. The purpose is to name a point on the road the driver was meant to take; naming one on the road they are being steered away from would confirm the detour rather than correct it.

New waypoints SHALL be merged into the existing list in the order the optimal route reaches them, because Google is asked to visit them in order and a list in another order describes a different journey.

The ranking SHALL decide only which stretches are corrected. It SHALL NOT affect where a waypoint is placed within its stretch, nor the order the waypoints appear in the link.

#### Scenario: An earlier stretch outranks a longer later one

- **WHEN** the budget is one, and Google leaves the corridor for 40 km beginning 50 km along a 1 000 km optimal route, and again for 60 km beginning 950 km along it
- **THEN** the earlier stretch is chosen, because 40 × 0.975 exceeds 60 × 0.525

#### Scenario: A later stretch still wins when it is long enough

- **WHEN** the budget is one, and Google leaves the corridor for 20 km near the origin and for 60 km near the destination of the same 1 000 km route
- **THEN** the later stretch is chosen, because the weight halves a stretch at most and cannot overturn a threefold difference in length

#### Scenario: Stretches at the same place are ranked by length

- **WHEN** two stretches begin at the same distance along the optimal route
- **THEN** the longer is ranked first, because they carry the same weight

#### Scenario: The worst stretches are chosen

- **WHEN** Google leaves the corridor over seventeen stretches and the budget is two
- **THEN** a waypoint is placed for the two highest-ranked, and none for the other fifteen

#### Scenario: The waypoint sits on the intended road

- **WHEN** a stretch of Google's route bypasses 86 km of the optimal route
- **THEN** the new waypoint is a point of the optimal route, halfway along those 86 km

#### Scenario: Ranking does not move a waypoint

- **WHEN** a stretch is chosen under the weighted ranking
- **THEN** its waypoint is at the midpoint of the bypassed portion, the same point raw-length ranking would have produced for it

#### Scenario: Order is preserved

- **WHEN** a new waypoint falls between the third and fourth existing ones
- **THEN** the merged list carries it in that position

#### Scenario: Google already followed the route

- **WHEN** no stretch of Google's route lies outside the corridor
- **THEN** no waypoint is added and the link is unchanged

### Requirement: Two budgets, and the answer says which one stopped it

Refinement SHALL proceed only when both budgets allow it.

The **waypoint budget** is nine — what a Google Maps directions URL carries — less the number the optimal route already needs. A journey already needing nine SHALL NOT be refined, because there is nowhere to put the result.

The **request budget** is `GOOGLE_DIRECTIONS_MAX_REQUEST_PER_MONTH` less the number of Google requests already made in the current calendar month. A journey SHALL NOT be refined when that is exhausted.

Where either budget is exhausted, the journey SHALL still be answered and the link SHALL still work, carrying the unrefined waypoints. The answer SHALL say which budget stopped it, so an operator can tell a route Google agreed with from one nobody could afford to ask about.

The system SHALL NOT contact Google when a stored refinement already answers the question being asked, and that SHALL NOT count against either budget.

#### Scenario: No room for another waypoint

- **WHEN** the optimal route already needs nine waypoints
- **THEN** no Google request is made, the link carries those nine, and the answer says the waypoint budget was full

#### Scenario: The month is spent

- **WHEN** the month's requests have reached the configured maximum
- **THEN** no Google request is made, the link carries the unrefined waypoints, and the answer says the monthly budget was spent

#### Scenario: A journey asked about twice

- **WHEN** a journey whose stored refinement answers the question is requested again
- **THEN** the stored refinement is returned, no request is made, and the month's count is unchanged

#### Scenario: An unconfigured maximum

- **WHEN** `GOOGLE_DIRECTIONS_MAX_REQUEST_PER_MONTH` is unset or zero
- **THEN** no refinement is attempted and every journey is answered unrefined

### Requirement: Every request against the budget is counted before it is made

The month's count SHALL be incremented, and the increment committed, before the request it accounts for is issued.

Counting afterwards loses the count of any request whose answer never arrives, and a request that fails has still been made and may still have been billed. A count that can only overstate is the one to have.

The counter SHALL be keyed on the calendar month as `YYYY-MM`, one row per month, and SHALL be incremented atomically so that two journeys answered at once cannot both read the same value and write it back.

#### Scenario: A failed request still counts

- **WHEN** a Google request is issued and errors
- **THEN** the month's count includes it

#### Scenario: One row per month

- **WHEN** the count is read
- **THEN** it is a single row for the current `YYYY-MM`, and a new month starts from zero without anything being reset by hand

#### Scenario: Two journeys at once

- **WHEN** two refinements are attempted concurrently
- **THEN** the month's count rises by two

### Requirement: A refinement is bought in two phases, and each is bought once

Refining and *seeing the result* are two questions, and they cost differently.

The **first phase** asks Google to drive the waypoints the route already has, reads the stretches where it went its own way, and produces the refined set. It is what a link needs: following a link requires the waypoints and nothing else.

The **second phase** asks Google to drive the refined set, and exists only to be looked at. It cannot be folded into the first: the route through the refined waypoints does not exist until it is asked for, and the first request's whole purpose is to find the places that route will differ.

A journey SHALL therefore cost at most two Google requests, ever — one if nobody looks at it. The second phase SHALL be performed only when a caller asks for the geometry, and SHALL NOT be performed by a redirect.

Where the first phase finds nothing to correct, the route it already has *is* the route the link produces, and the second phase SHALL be skipped. Such a journey costs one request whether or not anyone looks at it.

Each phase SHALL be stored as it completes, so a journey whose link was followed and is later looked at buys only the phase it is missing.

Stored SHALL be the refined waypoints, the waypoints the drawable route was driven through, Google's route geometry, its distance and duration, the faithfulness before and after, and when it was fetched.

A refinement SHALL be invalidated by the same data fingerprint that invalidates a route answer. A refinement is a statement about a particular optimal route; when the route changes, the statement is about a journey that no longer exists.

#### Scenario: A link costs one request

- **WHEN** a link is followed for a journey never asked about before
- **THEN** one Google request is made, and the geometry is not bought

#### Scenario: Looking at it afterwards buys only what is missing

- **WHEN** the control is used on a journey whose link has already been followed
- **THEN** one further request is made, and the total for that journey is two

#### Scenario: The second visitor pays nothing

- **WHEN** two visitors ask the same question about the same journey
- **THEN** the second makes no request and receives the same refinement

#### Scenario: A journey Google already agreed with

- **WHEN** the first phase finds no stretch to correct
- **THEN** no second request is made, and the route already obtained is the one drawn

#### Scenario: A rebuilt pipeline invalidates it

- **WHEN** the artefacts change and the same journey is requested
- **THEN** the stored refinement is not used, because the route it described has been recomputed

### Requirement: The refinement is reachable as an answer and as a redirect

The system SHALL expose the refinement two ways.

As an **answer**: given an origin and a destination, it returns the refined link, the refined waypoints, Google's route geometry, and which budgets applied. This is what the page calls when a visitor asks to see what Google did.

As a **redirect**: given an origin, a destination, and which of the three link forms is wanted, it computes the refinement and redirects to Google Maps. This is what the three link keys point at, so that following a link from the bot or the page gets the refined route without the sender having had to pay for it in advance.

The redirect SHALL redirect even when refinement did not happen, to the unrefined Google link. A link that fails because a budget was exhausted is worse than a link that is merely no better than it was.

The three forms SHALL be the three the answer already names: from the route's own origin, from the driver's current location, and from the driver's current location by way of the route's origin.

#### Scenario: The page asks and draws

- **WHEN** a visitor clicks the control beside a link
- **THEN** the answer form is called, and the reply carries geometry the page can draw

#### Scenario: The geometry matches the waypoints it is drawn with

- **WHEN** geometry is returned
- **THEN** it is Google's route through the waypoints the link carries, so every one of those waypoints lies on it

#### Scenario: A redirect buys no geometry

- **WHEN** a link is followed
- **THEN** no geometry is fetched, because a redirect has nothing to draw

#### Scenario: Following a link from the bot

- **WHEN** a link from the Telegram bot is followed
- **THEN** the request is redirected to Google Maps with the refined waypoints

#### Scenario: A redirect with nothing to refine

- **WHEN** a budget is exhausted and a link is followed
- **THEN** the redirect still goes to Google Maps, with the unrefined waypoints

#### Scenario: All three forms redirect

- **WHEN** each of the three link forms is followed
- **THEN** each redirects to Google Maps with the same refined waypoints and its own origin
