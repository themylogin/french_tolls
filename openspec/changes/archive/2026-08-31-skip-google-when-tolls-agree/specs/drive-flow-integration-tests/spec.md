## MODIFIED Requirements

### Requirement: The pinned journeys cover each way a journey can resolve

The suite SHALL pin one journey for each outcome the flow can produce, named by the outcome rather than by the place:

- a journey whose optimal route pays no tolls, answered with the avoid-tolls instruction and **no Google request at all**;
- a journey that pays a toll whose fastest route crosses exactly the booths the optimal route crosses, answered with a link carrying no waypoints and **no Google request at all**;
- a journey accepted on the first ask;
- a journey refused once, corrected with waypoints, and accepted on the second ask;
- a journey that splits, where one part pays no tolls and carries the avoid-tolls instruction;
- a journey that splits, where no part is toll-free.

Each SHALL assert the number of paid requests the flow would have made, because that is the cost the operator carries and nothing else in the suite would notice it changing.

A pinned journey that makes no paid request SHALL carry no recorded Google answer, because there is no request to replay. Its recording SHALL still exist and SHALL hold an empty list of answers, naming the journey and the routing quality it was driven at: that is what makes "this journey bought nothing" a recorded fact rather than a missing file.

**Where an outcome has no real journey, the suite SHALL say so and SHALL NOT invent one.** Two are unpinned today: a journey that splits into three, and a first ask that both beats the fit share and matches the booths. Both became rare under the routing preference `google-route-refinement` now requires, because the first ask is the one made with the fewest waypoints and so the one traffic moves most. A synthetic journey would pin an outcome the application does not produce.

#### Scenario: A toll-free journey buys nothing

- **WHEN** the pinned toll-free journey is driven
- **THEN** one message is sent, it carries the avoid-tolls instruction, and the recorded request count is zero

#### Scenario: A journey whose two routes agree on tolls buys nothing

- **WHEN** the pinned journey whose fastest and optimal routes cross the same booths is driven
- **THEN** one message is sent, its link carries no waypoints, it does not carry the avoid-tolls instruction, and the recorded request count is zero

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
