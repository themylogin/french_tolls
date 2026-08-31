## ADDED Requirements

### Requirement: The refinement is part of the route answer

Where the debug setting is on, a route query SHALL return the refinement with the answer, under a key of its own beside the two routes.

It SHALL carry the refined waypoints, which of those the refinement added, Google's route geometry, and the reason where there is no geometry to draw.

Where the debug setting is off the key SHALL be absent, and no Google request SHALL be made. The setting is what decides, and a caller that did not ask for the overlay does not pay for one.

**There SHALL be no separate endpoint for it.** A refinement describes a particular optimal route, so the two are computed together or the second computation re-derives the first. Asking for them separately meant routing the journey twice — once to answer it and once to have something to refine — for one thing a visitor asked for once.

Where a budget prevented the refinement, the answer SHALL still carry the key, naming the budget and holding the unrefined waypoints. A caller that cannot tell "Google agreed" from "nobody could afford to ask" cannot decide what to show.

The geometry returned SHALL be Google's route through the waypoints returned beside it, so that every one of those waypoints lies on it. Returning the route through a different set puts the markers visibly off the line they were computed for.

#### Scenario: One request carries both

- **WHEN** the page calculates a journey with the debug setting on
- **THEN** the single answer carries the two routes and the refinement, and the journey was routed once

#### Scenario: The setting off costs nothing

- **WHEN** a journey is calculated with the debug setting off
- **THEN** the answer carries no refinement key and no Google request is made

#### Scenario: The geometry matches the waypoints it is drawn with

- **WHEN** geometry is returned
- **THEN** it is Google's route through the waypoints returned with it, so every one of those waypoints lies on it

#### Scenario: A caller can tell agreement from an exhausted budget

- **WHEN** a budget prevented the refinement
- **THEN** the key is still present, names that budget, and carries the unrefined waypoints

#### Scenario: Nothing is served that nobody reads

- **WHEN** the refinement is returned
- **THEN** it carries the waypoints, the added waypoints, the geometry and the reason, and does not carry a directions link or a copy of the optimal route's distance, duration and waypoints

## REMOVED Requirements

### Requirement: The refinement is reachable as an answer

**Reason**: Replaced by **The refinement is part of the route answer**. The requirement described a refinement reachable on its own, given an origin and a destination, and that is what made a second endpoint necessary. Answering it separately meant routing the journey a second time to rebuild the optimal route the refinement describes, so one visitor's one question cost two full local searches.

It also required a directions link carrying the refined waypoints. Nothing reads it: the page stopped showing a link of its own when the three service-addressed link keys were removed, and the bot builds its own.

**Migration**: A caller that posted to `/api/refine` posts to `/api/calculate` instead and reads the refinement from the key beside `fast` and `optimal`. The fields it draws from are unchanged in name and meaning. `url` and the `ours` block are gone; `ours` duplicated `distance`, `duration` and `waypoints` that the same answer already carries under `optimal`.
