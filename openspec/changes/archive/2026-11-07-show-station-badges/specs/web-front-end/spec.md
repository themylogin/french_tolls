# Spec Delta

## MODIFIED Requirements

### Requirement: The dialog lists the stations of the answer

When the answer has `stop_needed` true and stations, the dialog SHALL list the stations in the order of the answer, below the fields. Each row SHALL have four columns: the name as a link to `google_url` that opens in a new tab, the distance in whole km, the price per liter, and the detour time in whole minutes with its sign. A null name SHALL be shown as `Unnamed station`. A `badge` SHALL be shown in bold after the name link.

#### Scenario: A listed station

- **WHEN** the answer lists the station `Leclerc` with the distance 235,400 m, the price `1.799`, and the detour time 420 s
- **THEN** the row shows `Leclerc` as a Google Maps link, `235 km`, `1,799 €/L`, and `+7 min`

#### Scenario: A station with a badge

- **WHEN** the answer lists the station `Leclerc` with the `badge` `"24"`
- **THEN** the first column shows the link `Leclerc`, then `24` in bold

#### Scenario: A station without a badge

- **WHEN** a listed station has the `badge` `null`
- **THEN** the first column shows only the name link

#### Scenario: A detour that saves time

- **WHEN** a listed station has the detour time -120 s
- **THEN** its detour column shows `-2 min`

#### Scenario: The fields stay

- **WHEN** the dialog lists the stations
- **THEN** the five fields stay in the dialog, and the visitor can change the fuel and click `Calculate` again
