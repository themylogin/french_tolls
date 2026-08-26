## Context

See `proposal.md` — Why. The requirements are in `specs/`. This change follows `resolve-gares-for-unrouted-booths`, which gave the same eight booths their gare codes and nothing else.

Three facts about step 6 shape the approach.

- `Rates.body(codes)` already builds a request from a list of gare codes. A one-element list is well-formed and needs no new request shape.
- `attribute()` already reads an item carrying `entranceToll` and no `exitToll` as a `PASSTHROUGH` charge with that amount as the group's price. A single-passage answer arrives in exactly that shape.
- `load_state` / `write_state` carry `routes: [{from, to}]`, the same resume shape step 5 uses. The `{from: booth, to: booth}` key works here for the same reason.

So the new code is a loop and two checks, not a new mechanism.

### Probe evidence

Six single-passage rate requests, and a local scan routing each border booth against the 60 nearest partners of the opposite role and counting the booths in between:

```
       booth  name               gare    lone passage   clean exits  clean entrances
  1702349430  Laghet             06028         EUR 1.20          0             0
  2193692586  Laghet             06028         EUR 1.20          0             0
  4172775770  Tunnel de Frejus   02001        EUR 55.50          0             0
  1154852457  St-Michel          02057         EUR 2.30          0             0
  1987610456  Le-Boulou (O)      04390         EUR 1.10          0             0
  1987610458  Le-Boulou (O)      04390         EUR 1.10          0             0
    36967365  Perthus            04345    No rate found         32             0
    36967326  Perthus            04345    No rate found          0            33
  1581498325  Beaurepaire        09240        EUR 14.70         44             0
```

Beaurepaire is the row that decides the design. It is stated `enter`, it is covered by routes, and step 6 already prices it against its two exits at EUR 53.90 and EUR 54.60. Its lone-passage answer is EUR 14.70, which is neither of those and is not a barrier toll.

So a lone passage answered with a price does **not** mean the gare is a barrier. The service answers one for a closed-section end as well.

What does separate the two is the partner count. Every barrier has zero clean partners in both directions; every closed-section end has many, in exactly the one direction its role predicts. Perthus reads 32/0 as an entrance and 0/33 as an exit, which is the stated roles confirmed by topology rather than by price.

That count belongs to the router, and step 6 must not contact one. So step 6 takes the classification from the override file, and uses the rate service only to fetch a price for what the file already calls a barrier.

## Goals

- Give all eight booths a tariff, by whichever route their gare kind allows.
- Add no request to a complete run.
- Record no price the operator does not charge.

## Non-Goals

- Changing step 8. Once the two Perthus booths carry `enter` and `exit`, its existing rule enumerates them.
- Catching a barrier misstated as `enter` or `exit`. Only the partner count reveals it, and only step 8 computes one.
- Publishing the stated role into `data/osm_toll_booths.yaml`. See the decision below.
- Correcting the OSM tags on `1154852457`, which name it `Saint-Michel-Barrière` with `operator:ref=056` while the operator calls it `02057 ST MICHEL-MODANE`. That is an upstream edit.

## Decisions

### Step 6 reads the stated role from the override file, not from the inventory

Step 6 already takes `--overrides` and already holds `ov.one_way`, which is the stated role keyed by booth. The role map that `apply_charges` consults becomes `inventory_types | ov.one_way`.

*Alternative: step 3 publishes the role as `type` in `data/osm_toll_booths.yaml`.* Rejected. `load_inventory_types` raises on any value outside `bidirectional` and `gantry`, and `toll-booth-inventory` constrains `type` to those two with a "SHALL NOT be both" rule — so this route widens a deliberately narrow vocabulary in a published file, and adds a step-3 rebuild to the cost of every override edit. Reading the override directly costs one dictionary merge.

### One request per booth, not per gare

Laghet and Le Boulou each have two booths on one gare, so asking per booth spends two requests to be told the same thing twice.

It is worth it. The per-booth loop is the same shape as the per-route loop, the resume key is the booth, and a booth is what the completeness check is about. Deduplicating by gare would make the resume key a gare and the answer shared between two booths, which is three special cases to save two requests once. The existing rule against a recorded price changing then checks the two agree rather than assuming it.

### The audit runs one way only

```
  stated passthrough + price      -> record the price
  stated passthrough + no rate    -> STOP: the service prices this gare only against a partner
  stated enter/exit               -> no request at all; record the role
```

The missing fourth row is deliberate. A check that read "stated enter/exit + lone price → STOP" would fire on Beaurepaire, which is correctly stated. Nothing in a rate answer distinguishes a barrier from an entrance, so this step does not pretend to.

A barrier misstated as `enter` or `exit` therefore passes here, and shows up downstream as an endpoint with no clean partner in either direction. That is step 8's question, and adding the check there is a follow-on rather than part of this change.

### Border-typed booths are fatal when unpriced, unlike covered booths

A covered booth without a price is reported and the step succeeds, because the cause is the route set. A border-typed booth is asked about directly, so nothing stands between the question and the answer. Left unpriced it means the question was never put, which is a fault in this step.

## Risks / Trade-offs

**Step 8 stops on a clean pair the operator will not price.** Le Perthus is the last gare before Spain and none of its ~60 clean partners has been asked about. → `--survey` collects every such stop in one run. If they turn out to be real absences rather than data faults, the remedy is the existing `prohibited_gare_pairs` section, which is per ordered gare pair and stable across route-set rebuilds.

**The two Perthus booths carry `type` alone until step 8 has run.** A consumer reading `data/vinci_price.yaml` between the two steps sees an `enter` with no `prices`. → The output format already permits that for `bidirectional` and `gantry`, and the spec now says so for a stated entrance. It is the same state an exit is always in.

**`04390` and `06028` are each one gare recorded twice as a barrier with the same price.** → That is already the ordinary case: `04344` is carried by two groups, and a barrier's price is a property of the gare, so two carriageways agreeing is what should happen. The existing "a price that would change stops the step" rule catches them disagreeing.

**A barrier stated as an endpoint passes this step silently.** → `04390` was exactly that, and it took a deliberate look to find. Until step 8 reports an endpoint with no clean partner, the only defence is that a stated role is written by hand and reviewed.

## Migration Plan

1. Run `make build_vinci_prices`. Four requests, eight new entries: six barriers with a price, two Perthus endpoints with a role alone.
2. Run `make build_vinci_direct_prices`, ideally with `--survey` first. It picks the two Perthus booths up as a source and a target and prices their clean pairs.

`1987610456` and `1987610458` were retyped from `exit` to `passthrough` by hand before this change was written, and the partner scan above is what supports it. Had they been left as `exit`, this step would have recorded them with a role and no price, and step 8 would have found no partner and said nothing.

Rollback is deleting `data/vinci_price.yaml` and re-running steps 6 and 8, which is the existing remedy for that file.

## Open Questions

Whether every clean Le Perthus pair is priced by the operator. It cannot be answered without asking, it does not change the specs or the task breakdown, and `--survey` is the existing instrument for answering it in one run.
