## Why

A passage list that reads `OSM node 12636038011` tells a driver nothing. Twelve of the 1 295 booths have no gare mapping, so they have no operator name, and the accounting falls back to the node id — which is honest and useless.

They are not nameless. Every one of the twelve carries an OSM `name` tag: Chanas, Bernay, Hochfelden, Cholet Sud, Péage de Vienne, Rosny-sur-Seine, Cagny, Beuzeville. The pipeline reads those nodes, sees the tag, and discards it, because `osm_toll_booths.yaml` records only position, onward nodes, and type.

The names also say something the ids hid. Six of the twelve are three co-located pairs — Chanas 30 m apart, Bernay 12 m, Rosny-sur-Seine 17 m — and two more, both `Péage de Vienne`, sit 300 m apart each carrying 1.90 EUR. A route driving the A7 past Vienne was checked and crosses only one, so nothing is double-charged; but that was a question the id-only listing could not even raise.

Three of the twelve carry a real tariff and are charged. The other nine cannot be priced, and listing them as `—` beside a node id is noise a driver cannot act on.

## What Changes

### The inventory carries the OSM name

- **BREAKING** `data/osm_toll_booths.yaml` gains a `name` on every entry whose node has an OSM `name` tag, representative and alias alike. The file is a committed artefact, so this rewrites it and moves the data fingerprint.
- The name is recorded as the extract states it, unaltered. It is what OSM says the place is called, not a decision this pipeline makes.

### A passage is named by whatever names it best

- A booth with a gare mapping keeps the operator's name, as today. The operator's name for a barrier is what a driver sees on the road.
- A booth without one takes its OSM name. `Péage de Vienne` is a name; `OSM node 12288199204` is a fact about a database.
- A booth with neither keeps the node id. There are none today, and a fallback that identifies nothing is worse than one that is ugly.

### A toll that cannot be priced is not always worth listing

- **BREAKING** A `passthrough` or `gantry` carrying no tariff SHALL NOT appear in the passage list. There is nothing to say about it: no amount, and a name that adds nothing to a route the driver is already looking at.
- It SHALL still be counted as unpriced. The journey continues to admit that something was crossed and not charged; it simply stops printing a line the reader cannot use.
- A ticketed section whose tariff is missing SHALL still be listed, named at both ends, with its cost shown as an explicit unknown rather than a dash. An entrance and an exit are a real charge of a real amount; the driver will pay it, and saying so is worth a line where a nameless gantry is not.

### The unknown amount looks like an amount

- **BREAKING** A passage that carries a real charge of an unknown size SHALL be displayed as `X €` rather than `—`. A dash reads as nothing; `X €` reads as a price nobody has filled in, which is what it is.

## Capabilities

### Modified Capabilities

- `toll-booth-inventory`: the output format requirement enumerates what an entry carries and does not include a name.
- `journey-toll-accounting`: the naming requirement says a booth without a gare is named by its node id; the unpriceable-passage requirement says every such passage is recorded.
- `web-front-end`: the currency requirement says a passage with no amount is shown as a marker that is plainly not a price, which is now true of only some of them.

## Impact

- Modified: `builder/build_osm_toll_booths.py` (record the tag), `data/osm_toll_booths.yaml` (rewritten, committed), `french_tolls/data.py` (read it), `french_tolls/tolls.py` (naming and what is listed), `www/index.js` (the `X €` cell).
- Unchanged: the waypoint search, the refinement, the pipeline's other ten steps, the unit suite's subjects.
- **The data fingerprint moves.** Every cached route answer and every stored refinement is invalidated. Answers recompute in under a second; the two refinements bought today would cost two Google requests to buy again, and only if someone asks for them.
- The evaluation's 20-journey corpus is unaffected: `report.py` reads the stored answers directly and carries no fingerprint stamp. It remains a valid pre-refinement baseline.
- Not addressed: why those twelve have no gare mapping. Nine of them carry no tariff either, so a name does not make their journeys better priced. The missing money is the real gap and it belongs to `vinci-gare-mapping`, not here.
