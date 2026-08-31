## 1. The page stops reading the reason

- [x] 1.1 In `www/index.js`, drop the `title` attribute from the unpriced branch of `peageCost` so it returns `<span class="unpriced">X €</span>`; verify `grep -n "title=" www/index.js` reports nothing in that function
- [x] 1.2 Drop the now-unreachable `peage.reason || "not priced"` fallback with it; verify `grep -n "peage.reason" www/index.js` returns nothing
- [x] 1.3 Verify the rendered markup: a passage with `cost: null` yields `X €` and no hover text, and a passage with `cost: 13.7` still yields `13,70 €`
- [x] 1.4 Verify a passage costing exactly 0 still reads `0,00 €` rather than `X €`, which is the distinction the surrounding comment exists for
- [x] 1.5 Rewrite the comment above `peageCost`: it currently explains the reason text the function no longer reads; verify what remains describes only the null-versus-zero rule it still enforces

## 2. The constants

- [x] 2.1 Verify before removing that `BOOTH_NOT_PRICED` is unreachable: every `reason=` in `french_tolls/tolls.py` and every `close_unpriced(...)` call names one of the other six, and this one appears in no assignment
- [x] 2.2 Verify the other six are worth removing too: nothing anywhere compares, matches or dispatches on a reason, so the constants bind `tolls.py` only to its own test — which fails loudly on drift with or without them
- [x] 2.3 Remove all seven from `french_tolls/tolls.py`, writing each string at the site that produces it; verify the six wordings are unchanged character for character
- [x] 2.4 Collapse the `..tolls` import in `french_tolls/tests/test_cost.py` to `account` and put the same literals in its assertions; verify `grep -rn "BOOTH_NOT_PRICED\|GARE_UNKNOWN\|SIDE_UNKNOWN" --include="*.py" .` returns nothing outside `openspec/`
- [x] 2.5 Rewrap the production lines that ran past 99 characters once the literal replaced the name; verify no line in either file exceeds it

## 3. The distinctness test

- [x] 3.1 Delete `test_the_eight_reasons_are_all_different_strings` rather than renaming it: its one merit was checking *production's* strings for duplicates, and with the constants inlined it can only compare literals it wrote itself; verify the suite drops by exactly one test
- [x] 3.2 Verify no other test name or docstring counts the reasons, so the number is not written down anywhere else to go stale

## 4. Verification

- [x] 4.1 Run the unit suite; verify it passes, including the exhaustive reason test at `test_cost.py` that asserts which reasons a synthetic journey produces
- [x] 4.2 Run the recorded drive-flow suite; verify it passes
- [x] 4.3 Verified at the unit level: all six surviving reasons keep their exact wording, and a `Passage` carrying one serialises it with `cost` None. On the live route checked every listed passage was priced, so none carried a reason — its two unpriced passages were gantries, which `journey-toll-accounting` requires be counted and not listed.
- [x] 4.4 Redeploy and verify the page renders a route normally, with the passage table intact
