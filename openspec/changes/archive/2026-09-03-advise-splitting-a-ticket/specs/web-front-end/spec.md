## ADDED Requirements

### Requirement: A route that splits a ticket is drawn under the optimal one

Where the answer carries `super_optimal`, the page SHALL draw it in red, beneath the green optimal route.

The two routes are the same road for almost their whole length. Drawing the red one underneath means the green covers it everywhere they agree, and red shows only where they differ — the detour off the motorway and back at each stop. That is the whole of what the driver is being asked to decide about, and it is the reason for the paint order rather than a matter of taste.

The page SHALL read from `super_optimal` the same keys it reads from the other two routes, and additionally `stops`, to mark the junctions on the map.

The route's own summary line already carries what the decision needs: its cost against the optimal route's, and its travel time against the optimal route's. The difference between the two rows is the trade, so the page states it once rather than twice.

Its absence SHALL be treated as nothing to draw, not as an error, exactly as a missing refinement is.

#### Scenario: The split route is drawn under the optimal one

- **WHEN** the answer carries `super_optimal`
- **THEN** a red route is drawn for it and the green optimal route is drawn over it

#### Scenario: Only the detours are visible

- **WHEN** both routes are drawn and they follow the same road between two stops
- **THEN** red is not visible along that stretch, and is visible at the junctions where the split route leaves the motorway

#### Scenario: No split offered

- **WHEN** the answer carries no `super_optimal`
- **THEN** the page renders the two routes as it does today and draws nothing red

### Requirement: The routes Maps would not find offer a link to drive them

Beside the title of the optimal route and of a split route, the page SHALL show a link to Google Maps for that route, and SHALL show nothing where the route's `google_url` is null.

It SHALL NOT show one beside the fastest route. That is the route a plain Maps query already returns, so a link to it tells a driver nothing they could not get by typing the two places in. The other two exist precisely because Maps would not choose them, and a waypointed link is the only way to drive them.

The page SHALL NOT build the link itself. Which waypoints reproduce a route, and whether they fit, is known to the service and not to the page; a link assembled here would drive whatever Maps chose rather than the route being offered.

#### Scenario: The optimal route carries a link

- **WHEN** the optimal route carries a `google_url`
- **THEN** a Maps link is shown beside its title, opening in a new tab

#### Scenario: The fastest route carries none

- **WHEN** the fastest route is listed
- **THEN** no Maps link is shown beside its title, whatever the answer carries

#### Scenario: A split route whose waypoints did not fit

- **WHEN** `super_optimal` carries a null `google_url`
- **THEN** no link is shown beside its title, and the route is otherwise drawn and listed as usual

### Requirement: The stops are marked on the map

Each junction a split route leaves and rejoins at SHALL be marked, so the driver can see where the manoeuvre happens before choosing it.

The marks are what make the route legible. Red is visible only at the detours, and a detour at motorway scale is a few hundred metres of line that is easy to miss; the marker is what says a stop is being asked for at all.

#### Scenario: The stops are marked

- **WHEN** a split route with two stops is drawn
- **THEN** two stop markers appear on the map at those junctions

#### Scenario: The route is named for what it is

- **WHEN** a split route is drawn
- **THEN** its panel is titled so that it is distinguishable from the optimal and fastest routes
