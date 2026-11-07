# Spec Delta

## MODIFIED Requirements

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
