## MODIFIED Requirements

### Requirement: An amount is shown as money; the absence of one is not

A passage carrying an amount SHALL be rendered as a currency value.

A passage carrying no amount SHALL be rendered as `X €` — an amount with its figure missing — and the reason the API gives SHALL be available on it.

Every passage that reaches the list is a charge the driver will pay; the only ones without an amount are the ones nobody could price. A dash reads as *nothing to pay*, which is the opposite of the truth. `X €` reads as a price nobody has filled in, which is what it is.

Formatting an absent amount as currency renders it `0,00 €`, which tells a driver a toll they will be charged for is free. `journey-toll-accounting` forbids the API from making that claim; a page that makes it at the last step defeats the requirement rather than satisfying it.

A route's total SHALL continue to be shown as currency, since it is always a real sum — of the passages that could be priced.

#### Scenario: A priced passage

- **WHEN** a passage carries a cost of 13.70
- **THEN** it is shown as `13,70 €`

#### Scenario: An unpriced passage

- **WHEN** a passage carries no cost
- **THEN** it is shown as `X €`, and never as `0,00 €` or as a dash

#### Scenario: The reason is available

- **WHEN** an unpriced passage is shown
- **THEN** the reason the API gave for it can be read from that row
