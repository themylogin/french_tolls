# French tolls

A tool that helps to save money on French toll roads.

* Site: https://french-tolls.undiscoveredlatitudes.com
* Reddit post: https://www.reddit.com/r/FranceTravel/comments/1eb190a/a_tool_to_save_money_on_french_toll_roads/
* Video presentation: https://youtu.be/MvvVoOzrodY
* Making of: https://youtu.be/iRt9NebmZfA

## Prerequisites

* Linux with Docker, the Compose plugin, and GNU make.
* 16 GB RAM. Graph preprocessing is the peak.
* 30 GB free disk: 4.8 GB for the OSM extract, 9.3 GB for the road graph,
  9.3 GB for the toll-weighted graph, and transient space for preprocessing.
  The Makefile refuses to start without 25 GB free at `OSRM_TOLL_PATH` and
  12 GB free at `OSRM_OPTIMAL_PATH`.
* Half an hour of preprocessing on 24 cores. Longer on fewer.

Every step runs in a container. If your user cannot reach the Docker socket, add
`DOCKER="sudo -n docker"` to each `make` command.

## Configuration

```
cp .env.example .env
```

Set `OSRM_TOLL_PATH` and `OSRM_OPTIMAL_PATH` to two different absolute paths
outside the repository. They hold the two routing graphs.

The other variables are optional:

| Variable | Purpose |
| --- | --- |
| `URL` | public address of the site, used in the links it emits |
| `OSRM_TOLL_URL`, `OSRM_OPTIMAL_URL` | another deployment's routers |
| `OSRM_ACCESS_TOKEN` | the token the relay checks and the client sends |
| `LOCATIONIQ_API_KEY` | the search box |
| `GOOGLE_DIRECTIONS_API_KEY` | route refinement |
| `GOOGLE_DIRECTIONS_MAX_REQUEST_PER_MONTH` | monthly ceiling for the above |
| `TELEGRAM_BOT_TOKEN` | the Telegram bot |
| `ULYS_SUBSCRIPTION_KEY`, `ULYS_PASSAGE_DATE` | option 2 only |

## Installation

### Option 1: use the pre-built data

`data/` holds the toll data for August 2026. It was built from the extract
below. Download that extract and build the two routing graphs from it:

```
curl -o data/france-latest.osm.pbf \
    https://french-tolls.undiscoveredlatitudes.com/download/france-latest.osm.pbf
make apply_segment_weights
```

No API key is needed for this option.

### Option 2: rebuild the data

Needs `ULYS_SUBSCRIPTION_KEY` and `ULYS_PASSAGE_DATE`. Read the key out of
https://www.vinci-autoroutes.com/fr/ with your browser's developer tools.

```
rm -f data/france-latest.osm.pbf
make clean clean-osrm
make all
```

`make all` downloads https://download.geofabrik.de/europe/france-latest.osm.pbf
and runs eleven steps. Each step is skipped or resumed when its output is
already in place, so an interrupted run continues where it stopped. The Vinci
API steps take several hours.

`clean-osrm` is required: the graph is rebuilt only when it is absent, and a new
extract must not be priced against a graph built from the old one.

## Run

Publish the front end with `docker-compose.override.yml`:

```yaml
services:
  nginx:
    ports:
      - "127.0.0.1:8080:80"
```

Then:

```
make web       # the site, on http://127.0.0.1:8080
make bot       # the Telegram bot
make app       # both
make app-down  # stop both
```

## Gas stations

`gas-stations` copies the fuel stations of https://www.prix-carburants.gouv.fr
into the application store:

```
docker compose run --rm gas-stations PT23H
```

The argument is an ISO 8601 duration. It updates stations that had the
last read more than that duration ago.

## Tests

```
make test
```
