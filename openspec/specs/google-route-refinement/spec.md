# google-route-refinement Specification

## Purpose
Asks Google to drive the route this project computed, finds where it went its own way instead, and spends the remaining waypoint budget on pulling it back — at most twice per journey, and no more often each month than the operator allows.

## Requirements

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

### Requirement: A refinement is bought in two phases, and nothing is kept between them

Refining and *seeing the result* are two questions, and they cost differently.

The **first phase** asks Google to drive the waypoints the route already has, reads the stretches where it went its own way, and produces the refined set. It is what a link needs: following a link requires the waypoints and nothing else.

The **second phase** asks Google to drive the refined set, and exists only to be looked at. It cannot be folded into the first: the route through the refined waypoints does not exist until it is asked for, and the first request's whole purpose is to find the places that route will differ.

The second phase SHALL be performed only when a caller asks for the geometry, and SHALL NOT be performed by a redirect.

Where the first phase finds nothing to correct, the route it already has *is* the route the link produces, and the second phase SHALL be skipped.

**A refinement SHALL NOT be stored.** Each ask buys what it needs and keeps nothing. A journey therefore costs one request per redirect and two per look at the geometry, without bound, and the same journey asked about twice costs twice.

The guarantee that a journey cost at most two Google requests ever is withdrawn. It was worth what it cost while it held, and it is being given up with the store that held it — for the reason the store is being given up, not because the amortisation stopped being valuable. **This is the price of the change, and it is stated here rather than left to be found in a bill.**

`web-front-end` requests a refinement for every journey calculated while its debug setting is on. Under that setting the month's ceiling is now consumed at two requests per calculation.

What bounds the spending is unchanged. `route-service` and this capability's two-budget requirement still apply: every request is claimed against the month's ceiling before it is issued, and a journey that cannot afford one still returns its unrefined waypoints naming the budget that stopped it. What is lost is the amortisation, not the ceiling.

Nothing stored means nothing stale. A rebuilt pipeline needs no purge for a refinement to stop describing a route that no longer exists, and a refinement bought at one routing preference can no longer be read back under another.

#### Scenario: A link costs one request

- **WHEN** a link is followed for a journey
- **THEN** one Google request is made, and the geometry is not bought

#### Scenario: Looking at it costs two

- **WHEN** the geometry is asked for
- **THEN** the first phase and the second phase are both bought, and the total for that ask is two

#### Scenario: The second visitor pays the same as the first

- **WHEN** two visitors ask the same question about the same journey
- **THEN** each pays for their own requests, and the second receives a refinement bought fresh

#### Scenario: A journey Google already agreed with

- **WHEN** the first phase finds no stretch to correct
- **THEN** no second request is made, and the route already obtained is the one drawn

#### Scenario: A redirect never buys the geometry

- **WHEN** a redirect is served
- **THEN** only the first phase is bought

#### Scenario: A rebuilt pipeline needs no purge

- **WHEN** the artefacts change and the same journey is refined
- **THEN** the refinement is bought against the route as it is now, because no earlier one was kept

#### Scenario: An exhausted budget still answers

- **WHEN** the month's ceiling is reached and a refinement is asked for
- **THEN** no request is made, and the answer carries the unrefined waypoints and names the budget that stopped it

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

### Requirement: The refinement is part of the route answer

Where the debug setting is on, a route query SHALL return the refinement with the answer, under a key of its own beside the two routes.

It SHALL carry the refined waypoints, which of those the refinement added, Google's route geometry, and the reason where there is no geometry to draw.

Where the debug setting is off the key SHALL be absent, and no Google request SHALL be made. The setting is what decides, and a caller that did not ask for the overlay does not pay for one.

**There SHALL be no separate endpoint for it.** A refinement describes a particular optimal route, so the two are computed together or the second computation re-derives the first. Asking for them separately meant routing the journey twice — once to answer it and once to have something to refine — for one thing a visitor asked for once.

Where a budget prevented the refinement, the answer SHALL still carry the key, naming the budget and holding the unrefined waypoints. A caller that cannot tell "Google agreed" from "nobody could afford to ask" cannot decide what to show.

The geometry returned SHALL be Google's route through the waypoints returned beside it, so that every one of those waypoints lies on it. Returning the route through a different set puts the markers visibly off the line they were computed for.

#### Scenario: One request carries both

- **WHEN** the page calculates a journey with the debug setting on
- **THEN** the single answer carries the two routes and the refinement, and the journey was routed once

#### Scenario: The setting off costs nothing

- **WHEN** a journey is calculated with the debug setting off
- **THEN** the answer carries no refinement key and no Google request is made

#### Scenario: The geometry matches the waypoints it is drawn with

- **WHEN** geometry is returned
- **THEN** it is Google's route through the waypoints returned with it, so every one of those waypoints lies on it

#### Scenario: A caller can tell agreement from an exhausted budget

- **WHEN** a budget prevented the refinement
- **THEN** the key is still present, names that budget, and carries the unrefined waypoints

#### Scenario: Nothing is served that nobody reads

- **WHEN** the refinement is returned
- **THEN** it carries the waypoints, the added waypoints, the geometry and the reason, and does not carry a directions link or a copy of the optimal route's distance, duration and waypoints

### Requirement: How faithfully Google followed is part of the answer

The system SHALL report, with a refinement, the share of Google's route by length that ran within the corridor of the optimal route.

A configured threshold SHALL define what counts as following it. The system SHALL NOT decide what to do about a route that falls short — that belongs to the caller — but SHALL make the judgement available so that every caller applies the same one.

The threshold SHALL default to the share `google-route-comparison` already uses to separate a route Google drove from one it did not, so that what the evaluation calls faithful and what the bot calls followable are the same thing.

**The share is no longer the only thing a caller judges on.** It answers "did Google drive our road", and the question a driver has is "will I pay what you told me". `toll-equivalence` answers the second, and a caller may accept a route on either. The share remains because it is cheap, because it is what the evaluation reports, and because it is the answer when the tolls cannot be established.

Measured over 205 journeys the two disagree in both directions: 72 of the 100 routes the share rejects pay identical tolls, and 5 of the routes it accepts cross a booth the optimal route does not.

#### Scenario: The share is reported

- **WHEN** a refinement is returned
- **THEN** it carries the share of Google's route that ran within the corridor

#### Scenario: One threshold, two readers

- **WHEN** the evaluation and the drive flow judge the same route
- **THEN** both use the same configured share

#### Scenario: The share does not decide alone

- **WHEN** a route falls below the share but pays no toll the optimal route does not
- **THEN** nothing in the refinement calls it unacceptable; what to do about it is the caller's
