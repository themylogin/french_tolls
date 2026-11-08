# Design

## Context

See `proposal.md` for the reason. The current state that shapes the approach:

- **The run.** `update` in `french_tolls/gas_stations.py` reads the list, selects the stale stations, and calls `_refresh` for each one. `_refresh` reads the page and upserts the row with the list position. A trigger moves the R*Tree entry when the position changes.
- **The OSM file.** `osm-gas-stations` writes `/cache/osm_gas_stations.json` in the same `cache` volume. It maps each id to a list of nodes (`latitude`, `longitude`, `tags`) and areas (`area`, `tags`). Its spec is `osm-gas-stations`.
- **Libraries.** `overlap.py` already uses `pyproj.Geod(ellps="WGS84")` for distances and `shapely` for geometry.
- **Data, studied on 2026-11-08.** The file had 10,079 ids. The store had 9,357 stations.
  - 9,334 stations have a candidate: 9,259 have one, and 75 have two or more. 23 have none.
  - The OSM positions are not copies of the list. Only 28 of 6,514 nodes are on the 0.00001° grid of the ministry data, though about 6,400 objects cite it as `source`. The import added tags to objects that mappers had placed.
  - Distance from the list position to the nearest candidate: median 53 m, 90th percentile 434 m, 99th percentile 2.2 km, largest 14.6 km. 372 stations are more than 1 km away.
  - The brand of the nearest candidate agrees with the stored brand for about 97% of the stations, in every distance band, also beyond 5 km. The OSM postcode agrees for 96%, where OSM has one (24% of the objects). So a far candidate is almost always the same station, and the list position is wrong. Spot checks confirm it: Épône (10 km), Cahors (8 km), and Cevins (14.6 km) are in their towns in OSM, and not in the list.
  - Most brand disagreements are rebrands: Esso and BP (71), Netto and Intermarché (26), Carrefour and Cora (18), Avia and Total (17).
  - No area has fewer than three points or a zero surface.

## Goals / Non-Goals

**Goals:**

- Each stored position comes from a rule that the data supports.
- The price refresh never fails because of the OSM file.
- No brand table to maintain.

**Non-Goals:**

- A new position for a station that the run does not refresh. A daily `PT23H` run refreshes every station anyway.
- A match without the prix-carburants id, for example by distance.
- A record of the source of each position.

## Decisions

### D1. The run reads the file once, before the pages

`update` loads `/cache/osm_gas_stations.json` with `json.load` after the list read, and before the page reads. `_refresh` gets the candidates of its station from that dict.

The file is 6.3 MB, and the parse takes less than a second. It is a blocking call in a coroutine, but nothing else runs in the process at that time.

The path is a parameter of `update`, with the default `/cache/osm_gas_stations.json`, as `base_url` is. The tests give a path in a temporary directory.

When the file is missing, or `json.load` fails, or the result is not a `dict`, the run logs a warning and uses an empty dict. So every station gets its list position.

Alternative: read the file in `_refresh`, once per station. That is 9,357 parses of 6.3 MB.

### D2. The choice is a pure function

```python
def osm_position(candidates, brand, listed):
```

It returns `(latitude, longitude)`, or `None` when no candidate is left. `_refresh` calls it with the candidates of the station, the `name` parsed from the page, and the list position. It stores the result, or the list position on `None`. The tests call the function without a server.

The steps:

1. **Position.** A node gives `(latitude, longitude)`. An area gives the centroid of `shapely.Polygon` over its points as `(longitude, latitude)`.
2. **Distance limit.** Drop each candidate more than 20 km from the list position. The distance is `Geod(ellps="WGS84").inv(...)`, as in `overlap.py`.
3. **Brand.** When more than one candidate is left and the brand is not null, take the first word of the brand. Fold case and accents of the word and of `brand | name | operator`: NFKD, drop the combining marks, then lowercase. Keep the candidates whose text contains the word, if there is one or more.
4. **Nearest.** Return the position of the candidate nearest to the list position.

### D3. The limit is 20 km

The largest gap on 2026-11-08 is 14.6 km. It is a list error: the list puts the Cevins station near Moûtiers. The brand agrees at all distances, so a lower limit would refuse correct positions. At 1 km, 372 stations would keep a wrong position. The limit only guards against an id typo in OSM that points to a station in another region.

Alternatives:

- **No limit.** One wrong digit in an OSM id moves a station across France.
- **1 km or 5 km.** It keeps 372 or 20 wrong list positions.

### D4. The first word of the brand breaks ties

On the 75 stations with several candidates, the study compared three rules: the nearest candidate, the nearest car pump, and the nearest candidate with the same brand family. They agree on 72 stations. Of the other 3:

- 26700001 (Carrefour Market): the nearest is a TotalEnergies 606 m away. The Carrefour Market is 1.85 km away.
- 51500002 (Leclerc): the nearest is PETRO-EST 253 m away. The Leclerc is 464 m away.
- 18170001 (Système U): the car and truck forecourts are 22 m apart.

The first word of the stored brand gives the right station in the first two cases. It also changes 2 more choices, between two objects of the same site, 3 m and 142 m apart.

Alternatives:

- **A table of brand families.** It needs about 20 patterns and their upkeep. It also gives a wrong answer after a rebrand.
- **A car pump filter, as in the study.** It changes one choice, by 22 m.
- **A brand check on a single candidate.** Brand mismatches are rebrands, and they do not get more frequent with distance. A check would refuse about 3% of correct positions.

### D5. The postcode is not used

OSM has `addr:postcode` on 24% of the objects. Where the postcodes differ, they are neighbor postcodes of the same place, for example `13700` and `13180` on the A55. The check would refuse correct positions and add nothing.

### D6. The counts are in the final log line

`_refresh` returns a result per station that tells success and the source of the position. `update` counts the stations that got an OSM position and the stations that got the list position. It adds both counts to its final log line.

## Risks / Trade-offs

- [An OSM object has a copied id, and the station has no brand word in common with it.] → The nearest rule can choose the wrong station. On 2026-11-08 this applied to no station: the brand rule fixed both cases found.
- [An OSM mapper moves a station by mistake.] → The next run stores the wrong position. The same risk exists today with the list. The run writes the source counts, so a large change is visible.
- [The OSM file is old.] → An old file still gives better positions than the list. Its age does not change the rules.
- [`osm-gas-stations` runs while `gas-stations` reads the file.] → `osm-gas-stations` replaces the file with one rename, so the reader gets the old file or the new file, never part of one.
- [The chosen candidate changes from one run to the next.] → Only the 75 stations with several candidates can switch, and only when their list position or OSM changes.

## Migration Plan

1. Deploy. Run `docker compose run --rm osm-gas-stations`, then `docker compose run --rm gas-stations PT23H`.
2. The positions change when the run refreshes each station. A full `PT23H` run refreshes all of them.

Rollback: revert the code. The next run that refreshes a station stores its list position again.
