## Context

See `proposal.md` — Why. What was measured before writing this:

- All twelve gare-less booths carry an OSM `name` tag. Checked against `data/filtered.osm.pbf`, which the pipeline already produces and which already contains these nodes.
- Three of the twelve carry a tariff: `1391610490` Hochfelden 1.40 EUR, `12288199204` and `12752375307` both Péage de Vienne 1.90 EUR. The other nine carry none — four `gantry`, five absent from the price file.
- The two Péage de Vienne nodes are 300 m apart and each priced 1.90 EUR. An A7 route past Vienne was driven through the accounting and crosses exactly one, charging 1.90 once. They are opposite carriageways, and nothing is double-charged.
- `build_osm_toll_booths.py` reads every booth node's tags already — it uses them to decide `barrier=toll_booth` against `highway=toll_gantry`. The name is in hand and thrown away.
- `french_tolls/data.py` builds `Booth.name` from `vinci_toll_booth.yaml` alone, and `Booth.label` falls back to `f"OSM node {node_id}"`.

## Goals / Non-Goals

**Goals:**

- A passage list a driver can read.
- A list that omits what cannot be acted on, and never omits money.
- The inventory carrying a fact it already had in hand.

**Non-Goals:**

- Finding out why those twelve have no gare. Nine carry no tariff either, so a name does not price their journeys any better. That is `vinci-gare-mapping`'s question.
- Grouping the co-located pairs. Chanas, Bernay and Rosny-sur-Seine each appear twice 12–30 m apart and are probably one plaza each; whether the plaza rule should merge them is a question about `toll-booth-inventory`'s grouping, not about names, and merging them on the strength of a shared name would be guessing.
- Correcting or translating OSM names. `Péage de Vienne` keeps its "Péage de".

## Decisions

### The name is recorded, not derived

`build_osm_toll_booths.py` writes `name` when the node has the tag, and omits the key when it does not. Recording the absence as an empty string would make a reader test two things.

Aliases carry it too. An alias is a lane of a plaza and may be tagged separately; the inventory already records each lane's own `latlon` for the same reason, and a consumer resolving a lane to its plaza takes the plaza's name anyway.

*Alternative rejected:* having the application read `filtered.osm.pbf` at start-up. It is 20 MB of PBF, the application has no OSM toolchain, and the pipeline is the thing that reads extracts.

### Naming falls through three sources

`Booth.label` becomes: operator name, then OSM name, then node id.

The operator's name first because it is painted on the barrier. `VOREPPE BARRIERE` is what the driver sees; if OSM calls that node something else, the operator wins.

The node id survives as the last resort. No booth needs it today, and that is the point — a fallback is for the case that has not happened yet.

### What is listed and what is only counted

Two rules, and they pull apart on purpose:

| passage | listed | counted unpriced |
| --- | --- | --- |
| priced, any type | yes | — |
| `passthrough` or `gantry`, no tariff | **no** | yes |
| ticketed section, tariff missing | yes | yes |
| exit with no entrance, entrance never closed | yes | yes |

The dividing line is whether a reader can do anything with the line. A gantry with no tariff has no amount and its name adds nothing to a road already on the screen. A ticketed section has two named ends and a charge of real size that the driver will pay; hiding it hides money.

The count is kept in both cases. `unpriced` stays the number of passages that could not be priced, whether or not each was printed — so the answer never stops admitting a toll is missing.

*Consequence, stated rather than discovered later:* `len(peages)` no longer equals the number of accounted crossings. Anything deriving one from the other breaks. Nothing does today: the page iterates `peages`, the bot reads `cost`, and the evaluation reads distances and durations.

### `X €`

The page renders a null cost as `X €`.

`—` was chosen when an unpriced passage might be anything. Now every passage that survives to the list is a charge the driver will pay, and only its size is unknown. `—` reads as *nothing to pay*, which is the opposite of the truth. `X €` reads as a form with a blank in it.

The reason stays on the row's tooltip.

### Re-running the booth step

`make build_osm_toll_booths` rewrites `data/osm_toll_booths.yaml`, which moves the data fingerprint. That invalidates every cached answer and every stored refinement, by design — the fingerprint exists to do exactly this.

The evaluation's corpus is **not** affected. `report.py` reads `data/google_routes/` directly and carries no fingerprint stamp — the stamp belonged to the unit suite's golden fixture, which `unit-test-the-algorithm` removed. Checked: the report prints its 20 journeys and mean multiplier of x0.9239 after the rewrite exactly as before. The corpus remains a valid pre-refinement baseline and needs nothing done to it.

The step is existence-based, so the file must be removed for it to run at all.

## Risks / Trade-offs

- **Hiding an unpriced gantry hides a charge.** A driver crossing one pays something the total does not include and the list does not mention. → `unpriced` still counts it, and the page can say so. This is the trade the change is asked for; it is stated in the proposal as breaking.
- **The OSM name may be wrong or stale.** OSM is edited by anyone. → It only ever applies where the operator has no name at all, so it replaces a node id rather than an authority.
- **Rewriting a committed artefact.** → It is regenerated from the extract by a documented step, and the diff is one key per booth.
- **Every cache invalidated.** → Answers recompute in under a second. Two refinements would cost two Google requests to rebuy, and only if someone asks.
- **A name shared by two nodes 300 m apart** now shows twice in a list if a route crosses both. → Measured: an A7 route crosses one. If a route is ever found crossing both, that is evidence for the grouping question this change deliberately leaves alone.

## Migration Plan

1. Record the tag in `build_osm_toll_booths.py`.
2. Remove `data/osm_toll_booths.yaml` and re-run `make build_osm_toll_booths`; confirm the diff is additive.
3. Read `name` in `data.py`; fall through in `Booth.label`.
4. Change what `tolls.py` lists.
5. Change the page's cell to `X €`.
6. Verify a real journey's passage list before and after.

Rollback is restoring the previous `osm_toll_booths.yaml` and reverting four files; nothing else reads the new key.

## Open Questions

None. Whether the co-located pairs should be merged is deliberately out of scope, and is recorded in Non-Goals rather than left as a question this change is expected to answer.
