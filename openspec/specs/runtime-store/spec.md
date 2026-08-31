# runtime-store Specification

## Purpose
What the application persists between requests, how that schema is declared and versioned, how a schema change reaches a running deployment, and why every call into the store is a coroutine.

## Requirements

### Requirement: Every persisted table is declared in one place

The application SHALL declare every table it reads or writes as a model, in one module, and SHALL NOT create a table from a statement written by hand anywhere else.

There SHALL be exactly two:

- an autocomplete cache, keyed by the normalised query string, holding the answer that was bought for it;
- a count of paid Google requests, one row per calendar month keyed as `YYYY-MM`.

Both survive because losing a row costs money. An autocomplete answer cost a paid LocationIQ request. A month's count is what the request ceiling is enforced against, and a lost count is a ceiling that stops holding.

Nothing else SHALL be a table. A route answer recomputes from local routing alone, and `route-service` states that it is no longer stored. A refinement is no longer stored either, and `google-route-refinement` states what that costs.

An answer bought from an external service SHALL be stored **as the provider sent it**, in a single column, and SHALL NOT be spread across columns that mirror its shape. The store is then unaffected when that shape changes, which is the property that lets the provider's answer change without a migration.

It SHALL NOT be stored in whatever shape this application serves to its own callers. What the money bought is what the provider said; the mapping into the shape the page reads costs nothing and SHALL be applied on the way out, each time. Storing the derived shape instead would make a change to what the page wants invalidate rows that were paid for, and would discard the fields of the provider's answer that nothing reads yet.

**The build pipeline's own stores are not covered by this requirement.** `vinci-direct-pricing` keeps a rejection database that is deleted and rebuilt from routing alone. It is a scratch file for one long build, not state the application carries between requests, and it SHALL NOT be declared here or versioned with these tables.

#### Scenario: The schema has one source

- **WHEN** the tables the application uses are enumerated
- **THEN** every one of them is declared as a model, and no table is created by a statement written elsewhere

#### Scenario: Two tables, and the reason each is kept

- **WHEN** the store is inspected
- **THEN** it holds the autocomplete cache and the monthly request count, and nothing else

#### Scenario: A bought answer is stored whole

- **WHEN** an autocomplete answer is stored
- **THEN** it is stored as one value, and adding a field to what the provider returns needs no schema change

#### Scenario: What is stored is the provider's answer, not ours

- **WHEN** an autocomplete answer is bought and stored
- **THEN** the stored value is the place list LocationIQ returned, with its own field names, and not the mapping the page is served

#### Scenario: Changing what the page is served costs no paid row

- **WHEN** the shape served to callers changes
- **THEN** every stored answer is still usable, because the mapping is applied on the way out rather than before the store

#### Scenario: The builder's rejection store is untouched

- **WHEN** the pipeline's direct-pricing step runs
- **THEN** it uses its own database, which is not versioned with the application's and is not declared with these models

### Requirement: The schema is versioned, and a change is a revision

The database SHALL carry a record of which schema version it is at.

A schema change SHALL be expressed as a revision applied to that record, and SHALL NOT be expressed as code that inspects the database and decides what to do. Three such functions existed — renaming the file, adopting a table under an old name, and dropping two tables that carried a column the current statements did not mention — and each was written because `CREATE TABLE IF NOT EXISTS` will not alter a table that is already there. A version record answers the question those functions were reading the schema to guess at.

Applying the revisions to a database already at the latest version SHALL do nothing.

**A revision's filename SHALL begin with the date and time it was written, and SHALL end with the name it was given.** Listing the directory then reads in the order the revisions were written, which is the order they apply in and the one thing a reader wants from the listing. Named for the revision id instead, the listing sorts by a hash and the history has to be reconstructed by opening files.

The identity of a revision SHALL remain the id recorded inside it, never its filename. A revision may therefore be renamed without touching any database, and the version a deployment records SHALL be unaffected.

#### Scenario: A fresh database is built from the revisions

- **WHEN** the application starts against no database at all
- **THEN** the revisions run in order and produce the schema the models declare

#### Scenario: Applying twice changes nothing

- **WHEN** the revisions are applied to a database already at the latest version
- **THEN** nothing is altered and no row is lost

#### Scenario: The version is recorded in the database

- **WHEN** the database is inspected
- **THEN** it names the schema version it is at, without the schema having to be read to work it out

#### Scenario: The revisions list in the order they were written

- **WHEN** the revision directory is listed in name order
- **THEN** the revisions appear oldest first, without any file being opened

#### Scenario: A new revision is named for when it was written

- **WHEN** a revision is generated
- **THEN** its filename carries the date and time of writing followed by the name it was given

#### Scenario: Renaming a revision changes no database

- **WHEN** a revision file is renamed
- **THEN** the version a database records is unchanged, because that version is the id inside the file

### Requirement: Exactly one process applies the schema

The schema SHALL be applied by a single dedicated one-shot run, and SHALL NOT be applied by a service that goes on to serve requests.

Every service that reads or writes the store SHALL NOT start until that run has completed. The web application and the Telegram bot open one SQLite file on one shared volume; both applying revisions at once is the failure this exists to prevent.

A service SHALL NOT create a missing table for itself as a side effect of opening the store.

#### Scenario: Migration is its own run

- **WHEN** the application stack is started
- **THEN** one run applies the schema and exits, and the serving processes start after it

#### Scenario: Two serving processes do not race

- **WHEN** the web application and the bot start together
- **THEN** neither applies a revision, because the schema was already applied before either began

#### Scenario: A serving process does not create its own tables

- **WHEN** a serving process opens a store whose schema was never applied
- **THEN** it does not create the tables itself

### Requirement: The store is reached without blocking the event loop

Every call that reads or writes the store SHALL be a coroutine, and SHALL reach the database through a driver that does not block the loop it is awaited on.

The application is asynchronous throughout. A blocking call inside it stalls every other request in flight for its duration, and a thread pool wrapped around a blocking driver is a second mechanism to reason about where an asynchronous driver is available.

#### Scenario: A read does not stall a concurrent request

- **WHEN** one request reads the store while another is being served
- **THEN** the second request is not held up by the first request's read

#### Scenario: Every store call is awaited

- **WHEN** a caller reads or writes the store
- **THEN** it awaits the call, and no caller reaches the database synchronously

### Requirement: A paid request is claimed atomically, and the claim is what counts

Claiming one paid request against the month's ceiling SHALL be a single atomic operation that both tests the ceiling and records the increment.

The claim SHALL be recorded before the request it accounts for is issued, so a request whose answer never arrives is still counted: it has been made and may still have been billed. The count SHALL be able to overstate and SHALL NOT be able to understate.

A claim refused at the ceiling SHALL NOT increment the count. Two claims made at once SHALL raise the count by two, and SHALL NOT both read the same value and write it back.

Correctness here SHALL NOT depend on the transaction mode a connection happens to be using. `google-route-refinement` states the same guarantee from the caller's side; this requirement is where it is kept.

#### Scenario: A refused claim costs nothing

- **WHEN** the month's count is already at the ceiling and a claim is made
- **THEN** the claim is refused and the count is unchanged

#### Scenario: Two claims at once

- **WHEN** two claims are made concurrently below the ceiling
- **THEN** both succeed and the month's count rises by two

#### Scenario: A failed request still counts

- **WHEN** a claim succeeds and the request it paid for then errors
- **THEN** the month's count still includes it

#### Scenario: A new month starts from zero

- **WHEN** the calendar month turns
- **THEN** the count for the new month starts at zero without anything being reset by hand

### Requirement: The dependencies the store needs are pinned, and every consumer has them

The application image SHALL install its Python dependencies from a pinned list rather than from the distribution's packages, and SHALL NOT mix the two in one environment.

The distribution's SQLAlchemy predates the declarative style these models are written in, so the version cannot be left to the distribution. Pinning the whole list rather than one package of it also means one file states what the application runs against.

**The pinned list SHALL name every package that will be installed, not only the ones this project asked for.** A list of direct dependencies alone leaves the packages they pull in to be resolved afresh at each build, against whatever the index holds that day — so the file that claims to say what the application runs against does not mention most of what it runs against.

**That list SHALL be compiled from a declaration rather than maintained by hand**, and the declaration SHALL carry only the bounds that have a reason. A version written by hand cannot distinguish a bound that matters from one that is merely what a resolver picked, and every pin then looks equally deliberate. Where a bound is load-bearing it belongs in the declaration, where it can be read and changed; the exact versions belong in the compiled list, where nothing is decided by a person.

The two SHALL agree. Regenerating the compiled list from an unchanged declaration SHALL produce the file already committed, so that a list which has drifted from the declaration is detectable rather than merely suspected.

**Regeneration SHALL resolve against the interpreter the application runs on**, not against whatever a developer's machine happens to have. A resolution is specific to a Python version, and one produced elsewhere can pin a set the image cannot install.

The compiled list SHALL remain installable by the image without additional tooling. Whatever produces it is a tool for producing it, and SHALL NOT become something the image needs.

**Every image that imports the application package SHALL be able to import the store.** The refinement module imports the store at module level, and the evaluation imports the refinement module for its corridor measure and waypoint placement. An image that can import one and not the other fails at import rather than at use.

#### Scenario: Versions come from one file

- **WHEN** the application image is built
- **THEN** every Python dependency it runs against is named with its version in one pinned list

#### Scenario: A transitive package is named too

- **WHEN** the pinned list is read
- **THEN** it names the packages the direct dependencies pull in, each pinned and each recorded with what required it

#### Scenario: The declaration carries the reasons

- **WHEN** a dependency's bound is inspected
- **THEN** it is stated where it can be read and changed, and a dependency with no reason to be bounded carries no bound

#### Scenario: The compiled list reproduces

- **WHEN** the list is regenerated from an unchanged declaration
- **THEN** the result is the file already committed

#### Scenario: A changed declaration is not enough on its own

- **WHEN** a dependency is added to the declaration and the list is not regenerated
- **THEN** the two disagree, and the disagreement is visible by regenerating rather than by reading

#### Scenario: The image needs no tool to install it

- **WHEN** the application image installs its dependencies
- **THEN** it does so from the compiled list alone, without whatever produced that list

#### Scenario: The environment is not mixed

- **WHEN** the application's Python environment is inspected
- **THEN** it does not draw on the distribution's site packages

#### Scenario: The evaluation can still import the application package

- **WHEN** the evaluation imports the refinement module for its corridor measure
- **THEN** the import succeeds, because the store's dependencies are present in that image too
