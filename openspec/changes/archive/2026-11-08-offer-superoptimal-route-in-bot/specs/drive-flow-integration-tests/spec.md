## MODIFIED Requirements

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
