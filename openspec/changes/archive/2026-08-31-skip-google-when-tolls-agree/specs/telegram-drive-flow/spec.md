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
