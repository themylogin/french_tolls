# Design

## Context

See `proposal.md` for the motivation, and the specs for the rules.

- `refuel.plan` builds each station entry in `_station_entry`, from a `GasStation` row. The row has `services` and `address` as JSON lists.
- `www/index.js` builds each row in `showRefuelAnswer`. The first cell is the name link.
- `tests/test_refuel.py` tests the entries in the unit suite. The page has no automatic tests.

## Goals / Non-Goals

**Goals:**

- One definition of the three rules, with unit tests.

**Non-Goals:**

- No change to which stations are listed, or to their order.

## Decisions

### The server picks the badge

`refuel.py` gets `station_badge(services, address)`, and `_station_entry` adds its result as `badge`. The page shows the text that it gets.

The alternative is to send the services and let the page choose. The rules then live where no test runs, and every answer carries a list of up to 30 services per station that nothing else reads.

### The service match is exact

`Automate CB 24/24` occurs in exactly this form in the store: 5,395 stations on 2026-11-07, and no other spelling of a service with `24`. The rule tests membership in the list, not a substring.

### The address matches ignore letter case

`autoroute` is a substring test on each lowercased line. The store has `Autoroute` 203 times and `autoroute` 32 times.

`aire` is one regular expression with `re.IGNORECASE`:

```
(?<![^\W\d_])aire\s+(?:de|des|du)\b|(?<![^\W\d_])aire\s+d['’]
```

`[^\W\d_]` is a letter, so the lookbehind refuses `aire` after a letter. A plain `\b` would refuse it after a digit too, and lose 9 lines such as `A71aire de ste thorette`. With the letter rule, only `Saint hilaire de brens` and `Zi portuaire des mielles` are refused in the store. The curly `’` is in the class because the source pages use both apostrophes.

## Risks / Trade-offs

- [An address that names a nearby motorway, for example `Avenue de l'Autoroute`, gets `Autoroute` without being on it.] → Accepted. The rule is the one requested, and the badge is a hint, not a filter.
- [`Automate CB 24/24` means a card machine that works at any hour. The shop can be closed.] → The badge text `24` says no more than that.
