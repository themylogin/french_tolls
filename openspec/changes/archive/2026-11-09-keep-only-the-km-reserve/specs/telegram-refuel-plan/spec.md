# Spec Delta

## MODIFIED Requirements

### Requirement: The bot says when no station is near

When a stop is needed and the list is empty, the bot SHALL send `No gas station sells this fuel within 50 km of the point where the range left reaches <reserve> km.`, with the reserve of the car in km. This SHALL hold after a gauge press, after a typed range, and after a chosen station. The plan SHALL end.

#### Scenario: No station after a gauge press

- **GIVEN** the car has the reserve `50`
- **WHEN** the plan after a gauge press lists no station
- **THEN** the bot sends `No gas station sells this fuel within 50 km of the point where the range left reaches 50 km.`

#### Scenario: No station after a typed range

- **GIVEN** the car has the reserve `42.5`
- **WHEN** the plan after a typed range, with no chosen station, lists no station
- **THEN** the bot sends `No gas station sells this fuel within 50 km of the point where the range left reaches 42.5 km.`

#### Scenario: No station after a chosen station

- **GIVEN** the plan started from a typed range, the driver chose a station, and the car has the reserve `50`
- **WHEN** the next plan lists no station
- **THEN** the bot sends `No gas station sells this fuel within 50 km of the point where the range left reaches 50 km.`
