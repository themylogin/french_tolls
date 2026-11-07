# Design

## Context

See `proposal.md` for the reason. The current state that shapes the approach:

- **Store.** The application uses one SQLite file, `/cache/database.db`, on the Compose volume `cache`. `french_tolls/db.py` opens it through `aiosqlite`, in WAL mode. `runtime-store` requires every store call to be a coroutine.
- **Schema.** Alembic owns the schema. The one revision, `alembic/versions/2026-08-30_17-46_baseline.py`, creates two tables. `alembic/env.py` sets `render_as_batch=True`. Only the `migrate` service applies revisions.
- **Image.** The root `Dockerfile` uses `debian:bookworm-slim`, Python 3.11, and the SQLite library of Debian (3.40.1). Python packages come from `requirements.txt`, which `make requirements` compiles from `pyproject.toml`.
- **Source, observed on 2026-11-07.**
  - The list endpoint returns JSON: 9,365 entries, about 1.1 MB. Each entry has `id` (an integer), `coordLatitude` and `coordLongitude` (strings), `deptCode`, `regionCode`, and `zipCode`. The latitudes are 41.391 to 51.065, and the longitudes are -4.723 to 9.547.
  - A station page is about 20 KB of HTML, and takes about 0.2 s. The page has no coordinates.
  - The price table is `table.details_pdv`. Each body row has the fuel in `<strong>`, the date in `span.date`, and the price in `td.prix strong`. A fuel that the station does not sell has `&nbsp;` for the date and an empty price cell. Each of nine sample pages had six fuel rows.
  - The block after the heading `Coordonnées station` is a `div.fr-pb-3v`. It holds `<strong>Marque :</strong> Leclerc<br/>Rue de quimper<br/>29520 Chateauneuf du faou`. The postcode and the town are one text node with a line break between them. All nine samples had a `Marque` line. An independent station shows `Indépendant sans enseigne`.
  - Each service is an `img.picto-service` with a `div.fr-pl-1w` that holds the name. The services section can be empty.
  - An unknown id returns the status 404.
  - Both endpoints answer the default user agent of `aiohttp`.

## Goals / Non-Goals

**Goals:**

- An area query costs an index search, not a scan of the station table.
- A run can stop at any point, and the next run continues from the stored state.
- The index cannot disagree with the station table, whatever code writes the table.
- The parser is tested against a real page, saved as a fixture.

**Non-Goals:**

- A price history. Each refresh replaces the row of the station.
- Retries in a run. A failed station stays stale, so the next run tries it again.
- Scheduling. The operator runs the command, or puts it in cron.
- The fields of the list that the page already shows (`deptCode`, `regionCode`, `zipCode`).
- A box that crosses the antimeridian. The query requires `west <= east`.

## Decisions

### D1. The geographic index is an SQLite R*Tree virtual table

The index is `gas_station_area(id, min_latitude, max_latitude, min_longitude, max_longitude)`. Each station has one entry, with `min = max` on each axis.

Alternatives:

- **SpatiaLite.** It needs a new Debian package in the image, an extension load on each connection (also through `aiosqlite`), and GeoAlchemy2. That is too much for a box query on points.
- **A composite B-tree on `(latitude, longitude)`.** SQLite uses the index for the latitude range only. It then reads every station in that band of latitude.
- **A geohash column.** One box needs several prefix ranges, and the edges need extra code.

Debian builds its SQLite with `SQLITE_ENABLE_RTREE`. The tasks include a check of `PRAGMA compile_options` in the built image.

### D2. Triggers keep the index equal to the table

The revision creates three triggers on `gas_station`:

- `AFTER INSERT` inserts the index entry;
- `AFTER UPDATE OF latitude, longitude` updates the index entry;
- `AFTER DELETE` deletes the index entry.

The SQLite `UPSERT` fires the `UPDATE` triggers when it takes the `DO UPDATE` path, so the upsert of the run moves the entry too.

Alternative: the run writes both rows in one transaction. Then each other writer (a test, a manual fix, a later change) must remember the index. A trigger makes the database keep it. Also, SQLite does not allow `UPSERT` on a virtual table, so the code would need `INSERT OR REPLACE` there.

### D3. The station table keeps the exact position; the index is a filter

An R*Tree stores 32-bit floats. It rounds a lower bound down and an upper bound up. At the latitudes of France this error is less than 1 m. So an entry can match a box that its station is just outside.

The area query therefore has two conditions:

1. an overlap test on the index, which selects the candidates;
2. a `BETWEEN` test on `gas_station.latitude` and `gas_station.longitude`, which gives the exact answer with inclusive edges.

```python
select(GasStation)
.join(GasStationArea, GasStationArea.id == GasStation.id)
.where(
    GasStationArea.max_latitude >= south,
    GasStationArea.min_latitude <= north,
    GasStationArea.max_longitude >= west,
    GasStationArea.min_longitude <= east,
    GasStation.latitude.between(south, north),
    GasStation.longitude.between(west, east),
)
```

A test reads `EXPLAIN QUERY PLAN` and requires `VIRTUAL TABLE INDEX` for `gas_station_area`.

### D4. Both structures are models; autogenerate ignores the index

`french_tolls/models.py` declares two new models:

| Model | Table | Columns |
| --- | --- | --- |
| `GasStation` | `gas_station` | `id` Integer primary key (the source id, no autoincrement); `latitude`, `longitude` Float, not null; `name` Text, nullable; `address`, `services`, `prices` JSON, not null; `last_updated_at` DateTime, not null |
| `GasStationArea` | `gas_station_area` | `id` Integer primary key; `min_latitude`, `max_latitude`, `min_longitude`, `max_longitude` Float |

The column for the prices is `prices`, not `price`, because it holds a list.

`last_updated_at` is a naive UTC datetime. SQLite has no time zone type. The SQLAlchemy `DateTime` type on SQLite drops the offset, and it compares values as text. Naive UTC values on both sides keep that comparison correct.

`alembic/env.py` gets an `include_object` hook. It hides `gas_station_area` and its internal tables (`gas_station_area_node`, `gas_station_area_parent`, `gas_station_area_rowid`) from autogenerate. Without it, autogenerate proposes to drop the internal tables and to create the virtual table as a plain table. A test runs `alembic check` after `upgrade head`, so the models and the revisions must agree.

The revision creates `gas_station` with `op.create_table`. It creates the virtual table and the triggers with `op.execute`, as the `runtime-store` delta permits.

### D5. BeautifulSoup with the built-in parser reads the page

The parser uses `beautifulsoup4` with `"html.parser"`. The package is pure Python.

Alternatives:

- **`html.parser.HTMLParser` alone.** It needs a hand-written state machine for three sections.
- **`lxml`.** It is a compiled package. Speed does not matter at 20 KB per page.
- **Regular expressions.** They break on small changes of the markup.

The parse rules:

- **Prices.** For each row of `table.details_pdv tbody`, the fuel is the first `strong`, the date is `span.date`, and the price is `td.prix strong`. A row without a price is skipped. A row with a price and no date is a parse error, because it cannot make a triple. This was not seen in the samples. The date is `datetime.strptime(text, "%d/%m/%y").date().isoformat()`.
- **Name and address.** The parser splits the children of the station block at each `br`. It joins the text of each part, and reduces each run of white space to one space. When the first line matches `^Marque\s*:\s*(.*)$`, the group is the name, and the other lines are the address. Otherwise the name is null and every line is an address line.
- **Services.** The names are the `div.fr-pl-1w` texts in the column with the heading `Services`.
- **Errors.** A page without the price table or without the station block raises a parse error. The run then counts the station as failed.

### D6. ISO 8601 durations come from `isodate`

`isodate.parse_duration` is the `type=` of the `argparse` argument. An invalid value makes `argparse` exit with the status 2 before the run sends a request. The function returns a `timedelta`, or an `isodate.Duration` for years and months. Both can be subtracted from a `datetime`.

Alternative: a regular expression for `P[nD]T[nH][nM][nS]`. It needs its own tests for weeks, fractions, and order, and the library already has them.

### D7. One run, step by step

1. Parse the arguments. Configure logging from `config.log_level`, as `web.py` does.
2. Set `started_at` to the current UTC time, and `cutoff` to `started_at - max_age`.
3. Read the list. Check that it is a list of objects, each with an integer `id` and two coordinates that convert to `float`. When the check fails, log the reason and exit with the status 1.
4. Read `(id, last_updated_at)` of every stored station in one query.
5. Select each listed station that has no row, or whose `last_updated_at` is before `cutoff`.
6. Read the selected pages with `asyncio.gather`, through `asyncio.Semaphore(4)`, in one `aiohttp.ClientSession` with a total timeout of 30 s per request.
7. For each page: require the status 200, parse the page, and take the UTC time of the read. Then upsert the row in its own session and commit it. The upsert is `insert(GasStation).on_conflict_do_update(...)`, the same form as `autocomplete.py`.
8. Log the counts: listed, selected, refreshed, failed. Exit with the status 1 when a station failed, and with 0 otherwise.

The run catches `aiohttp.ClientError`, `asyncio.TimeoutError`, and the parse error for each station. It does not catch a store error. A store that cannot be written stops the run, as elsewhere in this project.

The base URL is a parameter of the update function, with the default `https://www.prix-carburants.gouv.fr`. The tests start a local `aiohttp` server and give its URL. No test reaches the network.

### D8. The Compose service puts the module in `entrypoint`

```yaml
gas-stations:
  build: .
  entrypoint: ["python3", "-m", "french_tolls.gas_stations"]
  depends_on:
    migrate:
      condition: service_completed_successfully
  volumes:
    - "cache:/cache"
  environment:
    LOG_LEVEL: "${LOG_LEVEL:-INFO}"
  profiles: ["gas-stations"]
```

`docker compose run SERVICE ARGS` replaces `command` and keeps `entrypoint`. So `docker compose run --rm gas-stations PT23H` gives `PT23H` to the module. There is no default age, so the operator states it each time.

`migrate` adds `gas-stations` to its `profiles`. Compose enables the profile of a service named on the command line, but not the profiles of its dependencies. The `recorder` service uses the `record` profile for the same reason.

The service has no `env_file`, because the run needs no key.

### D9. One module, one test file, one fixture

- `french_tolls/gas_stations.py`: the parser, the area query, the update, and `main`.
- `french_tolls/tests/test_gas_stations.py`: the tests. They migrate a temporary store with Alembic, as `test_spending.py` does.
- `french_tolls/tests/station_29520005.html`: the page of 2026-11-07, without the header, the footer, and the scripts.

## Risks / Trade-offs

- [The site changes its page layout, and every station fails.] → The run logs each failure and exits with the status 1. The rows keep their old data, and `last_updated_at` shows their age. The fixture test shows which rule broke.
- [The source blocks or limits the run. Imperva is in front of the list endpoint.] → No more than four requests are open at once. A failed station is tried again by the next run.
- [A later batch revision copies `gas_station`. SQLite drops the triggers with the old table.] → That revision must create the triggers again. The revision of this change has a comment that says so. The trigger tests run against `head`, so they find a missing trigger.
- [A station that leaves the list keeps its old prices.] → A caller can filter on `last_updated_at`. A later change can delete such stations.
- [Four tasks write to one SQLite file while `web` or `bot` also write.] → Each upsert is one short transaction. WAL lets readers continue. The default busy timeout of 5 s of the driver covers the wait.
- [A full run takes time.] → About 9,366 requests at about 0.2 s, four at once, is about 8 to 10 minutes. The first real run took 6 minutes. An interrupted run keeps each committed station.

## Migration Plan

1. Build the image. Run `docker compose run --rm gas-stations PT23H`. `migrate` applies the new revision. The revision adds objects only, and does not change the two existing tables.
2. To refresh each day, the operator adds the same command to cron.

Rollback: `docker compose run --rm migrate alembic downgrade -1`. The downgrade drops the triggers, then `gas_station_area`, then `gas_station`. The two existing tables do not change.
