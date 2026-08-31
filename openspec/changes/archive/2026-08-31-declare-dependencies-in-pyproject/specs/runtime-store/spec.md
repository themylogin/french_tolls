## MODIFIED Requirements

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
