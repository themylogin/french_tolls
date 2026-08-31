## Why

Twenty-one settings are read in nine modules, each with its own spelling of the same three lines: name the variable, pick a default, coerce the string. There is no list of them anywhere.

Writing that list is the whole value of this change, and it produced a result worth having before a line of it is implemented. **Twelve of the twenty-one are not settings at all.** No environment has ever given any of them a value:

```
  DATA_DIR            hardcoded to /data in all five Compose services
  CACHE_DIR           hardcoded to /cache in four
  PORT                nginx proxies to 8080; changing it breaks the front end
  OSRM_TIMEOUT_S      in no .env, no .env.example, no Compose file
  GOOGLE_TIMEOUT_S    the same
  REFINE_CORRIDOR_M   the same, and its default is another module's constant
  OSRM_TOLL_URL       the routers are addressed by Compose service name; there
  OSRM_OPTIMAL_URL      is one network and the published ports refuse connections
  GOOGLE_FIT_THRESHOLD  0.98, chosen because the corpus leaves an empty band
                        between 97.7% and 99.5%. The evaluation reads the
                        constant, not the variable, so the two already agree
                        without it
  MAX_WAYPOINTS       9, which is what a Google Maps URL carries. Raising it
                        makes the search place waypoints the link silently drops
  QUERY_BUDGET        a runaway guard on local routing requests, not a dial
  SNAP_REACH_M        1000, and it does not work: bot.py rejects at a literal
                        1000 and says "kilometer" in prose, so moving the
                        variable moves the router's reach and nothing else
```

Nothing could have noticed. `route-service` already requires `.env.example` to document every setting, and the only way to enumerate them was to grep the source — which is how these were found. A knob that turns nothing is worse than no knob: it invites a reader to set `PORT` and wonder why the site went down.

## What Changes

- **`french_tolls/config.py`**, holding one documented, typed settings object. `from .config import config`, and `config.public_site_url` is a `str`, `config.query_budget` an `int`, `config.debug` a `bool`. **Nine settings**, each one something an operator really sets.
- **The eleven non-settings become plain constants** where they are used, with a comment saying who fixes the value: `/data` and `/cache` because Compose mounts them there, `8080` because nginx proxies to it, the service names because there is one network, `9` because that is what a URL carries, and `0.98` because it was measured.
- **The reach stops being three values.** `SNAP_REACH_M` is fixed in `osrm.py`, and `bot.py` reads that constant instead of its own literal `1000`, so the router's reach, the bot's check and the words "not within a kilometer" finally agree.
- **The query budget is raised from 500 to 1000** and stays in `osrm.py`. It is a runaway guard rather than a setting: the dearest journey measured costs 325, and doubling the ceiling buys headroom for a graph that grows without anyone editing an environment to get it.
- **`REFINE_CORRIDOR_M` is deleted outright.** `refine` uses `geometry.DEFAULT_CORRIDOR_M` directly, which is what the evaluation already does. One corridor, one place, and the environment stops offering a second answer.
- **No module under `french_tolls/` reads `os.environ`** except `config.py`.
- **One reader, not five.** `_env` returns the variable or its default, treating empty as unset; `int` and `float` do the rest, and a value that is not a number stops the service on its own. No wrapper exists to reword an error that was already clear.
- `evaluation/` and `builder/` keep their own reads. Separate images, separate lifecycles, and `builder` cannot import the package.

## Capabilities

### New Capabilities

None. This is one place for behaviour that is already specified, not new behaviour.

### Modified Capabilities

- `route-service`: the requirement `Configuration is read from the environment`. It gains the demand that the settings be declared in one typed place, that nothing else read the environment, and that the documentation be checked. Its opening list is corrected: it names the published port, the fit threshold and the routers' addresses, none of which anything configures, and the wage, which belongs to `toll-weighted-graph` and is a parameter of the pipeline rather than of the application.

## Impact

- `french_tolls/config.py` — new, nine settings.
- `french_tolls/{api,autocomplete,data,db,osrm,refine,service,web,bot}.py` — 24 reads replaced or removed.
- `.env.example` — one setting documented: `GOOGLE_ROUTES_ENDPOINT`.
- **`GOOGLE_ROUTES_ENDPOINT` stays configurable**, though Compose hardcodes it. It is the seam that makes `drive-flow-integration-tests` unable to spend money — pointed at the replay server, a real key in the environment buys nothing — and that capability requires it. Hardcoding it would break a requirement shipped this week.
- **No externally visible behaviour changes.** Every default keeps its value, `URL` still refuses to start when unset, the Google key stays optional. Three exceptions. Two are corrections: an empty integer or float now reads as its default instead of raising `ValueError` at import, and `DEBUG=FALSE` now means off. The third is deliberate: **the query budget doubles to 1000**, which lets a search issue more local routing requests before it is cut off, and bounds a worst case at about four seconds rather than two.
- 111 unit tests and 59 integration tests must pass unchanged. The unit suite imports `osrm`, `data`, `search`, `tolls`, `refine`, `drive`, `equivalence` with **no environment at all**, so nothing the config does may require a value to import.
