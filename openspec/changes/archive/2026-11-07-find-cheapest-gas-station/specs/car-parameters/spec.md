# Spec Delta

## ADDED Requirements

### Requirement: The consumption at 130 km/h is not less than the consumption at 80 km/h

The bot SHALL refuse a consumption at 130 km/h that is less than the consumption at 80 km/h of the same dialog. It SHALL send an error message that names the consumption at 80 km/h, and SHALL ask for the consumption at 130 km/h again. The bot SHALL accept an equal value.

#### Scenario: A lower value at 130 km/h

- **GIVEN** the driver answered `7.2` to the consumption at 80 km/h
- **WHEN** the driver answers `5.5` to the consumption at 130 km/h
- **THEN** the bot sends `The consumption at 130 km/h must be equal to or more than the consumption at 80 km/h, 7.2 L/100 km. Enter it again.`, the next answer is again the consumption at 130 km/h, and the stored car does not change

#### Scenario: An equal value

- **GIVEN** the driver answered `6` to the consumption at 80 km/h
- **WHEN** the driver answers `6` to the consumption at 130 km/h
- **THEN** the bot saves the car and sends `Your car parameters are saved.`

## MODIFIED Requirements

### Requirement: A consumption is a number more than 0 and less than 30

The bot SHALL accept as a consumption only a number more than 0 and less than 30, written in digits, with a point or a comma before an optional decimal part. White space around the number is permitted. The bot SHALL refuse any other answer with an error message and SHALL ask the same question again.

#### Scenario: A decimal comma

- **WHEN** the driver answers `6,5` to a consumption question
- **THEN** the bot stores the consumption `6.5`

#### Scenario: Values inside the limits

- **WHEN** the driver answers `0.1`, `7`, or `29.9` to the consumption question at 80 km/h
- **THEN** the bot accepts the answer

#### Scenario: Values outside the limits

- **WHEN** the driver answers `0`, `30`, `-5`, `1e1`, `nan`, or `6.5 l` to a consumption question
- **THEN** the bot sends `The consumption must be a number more than 0 and less than 30, for example 6.5. Enter it again.`, and asks the same question again
