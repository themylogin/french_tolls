# Spec Delta

## MODIFIED Requirements

### Requirement: Every persisted table is declared in one place

The application SHALL declare every table it reads or writes as a model, in one module, and SHALL NOT create a table from a statement written by hand anywhere else.

**One exception: a structure that the model layer cannot create SHALL be created by a hand-written statement inside a revision, and nowhere else.** The geographic index of `gas-station-inventory` is a virtual table, and triggers keep it equal to the station table. The model layer cannot create either of them. The index SHALL still be declared as a model, so that a query reaches it through the model.

There SHALL be exactly three tables:

- an autocomplete cache, keyed by the normalised query string, holding the answer that was bought for it;
- a count of paid Google requests, one row per calendar month keyed as `YYYY-MM`;
- the gas stations that `gas-station-inventory` collects, one row per station, keyed by the station id of the source.

The station table SHALL have exactly one geographic index. SQLite keeps internal tables for that index. They are part of the index, and they are not a fourth table.

The first two survive because losing a row costs money. An autocomplete answer cost a paid LocationIQ request. A month's count is what the request ceiling is enforced against, and a lost count is a ceiling that stops holding.

The station table survives for a different reason. Losing it costs no money, but a rebuild reads one page per station from a public service, about 9,400 requests. A run reads only the stale stations, and the stored rows tell it which stations are stale.

Nothing else SHALL be a table. A route answer recomputes from local routing alone, and `route-service` states that it is no longer stored. A refinement is no longer stored either, and `google-route-refinement` states what that costs.

An answer bought from an external service SHALL be stored **as the provider sent it**, in a single column, and SHALL NOT be spread across columns that mirror its shape. The store is then unaffected when that shape changes, which is the property that lets the provider's answer change without a migration.

It SHALL NOT be stored in whatever shape this application serves to its own callers. What the money bought is what the provider said; the mapping into the shape the page reads costs nothing and SHALL be applied on the way out, each time. Storing the derived shape instead would make a change to what the page wants invalidate rows that were paid for, and would discard the fields of the provider's answer that nothing reads yet.

**A station page is not bought, and the two rules above do not apply to it.** The page is HTML, and a caller reads fields. The station table SHALL store the fields that `gas-station-inventory` parses from the page, and SHALL NOT store the page.

**The build pipeline's own stores are not covered by this requirement.** `vinci-direct-pricing` keeps a rejection database that is deleted and rebuilt from routing alone. It is a scratch file for one long build, not state the application carries between requests, and it SHALL NOT be declared here or versioned with these tables.

#### Scenario: The schema has one source

- **WHEN** the tables the application uses are enumerated
- **THEN** every one of them is declared as a model, and no table is created by a statement written elsewhere

#### Scenario: A hand-written statement lives only in a revision

- **WHEN** the source is searched for statements that create a table, a virtual table, or a trigger
- **THEN** the only ones are in the revision that creates the geographic index and its triggers

#### Scenario: Two tables, and the reason each is kept

- **WHEN** the paid tables of the store are inspected
- **THEN** they are the autocomplete cache and the monthly request count, and each is kept because a lost row costs money

#### Scenario: Three tables in all

- **WHEN** the store is inspected
- **THEN** it holds the autocomplete cache, the monthly request count, the station table with its geographic index, and nothing else

#### Scenario: A bought answer is stored whole

- **WHEN** an autocomplete answer is stored
- **THEN** it is stored as one value, and adding a field to what the provider returns needs no schema change

#### Scenario: What is stored is the provider's answer, not ours

- **WHEN** an autocomplete answer is bought and stored
- **THEN** the stored value is the place list LocationIQ returned, with its own field names, and not the mapping the page is served

#### Scenario: Changing what the page is served costs no paid row

- **WHEN** the shape served to callers changes
- **THEN** every stored answer is still usable, because the mapping is applied on the way out rather than before the store

#### Scenario: A station is stored as parsed fields

- **WHEN** a station is stored
- **THEN** its name, address, services, and prices are separate values, and the page HTML is not stored

#### Scenario: The builder's rejection store is untouched

- **WHEN** the pipeline's direct-pricing step runs
- **THEN** it uses its own database, which is not versioned with the application's and is not declared with these models
