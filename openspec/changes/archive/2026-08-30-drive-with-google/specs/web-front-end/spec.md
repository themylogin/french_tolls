## REMOVED Requirements

### Requirement: The overlay is not gated on an operator's flag

**Reason**: It was written to correct a narrower fault — the overlay used to draw only for the 2 450 journeys the evaluation had already bought, so for anything else a visitor got nothing and no explanation. Ungating it fixed that, and made every visitor able to spend money on a click.

The page is not where a driver decides anything now. The bot's action produces the route someone actually drives, and the page's orange line is what an operator looks at when asking how well the link fits. That is a debug tool, and a debug tool is exactly the thing an operator's flag should gate.

**Migration**: The overlay is now drawn automatically when the debug setting is on, and not offered at all when it is off — see the modified requirement below. The narrower fault the removed requirement was written against does not return: the overlay draws the answer for the journey on screen, whatever journey that is, rather than only for journeys already bought.

## MODIFIED Requirements

### Requirement: The page reads a fixed set of keys from the answer

The page SHALL read, from each of the answer's two routes:

- `nodes` — to draw the route on the map, and to place the start and end markers;
- `duration`, `distance`, and `cost` — for the summary line;
- `peages`, each entry's `name` and `cost` — for the passage table.

These are the keys `route-service` requires the answer to carry, and this is what depends on them. A change to any of their names or meanings breaks this page, which is the reason that requirement exists.

The three service-addressed link keys are no longer read, because they are no longer sent. The page shows no directions link of its own.

The page SHALL tolerate keys it does not read. The answer carries `duration_osrm`, `google_url`, `waypoints`, `waypoints_needed`, `complete`, `divergences` and `unpriced`; the page ignores them and SHALL keep working when more are added.

#### Scenario: Every key the page reads is present

- **WHEN** the API answers a route query
- **THEN** each of the listed keys is present on both `fast` and `optimal`

#### Scenario: An unknown key is harmless

- **WHEN** the answer carries a key the page does not read
- **THEN** the page renders normally

### Requirement: A visitor can ask what Google actually drove

Where the debug setting is on, the page SHALL request the refinement for each journey it calculates and draw Google's own route on the map, without being asked.

Where it is off, the page SHALL neither request nor draw it, and SHALL offer no control that would.

The overlay costs **two** Google requests per journey drawn — one to find where Google left the route and one to buy the route through the corrected waypoints. That is the price of the setting and the reason it is a setting: seeing how well a link fits is the whole purpose, and it cannot be seen without asking.

Google's route SHALL be drawn in orange, **beneath** the optimal route and at **twice its width**, so that agreement reads as the green line centred on a band of orange and divergence reads as orange running out on its own. A line drawn over the top would hide the route it is being compared against; a line of the same width would disappear beneath it.

The waypoints sent SHALL be drawn with it, distinguishing those the waypoint search chose from those the refinement added, since which is which is what the overlay is there to judge.

The overlay SHALL be cleared when a new journey is calculated.

#### Scenario: The control draws what Google did

- **WHEN** a journey is calculated and the debug setting is on
- **THEN** the refinement is requested and Google's route appears in orange, with no control involved

#### Scenario: Nothing is spent until it is asked for

- **WHEN** a journey is calculated and the debug setting is off
- **THEN** no refinement is requested, no orange route is drawn, and no control offers one

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
