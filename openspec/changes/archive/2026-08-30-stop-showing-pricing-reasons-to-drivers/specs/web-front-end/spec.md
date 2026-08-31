## ADDED Requirements

### Requirement: An amount is shown as money; the absence of one is marked, not explained

A passage carrying an amount SHALL be rendered as a currency value.

A passage carrying no amount SHALL be rendered as `X €` — an amount with its figure missing.

Every passage that reaches the list is a charge the driver will pay; the only ones without an amount are the ones nobody could price. A dash reads as *nothing to pay*, which is the opposite of the truth. `X €` reads as a price nobody has filled in, which is what it is.

Formatting an absent amount as currency renders it `0,00 €`, which tells a driver a toll they will be charged for is free. `journey-toll-accounting` forbids the API from making that claim; a page that makes it at the last step defeats the requirement rather than satisfying it.

**The reason the API gives SHALL NOT be shown.** It is written to tell an operator which of six accounting states was reached — *the booth maps to no gare*, *neither neighbour is a recorded side of this barrier* — in the vocabulary of this project's own data files. A driver cannot act on it, and `X €` already says the only thing they can act on: that this charge is real and its size is not known here.

The API SHALL still carry it. `route-service` requires an unpriced passage to carry a reason and `journey-toll-accounting` requires the reasons be told apart; both stand. What changes is that the page is no longer one of its readers.

A route's total SHALL continue to be shown as currency, since it is always a real sum — of the passages that could be priced.

#### Scenario: A priced passage

- **WHEN** a passage carries a cost of 13.70
- **THEN** it is shown as `13,70 €`

#### Scenario: An unpriced passage

- **WHEN** a passage carries no cost
- **THEN** it is shown as `X €`, and never as `0,00 €` or as a dash

#### Scenario: The reason is not put in front of the reader

- **WHEN** an unpriced passage is shown
- **THEN** the reason the API gave for it appears nowhere on the page, as text or as hover text

#### Scenario: The API still carries it

- **WHEN** the answer behind that passage is read
- **THEN** it carries the reason, so an operator can still tell which accounting state was reached

## REMOVED Requirements

### Requirement: An amount is shown as money; the absence of one is not

**Reason**: Replaced by **An amount is shown as money; the absence of one is marked, not explained**, which keeps every clause about rendering the amount and reverses one: the requirement said the API's reason "SHALL be available on it", and its scenario said the reason "can be read from that row".

That is what put developer prose in front of drivers. The reasons name a gare code and a recorded barrier side — the vocabulary of this project's data files, not of a person looking at a toll. Nobody asked for the hover text, and a reader who gets it learns nothing they can act on.

**Migration**: None for the API, which still carries the reason under the same key with the same wording. A reader who was relying on the page to show it reads the response instead.
