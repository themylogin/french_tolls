## Why

**The page shows a driver text written for a developer.** When a passage cannot be priced the page renders `X €` and hangs the API's reason on it as a hover tooltip. Those reasons read: *"the booth maps to no gare"*, *"neither neighbour is a recorded side of this barrier"*. "Gare" is Vinci's internal word for a toll station; "recorded side" refers to a YAML file in this repository. A driver who hovers learns nothing they can act on, and the tooltip was never asked for.

**One string is doing two jobs that pull apart.** The same seven constants are the API's user-facing prose *and* the enum `test_cost.py` uses to assert which of six failure modes fired — `assert reasons(journey) == [("ESVRES", SIDE_UNKNOWN)]`. The test wants them stable and precise; a reader wants them short and plain.

**Neither job survives inspection.** Nothing outside `tolls.py` and `test_cost.py` names them, and nothing anywhere branches on a reason — no comparison, no match, no dispatch. A constant shared between a module and its own test does not catch drift: if the string and the assertion disagreed, the test would fail loudly either way. It saves an edit in two places, not a bug.

**One of the constants is dead, and the spec says why.** `BOOTH_NOT_PRICED` — "the booth carries no tariff" — is never assigned to any passage. `journey-toll-accounting` requires that a `passthrough` or `gantry` carrying no tariff **not appear in the passage list at all**, only in the unpriced count. A passage that is never listed never carries a reason, so the constant outlived the behaviour it named.

**And a test name counts wrong.** `test_the_eight_reasons_are_all_different_strings` lists seven.

## What Changes

### The page stops reading `reason`

- **BREAKING (page)** An unpriced passage renders as `X €` with no hover text. The `title` attribute goes; nothing replaces it.
- `peageCost` stops reading `peage.reason`, and its `|| "not priced"` fallback goes with it.
- **`reason` stays in the API.** `route-service` requires an unpriced passage to carry it and `journey-toll-accounting` requires the reasons be distinguished. It remains what it is useful as: something to read in a log or a response when diagnosing why a journey came back short.

### The constants go, all seven

- `BOOTH_NOT_PRICED` is removed as dead. It is never assigned to any passage: `journey-toll-accounting` requires that a `passthrough` or `gantry` carrying no tariff **not appear in the passage list at all**, only in the unpriced count, and a passage that is never listed never carries a reason.
- The other six are removed too, and their strings written at the six places that produce them — `reason="the booth maps to no gare"` rather than `reason=GARE_UNKNOWN`. `test_cost.py` asserts against the same literals; its import of `tolls` collapses from eight names to `account`.
- **`test_the_eight_reasons_are_all_different_strings` is deleted** rather than renamed. Its one merit was checking *production's* six strings for duplicates. With the constants inlined it can only compare six literals it typed itself, which proves nothing. It could fail only on a copy-paste duplicate in the first place.

### What does not change

- Every reason still reaches the API, character for character. This moves where the strings are written, not what they say.
- The reasons stay distinguished, which is all `journey-toll-accounting` requires — by having different text, not by having names.
- `X €` is still `X €`, still never `0,00 €` and never a dash.

## Capabilities

### Modified Capabilities

- `web-front-end`: an unpriced passage no longer surfaces the API's reason to the reader.

`journey-toll-accounting` and `route-service` are deliberately **not** modified. Both require the API to carry and distinguish the reasons, and it still does; this changes only what the page does with one.

## Impact

- Modified: `www/index.js` (`peageCost` and its comment), `french_tolls/tolls.py` (the constant block gone, six strings inlined, three lines rewrapped), `french_tolls/tests/test_cost.py` (import collapsed to one name, 23 assertions now on literals, one test deleted).
- Unchanged: the accounting, the API response, and every reason string the API produces.
- **A driver loses nothing.** The text they lose named a YAML file and an internal identifier.
- **An operator loses a hover.** Diagnosing an unpriced passage now means reading the API response rather than pointing at the page. That is where the other unpriced diagnostics already live — `unpriced` counts, and the failure records under `/cache/errors`.
- **Rewording a reason is now an edit in two files.** `tolls.py` produces it and `test_cost.py` asserts it, and nothing binds them. The test fails loudly when they disagree, which is what the constant was doing for the same money.
- Not addressed: after this, `<span class="unpriced">` carries a class that `style.css` does not style and no behaviour at all. Whether the span is worth keeping as a styling hook is a separate question from what this change is for.
