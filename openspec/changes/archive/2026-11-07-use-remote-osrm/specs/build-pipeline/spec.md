# Spec Delta

## MODIFIED Requirements

### Requirement: Named routing service

The pipeline SHALL define two long-running OSRM query services, each addressable under its own name both as a container and on the Compose network.

`osrm-toll` SHALL serve the graph from `OSRM_TOLL_PATH` and SHALL be the service every step that reasons about the road network queries. `osrm-optimal` SHALL serve the graph from `OSRM_OPTIMAL_PATH`.

The two SHALL be published on different host ports, so that a consumer outside the Compose network can reach either where the host permits it. A published port is a convenience for inspection and SHALL NOT be the path any service of this project takes: measured on the development host, both published ports refuse connections while the same query over the Compose network is answered. Every consumer in the repository — the build steps, the web application, and the bot — SHALL therefore address the routers by service name.

**The one exception is an address that `remote-routers` configures.** The web application and the bot SHALL then address that router there. The build steps SHALL NOT follow it. A step reads or writes the local graph, so it SHALL query the local router.

The test runner is not among them. Its suite answers its own routing questions from a graph written in the test, so it queries neither router and is given neither address.

Services that are not part of the pipeline SHALL sit behind a Compose profile, so that a plain `docker compose up` starts the two query services and nothing else. One-shot preprocessing containers SHALL NOT be started by a plain `docker compose up` either.

#### Scenario: Service is addressable by name

- **WHEN** the route set step issues routing requests
- **THEN** it reaches the query service at the host name `osrm-toll`

#### Scenario: Consumers do not use the published ports

- **WHEN** the web application or the bot queries a router that has no configured address
- **THEN** it addresses `osrm-toll` or `osrm-optimal` over the Compose network, not a host port

#### Scenario: A build step ignores a configured address

- **WHEN** `OSRM_TOLL_URL` is set and the route set step issues routing requests
- **THEN** it still reaches `osrm-toll` over the Compose network

#### Scenario: The test runner queries no router

- **WHEN** the test runner runs
- **THEN** it issues no routing request, and its configuration carries neither router's address

#### Scenario: Both services are reachable from the host

- **WHEN** both services are running on a host that permits the published ports
- **THEN** each answers on its own host port, and a route requested from one is answered from its own graph

#### Scenario: Plain compose up

- **WHEN** `docker compose up` is run
- **THEN** the query services start, and the one-shot preprocessing containers, the web application, the bot, and the test runner do not

#### Scenario: The toll-weighted service without its graph

- **WHEN** `osrm-optimal` is started before the toll-weighted graph has been produced
- **THEN** it fails to start rather than answering from anything else
