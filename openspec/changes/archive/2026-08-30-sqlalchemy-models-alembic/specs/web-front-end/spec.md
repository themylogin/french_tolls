## MODIFIED Requirements

### Requirement: A visitor can ask what Google actually drove

Where the debug setting is on, the page SHALL request the refinement for each journey it calculates and draw Google's own route on the map, without being asked.

Where it is off, the page SHALL neither request nor draw it, and SHALL offer no control that would.

The overlay costs **two** Google requests every time it is drawn — one to find where Google left the route and one to buy the route through the corrected waypoints. That is the price of the setting and the reason it is a setting: seeing how well a link fits is the whole purpose, and it cannot be seen without asking.

**That price is now paid per calculation rather than once per journey.** `google-route-refinement` no longer stores what it buys, so calculating the same journey a second time with the setting on costs two requests again. A page left on with the setting on consumes the month's ceiling at two requests per calculation, and there is no journey that comes back free.

Google's route SHALL be drawn in orange, **beneath** the optimal route and at **twice its width**, so that agreement reads as the green line centred on a band of orange and divergence reads as orange running out on its own. A line drawn over the top would hide the route it is being compared against; a line of the same width would disappear beneath it.

The waypoints sent SHALL be drawn with it, distinguishing those the waypoint search chose from those the refinement added, since which is which is what the overlay is there to judge.

The overlay SHALL be cleared when a new journey is calculated.

#### Scenario: The control draws what Google did

- **WHEN** a journey is calculated and the debug setting is on
- **THEN** the refinement is requested and Google's route appears in orange, with no control involved

#### Scenario: Nothing is spent until it is asked for

- **WHEN** a journey is calculated and the debug setting is off
- **THEN** no refinement is requested, no orange route is drawn, and no control offers one

#### Scenario: The same journey costs again

- **WHEN** a journey already calculated with the setting on is calculated again with it still on
- **THEN** two further Google requests are spent, because nothing about the first drawing was kept

#### Scenario: The orange is visible under the green

- **WHEN** the overlay is drawn
- **THEN** it is twice the width of the optimal route and beneath it, so the green runs down the middle of the orange where the two agree

#### Scenario: The waypoints are visible

- **WHEN** the overlay is drawn
- **THEN** the waypoints sent to Google are marked on it, and those the search chose are distinguished from those the refinement added

#### Scenario: A new journey clears it

- **WHEN** another journey is calculated
- **THEN** the orange route and its waypoint marks are removed

#### Scenario: An exhausted budget is explained

- **WHEN** the debug setting is on and the month's requests are spent
- **THEN** the page says so rather than silently drawing nothing
