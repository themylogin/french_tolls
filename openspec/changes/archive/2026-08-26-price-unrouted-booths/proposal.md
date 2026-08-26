## Why

`resolve-gares-for-unrouted-booths` gave the eight border booths a gare. It gave them nothing else. Step 6 prices what the route set crosses, and these booths are on no route, so they get no entry in `data/vinci_price.yaml` at all. Step 8 takes its sources and targets from that file, so it never asks about them either. Eight booths now carry a gare code and no tariff.

They divide in two, and the router says which is which. Routing each booth against the 60 nearest partners of the opposite role, and counting the booths in between:

| booths | gare | clean exits | clean entrances | is |
|---|---|---|---|---|
| 1702349430, 2193692586 Laghet | `06028` | 0 | 0 | barrier |
| 4172775770 Tunnel de Fréjus | `02001` | 0 | 0 | barrier |
| 1154852457 St-Michel | `02057` | 0 | 0 | barrier |
| 1987610456, 1987610458 Le Boulou (O) | `04390` | 0 | 0 | barrier |
| 36967365 Perthus | `04345` | 32 | 0 | entrance |
| 36967326 Perthus | `04345` | 0 | 33 | exit |

The six barriers charge for themselves, and the rate service prices a single gare passage on its own: `06028` €1.20, `02001` €55.50, `02057` €2.30, `04390` €1.10. One request each is the whole answer.

The two Perthus booths are the two ends of a closed section, and step 8 already knows how to price those. It needs only a role in the price file to enumerate them.

## What Changes

- Step 6 records every booth the override file types `enter`, `exit`, or `passthrough` under that type, whether or not any route covers it. That alone makes the Perthus booths a source and a target for step 8.
- For a booth typed `passthrough`, step 6 also issues one single-passage rate request built from that booth's gare alone, and records the amount as its price.
- A booth typed `enter` or `exit` is **not** asked about that way. The service answers a lone passage for a closed-section end too, with an amount that is not what the gare charges — `09240` BEAUREPAIRE is an entrance whose real tariffs are €53.90 and €54.60 and whose lone-passage answer is €14.70.
- A booth typed `passthrough` that gets `No rate found.` stops the step: the service declines a lone passage only for a closed-section end, so the statement is wrong.
- Step 6 records each request under its own `routes` resume list as `{from: <booth>, to: <booth>}`, exactly as step 5 records a stub leg.
- Step 8 is unchanged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `vinci-price-mapping`: the step may build a request that is not a route from the route set, which the current specification forbids outright; adds the single-passage request for a stated barrier, the stated-role record, the one-directional audit, the resume rule, and the completeness rule.

## Impact

Code:

- `builder/build_vinci_prices.py` — the single-passage loop, the stated-role record, the merged role map, the audit, the resume and completeness checks

Data:

- `data/vinci_price.yaml` — gains 8 entries: 6 barriers with a price, 2 Perthus endpoints with a role alone
- `data/vinci_routes_rejected.sqlite3` — grows by the pairs step 8 rejects around Le Perthus

Requests, issued once:

- 4 in step 6, one per stated barrier gare across its 6 booths
- in step 8, one routing call and up to one rate call per clean Perthus pair; 32 and 33 clean partners were found among the 60 nearest, so of the order of 65

## Risks

**Step 8 stops when a pair the router calls clean is one the operator will not price.** Le Perthus is the last gare before Spain and none of its ~65 clean partners has been asked about. `--survey` collects them all in one run rather than one per attempt.

**A barrier misstated as `enter` or `exit` is not caught by this step.** Nothing in a rate answer distinguishes it, as Beaurepaire shows. What distinguishes it is having no clean partner in either direction, which only the router knows — so the natural home for that check is step 8, and it is not in this change's scope. It is worth a follow-on: `04390` was misstated exactly that way, and the only reason it was noticed is that someone went looking.
