## MODIFIED Requirements

### Requirement: A visitor can ask what Google actually drove

Where the debug setting is on, the page SHALL draw Google's own route on the map for each journey it calculates, without being asked.

**The page SHALL make one request per journey.** It calculates, and draws the overlay from the refinement the answer carries. It used to calculate and then ask a second time for the same journey's refinement, which routed the journey again from nothing to rebuild the route the refinement describes.

The page SHALL draw the overlay when the answer carries a refinement and SHALL draw nothing when it does not. It SHALL NOT read the debug setting itself: the server decides what to send, and the presence of the key is the whole signal. Where it is off, the answer carries no refinement, so the page draws nothing and offers no control that would.

The overlay costs **two** Google requests every time one is drawn — one to find where Google left the route and one to buy the route through the corrected waypoints — and nothing is kept between drawings, so the same journey drawn twice is bought twice. That is the price of the setting and the reason it is a setting: seeing how well a link fits is the whole purpose, and it cannot be seen without asking.

Google's route SHALL be drawn in orange, **beneath** the optimal route and at **twice its width**, so that agreement reads as the green line centred on a band of orange and divergence reads as orange running out on its own. A line drawn over the top would hide the route it is being compared against; a line of the same width would disappear beneath it.

The waypoints sent SHALL be drawn with it, distinguishing those the waypoint search chose from those the refinement added, since which is which is what the overlay is there to judge.

The overlay SHALL be cleared when a new journey is calculated.

#### Scenario: One journey, one request

- **WHEN** a journey is calculated with the debug setting on
- **THEN** the page makes one request, and the orange route is drawn from what that answer carried

#### Scenario: The control draws what Google did

- **WHEN** a journey is calculated and the debug setting is on
- **THEN** Google's route appears in orange, with no control involved

#### Scenario: Nothing is spent until it is asked for

- **WHEN** a journey is calculated and the debug setting is off
- **THEN** the answer carries no refinement, no orange route is drawn, and no control offers one

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

### Requirement: The page reads a fixed set of keys from the answer

The page SHALL read, from each of the answer's two routes:

- `nodes` — to draw the route on the map, and to place the start and end markers;
- `duration`, `distance`, and `cost` — for the summary line;
- `peages`, each entry's `name` and `cost` — for the passage table.

These are the keys `route-service` requires the answer to carry, and this is what depends on them. A change to any of their names or meanings breaks this page, which is the reason that requirement exists.

**From the answer itself the page SHALL additionally read the refinement key, where it is present**, and from it: `nodes` to draw the orange route, `waypoints` and `added` to mark them, and `reason` to explain a drawing that did not happen. It SHALL treat the key's absence as "nothing to draw" rather than as an error, because that is how the debug setting reaches it.

The three service-addressed link keys are no longer read, because they are no longer sent. The page shows no directions link of its own.

The page SHALL tolerate keys it does not read. The answer carries `duration_osrm`, `google_url`, `waypoints`, `waypoints_needed`, `complete`, `divergences` and `unpriced`; the page ignores them and SHALL keep working when more are added.

#### Scenario: Every key the page reads is present

- **WHEN** the API answers a route query
- **THEN** each of the listed keys is present on both `fast` and `optimal`

#### Scenario: An unknown key is harmless

- **WHEN** the answer carries a key the page does not read
- **THEN** the page renders normally

#### Scenario: A missing refinement is not an error

- **WHEN** the answer carries no refinement key
- **THEN** the page renders the two routes normally and draws no overlay
