## Why

Le Boulou → Annecy is answered with a passage reading `ANNECY CENTRE` and no amount. The route leaves the tolled network at Tullins, rejoins it at the Chambéry Nord **gantry**, and leaves at Annecy Centre — and nothing charges for the last section, which the operator sells for 5.60 EUR.

```
TULLINS          exit    03095   ticket closed, 7.50 charged
CHAMBERY NORD    gantry  03008   <- the ticketless entrance; silently unpriced
ANNECY CENTRE    exit    03012   <- nothing open, so "exit without an entrance"
```

`journey-toll-accounting` says a gantry "SHALL be charged its own flat price and SHALL leave the ticket state alone". That is one of the three things a gantry can be, and the one this journey needs is written down elsewhere: `toll-weighted-graph` describes "**a ticketless entrance that takes no money and leaves the collecting to an exit barrier**", and its scenario *A ticketless entrance gets no flat row* names Chambéry Nord. The accounting was written before the `gantry` type existed and only the flat behaviour was ever modelled.

The tariff is already on disk. Both `7346104910` (the gantry) and `12608140` (the `enter` booth beside it) carry gare `03008`, and the second records `03012: 5.60`. They hold different numbers of tariffs because `vinci-direct-pricing` never asks about a gantry: its sources are `enter` and `bidirectional` groups only. So the gantry's tariffs come from `vinci-price-mapping` alone, which prices the routes in the route set that happen to cross it. The gantry holds 3 tariffs and 0 rejections; the booth beside it holds 27 tariffs and 538 rejections.

## What Changes

- **An exit with no ticket open looks back at the gantry behind it.** Where that gantry's gare prices the exit, the passage is that section. Nothing else in the walk moves: a gantry with a flat price is still charged where it stands, an entrance still opens a ticket, and every branch that prices a passage today prices it the same way.
- **For that look-back, the tariff is read under the gare rather than the node.** A rate request names two gare codes and the answer is the pair's, so every group of a gare charges the same. The widening is confined to the look-back, which is reached only where the passage would otherwise be unpriced — so it can replace a gap with an amount and can never change one.

No pipeline step changes, no rate request is spent, and no data file is rewritten.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `journey-toll-accounting`: an exit reached with no ticket open is priced from the last gantry crossed, where that gantry's gare prices it.
- `route-algorithm-tests`: the look-back and the gare-wide lookup are demonstrated, along with the cases that bound them.
