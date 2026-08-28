## MODIFIED Requirements

### Requirement: The page reads a fixed set of keys from the answer

The page SHALL read, from each of the answer's two routes:

- `nodes` — to draw the route on the map, and to place the start and end markers;
- `duration`, `distance`, and `cost` — for the summary line;
- `peages`, each entry's `name` and `cost` — for the passage table;
- `url`, `url_from_current_location`, and `url_from_current_location_through_start` — for the three directions links. These address this service and redirect to Google Maps; the page neither knows nor needs to know that.

These are the keys `route-service` requires the answer to carry, and this is what depends on them. A change to any of their names or meanings breaks this page, which is the reason that requirement exists.

The page SHALL tolerate keys it does not read. The answer carries `waypoints`, `waypoints_needed`, `complete`, `divergences`, and `unpriced`; the page ignores all of them today and SHALL keep working when more are added.

#### Scenario: Every key the page reads is present

- **WHEN** the API answers a route query
- **THEN** each of the listed keys is present on both `fast` and `optimal`

#### Scenario: An unknown key is harmless

- **WHEN** the answer carries a key the page does not read
- **THEN** the page renders normally

## ADDED Requirements

### Requirement: A visitor can ask what Google actually drove

Beside each of the three directions links the page SHALL offer a control that, when activated, asks this service for the refinement and draws Google's own route on the map.

The control SHALL be the icon already beside each link, made to look and behave like something clickable — a pointer cursor, and a title saying what it does. A visitor who does not press it SHALL cause no request and no spending.

Google's route SHALL be drawn in orange, above the optimal route and below the fast one, and thinner than both, so that where Google agreed the green shows along both edges and where it did not the orange runs off on its own.

The waypoints that were sent SHALL be drawn with it, as marks distinct from the endpoint pins, since they are the thing the overlay is there to judge.

The overlay SHALL be cleared when a new journey is calculated.

#### Scenario: Nothing is spent until it is asked for

- **WHEN** a journey is calculated
- **THEN** no refinement is requested, and no orange route is drawn

#### Scenario: The control draws what Google did

- **WHEN** the control beside a link is activated
- **THEN** the refinement is requested and Google's route appears in orange, over the optimal route and under the fast one

#### Scenario: The waypoints are visible

- **WHEN** the overlay is drawn
- **THEN** the waypoints sent to Google are marked on it

#### Scenario: A new journey clears it

- **WHEN** another journey is calculated
- **THEN** the orange route and its waypoint marks are removed

### Requirement: The overlay is not gated on an operator's flag

The control SHALL be available to every visitor. It SHALL NOT depend on a debug setting.

The overlay was previously drawn only when an operator set `GOOGLE_DIRECTIONS_DEBUG`, and only for journeys the evaluation had already bought — which is 2 450 of the journeys a visitor could ask for and none of the rest. It now draws the answer for the journey on screen, and it is a visitor's click rather than an operator's switch that decides whether it is asked for.

Where a budget is exhausted, the control SHALL say so rather than fail silently. Nothing to draw and nothing said is indistinguishable from a page that is broken.

#### Scenario: No flag is involved

- **WHEN** the page is served with no debug setting configured
- **THEN** the control is present and works

#### Scenario: An exhausted budget is explained

- **WHEN** the control is activated and no refinement could be made
- **THEN** the page says why rather than doing nothing
