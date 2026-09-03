## Context

See `proposal.md` — Why. Two measurements shape the approach.

**A gantry is not one kind of thing, and the price file already says which kind.** Of 56 gantries: 40 carry a flat `price` and no tariffs, 6 carry tariffs and no price, 1 carries both, 5 carry neither. What is recorded is what the operator answered, so the entry — not the type — is what the accounting can read.

**The 7 gantries carrying tariffs are of two shapes.**

```
CHAMBERY NORD  -> 03011 / 03015 / 15018   an exit and an enter gare
                                          ticketless entrance, closed by a barrier
A79 chain      -> gantry gares, 6 pairs   Le Montet, Montbeugny, Molinet
                                          Sens 1 -> Sens 1, Sens 2 -> Sens 2
```

Only the first shape produces the reported fault, because only it ends at an `exit`.

## Goals / Non-Goals

**Goals.** Price the section a ticketless entrance sells, using tariffs already on disk.

**Non-Goals.** The A79 shape — a section whose far end is another gantry — is not addressed. It is a second journey shape, no reported route needs it, and the look-back below never fires there because the closing booth is not an `exit`. It is recorded in `tasks.md` as not done rather than left implicit.

## Decisions

### The rule is a look-back at the exit, not a role decided at the gantry

An earlier draft read a gantry's role when it was crossed: close an open ticket it prices, else open one if it carries tariffs, else charge flat. That is more machinery than the fault needs and it changes what happens at every gantry crossing.

The rule taken instead fires in one place — the branch that already recorded `exit without an entrance`:

```
exit reached, no ticket open
  -> is there a gantry behind it, since the last ticket ended?
  -> does that gantry's gare price this exit?
       yes  -> the passage is that section
       no   -> unpriced, as today
```

Everything that prices a passage today is untouched, so the change can only replace a gap with an amount. That is what makes it safe to ship without re-measuring the country's fares.

### One gantry is held, not a list

The last one crossed is the only candidate. An earlier gantry belongs to a section already settled, and crossing an entrance or an exit clears the slot.

### A gantry carrying a flat price is not a candidate

It collected where it stands and is charged there. Billing a section for the same passage would charge it twice. One booth in the country carries both a price and tariffs — Montbeugny Est Sens 2 — and this rule decides it.

### The look-back reads tariffs by gare; nothing else does

A rate request names two gare codes and the answer is the pair's, so every group carrying a gare charges the same. Groups hold different numbers of tariffs for two reasons, measured:

```
7346104910  gantry   3 tariffs    0 rejections as source
12608140    enter   27 tariffs  538 rejections as source

CORZE 1157490221  enter  29 tariffs  534 rejections
CORZE 1157490224  enter   5 tariffs  560 rejections
```

`vinci-direct-pricing` sets `SOURCE_TYPES = (ENTER, BIDIRECTIONAL)`, so a gantry is never a source — its zero rejections are not a clean grid but an absent one, and its 3 tariffs come from `vinci-price-mapping` pricing the routes that happen to cross it. Two groups that *are* both enumerated can still differ, because a pair is asked about only where no booth lies between: Corze's two entrances hold 29 and 5.

Where two groups of a gare both hold a pair, the amounts agree: 210 shared pairs, 0 contradictions.

The widening is nonetheless confined to the look-back. An entrance the route actually crossed already answers for itself, and reading it gare-wide would move fares that are correct today for no reported fault. Confining it means the blast radius is exactly the passages that read `× €` before.

Measured reach: 6 of 56 gantries can open a section, and the gare-wide read adds tariffs to one of them — Chambéry Nord, 3 → 27. The other five are 1 → 1.

## Risks / Trade-offs

**The gare-wide read could pair a group with an exit it cannot reach.** Direct pricing omits such a pair because the route between them crosses a booth; the tariff is still what the operator charges for the pair. The look-back only applies it when the route actually drove from that gantry to that exit, so an unreachable pair is never used.

**Two rules for one lookup.** An entrance reads its own mapping; the look-back reads the gare's. That is a real inconsistency, taken deliberately: the alternative moves fares nobody reported wrong. It is written into `journey-toll-accounting` so the asymmetry is stated rather than discovered.
