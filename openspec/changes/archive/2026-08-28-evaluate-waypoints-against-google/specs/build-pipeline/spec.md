## MODIFIED Requirements

### Requirement: Project layout

The repository root SHALL hold only the pipeline's entry points — `Makefile` and `docker-compose.yml` — together with configuration dotfiles such as `.gitignore` and `.env.example`. No source file SHALL sit at the root.

The container image definition and all pipeline scripts SHALL live under `builder/`. Generated artifacts SHALL live under `data/`.

The application that consumes those artifacts SHALL live under `french_tolls/`, together with its own container image definition and its tests. It is not part of the pipeline: it reads what the pipeline publishes and it is never invoked by a build step. Keeping it out of `builder/` keeps that boundary legible, and keeps a change to the web application from rebuilding the pipeline image.

The browser page SHALL live under `www/`, together with its own container image definition and the configuration of the server that fronts it. It is a third thing again: it holds no Python, it reads no artefact, and it reaches the application only over HTTP. A stylesheet has no business rebuilding a Python image.

The paid evaluation SHALL live under `evaluation/`, together with its own container image definition. It is a fourth kind of thing: it is not a build step, it produces no artefact the application reads, and it is the only part of this repository that spends money. Keeping it out of `builder/` is what stops it from ever becoming a prerequisite of a build.

What the evaluation produces SHALL be committed, unlike the pipeline's intermediates. The rule for the rest of `data/` is that anything regenerable is left out; the rule here is the opposite, because regenerating these costs money rather than time.

The application SHALL be tracked. It SHALL NOT carry a booth inventory or a tariff table of its own: those live under `data/`, are committed there already, and a second copy goes stale without saying so.

The artifacts the pipeline is asked to produce — the booth inventory, the route set, the gare mapping, and the segment weight file — SHALL be committed, so a consumer can read them without running the pipeline. Regenerable intermediates, OSM extracts, and the per-run diagnostic reports SHALL NOT be committed.

The segment weight file is carried for the reason the booth sides are: it is derived from the routing graph, which is not in the repository, so a consumer who has only the checkout cannot rebuild it however cheap the step is.

The exclusion report, the uncovered report, and the segment weight report SHALL still be produced on every run: they describe what one run of the pipeline decided, and the gare mapping step reads the exclusion report to name the nearest excluded booth when a placemark matches nothing. They are diagnostics about a run rather than published outputs, so they are not carried in the repository.

#### Scenario: Scripts are located together

- **WHEN** the repository is inspected
- **THEN** the Dockerfile and the pipeline scripts are under `builder/`, and no pipeline script sits at the repository root

#### Scenario: The page is located together

- **WHEN** the repository is inspected
- **THEN** the page, its Dockerfile, and its server configuration are under `www/`, and none of them sits under `french_tolls/` or `builder/`

#### Scenario: The evaluation is located together

- **WHEN** the repository is inspected
- **THEN** the evaluation's scripts and its Dockerfile are under `evaluation/`, and none of them sits under `builder/`

#### Scenario: Bought answers are committed

- **WHEN** the repository is checked out
- **THEN** `data/test_cities.yaml` and the stored Google routes are present, because buying them again costs money

#### Scenario: The application is located together

- **WHEN** the repository is inspected
- **THEN** the application, its Dockerfile, and its tests are under `french_tolls/`, and none of them sits under `builder/`

#### Scenario: The application carries no data of its own

- **WHEN** the files under `french_tolls/` are listed
- **THEN** none of them is a booth inventory or a tariff table

#### Scenario: Root holds only entry points and configuration

- **WHEN** the tracked files at the repository root are listed
- **THEN** they are `Makefile`, `docker-compose.yml`, and configuration dotfiles, and nothing else

#### Scenario: Deliverables are committed

- **WHEN** the repository is checked out without running the pipeline
- **THEN** the booth inventory, the route set, the gare mapping, and `data/segment_weights.csv` are present under `data/`

#### Scenario: Reports are produced but not committed

- **WHEN** the pipeline has run
- **THEN** the exclusion report, the uncovered report, and `data/segment_weights_report.json` exist under `data/` and are untracked

#### Scenario: Extracts and intermediates are not committed

- **WHEN** the pipeline has run
- **THEN** the OSM extracts and the regenerable intermediates it produced are untracked
