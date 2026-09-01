## Context

See `proposal.md` — Why.

Three facts about `builder/build_route_set.py` shape the approach.

`covers` is derived from the driven path, not from the target set. `cover_many` walks the node list OSRM returns and records every node in `traversable`, which is the whole inventory:

```python
# :377
for n in nodes:
    if n in traversable:            # traversable = booths | set(aliases)   (:904)
        rep = resolve.get(n, n)
        hits.setdefault((rep, prev if rep in bidirectional else None), None)
```

Selection scores a candidate on marginal gain alone, with no notion of a route being unusable:

```python
# :756
gains = {pair: len(sets[pair] & uncovered) for pair in candidates}
```

Every route that reaches `selected` passes through `cover_many` exactly once — the three candidate waves at `:969`, `:1003` and `:1033`, and the resume path at `:954`. That single choke point is what makes this a small change.

The pricing step already refuses these routes, and tests the group representatives in `covers`:

```python
# builder/build_vinci_prices.py:402
absent = ov.absent.get(group)
if absent in BLOCKING_ABSENT:
    return None, group
```

## Goals / Non-Goals

**Goals:**

- No route in `data/route_set.yaml` is one the pricing step will refuse.
- The route search and the pricing step decide "unaskable" from one definition, applied to one domain of booth ids.
- The change is reachable through `make update_route_set`, without a clean rebuild and its ~24,000 Ulys requests.

**Non-Goals:**

- Changing what a selected route reports. `covers` stays a faithful record of the drive.
- Removing the pricing step's own guard. It stays as the backstop.
- Any of the items in the proposal's Non-goals section.

## Decisions

### One filter inside `cover_many`, not one per call site

`cover_many` takes the blocking set and omits any pair whose computed `covers` intersects it.

Alternative considered: return everything and filter at the four call sites. Rejected — a fifth call site added later would silently reopen the hole, and the resume path is exactly the call site an author is most likely to forget. It is the one that reintroduced the problem in the first place.

Cost: `cover_many`'s contract widens from "route these pairs" to "route these pairs and drop the ones nothing can price". That is a policy in a routing helper. It is worth the coupling because the guarantee — *no route reaches `selected` without passing this test* — is exactly what the specification asserts, and putting the test anywhere else makes that guarantee an argument rather than a fact.

### The blocking pair moves to `builder/overrides.py`

`BLOCKING_ABSENT = ("absent_enter", "absent_exit")` lives in `build_vinci_prices.py:123` today. Two steps must now agree on it exactly, and a copied tuple is a second source of truth that drifts silently.

`overrides.py` already holds `ABSENT`, `BORDER`, `PRICED_TYPES` and `TYPES`, and both steps already import it. The pair belongs beside them. `build_vinci_prices` imports it and keeps its guard unchanged.

The header comment at `overrides.py:47` says an `absent_*` booth "stays in the inventory and in the route set" and that the suffix is something "which nothing consumes yet". Both halves become false. Correct them in the same edit; a comment that documents the opposite of the code is worse than none.

### The test is on group representatives

`cover_many` resolves aliases to representatives before recording a hit. The blocking test runs on the resolved ids, which are exactly what `passages_for` tests.

Alternative considered: test the raw traversed node ids, before resolution. That is strictly wider — it would also catch a blocker that is an alias of some other group. Rejected, because the pricing step would *not* catch that case, and the two steps disagreeing is the bug being fixed. A wider search-side test would drop routes the pricing step would happily submit.

The narrower behaviour is a real blind spot: an `absent_enter` booth that is an alias rather than a representative is invisible to both steps. All five blocking booths are representatives today. If that changes, both steps need fixing together, and a shared definition in `overrides.py` is where that fix goes.

### The pricing step keeps its guard, and keeps only reporting

`passages_for` still skips such a route and the end-of-run report still names it. It does not become a hard failure.

Alternative considered: fail the pricing step when it meets an unaskable route, on the grounds that the route set should no longer produce one. Rejected — it converts a recoverable condition into a stop, and it would fire on any route set generated before this change. The report is enough: after this change the skipped count should be zero, and a non-zero one names the disagreement.

### Reporting distinguishes the two reasons for dropping a resumed route

`load_existing` already prints "dropped N that no longer cover anything". A route dropped for crossing a blocking booth is a different fact and gets its own line. Folding both into one count would hide the change taking effect on the run where it first does.

## Risks / Trade-offs

**A freed target may have no askable route at all.** → The seven routes being dropped are the sole cover of seven booths that carry a gare. The search will look for replacements. `08322 ST ROMAIN SF`, 18 m from one of them, is reached by an unblocked route, so at least that neighbourhood is reachable. Where no replacement is found the booth becomes an honest entry in `data/uncovered_booths.json`, which is better than today, where it is silently unpriced.

**`data/uncovered_booths.json` changes in two directions at once.** → Five blocking booths leave it because they stop being targets; some freed booths may enter it. Verify the diff booth by booth rather than by count.

**The pricing file will not shrink on the update path.** → `build_vinci_prices` carries every prior entry forward (`load_state:245`). A booth that loses its route keeps its price. That is the intended behaviour here, and it means the improvement shows up as entries gained, not as churn.

**An `absent_*` booth that is an alias is invisible to the rule.** → Noted above. Not present today. A check that every blocking booth is a group representative could be added to `overrides.load`, but it needs the inventory, which `overrides.load` does not read. Left out.

## Migration Plan

1. Land the code and the unit tests. Nothing in `data/` changes yet.
2. `make update_route_set`. It re-queries the routes on disk, drops the seven, and searches only for the targets they freed. Needs `osrm-toll` and the existing graph. No Ulys requests.
3. Inspect the diff of `data/route_set.yaml` and `data/uncovered_booths.json` before going further.
4. Re-run the gare mapping and the pricing step for the new routes only. Both are resumable and both skip what they have already asked about, so the cost is a handful of requests, not a sweep.
5. Re-run `build_toll_extent`, `build_segment_weights` and `apply_segment_weights`.

Rollback: revert the code and restore `data/route_set.yaml` from git. `data/vinci_price.yaml` needs no rollback — it only gained entries, and an entry gained is a real tariff the operator returned.

**Do not run `make clean`.** It drops `$(ROUTE_SET)` and `$(PRICES)` together (`Makefile:598`), discarding every price already learned and costing roughly 24,000 Ulys requests to relearn.
