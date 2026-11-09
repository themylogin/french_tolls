# Spec Delta

## REMOVED Requirements

### Requirement: The answer message costs nothing and offers at most one action

**Reason**: The answer now asks two questions before it drives: which route, and whether to plan a refuel. It offers up to three route buttons, and then two buttons for the chosen route. It no longer carries a directions link for a journey that needs no Google request.

**Migration**: The free message, the comparison map, and the avoid-tolls instruction move unchanged to "The answer message costs nothing", "The comparison map is sent only where the routes differ", and "A toll-free optimal route carries the avoid-tolls instruction". The buttons are in "The driver chooses a route before driving it" and "The chosen route offers Drive with Google and Plan refuel".

### Requirement: A chosen route that needs no request is answered on the choice

**Reason**: Every chosen route now offers `Drive with Google` and `Plan refuel`, so the driver can plan a refuel first. A route that needs no request gets its link from the press on `Drive with Google`.

**Migration**: "Asking to drive resolves a journey into followable parts" sends the link of such a route on that press, with no Google request.

## MODIFIED Requirements

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

Every whole journey SHALL reach this decision through a press on `Drive with Google`, and a half produced by a split through a press too. The driver first chooses a route and whether to plan a refuel, so the answer message settles nothing.

**Where rule 1 or rule 2 settles the part, the press SHALL send the link at once, and SHALL show no message that Google is being checked.** Nothing is checked.

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

- **WHEN** the driver chooses a route that rule 1 or rule 2 settles, and then presses `Drive with Google`
- **THEN** the link is sent on that press, no Google request is made, and no message says that Google is being checked

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

### Requirement: The driver chooses a route before driving it

Where at least two routes of the answer differ, the answer message SHALL offer one row of buttons, in this order: "Super" where a superoptimal route is listed, then "Optimal", then "Fastest" where the fastest route and the optimal route are not the same road. A press SHALL choose that route and spend the choice. The press SHALL NOT cause a Google request.

The bot SHALL then edit the same message. It replaces the buttons with the buttons of "The chosen route offers Drive with Google and Plan refuel". It adds an empty line and "Superoptimal route chosen", "Optimal route chosen", or "Fastest route chosen" at the end. The rest of the message SHALL NOT change.

Where no other route differs from the optimal route, the answer message SHALL offer no choice. It SHALL offer the buttons of "The chosen route offers Drive with Google and Plan refuel" at once, for the optimal route.

#### Scenario: The choice is offered

- **WHEN** a superoptimal route is listed, and the fastest route and the optimal route are not the same road
- **THEN** the answer message offers the buttons "Super", "Optimal", and "Fastest" in one row, and no "Drive with Google" or "Plan refuel" button

#### Scenario: A superoptimal route on the fastest road

- **WHEN** a superoptimal route is listed, and the fastest route and the optimal route are the same road
- **THEN** the answer message offers the buttons "Super" and "Optimal" in one row

#### Scenario: The fastest route differs

- **WHEN** no superoptimal route is listed, and the fastest route and the optimal route are not the same road
- **THEN** the answer message offers the buttons "Optimal" and "Fastest" in one row

#### Scenario: Nothing to choose

- **WHEN** no superoptimal route is listed, and the fastest route and the optimal route are the same road
- **THEN** the answer message offers "Drive with Google" and "Plan refuel" for the optimal route, and no route button

#### Scenario: A choice leads to "Drive with Google"

- **WHEN** the driver presses "Super"
- **THEN** the same message now offers one row with "Drive with Google" and "Plan refuel", and no Google request was made

#### Scenario: The choice is written under the answer

- **WHEN** the driver presses "Super"
- **THEN** the answer message keeps its text, its bold titles, and its links, and ends with an empty line and "Superoptimal route chosen"

#### Scenario: "Drive with Google" drives the chosen route

- **WHEN** the driver presses "Drive with Google" after a press on "Super"
- **THEN** every link sent drives the superoptimal route

#### Scenario: "Drive with Google" after the optimal choice

- **WHEN** the driver presses "Drive with Google" after a press on "Optimal"
- **THEN** the links and the Google requests are the ones a journey without a superoptimal route gets

#### Scenario: A spent choice

- **WHEN** a choice that was already pressed is pressed again
- **THEN** the bot says that the route has expired, as it does for a spent drive button

### Requirement: A superoptimal route is listed above the optimal one

Where the route answer carries a superoptimal route that the bot can drive, the answer message SHALL list it first. Its title is "Superoptimal". Its summary has the format of the others: travel time, cost, and distance. The optimal and fastest routes SHALL follow, as today.

The bot can drive the route when its stops fit in one directions link. Otherwise the bot SHALL treat the route as absent.

#### Scenario: The superoptimal route is listed first

- **WHEN** the answer carries a superoptimal route whose stops fit in one link
- **THEN** the message lists "Superoptimal", "Optimal route", and "Fastest route" in that order, each with its travel time, cost, and distance

#### Scenario: No superoptimal route

- **WHEN** the answer carries no superoptimal route
- **THEN** the message does not mention one, and is the message sent today

#### Scenario: Stops that do not fit in one link

- **WHEN** the stops of the superoptimal route alone are more than one directions link carries
- **THEN** the message is the one sent for a journey without a superoptimal route

## ADDED Requirements

### Requirement: The answer message costs nothing

For a journey it has calculated, the bot SHALL send the route summaries: the optimal route and the fastest route, with the superoptimal route above them where "A superoptimal route is listed above the optimal one" lists it. The message SHALL NOT cause a Google request. Most journeys are looked at and never driven, and a message sent for every journey cannot be allowed to spend on every journey.

#### Scenario: A message is free

- **WHEN** a journey is calculated and its answer sent
- **THEN** no Google request has been made and the month's count is unchanged

### Requirement: The answer message carries no directions link

The answer message SHALL carry no link addressed to Google Maps directions, also where rule 1 or rule 2 of "Asking to drive" settles the route. The driver first chooses a route, and then chooses between driving and planning a refuel. A directions link comes only from a press on `Drive with Google`.

#### Scenario: A settled journey asks before it drives

- **WHEN** the optimal route pays no tolls, and no other route differs from it
- **THEN** the answer message carries no directions link, and offers "Drive with Google" and "Plan refuel"

### Requirement: The comparison map is sent only where the routes differ

The answer message SHALL carry a link to the comparison map only where the fastest route and the optimal route are not the same road, or where a superoptimal route is listed. The map draws one route against the other; where nothing differs, it would draw one line twice. The address SHALL be built from this service's configured public address rather than written into the bot.

#### Scenario: No map where there is nothing to compare

- **WHEN** the fastest route and the optimal route are the same road, and no superoptimal route is listed
- **THEN** the message carries no comparison map link

#### Scenario: The map is sent where the routes differ

- **WHEN** the fastest route and the optimal route are not the same road
- **THEN** the message carries the comparison map link

#### Scenario: The map is sent where a superoptimal route is listed

- **WHEN** the fastest route and the optimal route are the same road, and a superoptimal route is listed
- **THEN** the message carries the comparison map link

### Requirement: A toll-free optimal route carries the avoid-tolls instruction

Where the optimal route pays no tolls, the answer message SHALL carry, in bold, an instruction to enable "Avoid tolls" before driving. That setting reproduces the whole intent of a toll-free route in one action, and it is not expressible in a directions link.

#### Scenario: A toll-free route says how to drive it

- **WHEN** the optimal route's toll cost is zero
- **THEN** the message carries the avoid-tolls instruction in bold

#### Scenario: A tolled route does not

- **WHEN** the optimal route pays tolls
- **THEN** the message carries no avoid-tolls instruction

### Requirement: The chosen route offers Drive with Google and Plan refuel

For the chosen route, the answer message SHALL offer one row: `Drive with Google`, then `Plan refuel`. This SHALL hold also where rule 1 or rule 2 settles the route. A press on either button SHALL spend both. `Plan refuel` SHALL start `telegram-refuel-plan` on the chosen route.

#### Scenario: A journey that needs Google

- **WHEN** the answer message offers the buttons for the optimal route, and the route needs a Google request
- **THEN** the row has `Drive with Google` and then `Plan refuel`

#### Scenario: A toll-free journey

- **WHEN** the optimal route pays no tolls, and no other route differs from it
- **THEN** the row has `Drive with Google` and then `Plan refuel`

#### Scenario: A press on Drive with Google spends Plan refuel

- **WHEN** the driver presses `Drive with Google`
- **THEN** the answer message has no `Plan refuel` button, and an old copy of `Plan refuel` has expired

#### Scenario: Split parts offer no Plan refuel

- **WHEN** a part of a split journey is sent with the button for the next part
- **THEN** that message has no `Plan refuel` button

### Requirement: The fastest route is driven without a request

`Drive with Google` for the fastest route SHALL send one link from the driver's current location to the destination, with no waypoints. It SHALL make no Google request, because the fastest route is the road that Google drives without waypoints. Where the fastest route pays no tolls, the link SHALL carry the avoid-tolls instruction in bold.

#### Scenario: The fastest route is chosen

- **WHEN** the driver presses "Fastest", and then `Drive with Google`
- **THEN** the bot sends one link from the driver's current location with no waypoints, and makes no Google request

### Requirement: A refuel plan is driven through its gas stations

The rules of "Asking to drive" SHALL drive the route of a finished refuel plan on the optimal or the superoptimal route. Where they read the optimal route, they SHALL read the planned route through the chosen stations: its cost, its booths, and its geometry. Every link SHALL carry a waypoint at each chosen station, in route order. This SHALL hold for a link of rule 1 and of rule 2 too.

#### Scenario: A toll-free plan

- **WHEN** the driver drives a refuel plan with the stations A and B, and the planned route pays no tolls
- **THEN** the bot sends one link from the driver's current location through A and B, with the avoid-tolls instruction, and makes no Google request

#### Scenario: Every link carries the stations

- **WHEN** a link for a refuel plan is sent, whether it is accepted, corrected, unchecked, or the best link available
- **THEN** it carries a waypoint at each chosen station of that part

#### Scenario: The stations are kept first

- **WHEN** a refuel plan has 2 chosen stations, and the optimal route needed 8 waypoints that all lie on the planned route
- **THEN** the first link carries 9 waypoints, and both stations are among them

### Requirement: A refuel plan on the fastest route is driven without a request

For a finished plan on the fastest route, `Drive with Google` SHALL send one link from the driver's current location through each chosen station, in route order, and through no other waypoint. It SHALL make no Google request. Where the route through the stations pays no tolls, the link SHALL carry the avoid-tolls instruction in bold.

#### Scenario: A plan on the fastest route

- **WHEN** the driver drives a plan on the fastest route with the stations A and B
- **THEN** the bot sends one link from the driver's current location through A and B only, and makes no Google request

### Requirement: Rule 2 for a refuel plan reads the fastest route through its stations

For a refuel plan, rule 2 SHALL compare the booths of the planned route with the booths of the fastest route through the same chosen stations, in the same order. Its link SHALL carry the chosen stations and no other waypoint.

#### Scenario: The two routes through the stations agree

- **WHEN** the fastest route through the station A crosses exactly the booths of the planned route through A
- **THEN** the bot sends a link from the driver's current location through A only, and makes no Google request

#### Scenario: The fastest route through the stations adds a booth

- **WHEN** the fastest route through the station A crosses one booth more than the planned route through A
- **THEN** rule 2 does not apply, and the decision continues to the rules below it

### Requirement: Google's route for a refuel plan is judged as the route it was planned on

For a plan on the optimal route, Google's route SHALL be accepted by the tests for an optimal part. For a plan on the superoptimal route, it SHALL also cross both booths of each split stop, as "Google's route for a superoptimal part makes every stop" requires. A chosen station SHALL add no booth to these tests.

#### Scenario: A plan on the optimal route with unknown tolls

- **WHEN** the booths of Google's route for a plan on the optimal route cannot be established, and the route follows the planned route for the configured share
- **THEN** it is accepted on the road it drives

#### Scenario: A plan on the superoptimal route that skips a stop

- **WHEN** Google's route for a plan on the superoptimal route goes through the chosen stations, but not through the exit booth of a split stop
- **THEN** it is not accepted, and the part is corrected or split

### Requirement: A split refuel plan keeps each station in its half

Where a refuel plan is divided at its midpoint, each chosen station and each split stop SHALL go to the half that drives it. A half with stations or stops SHALL be routed through them, in order, on the toll-weighted graph, and priced from its own geometry. A half without them SHALL be answered as an optimal part.

#### Scenario: A station stays in its half

- **WHEN** a refuel plan with the station A in its first half and the station B in its second half is split
- **THEN** each link of the first half carries A and not B, and each link of the second half carries B and not A

#### Scenario: A half without a station

- **WHEN** a refuel plan with one station in its first half is split
- **THEN** the second half is answered as an optimal part
