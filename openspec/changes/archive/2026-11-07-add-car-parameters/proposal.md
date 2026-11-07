# Proposal

## Why

The bot knows nothing about the car of a driver. The tank volume, the fuel type, and the fuel consumption are necessary to plan fuel stops and fuel cost on a route. The store now holds the fuel prices of 9,357 stations, so the next step is the car data that uses them.

## What Changes

- A new table, `car`, stores one row per Telegram user:
  - `telegram_user_id`, the primary key;
  - `fuel_type`, one of `diesel`, `95`, `98`;
  - `tank_volume`, an integer number of liters;
  - `consume_80`, liters per 100 km at 80 km/h, a float;
  - `consume_130`, liters per 100 km at 130 km/h, a float.
- A new Alembic revision creates the table.
- The bot gets the command `/car`, with the menu text "Enter car parameters".
- `/car` asks four questions in this order:
  - the tank volume in liters, a whole number of 30 or more;
  - the fuel type, chosen with a button;
  - the consumption at 80 km/h, a number more than 0 and less than 30;
  - the consumption at 130 km/h, with the same limits.
- After the last valid answer, the bot saves the four values.
- When the driver already has saved values, `/car` shows them first and asks "Do you want to change them?" with the buttons "Yes" and "No". "Yes" asks the four questions again. "No" keeps the values.
- An answer that breaks a limit gets an error message, and the bot asks the same question again.
- The bot offers three fuel types. They cover four of the six fuel names in the gas station table:

  | Fuel type | Button label | Station fuel names |
  | --- | --- | --- |
  | `diesel` | Diesel | `Gazole (B7)` |
  | `95` | 95 | `SP95-E10 (E10)`, `SP95 (E5)` |
  | `98` | 98 | `SP98 (E5)` |

  The code keeps the station fuel names of each type, so a later query can filter the stations by the fuel of a car.

## Capabilities

### New Capabilities

- `car-parameters`: what the bot stores about the car of a driver, how `/car` collects and changes the values, the limits on each value, and the fuel types that the bot offers.

### Modified Capabilities

- `runtime-store`: the requirement "Every persisted table is declared in one place" names exactly three tables. It changes to name `car` as a fourth table, with the reason to keep it.

## Impact

- New files: `french_tolls/car.py`, a new revision under `alembic/versions/`, `french_tolls/tests/test_car.py`, and `french_tolls/integration/test_car_dialog.py`.
- Changed files: `french_tolls/models.py`, `french_tolls/bot.py`, and `french_tolls/tests/test_gas_stations.py`. The last one asserts the full table list, so it must name `car`.
- `drive_button_handler` gets a callback pattern. Without it, the handler catches the presses of the new buttons.
- While the questions are open, a typed message is an answer, not a location. `6,5` is a valid consumption, and `parse_location` reads it as a location.
- No new dependency.
- Unchanged: the web service, the routing, the gas station run, and the build pipeline. No code reads the `car` table yet.
- Not in scope:
  - the use of the car values for fuel stops or fuel cost;
  - the fuel types E85 and LPG, and the station fuel names `E85 (E85)` and `GPLc (LPG)`;
  - a separate fuel type for a 95 car that cannot use E10;
  - electric cars, because no station in the table sells electricity;
  - a command that deletes the saved values.
