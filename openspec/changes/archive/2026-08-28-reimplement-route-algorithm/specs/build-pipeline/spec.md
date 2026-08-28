## MODIFIED Requirements

### Requirement: Project layout

The repository root SHALL hold only the pipeline's entry points — `Makefile` and `docker-compose.yml` — together with configuration dotfiles such as `.gitignore` and `.env.example`. No source file SHALL sit at the root.

The container image definition and all pipeline scripts SHALL live under `builder/`. Generated artifacts SHALL live under `data/`.

The application that consumes those artifacts SHALL live under `french_tolls/`, together with its own container image definition and its tests. It is not part of the pipeline: it reads what the pipeline publishes and it is never invoked by a build step. Keeping it out of `builder/` keeps that boundary legible, and keeps a change to the web application from rebuilding the pipeline image.

The application SHALL be tracked. It SHALL NOT carry a booth inventory or a tariff table of its own: those live under `data/`, are committed there already, and a second copy goes stale without saying so.

The artifacts the pipeline is asked to produce — the booth inventory, the route set, the gare mapping, and the segment weight file — SHALL be committed, so a consumer can read them without running the pipeline. Regenerable intermediates, OSM extracts, and the per-run diagnostic reports SHALL NOT be committed.

The segment weight file is carried for the reason the booth sides are: it is derived from the routing graph, which is not in the repository, so a consumer who has only the checkout cannot rebuild it however cheap the step is.

The exclusion report, the uncovered report, and the segment weight report SHALL still be produced on every run: they describe what one run of the pipeline decided, and the gare mapping step reads the exclusion report to name the nearest excluded booth when a placemark matches nothing. They are diagnostics about a run rather than published outputs, so they are not carried in the repository.

#### Scenario: Scripts are located together

- **WHEN** the repository is inspected
- **THEN** the Dockerfile and the pipeline scripts are under `builder/`, and no pipeline script sits at the repository root

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

### Requirement: Named routing service

The pipeline SHALL define two long-running OSRM query services, each addressable under its own name both as a container and on the Compose network.

`osrm-toll` SHALL serve the graph from `OSRM_TOLL_PATH` and SHALL be the service every step that reasons about the road network queries. `osrm-optimal` SHALL serve the graph from `OSRM_OPTIMAL_PATH`.

The two SHALL be published on different host ports, so that a consumer outside the Compose network can reach either where the host permits it. A published port is a convenience for inspection and SHALL NOT be the path any service of this project takes: measured on the development host, both published ports refuse connections while the same query over the Compose network is answered. Every consumer in the repository — the build steps, the web application, the bot, and the test runner — SHALL therefore address the routers by service name.

Services that are not part of the pipeline SHALL sit behind a Compose profile, so that a plain `docker compose up` starts the two query services and nothing else. One-shot preprocessing containers SHALL NOT be started by a plain `docker compose up` either.

#### Scenario: Service is addressable by name

- **WHEN** the route set step issues routing requests
- **THEN** it reaches the query service at the host name `osrm-toll`

#### Scenario: Consumers do not use the published ports

- **WHEN** the web application, the bot, or the test runner queries a router
- **THEN** it addresses `osrm-toll` or `osrm-optimal` over the Compose network, not a host port

#### Scenario: Both services are reachable from the host

- **WHEN** both services are running on a host that permits the published ports
- **THEN** each answers on its own host port, and a route requested from one is answered from its own graph

#### Scenario: Plain compose up

- **WHEN** `docker compose up` is run
- **THEN** the query services start, and the one-shot preprocessing containers, the web application, the bot, and the test runner do not

#### Scenario: The toll-weighted service without its graph

- **WHEN** `osrm-optimal` is started before the toll-weighted graph has been produced
- **THEN** it fails to start rather than answering from anything else
