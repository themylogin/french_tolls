## Purpose

Defines what the Telegram bot sends for a journey, what happens when a driver asks to drive it, and how a route too complex for one Google Maps link is broken into parts the driver can follow in sequence.

## ADDED Requirements

### Requirement: The answer message costs nothing and offers one action

For a journey it has calculated, the bot SHALL send the two route summaries it sends today, a link to the comparison map, and nothing else that addresses Google.

The message SHALL NOT cause a Google request. Most journeys are looked at and never driven, and a message sent for every journey cannot be allowed to spend on every journey.

Where the optimal route pays no tolls, the message SHALL carry, in bold, an instruction to enable "Avoid tolls" before driving. That setting reproduces the whole intent of a toll-free route in one action, and it is not expressible in a directions link.

The message SHALL offer exactly one action, labelled so a driver knows it produces something to drive.

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

#### Scenario: The direct links are gone

- **WHEN** the message is read
- **THEN** it carries no link addressed to Google Maps directions, only the comparison map

### Requirement: Asking to drive resolves a journey into followable parts

When the driver asks to drive, the system SHALL produce a link, or a sequence of links, that a general-purpose navigation application will follow.

It SHALL decide in this order:

1. **The part pays no tolls.** Send a directions link and the avoid-tolls instruction in bold. No Google request: a waypoint cannot say anything the setting does not say better.
2. **The monthly request budget is exhausted.** Send the link built from the waypoints already computed, and say it was not checked against Google. A link that may drift is worth more than no link, and the driver is entitled to know which they have.
3. **Otherwise.** Ask Google for the route it would drive through those waypoints. Where that route follows the optimal route to at least the configured share of its length, send it. Where it does not, spend whatever waypoint budget remains on the stretches where it left, and ask once more. Where it still falls short, split.

A part that is split SHALL be divided at the midpoint of the optimal route by distance, and each half answered by the same rules.

Splitting SHALL be bounded: a journey SHALL resolve into at most four parts. A part at that bound SHALL be sent as the best link available for it, whether or not it fits.

Every link SHALL start from the driver's current location. A driver who has asked to drive is somewhere already, and the route's own origin is not where they are.

#### Scenario: A toll-free journey costs nothing to drive

- **WHEN** the driver asks to drive a journey whose optimal route pays no tolls
- **THEN** a link from their current location is sent with the avoid-tolls instruction, and no Google request is made

#### Scenario: A route Google already follows is sent as it is

- **WHEN** Google's route through the computed waypoints meets the fit threshold
- **THEN** that link is sent and no further request is made

#### Scenario: A route Google leaves is corrected once

- **WHEN** Google's first route falls short of the threshold and waypoint budget remains
- **THEN** waypoints are placed in the stretches where it left, a second route is requested, and the corrected link is sent when it meets the threshold

#### Scenario: A route that cannot be corrected is split

- **WHEN** the corrected route still falls short of the threshold
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

A part that pays no tolls SHALL carry the avoid-tolls instruction in bold, as a whole journey does.

The final part SHALL offer no further action.

#### Scenario: The first part arrives with a way to get the next

- **WHEN** a journey resolves into two parts
- **THEN** the first part's link is sent with an action for the second, and the second is not sent yet

#### Scenario: A complex route says so

- **WHEN** a part of a split journey is sent
- **THEN** the message states that the route is complex and this is one part of it

#### Scenario: A toll-free part is driven by setting, not by waypoints

- **WHEN** a part of a split journey pays no tolls
- **THEN** its message carries the avoid-tolls instruction in bold

#### Scenario: The last part ends the exchange

- **WHEN** the final part is sent
- **THEN** no further action is offered

### Requirement: The decision is separable from the chat

The rules above SHALL be expressed as a decision over values — the journey, its cost, the budget, and what Google answered — that produces what to send: the text, whether an action follows, and which requests to make.

That decision SHALL be testable without a Telegram client, without a chat, without a network, and without substituting objects for the messaging library. A test SHALL be able to state a journey and a sequence of Google answers and assert the messages and requests that result.

Sending the messages, drawing the action, and receiving the press SHALL be the only part that knows about Telegram, and SHALL hold none of the rules.

The state carried between a message and the press that answers it SHALL be explicit and serialisable, so that a test can construct it directly rather than reproduce the exchange that would have produced it.

#### Scenario: The rules run without a chat

- **WHEN** the decision is exercised with a journey and a prepared sequence of Google answers
- **THEN** it yields the messages and the requests, with no Telegram client involved

#### Scenario: A split is testable end to end

- **WHEN** a test supplies answers that fail the threshold twice
- **THEN** the decision yields a split, the first part's message, and a pending second part, without a network

#### Scenario: The pending part is a value

- **WHEN** a part is left pending
- **THEN** what is needed to answer it is a value a test can build directly
