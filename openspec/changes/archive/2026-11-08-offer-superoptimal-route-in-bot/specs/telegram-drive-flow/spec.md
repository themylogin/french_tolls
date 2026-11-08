## MODIFIED Requirements

### Requirement: The answer message costs nothing and offers at most one action

For a journey it has calculated, the bot SHALL send the route summaries, and nothing else addressed to Google beyond what this requirement allows. The summaries are the optimal route and the fastest route, with the superoptimal route above them where "A superoptimal route is listed above the optimal one" lists it.

The message SHALL NOT cause a Google request. Most journeys are looked at and never driven, and a message sent for every journey cannot be allowed to spend on every journey.

A link to the comparison map SHALL be sent **only where the routes differ**: where the fastest route and the optimal route are not the same road, or where a superoptimal route is listed. The map draws one route against the other; where the fastest route and the optimal route are the same road and nothing else is listed, it would draw one line twice, and the link offers a driver nothing to look at. A listed superoptimal route always leaves the optimal road at its stops, and the map marks the stops.

Where the optimal route pays no tolls, the message SHALL carry, in bold, an instruction to enable "Avoid tolls" before driving. That setting reproduces the whole intent of a toll-free route in one action, and it is not expressible in a directions link.

**Where a superoptimal route is listed, the message SHALL offer the choice of route as its one action**, as "The driver chooses a route before driving it" specifies, and SHALL carry no link addressed to Google Maps directions. This applies even where the optimal route alone could be answered outright: the driver has not yet said which route they want.

**Where no superoptimal route is listed and the journey can be answered without a Google request** — it pays no tolls, or the fastest route crosses exactly the booths the optimal route crosses — **the message SHALL carry the directions link itself and SHALL offer no action.** The answer is already known, so asking a driver to press for it buys nothing and costs them a second message saying what the first could have said. That link SHALL start from the driver's current location and SHALL carry no waypoints.

Otherwise the message SHALL offer exactly one action, labelled so a driver knows it produces something to drive, and SHALL carry no link addressed to Google Maps directions. A journey that has still to be checked against Google must not be handed out as a link before it is.

The comparison map address SHALL be built from this service's configured public address rather than written into the bot.

#### Scenario: A message is free

- **WHEN** a journey is calculated and its answer sent
- **THEN** no Google request has been made and the month's count is unchanged

#### Scenario: A toll-free route says how to drive it

- **WHEN** the optimal route's toll cost is zero
- **THEN** the message carries the avoid-tolls instruction in bold

#### Scenario: A tolled route does not

- **WHEN** the optimal route pays tolls
- **THEN** the message carries no avoid-tolls instruction

#### Scenario: A journey still to be checked carries no directions link

- **WHEN** the answer is sent for a journey that will need a Google request to resolve
- **THEN** it carries no link addressed to Google Maps directions, and offers the action instead

#### Scenario: A journey needing no request is answered outright

- **WHEN** no superoptimal route is listed, and the optimal route pays no tolls or the fastest route crosses exactly the booths the optimal route crosses
- **THEN** the message carries a directions link from the driver's current location with no waypoints, and offers no action

#### Scenario: A listed superoptimal route replaces the outright answer

- **WHEN** a superoptimal route is listed, and the fastest route crosses exactly the booths the optimal route crosses
- **THEN** the message carries no link addressed to Google Maps directions, and offers the choice of route

#### Scenario: No map where there is nothing to compare

- **WHEN** the fastest route and the optimal route are the same road, and no superoptimal route is listed
- **THEN** the message carries no comparison map link

#### Scenario: The map is sent where the routes differ

- **WHEN** the fastest route and the optimal route are not the same road
- **THEN** the message carries the comparison map link

#### Scenario: The map is sent where a superoptimal route is listed

- **WHEN** the fastest route and the optimal route are the same road, and a superoptimal route is listed
- **THEN** the message carries the comparison map link

### Requirement: Asking to drive resolves a journey into followable parts

When the driver asks to drive, the system SHALL produce a link, or a sequence of links, that a general-purpose navigation application will follow.

It SHALL decide in this order:

1. **The part pays no tolls.** Send a directions link and the avoid-tolls instruction in bold. No Google request: a waypoint cannot say anything the setting does not say better.
2. **The fastest route crosses exactly the booths the optimal route crosses.** Send a directions link carrying no waypoints. No Google request: the two roads cost the driver the same, so there is no cheaper road for a waypoint to steer onto and nothing Google could answer that would change what is sent.
3. **The monthly request budget is exhausted.** Send the link built from the waypoints already computed, and say it was not checked against Google. A link that may drift is worth more than no link, and the driver is entitled to know which they have.
4. **Otherwise.** Ask Google for the route it would drive through those waypoints, and accept it when it is **equivalent** by `toll-equivalence` — when it crosses no toll booth the optimal route does not. Where the tolls cannot be established, accept it when it follows the optimal route to at least the configured share of its length. Where neither holds, spend whatever waypoint budget remains on the stretches where it left, and ask once more. Where it still qualifies on neither, split.

Rule 2 SHALL be tested by comparing the two booth sets for equality rather than the two costs. Routes crossing the same booths cost the same, so the booth set decides the same question and decides it on the finer fact.

Rule 2 SHALL carry no waypoints. Waypoints exist to steer a fastest-path router off the road it would choose and onto the optimal one; where both roads cross the same booths there is nothing to steer away from, and a waypoint would only constrain a route that is already acceptable.

Rule 1 SHALL be tried before rule 2. A part that pays no tolls has two empty booth sets and satisfies rule 2 as well, but the avoid-tolls instruction is still owed: the sets compared are drawn from this project's own graph, and the setting governs the route the driver's application actually chooses.

Rule 2 SHALL apply to a part at any depth, not only to a whole journey. A half of a journey is answered by the same rules as the journey.

Rules 1 and 2 SHALL also settle the answer message, before any driver asks to drive. Both produce a link and neither makes a request, so a whole journey either reaches this decision through a press or is answered outright when it is first calculated, never both. A half produced by a split still reaches it through a press.

**Where the answer message offers the choice of route, rules 1 and 2 SHALL settle the chosen route on the press that chooses it, and not in the answer message.** The answer message cannot settle a route the driver has not chosen yet.

Where the two booth sets are not both known, rule 2 SHALL NOT apply and the decision SHALL continue to the rules below it. An unknown set is not an equal one.

Toll equivalence SHALL be tried before the geometric test, because it answers the driver's question and the other only approximates it. Measured over 205 journeys, 72 of the 100 that fail the geometric test cross an identical set of booths; every one of those is corrected today, and may be split into as many as four links, for a difference that costs the driver nothing.

A part that is split SHALL be divided at the midpoint of the optimal route by distance, and each half answered by the same rules.

Splitting SHALL be bounded: a journey SHALL resolve into at most four parts. A part at that bound SHALL be sent as the best link available for it, whether or not it fits.

Every link SHALL start from the driver's current location. A driver who has asked to drive is somewhere already, and the route's own origin is not where they are.

A link SHALL record which test accepted it, and a link accepted by rule 2 SHALL be distinguishable from one accepted on tolls Google was asked about. The two are different facts: one was settled without spending anything and the other was settled by a paid request.

#### Scenario: A toll-free journey costs nothing to drive

- **WHEN** the driver asks to drive a journey whose optimal route pays no tolls
- **THEN** a link from their current location is sent with the avoid-tolls instruction, and no Google request is made

#### Scenario: A journey whose two routes pay the same tolls is answered without asking

- **WHEN** the driver asks to drive a part that pays a toll, and the fastest route crosses exactly the booths the optimal route crosses
- **THEN** a link from their current location to the part's destination is sent carrying no waypoints, no Google request is made, and the journey is not split

#### Scenario: A part whose fastest route adds a booth is not answered that way

- **WHEN** the fastest route crosses every booth the optimal route does and one besides
- **THEN** rule 2 does not apply and the decision continues to the rules below it

#### Scenario: A chosen route is settled on the choice

- **WHEN** the answer message offers the choice of route, and the driver chooses a route that rule 1 or rule 2 settles
- **THEN** the link is sent on that press, and no Google request is made

#### Scenario: A route Google already follows is sent as it is

- **WHEN** Google's route through the computed waypoints meets the fit threshold
- **THEN** that link is sent and no further request is made

#### Scenario: A route on a different road but the same tolls is sent as it is

- **WHEN** Google's route falls short of the fit threshold but crosses no booth the optimal route does not
- **THEN** that link is sent, no waypoint is added, and the journey is not split

#### Scenario: A route that adds a toll is not accepted

- **WHEN** Google's route crosses every booth the optimal route does and one besides
- **THEN** it is corrected or split, however faithfully it followed the road

#### Scenario: A route Google leaves is corrected once

- **WHEN** Google's first route qualifies on neither test and waypoint budget remains
- **THEN** waypoints are placed in the stretches where it left, a second route is requested, and the corrected link is sent when it qualifies

#### Scenario: A route that cannot be corrected is split

- **WHEN** the corrected route qualifies on neither test
- **THEN** the journey is divided at the midpoint of the optimal route and each half is answered separately

#### Scenario: Splitting stops at four parts

- **WHEN** a part produced by two splits still falls short
- **THEN** it is sent as the best link available and is not split again

#### Scenario: An exhausted budget still produces a link

- **WHEN** the driver asks to drive and the month's requests are spent
- **THEN** the unrefined link is sent, together with a statement that it was not checked

#### Scenario: Every link starts where the driver is

- **WHEN** any link is sent, for a whole journey or a part
- **THEN** its origin is the driver's current location, not the route's own origin

## ADDED Requirements

### Requirement: A superoptimal route is listed above the optimal one

Where the route answer carries a superoptimal route that the bot can drive, the answer message SHALL list it first. Its title is "Superoptimal route". Its summary has the format of the others: travel time, cost, and distance. The optimal and fastest routes SHALL follow, as today.

The bot can drive the route when its stops fit in one directions link. Otherwise the bot SHALL treat the route as absent.

#### Scenario: The superoptimal route is listed first

- **WHEN** the answer carries a superoptimal route whose stops fit in one link
- **THEN** the message lists "Superoptimal route", "Optimal route", and "Fastest route" in that order, each with its travel time, cost, and distance

#### Scenario: No superoptimal route

- **WHEN** the answer carries no superoptimal route
- **THEN** the message does not mention one, and is the message sent today

#### Scenario: Stops that do not fit in one link

- **WHEN** the stops of the superoptimal route alone are more than one directions link carries
- **THEN** the message is the one sent for a journey without a superoptimal route

### Requirement: The driver chooses a route before driving it

Where a superoptimal route is listed, the answer message SHALL offer one row of two buttons: "Optimal", then "Superoptimal". A press SHALL choose that route and spend the choice. The press SHALL NOT cause a Google request.

The bot SHALL then edit the same message. It replaces the buttons with one "Drive with Google" button, which drives the chosen route. It adds an empty line and "Optimal route chosen" or "Superoptimal route chosen" at the end. The rest of the message SHALL NOT change.

#### Scenario: The choice is offered

- **WHEN** a superoptimal route is listed
- **THEN** the answer message offers the buttons "Optimal" and "Superoptimal" in one row, and no "Drive with Google" button

#### Scenario: A choice leads to "Drive with Google"

- **WHEN** the driver presses "Superoptimal", and the superoptimal route needs a Google request
- **THEN** the same message now offers one "Drive with Google" button, and no Google request was made

#### Scenario: The choice is written under the answer

- **WHEN** the driver presses "Superoptimal"
- **THEN** the answer message keeps its text, its bold titles, and its links, and ends with an empty line and "Superoptimal route chosen"

#### Scenario: "Drive with Google" drives the chosen route

- **WHEN** the driver presses "Drive with Google" after a press on "Superoptimal"
- **THEN** every link sent drives the superoptimal route

#### Scenario: "Drive with Google" after the optimal choice

- **WHEN** the driver presses "Drive with Google" after a press on "Optimal"
- **THEN** the links and the Google requests are the ones a journey without a superoptimal route gets

#### Scenario: A spent choice

- **WHEN** a choice that was already pressed is pressed again
- **THEN** the bot says that the route has expired, as it does for a spent drive button

### Requirement: A chosen route that needs no request is answered on the choice

Where rule 1 or rule 2 of "Asking to drive" settles the chosen route, the press that chooses it SHALL remove the buttons and send the directions link at once. The link is the one the answer message carries for a journey without a choice. The bot SHALL NOT offer "Drive with Google", because a press on it would buy nothing.

#### Scenario: The optimal route agrees with the fastest one

- **WHEN** the driver presses "Optimal", and the fastest route crosses exactly the booths the optimal route crosses
- **THEN** the buttons are removed, the answer message ends with "Optimal route chosen", a link from the driver's current location with no waypoints is sent, no "Drive with Google" button is offered, and no Google request is made

### Requirement: A superoptimal route is driven through its stops

The rules of "Asking to drive" SHALL drive a superoptimal route. Where those rules read the optimal route, a superoptimal part SHALL read its own route: its cost, its booths, and its geometry. Google's route SHALL be measured against the superoptimal route.

Every link for a superoptimal part SHALL carry a waypoint at each of its stops. Where the stops and the optimal route's waypoints do not all fit, the link SHALL keep every stop.

#### Scenario: Every link carries the stops

- **WHEN** a link for a superoptimal part is sent, whether it is accepted, corrected, unchecked, or the best link available
- **THEN** it carries a waypoint at each stop of that part

#### Scenario: The stops are kept first

- **WHEN** the superoptimal route has 2 stops, and the optimal route needed 8 waypoints that all lie on the superoptimal route
- **THEN** the first link carries 9 waypoints, and both stops are among them

#### Scenario: Google is measured against the superoptimal route

- **WHEN** Google's route for a superoptimal part is measured for its share and for its corrections
- **THEN** the corridor is the geometry of the superoptimal route

### Requirement: Google's route for a superoptimal part makes every stop

Google's route for a superoptimal part SHALL be accepted on tolls only when two conditions are true. It crosses no booth that the superoptimal route does not cross. It crosses the exit booth and the entrance booth of each stop.

Where the tolls cannot be established, the route SHALL NOT be accepted on the road it drives. A route that stays on the motorway past a junction lies inside the corridor of a route that leaves there, so the road test cannot see a missed stop.

#### Scenario: A route that skips a stop

- **WHEN** Google's route crosses only booths of the superoptimal route, but not the exit booth or the entrance booth of a stop
- **THEN** it is not accepted, and the part is corrected or split

#### Scenario: A route that makes every stop

- **WHEN** Google's route crosses both booths of each stop and no booth outside the superoptimal route
- **THEN** it is accepted on its tolls

#### Scenario: Unknown tolls

- **WHEN** the booths of Google's route for a superoptimal part cannot be established
- **THEN** it is not accepted, whatever share of the corridor it follows

### Requirement: A split superoptimal part keeps each stop in its half

Where a superoptimal part is divided at its midpoint, each stop SHALL go to the half that drives it. A half with stops SHALL be routed through them on the toll-weighted graph and priced from its own geometry. A half without stops SHALL be answered as an optimal part.

Where the route of a half does not cross both booths of each of its stops, the part SHALL NOT be split. It SHALL be sent as the best link available, as when a half cannot be routed.

#### Scenario: A stop stays in its half

- **WHEN** a superoptimal part with one stop in its first half is split
- **THEN** the first half is routed through that stop and its links carry it, and the second half carries no stop

#### Scenario: A half that misses its stop

- **WHEN** the route of a half does not cross both booths of one of its stops
- **THEN** the part is not split, and it is sent as the best link available
