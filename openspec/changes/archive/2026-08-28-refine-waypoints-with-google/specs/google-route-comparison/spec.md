## MODIFIED Requirements

### Requirement: The evaluation is a Compose service of its own

`docker-compose.yml` SHALL define an `evaluation` service, built from an image under `evaluation/`, behind its own profile so that neither `docker compose up` nor the application's profile starts it.

It SHALL mount `./data` writable, because what it produces is kept there, and SHALL reach the application and the routers by service name over the Compose network.

It is not the only service that makes a paid outbound request: the web application refines a journey's waypoints against Google, under a monthly ceiling of its own. The two are separate spenders with separate purposes — the evaluation buys a corpus once to measure against, the application buys one answer to improve one link — and neither reads the other's budget.

#### Scenario: It is not started by anything else

- **WHEN** `docker compose up` or `docker compose --profile app up` is run
- **THEN** the evaluation service does not start

#### Scenario: The two spenders are independent

- **WHEN** the evaluation runs a sweep
- **THEN** the application's monthly refinement budget is unaffected by it, and the evaluation's spending is not counted against it

#### Scenario: It reaches the application by name

- **WHEN** the sweep asks for a route
- **THEN** it calls the web service over the Compose network, not a published host port
