## Context

See proposal.md — Why.

`data/osm_toll_booths_overrides.yaml` already exists and is hand-maintained. It carries four `type: ignore` entries, one `parent_id`, and nine border classifications written while diagnosing the cases this change exists to close. Nothing reads it today.

## Goals / Non-Goals

**Goals:**

- Let a human state an exception about one booth, and have the pipeline honour it.
- Make a stale override fail loudly rather than silently produce a wrong inventory.

**Non-Goals:**

- Acting on the border classifications. `enter`, `exit` and `passthrough` are accepted and inert.
- Acting on `price`. It is parsed, validated as a number, and kept; nothing consumes it yet.
- Overriding anything but membership. The override file decides whether a booth exists and which group it joins, not its position, its name, or its gare.
- A general rule for the cases being overridden. Each is here precisely because no rule fitted.

## Decisions

### Validate every override against the extract, and stop on any that does not apply

An override is a claim about a node in OpenStreetMap. Nodes get retagged, deleted, and replaced, and the pipeline is regenerated from a fresh Geofabrik extract every time. An override that no longer matches anything is worse than no override: it looks like the exception is handled when it is not.

So every entry is checked — the node must be a booth in the extract, a `parent_id` target must have survived the through-road filter, a `type` must be one of the four accepted values, and no entry may carry both keys. Any failure stops the step and names the entry.

This is the same reasoning that led to fixing the Beaurepaire `oneway=no` tag upstream rather than working around it: the pipeline should tell the truth about its inputs.

### `enter`, `exit` and `passthrough` are accepted and inert

They classify how a booth relates to a border crossing and nothing consumes them yet. Two alternatives were rejected:

- **Reject any `type` other than `ignore`.** Breaks the existing file, which carries nine of them.
- **Accept any `type` at all.** Then `type: igore` silently does nothing, which is exactly the failure mode this change is trying to remove.

Enumerating the four keeps the file valid and still catches a typo.

### `absent_*` is not `ignore`

They produce the same outcome in the gare mapping and nowhere else. An ignored booth is one we do not care about: it leaves the inventory, the grouping, and the coverage universe. An `absent_*` booth is a real booth on a real road that routes drive through — it keeps its inventory entry and its coverage target, and only the demand for a gare is waived, because the operator's layer has none to give.

Conflating them would have been simpler and wrong: the twelve booths so marked would have vanished from the coverage universe, and the pipeline would have stopped reporting toll booths that genuinely exist and genuinely charge.

`price` rides on `absent_passthrough` alone. An enter or an exit is one half of a journey whose charge depends on where the other half was, so there is no single number to state.

### An ignored booth is recorded as excluded

"Act as though it does not exist" is the behaviour; vanishing from the record is not. The inventory spec requires that the inventory and the exclusion report together account for every booth in the extract, and a booth that disappears from both would break that invariant and hide the removal.

So an ignored booth is removed from grouping, the inventory, and the coverage universe, and gains an entry in `data/excluded_booths.json` naming the override as its reason. The step also reads that report to name the nearest excluded booth when a placemark matches nothing, so keeping ignored booths in it makes that diagnostic better rather than worse.

### Two steps read the file, and the inventory can drift

`type: ignore` and `parent_id` decide what the inventory contains, so the extraction step applies them. `vinci` and `absent_*` are about the operator's data, so the gare mapping step consumes them. That split is unavoidable, and it creates a trap: editing an `ignore` has no visible effect until the inventory is rebuilt, and the booth simply reappears in the mapping's report.

Making the override file a make prerequisite would close the gap and open a worse one — the pipeline skips on existence, never on modification time, precisely so that touching an upstream file cannot trigger half an hour of work. So the gap is closed by detection instead: the gare mapping compares the inventory against the override file and stops with the rebuild command when they disagree.

Reusing the two carved extracts is what makes that rebuild cheap enough to be a reasonable instruction. Both derive from the source extract alone, so no override can invalidate either.

### Forced membership merges whole groups, after the rules have run

`parent_id` says a booth belongs to a named group. The booth may already have a group of its own, and a group cannot be split by decree, so the merge takes the overridden booth's entire group into the target's.

The target must be a representative *after* the natural grouping. If the rules made it an alias of some other group, then "group 635884768" does not exist and the entry is pointing at nothing — which is a stale override, not a merge to perform silently.

The representative of the merged group follows the existing rule, the smallest member id. Forcing membership does not also force which id names the group.

An override may contradict a rule — a booth the two-way rule leaves ungrouped can still be forced into a group. That is the point of an override, and the alternative is a file whose entries sometimes apply and sometimes do not.

## Risks / Trade-offs

- **An override can reintroduce a defect the grouping rules exist to prevent.** → Accepted. Overrides are hand-written, few, and each carries a comment saying why. The validation catches staleness, not bad judgement.
- **Removing four booths changes the coverage universe**, so the uncovered count and the route set both move. → The route set is regenerated and the difference read before the result is accepted.
- **The override file is an input living under `data/`**, next to generated artifacts. → The layout requirement says generated artifacts live under `data/`; it does not say only they may. The file is tracked, unlike the generated reports beside it.

## Migration Plan

1. Read and validate the overrides in the extraction step; regenerate the inventory and check the four ignored booths are gone and `13719126553` has joined `635884768`.
2. Regenerate the route set and read the change in the uncovered count.
3. Re-run the gare mapping, which resumes from what it already has.

Rollback is deleting the override file: the validation treats a missing file as empty.

## Outcome

The inventory went from 1303 groups to 1299 and the route set from 1354 targets to 1350. Uncovered fell from 14 to 10, and every removal is an override:

| target | why it went |
|---|---|
| `257077660`, `7795369636` | Arc 1800, `type: ignore` |
| `600203475` | Porte de Rungis, `type: ignore` |
| `13719126553` | `parent_id: 635884768` — not merely removed but **covered**, because the route through the plaza covers the group it now belongs to |

Nothing became uncovered. `14061571393` was an alias rather than a representative, so ignoring it removed no target.

`12010 SEES` still stops the run, unchanged. **No booth-level override can fix it.** The placemark is 45.3 m from the lane the route drove and 7.3 m from an Argentan booth that is not on the route; `ignore` and `parent_id` decide which booths exist and how they group, and neither moves a placemark. Closing it needs an upstream OSM fix at the Sées/Argentan plaza or a gare-level exemption in the mapping step — new scope in both cases.

## Open Questions

- Whether `enter`, `exit` and `passthrough` should stay inert or be rejected until something consumes them.
