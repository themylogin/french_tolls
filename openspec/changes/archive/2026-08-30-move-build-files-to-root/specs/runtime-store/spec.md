## MODIFIED Requirements

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
