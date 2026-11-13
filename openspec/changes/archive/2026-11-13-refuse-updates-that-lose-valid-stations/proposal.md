# Proposal

## Why

A `gas-stations` run stores what each station page shows, with no check on the result. A layout change or a mass of empty price rows on `prix-carburants.gouv.fr` can replace good rows with rows that have no diesel or 95 price. The application then loses most of the stations that a driver can use. A run must refuse such an update and keep the store as it was.

## What Changes

- A new term, **valid station**: a stored station whose prices hold an entry for a fuel of the type `diesel` and an entry for a fuel of the type `95`. `car-parameters` gives the fuels of each type: today `Gazole (B7)`, and `SP95-E10 (E10)` or `SP95 (E5)`. The date of the price does not matter.
- The run reads every selected page first. Then it writes all the read stations in one transaction.
- In that transaction, the run counts the valid stations in the store before the writes and after them. When the after count is 80% or less of the before count, the run:
  - rolls the transaction back, so no row changes;
  - logs both counts;
  - exits with the status 1.
- **BREAKING**: a run that stops early stores nothing. Before this change, each station had its own commit, and an interrupted run kept its stored stations. The requirement "Each station is stored in its own transaction" is removed.
- The summary line `… stations refreshed (…), … failed` appears only when the run stores its stations. A refused run logs the refusal line instead.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `gas-station-inventory`:
  - adds the definition of a valid station;
  - adds the refusal of a run that loses too many valid stations;
  - adds one transaction for all the stations of a run;
  - removes "Each station is stored in its own transaction";
  - limits "The run logs the source of the positions" to a run that stores its stations.

## Impact

- Changed files: `french_tolls/gas_stations.py`, `french_tolls/tests/test_gas_stations.py`, `README.md`.
- No schema change, no new dependency, no change to the Compose service.
- A full run takes 6 to 10 minutes. When it stops early, the next run reads every page again.
- The run holds the SQLite write lock for one transaction of up to about 9,500 upserts, not for 9,500 short ones.
- Unchanged: the web service, the bot, the refuel planning, and the OpenStreetMap position rules.

## Assumptions to review

- When the store has no valid station before the run, the run is never refused. Without this rule, a run on an empty store that gets no valid station fails, and so does a run that selects no station.
- The counts cover every stored station, also the stations that left the open list.
- A failed station does not stop the check. The run checks the stations that it read. Failures and a refusal both give the status 1.
- No option forces a refused update. Do you want one, for example for a real drop in the number of stations?
