# Proposal

## Why

The project holds no data about fuel stations. The government site `prix-carburants.gouv.fr` publishes every open station with its prices and services. A local copy with a geographic index lets the application find the stations in an area without one request per station.

## What Changes

- A new table, `gas_station`, stores one row per station:
  - the station id from the source, as the primary key;
  - latitude and longitude;
  - the brand, with the `Marque :` label removed (for example, `Leclerc`);
  - the address lines, as a JSON list (for example, `["Rue de quimper", "29520 Chateauneuf du faou"]`);
  - the services, as a JSON list (for example, `["Lavage automatique"]`);
  - the prices, as a JSON list of `[fuel, ISO date, price]` triples (for example, `["SP95-E10 (E10)", "2026-11-06", "1.999"]`);
  - `last_updated_at`, the UTC time this project last read the station page.
- A new R*Tree index, `gas_station_area`, holds the position of each station. Database triggers keep it equal to `gas_station`.
- A new Alembic revision creates the table, the index, and the triggers.
- A new module, `french_tolls/gas_stations.py`, does the update:
  - it reads the open station list from `https://www.prix-carburants.gouv.fr/map/recupererOpenPdvs/`;
  - it selects each listed station that has no row, or whose row is older than a given ISO 8601 duration;
  - it reads `https://www.prix-carburants.gouv.fr/station/<id>` for each selected station and parses the HTML;
  - it writes each station in its own transaction.
- The same module gives a query that returns the stations in a latitude and longitude box through the index.
- A new Compose service, `gas-stations`, runs the update. The operator starts it with `docker compose run --rm gas-stations PT23H`.
- The `migrate` service joins the `gas-stations` profile, so the schema is applied before the update starts.
- `beautifulsoup4` and `isodate` become dependencies. `requirements.txt` is compiled again from `pyproject.toml`.

## Capabilities

### New Capabilities

- `gas-station-inventory`: which fuel stations the project stores, what it stores for each one, how a run selects and refreshes stale stations, and how a caller finds the stations in an area.

### Modified Capabilities

- `runtime-store`: the requirement "Every persisted table is declared in one place" names exactly two tables. It changes to name `gas_station` as a third table. It also permits the revision to create the R*Tree index and its triggers with hand-written statements, because SQLAlchemy cannot declare them.

## Impact

- New files: `french_tolls/gas_stations.py`, a new revision under `alembic/versions/`, unit tests and an HTML fixture under `french_tolls/tests/`.
- Changed files: `french_tolls/models.py`, `alembic/env.py`, `docker-compose.yml`, `pyproject.toml`, `requirements.txt`, `README.md`.
- External load: one run reads the list (about 1.1 MB) and one page per stale station. On 2026-11-07 the list held 9,365 stations, so a full run makes about 9,366 requests.
- Unchanged: the web service, the bot, the routing, and the build pipeline. No current caller reads the new table.
- Not in scope:
  - showing stations or prices on the page or in the bot;
  - removing a station that is no longer in the open list;
  - storing the station label at the top of the page (for example, `Loc'halles`).
