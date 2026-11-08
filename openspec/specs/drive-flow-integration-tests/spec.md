# drive-flow-integration-tests Specification

## Purpose
Defines the suite that drives the Telegram bot end to end over real routes and real toll data, with Google's answers replayed from recordings and Telegram replaced by a transport that records what would have been sent. It states what the suite may reach, how a Google answer is recorded and replayed, which journeys are pinned, and what a test asserts.

## Requirements

### Requirement: The suite drives the bot, not the rules beneath it

The suite SHALL exercise the bot through the same entry point Telegram uses: an update goes in, and what the bot would have sent comes out.

It SHALL send the two locations a driver sends, read the reply, press the button the bot actually offered, and press again for each part the bot still owes. It SHALL NOT construct a part, a token, or a decision directly. `route-algorithm-tests` and the decision's own tests already cover the rules with values; what is untested is everything between them and a driver, and reaching past the handlers would leave it untested still.

The button a test presses SHALL be the one carried in the recorded reply markup. A test that invented a token would pass while the bot offered nothing.

A button that the bot offers by an edit of the markup of a message it already sent SHALL count as offered, as a button sent with a new message does. The "Drive with Google" button that follows a choice of route arrives this way.

Where the bot offers the choice of route, the suite SHALL press the button for the route that the journey is pinned to choose.

#### Scenario: A journey is driven the way a driver drives it

- **WHEN** a test sends an origin, a destination, and presses the offered button
- **THEN** the messages asserted are the ones the bot produced from those updates alone

#### Scenario: The token comes from the bot

- **WHEN** a test presses a button
- **THEN** the callback data it sends is the data the bot put in the markup it sent, by a new message or by an edit

#### Scenario: Every owed part is asked for

- **WHEN** a journey resolves into more than one part
- **THEN** the test presses for each remaining part in turn, until the bot offers no further action

#### Scenario: A button offered by an edit is pressed

- **WHEN** a press on a choice replaces the buttons of the answer message with "Drive with Google"
- **THEN** the suite presses "Drive with Google" next

#### Scenario: The pinned choice is pressed

- **WHEN** the answer message offers "Optimal" and "Superoptimal", and the journey is pinned to choose "Optimal"
- **THEN** the suite presses "Optimal" and not "Superoptimal"

### Requirement: Telegram is answered, not reached

The suite SHALL supply the Telegram application with a transport that answers the Bot API from written responses and records every call.

The transport SHALL answer the calls the flow makes — identifying the bot, setting the commands, sending a message, editing a message's text, editing its markup, answering a callback, and deleting a message — with payloads the messaging library accepts, so that the library's own objects are constructed as they would be in production.

The suite SHALL NOT substitute an object for the messaging library, patch its methods, or import a private name from it. Replacing the transport is the seam; anything above it is the code under test.

The recorded calls SHALL be the assertion surface. A test SHALL assert on the text sent, its order, the links it carries and the buttons offered — what a driver would have seen — rather than on the internal state the flow passed around.

#### Scenario: No socket is opened

- **WHEN** the suite runs with no network route to Telegram and no valid token
- **THEN** every test runs and passes

#### Scenario: The library builds its own objects

- **WHEN** the transport answers a send
- **THEN** the payload is one the messaging library parses into a message, so nothing above the transport knows it is a test

#### Scenario: The assertion is what a driver would see

- **WHEN** a test asserts an outcome
- **THEN** it asserts the recorded text, order, links and buttons, and not the values passed between functions

### Requirement: Google is replayed from what it really answered

The suite SHALL answer Google's Routes API from recordings of real answers, kept beside the suite as data.

A recording SHALL hold the request that was sent and the answer that came back. Replay SHALL match on the request, so that a test which asks a different question gets no answer rather than the wrong one. A request with no recording SHALL fail the test loudly and SHALL NOT be sent.

The recordings SHALL be refreshable by a run that spends real requests, and that run SHALL be separate from the suite. The suite SHALL spend nothing.

Recordings SHALL be valid only for the routing preference they were made under. `google-route-refinement` fixes that preference, and the same journeys resolve differently beneath it — one measured journey is accepted outright at the higher quality and splits into three parts and eight requests at the lower. A recording SHALL therefore record which preference bought it, and the suite SHALL refuse a recording made under another.

#### Scenario: A recorded journey costs nothing

- **WHEN** the suite runs
- **THEN** no paid request is made and no Google key is needed

#### Scenario: An unrecorded question is not asked

- **WHEN** the flow asks something no recording answers
- **THEN** the test fails naming the request, and nothing is sent to Google

#### Scenario: A recording knows what bought it

- **WHEN** a recording is replayed under a routing preference other than the one it was made under
- **THEN** the suite refuses it rather than asserting against an answer the application would not receive

### Requirement: The suite runs the real routers and the real booths

The suite SHALL reach `osrm-toll` and `osrm-optimal`, and SHALL read the booth artefacts under `data/`.

**Where `remote-routers` configures an address for a router, the suite SHALL reach that router there.** The remote router serves the same graph, so the pinned journeys still hold. A host without graphs can then run the suite.

Only Google and Telegram are replaced, and for one reason each: one costs money per call and the other needs a chat. The routers are local, free, and are the thing being tested — a waypoint search against a hand-built graph is what `route-algorithm-tests` already covers, and it would say nothing about whether a real journey through France resolves into one link or three.

A run SHALL leave the application's stored answers as it found them, using a cache of its own.

#### Scenario: The routes are real

- **WHEN** a test drives a journey
- **THEN** the optimal route, its waypoints and its tolls come from the routers and the artefacts, not from a fixture

#### Scenario: The routers are remote

- **WHEN** both router addresses and the access token are configured and the suite runs
- **THEN** every router request goes to the configured addresses with the token, and the pinned journeys pass

#### Scenario: A run leaves no trace

- **WHEN** the suite has run
- **THEN** the application's cached answers and its count of requests spent are unchanged

### Requirement: The pinned journeys cover each way a journey can resolve

The suite SHALL pin one journey for each outcome the flow can produce, named by the outcome rather than by the place:

- a journey whose optimal route pays no tolls, answered with the avoid-tolls instruction and **no Google request at all**;
- a journey that pays a toll whose fastest route crosses exactly the booths the optimal route crosses, answered with a link carrying no waypoints and **no Google request at all**;
- a journey accepted on the first ask;
- a journey refused once, corrected with waypoints, and accepted on the second ask;
- a journey that splits, where one part pays no tolls and carries the avoid-tolls instruction;
- a journey that splits, where no part is toll-free;
- a journey that offers a superoptimal route and is driven through it, where every link carries a waypoint at each stop.

Each SHALL assert the number of paid requests the flow would have made, because that is the cost the operator carries and nothing else in the suite would notice it changing.

Each SHALL state which route it chooses where the answer offers a choice. A journey that chooses the optimal route SHALL make the requests it would make if no choice were offered.

The two journeys answered with no Google request SHALL be journeys that offer no choice, so that they pin the answer message that settles a journey outright.

A journey the answer message settles outright SHALL be asserted to press nothing, and every other journey SHALL be asserted to press. A suite that checked only the presses it did make would not notice a button appearing where the answer was already known, nor one disappearing where it was not.

A pinned journey that makes no paid request SHALL carry no recorded Google answer, because there is no request to replay. Its recording SHALL still exist and SHALL hold an empty list of answers, naming the journey and the routing quality it was driven at: that is what makes "this journey bought nothing" a recorded fact rather than a missing file.

**Where an outcome has no real journey, the suite SHALL say so and SHALL NOT invent one.** Two are unpinned today: a journey that splits into three, and a first ask that both beats the fit share and matches the booths. Both became rare under the routing preference `google-route-refinement` now requires, because the first ask is the one made with the fewest waypoints and so the one traffic moves most. A synthetic journey would pin an outcome the application does not produce.

#### Scenario: A toll-free journey buys nothing

- **WHEN** the pinned toll-free journey is driven
- **THEN** one message is sent, it carries the avoid-tolls instruction, and the recorded request count is zero

#### Scenario: A journey whose two routes agree on tolls buys nothing

- **WHEN** the pinned journey whose fastest and optimal routes cross the same booths is driven
- **THEN** one message is sent, its link carries no waypoints, it does not carry the avoid-tolls instruction, and the recorded request count is zero

#### Scenario: A journey settled outright is never pressed

- **WHEN** a journey pinned at zero paid requests is driven
- **THEN** no button was pressed, because the answer message carried the link and offered no action

#### Scenario: A split journey arrives one part at a time

- **WHEN** the pinned splitting journey is driven to its end
- **THEN** each part arrives on its own press, every link starts from the driver's current location, and only the last offers no further action

#### Scenario: A toll-free part says so

- **WHEN** the pinned journey with a toll-free part is driven
- **THEN** that part's message carries the avoid-tolls instruction and the others do not

#### Scenario: The cost of a journey is asserted

- **WHEN** a pinned journey is driven
- **THEN** the number of paid requests the flow would have made is asserted, not merely the messages

#### Scenario: A missing outcome is recorded as missing

- **WHEN** the suite is read for what it covers
- **THEN** the outcomes with no pinned journey are named, with the reason no real journey produces one

#### Scenario: A superoptimal journey is driven through its stops

- **WHEN** the pinned superoptimal journey is driven
- **THEN** the answer lists "Superoptimal route" above "Optimal route", the choice is offered, "Drive with Google" is offered after the press on "Superoptimal", every link carries a waypoint at each stop, and the request count is the pinned one

#### Scenario: Choosing the optimal route changes no request

- **WHEN** a pinned journey that offers a choice is pinned to choose "Optimal" and is driven
- **THEN** it makes the paid requests it is pinned to make, and its recording is the one it had before the choice existed
