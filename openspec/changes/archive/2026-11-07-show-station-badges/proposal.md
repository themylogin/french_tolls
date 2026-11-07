# Proposal

## Why

The station list of the gas station dialog shows the name, the distance, the price, and the detour. It does not show whether a station sells fuel at any hour, or whether it is on a motorway. A driver at night or on a motorway needs this to choose a stop. The store already holds the services and the address lines of each station.

## What Changes

- Each station of `POST /api/refuel` gets a `badge`: `"24"`, `"Autoroute"`, `"Aire"`, or `null`. The first rule that matches gives the badge:
  1. `24` when the services contain `Automate CB 24/24`;
  2. else `Autoroute` when an address line contains `autoroute`, in any letter case;
  3. else `Aire` when an address line contains the word `aire` followed by `de`, `des`, `du`, or `d'`, in any letter case.
- In rule 3, `aire` must not follow a letter. So `Saint hilaire de brens` and `Zi portuaire des mielles` get no badge. `A71aire de ste thorette` gets `Aire`, because the source dropped the space after the motorway number.
- The dialog shows the badge in bold after the name link, for example `Leclerc` **24**. A row shows at most one badge.
- On 2026-11-07, the store gives `24` to 5,395 stations, `Autoroute` to 136, `Aire` to 77, and no badge to 3,749.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `refuel-planning`: a new requirement says that each listed station carries a `badge`, and which rule gives it.
- `web-front-end`: the requirement "The dialog lists the stations of the answer" changes. A row shows the badge in bold after the name link.

## Impact

- Changed files: `french_tolls/refuel.py`, `french_tolls/tests/test_refuel.py`, and `www/index.js`.
- The answer of `POST /api/refuel` gets one more key for each station. The answer does not send the services list.
- No new dependency, no schema change, and no new router request.
- Unchanged: the ranking, the cost, the bot, and `/api/calculate`.
- Not in scope:
  - other services of the station page, for example `Lavage automatique`;
  - a filter or a ranking by badge;
  - a badge on the map.
