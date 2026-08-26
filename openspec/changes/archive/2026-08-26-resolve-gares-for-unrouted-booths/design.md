## Context

See `proposal.md` — Why. The requirements are in `specs/`.

Three facts about the current pipeline shape the approach.

- Step 3 (`build_osm_toll_booths.py`) already builds a directed graph over the through road classes from the carved plaza extract, in `booth_groups.GraphBuilder`. `fwd` and `rev` hold the predecessors and successors of every booth node.
- Step 5 (`build_vinci_toll_booths.py`) reads `filtered.osm.pbf`, which holds nodes only. It has no way topology and no road graph at all.
- Step 5's matching is already exactly what a stub needs. `process_route` takes a list of placemarks and a route, narrows the candidate groups to that route's `covers`, and matches by position with the hand-stated gare as a fallback.

### Probe evidence

Nine legs were submitted to the placemark service before this design was fixed. One was a control on a booth a route already resolves. All nine returned exactly one placemark.

| booth | leg | gare returned | offset from booth |
|---|---|---|---|
| 1581498325 Beaurepaire (control) | 14.2 m | `09240` BEAUREPAIRE | 0.51 m |
| 1987610456 Le-Boulou | 14.0 m | `04390` LE BOULOU (O) | 0.49 m |
| 1987610458 Le-Boulou | 10.2 m | `04390` LE BOULOU (O) | 0.83 m |
| 36967326 Perthus | 137.9 m | `04345` LE PERTHUS | 0.80 m |
| 36967365 Perthus | 97.1 m | `04345` LE PERTHUS | 1.12 m |
| 1702349430 Laghet | 79.3 m | `06028` LAGHET | 0.99 m |
| 2193692586 Laghet | 49.4 m | `06028` LAGHET | 0.62 m |
| 4172775770 Tunnel de Fréjus | 17.2 m | `02001` ENTREE TUNNEL DU FREJUS | 0.85 m |
| 1154852457 St-Michel-Barrière | 49.7 m | `02057` ST MICHEL-MODANE | 1.15 m |

Four results decide the design.

- A 10 m leg is answered. Leg length does not have to resemble a real trip.
- The placemark is projected onto the submitted leg, not returned at a fixed point per gare. The worst offset is 1.15 m against a 2.5 m threshold, and the two Le-Boulou lanes 10 m apart each got their own point.
- No stub picked up a neighbouring plaza. Perthus returned `04345`, not the `04344` lanes 550 m away. Laghet returned `06028`, not `06026`/`06027` LA TURBIE at 140 m.
- All five gares are new. None of `04390`, `04345`, `06028`, `02001`, `02057` is in `data/vinci_toll_booth.yaml` today.

## Goals

- Resolve the eight unreachable booths without weakening any existing check.
- Add no pipeline input, no container dependency, and no Makefile target.
- Keep a completed run at zero requests.

## Non-Goals

- Publishing the declared role (`enter` / `exit` / `passthrough`) into the inventory's `type` field for step 6 to price. Step 6 accepts those values already, but pricing a booth no route reaches is a separate problem: a pair price needs a partner gare, and there is no route to supply one.
- Extending the route set to cover these booths. That would need place nodes outside France.
- Correcting `data/uncovered_booths.json`. It is already the right list and this change does not consume it.

## Decisions

### The passage is computed in step 3, not step 4 or step 5

Step 3 already holds the directed graph and is cheap to re-run. Rebuilding the inventory after an override edit costs about a minute, because `run_tags_filter` and `carve_neighbourhoods` reuse their extracts.

*Alternative: step 5 parses `plazas.osm.pbf` itself.* Rejected. That file is 581 MB, and step 5 is the resumable step whose design goal is to do nothing on a complete file. A one-minute parse on every invocation works against that.

*Alternative: step 4 writes stub routes into `data/route_set.yaml` with inline geometry.* Rejected. `route_set.yaml` is a coverage set of trips a car drives, chosen so that every group is crossed. A stub is neither a drivable trip nor a coverage claim, and putting one there would corrupt what the file means. It would also force a full step-4 solve after every override edit, which is far more expensive than a step-3 rebuild.

### The stub is built from published positions, never routed

The leg is `passage[0]`, `latlon`, `passage[1]`, encoded at precision 6 and posted directly.

*Alternative: ask OSRM to route from the predecessor to the successor.* Rejected for two reasons. The router is what could not reach these booths in the first place, so it is the wrong instrument. And `patch_car_profile.py` closes barriers off major roads, so a routed leg may not pass through the booth at all. Raw OSM positions sidestep both.

### The placemark is matched positionally, not trusted

A stub is submitted with a synthetic route whose `covers` names exactly one group, and passed through `process_route` unchanged. The 2.5 m and 10 m thresholds and the `vinci:` fallback apply as they do to any route.

*Alternative: record whatever single gare comes back.* Rejected on the geometry. Perthus sits 550 m from the mapped Le Boulou lanes and Laghet 140 m from La Turbie. A trusting rule would have recorded a neighbour's gare had the service reported one, and nothing downstream would have caught it. The probe shows the service does not do this, which makes the check cheap rather than unnecessary.

### `passage` holds two points, not three

The booth's own position is already in the same entry as `latlon`. Repeating it would let the two disagree.

### Direction comes from the graph, not from the declared type

`type: enter` says what the booth is to the toll network. It does not say which neighbour is upstream. The directed graph does, and seven of the eight booths lie on `oneway=yes` ways where the answer is unambiguous.

The eighth, 1154852457, lies on `oneway=no` ways in both directions, so the graph offers both neighbours in both roles. Way order settles it arbitrarily, and the probe answered on the first orientation. No reverse-orientation fallback is specified, because nothing has been observed to need one.

### Resume reuses the existing `routes` list

A processed stub is recorded as `{from: <booth>, to: <booth>}` in `data/vinci_toll_booth.yaml`. `load_state` already reads that into `done_pairs`, and `outstanding` is computed against `route_set.yaml`, so the entry sits inertly and the stub loop skips on it.

A route can never produce such a pair: its endpoints are two distinct place nodes.

*Alternative: a new top-level key such as `stub_routes`.* Rejected. It buys nothing over the existing key and adds a second resume mechanism to keep correct.

## Risks / Trade-offs

**The service could stop projecting placemarks onto the submitted leg.** → The positional check fails loudly rather than recording a wrong gare. The failure names the booth and the distance, which is enough to diagnose.

**A refreshed extract renumbers or re-tags a passage node.** → `passage` is regenerated from the extract on every inventory rebuild, so it cannot go stale independently. Step 5 stops when a border-typed booth carries no `passage`, which is the case where the inventory predates the override edit.

**A future border-typed booth genuinely is not in the operator's layer.** → The run stops and names it. The remedy is the existing one: change the entry to `absent_passthrough` and state its price, or to `ignore`. That is a decision for a human, and the failure is what puts it in front of one.

**The two `oneway=no` booths could need the reverse orientation after an upstream retag.** → The failure is an empty placemark list, which stops the run and names the booth. Adding a reverse retry then is a one-line change with evidence behind it, which is better than speculating now.

**`data/osm_toll_booths_overrides.yaml` records 1154852457 under the comment `# Saint-Michel-Barrière`.** The operator calls it `02057 ST MICHEL-MODANE`, and `02056 ST MICHEL BARRIERE` is a different plaza 590 m away. → The comment is corrected as part of this change. The OSM tags on that node (`name=Saint-Michel-Barrière`, `operator:ref=056`) are wrong, not the pipeline; correcting them upstream is out of scope here.

## Migration Plan

1. Rebuild the inventory: `rm data/osm_toll_booths.yaml && make build_osm_toll_booths`. Nine entries gain `passage`. Nothing else changes, because the border types already had their grouping effect.
2. Run `make build_vinci_toll_booths`. Eight stubs are submitted, eight groups gain a gare, and the new completeness check passes.
3. `data/route_set.yaml` is untouched, so steps 6 and 7 need no rerun for the routes they already priced.

Rollback is deleting `data/vinci_toll_booth.yaml` and re-running step 5, which is the existing remedy for that file.

## Open Questions

None. The nine probe requests settled the ones that would have changed the specs or the approach.
