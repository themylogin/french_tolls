## MODIFIED Requirements

### Requirement: Asking to drive resolves a journey into followable parts

When the driver asks to drive, the system SHALL produce a link, or a sequence of links, that a general-purpose navigation application will follow.

It SHALL decide in this order:

1. **The part pays no tolls.** Send a directions link and the avoid-tolls instruction in bold. No Google request: a waypoint cannot say anything the setting does not say better.
2. **The monthly request budget is exhausted.** Send the link built from the waypoints already computed, and say it was not checked against Google. A link that may drift is worth more than no link, and the driver is entitled to know which they have.
3. **Otherwise.** Ask Google for the route it would drive through those waypoints, and accept it when it is **equivalent** by `toll-equivalence` — when it crosses no toll booth the optimal route does not. Where the tolls cannot be established, accept it when it follows the optimal route to at least the configured share of its length. Where neither holds, spend whatever waypoint budget remains on the stretches where it left, and ask once more. Where it still qualifies on neither, split.

Toll equivalence SHALL be tried before the geometric test, because it answers the driver's question and the other only approximates it. Measured over 205 journeys, 72 of the 100 that fail the geometric test cross an identical set of booths; every one of those is corrected today, and may be split into as many as four links, for a difference that costs the driver nothing.

A part that is split SHALL be divided at the midpoint of the optimal route by distance, and each half answered by the same rules.

Splitting SHALL be bounded: a journey SHALL resolve into at most four parts. A part at that bound SHALL be sent as the best link available for it, whether or not it fits.

Every link SHALL start from the driver's current location. A driver who has asked to drive is somewhere already, and the route's own origin is not where they are.

#### Scenario: A toll-free journey costs nothing to drive

- **WHEN** the driver asks to drive a journey whose optimal route pays no tolls
- **THEN** a link from their current location is sent with the avoid-tolls instruction, and no Google request is made

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

### Requirement: Parts are delivered one at a time

Where a journey resolves into more than one part, the system SHALL send the first part and offer an action for the next, rather than sending every part at once.

Each message SHALL say that the route was too complex for a single link, and SHALL carry the link for the part it describes.

**It SHALL describe that part as the next one, and SHALL NOT call it the first half.** A journey may be halved twice, so a driver can be sent three or four links. Calling each of them the first half said the same thing about the first half, about a quarter of it, and about the far half — the last two to a driver who had already driven a part. Numbering them is not available either: splitting is decided lazily, so when the message is written the system does not yet know how many parts there will be.

A part that pays no tolls SHALL carry the avoid-tolls instruction in bold, as a whole journey does.

The final part SHALL offer no further action.

#### Scenario: The first part arrives with a way to get the next

- **WHEN** a journey resolves into two parts
- **THEN** the first part's link is sent with an action for the second, and the second is not sent yet

#### Scenario: A complex route says so

- **WHEN** a part of a split journey is sent
- **THEN** the message states that the route is complex and this is one part of it

#### Scenario: No part claims to be the first half

- **WHEN** a journey is halved twice and resolves into three parts
- **THEN** no message describes its part as the first half of the route

#### Scenario: A toll-free part is driven by setting, not by waypoints

- **WHEN** a part of a split journey pays no tolls
- **THEN** its message carries the avoid-tolls instruction in bold

#### Scenario: The last part ends the exchange

- **WHEN** the final part is sent
- **THEN** no further action is offered
