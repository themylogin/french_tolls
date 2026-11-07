# remote-routers Specification

## Purpose
Lets a deployment reach OSRM at a configured address instead of its own internal servers. Lets a deployment that holds the graphs lend them to another deployment through a relay that checks a shared token.

## Requirements

### Requirement: Each router's address is a setting

The application SHALL send every request for the untouched graph to `OSRM_TOLL_URL`. It SHALL send every request for the toll-weighted graph to `OSRM_OPTIMAL_URL`.

An unset or empty value SHALL mean the internal server: `http://osrm-toll:5000` or `http://osrm-optimal:5000`. A trailing `/` SHALL be ignored. Each setting SHALL act alone.

#### Scenario: No address is configured

- **WHEN** neither `OSRM_TOLL_URL` nor `OSRM_OPTIMAL_URL` is set
- **THEN** snapping, the distance check, matching and the fast route reach `http://osrm-toll:5000`, and the optimal route reaches `http://osrm-optimal:5000`

#### Scenario: The untouched graph is remote

- **WHEN** `OSRM_TOLL_URL` is `https://example.org/api/osrm/toll` and a journey is answered
- **THEN** every snap, distance check, match and fast route goes to an address that starts with `https://example.org/api/osrm/toll/`, and none reaches `osrm-toll`

#### Scenario: Only one graph is remote

- **WHEN** only `OSRM_TOLL_URL` is set
- **THEN** the optimal route and the routes through waypoints still reach `http://osrm-optimal:5000`

#### Scenario: A trailing slash is ignored

- **WHEN** `OSRM_TOLL_URL` is `https://example.org/api/osrm/toll/`
- **THEN** a snap goes to `https://example.org/api/osrm/toll/nearest/v1/driving/...`, with one `/` after `toll`

### Requirement: The client sends the access token

When `OSRM_ACCESS_TOKEN` is set, every router request from the application and from the evaluation SHALL carry the header `X-Auth` with the token as its value. This SHALL apply to both graphs, internal or remote.

When the token is unset, a router request SHALL carry no `X-Auth` header. The token SHALL NOT appear in a URL, a log line or a failure record.

#### Scenario: The token is set

- **WHEN** `OSRM_ACCESS_TOKEN` is `s3cret` and the client asks either graph
- **THEN** the request carries `X-Auth: s3cret`

#### Scenario: The token is unset

- **WHEN** `OSRM_ACCESS_TOKEN` is unset or empty
- **THEN** no router request carries an `X-Auth` header

#### Scenario: The evaluation sends the token

- **WHEN** `OSRM_ACCESS_TOKEN` is set and `make test_cities` asks the router for a table
- **THEN** the table request carries `X-Auth` with the token

#### Scenario: A refusal does not leak the token

- **WHEN** a router address refuses a request
- **THEN** the failure names the address and the code the router answered, and does not contain the token

### Requirement: The relay exists only when a token is set

When `OSRM_ACCESS_TOKEN` is unset, the API SHALL serve no path under `/api/osrm/`.

When the token is set, the API SHALL serve `GET /api/osrm/toll/<rest>` and `GET /api/osrm/optimal/<rest>`. It SHALL serve no other graph name and no other method under `/api/osrm/`.

#### Scenario: No token, no relay

- **WHEN** `OSRM_ACCESS_TOKEN` is unset and a request for `/api/osrm/toll/nearest/v1/driving/2.35,48.86` arrives
- **THEN** the API answers 404 and sends nothing to a router

#### Scenario: An unknown graph

- **WHEN** the token is set and a request for `/api/osrm/fast/nearest/v1/driving/2.35,48.86` arrives
- **THEN** the API answers 404

#### Scenario: Another method

- **WHEN** the token is set and a `POST` to `/api/osrm/toll/nearest/v1/driving/2.35,48.86` arrives
- **THEN** the API answers 405 and sends nothing to a router

### Requirement: The relay serves only a holder of the token

The relay SHALL answer a request only when its `X-Auth` header equals the token exactly.

Otherwise it SHALL answer 401 with the JSON body `{"code": "Unauthorized", "message": ...}`, and SHALL send nothing to a router. The comparison SHALL take the same time wherever the two values differ.

#### Scenario: The header is missing

- **WHEN** a relay request arrives without `X-Auth`
- **THEN** the relay answers 401 with `code` set to `Unauthorized`, and no router receives a request

#### Scenario: The header is wrong

- **WHEN** the token is `s3cret` and a relay request carries `X-Auth: s3cre`
- **THEN** the relay answers 401, and no router receives a request

### Requirement: The relay forwards a request unchanged

The relay SHALL send the path after `/api/osrm/<graph>` and the query string to that graph's router, byte for byte. It SHALL return the router's status, content type and body unchanged.

The router SHALL be the one the deployment itself uses for that graph. The relay SHALL send the token to it as the client does.

#### Scenario: The answer is the router's

- **WHEN** a holder of the token asks for `/api/osrm/optimal/route/v1/driving/2.35,48.86;4.83,45.76?overview=false`
- **THEN** the router receives `/route/v1/driving/2.35,48.86;4.83,45.76?overview=false`, and the relay returns its status, content type and body

#### Scenario: Escapes are kept

- **WHEN** a relayed query carries a hint with `%2B`, `%2F` and `%3D` in it
- **THEN** the router receives `%2B`, `%2F` and `%3D` in the same places

#### Scenario: A router error passes through

- **WHEN** the router answers 400 with `code` set to `NoSegment`
- **THEN** the relay answers 400 with the same body

### Requirement: The relay reports a router that does not answer

When the router refuses the connection, or does not answer within the request timeout, the relay SHALL answer 502. The body SHALL be `{"code": "RouterUnavailable", "message": ...}`. The message SHALL name the graph and SHALL NOT contain the token.

#### Scenario: The router is down

- **WHEN** a holder of the token asks the relay and that graph's router is not running
- **THEN** the relay answers 502 with `code` set to `RouterUnavailable`, and the message names the graph

#### Scenario: The client reads the relay's failure

- **WHEN** a remote client receives that 502
- **THEN** the journey fails with the router reported unavailable

### Requirement: A whole trace fits through the relay

The front end and the web application SHALL accept a request line of up to 1 MiB.

The bot matches a trace as one GET request of 40 to 120 KB. Both servers refuse more than 8 KB by default.

#### Scenario: A long trace is relayed

- **WHEN** a holder of the token sends a `/api/osrm/toll/match/...` request with a 200 KB request line to the front end
- **THEN** the router answers it, and neither the front end nor the web application refuses it for its length

### Requirement: An answer that is not JSON is an unavailable router

The routing client SHALL treat an answer whose body is not a JSON object as a router that did not answer. The failure SHALL name the address and the HTTP status.

#### Scenario: A proxy error page

- **WHEN** a router address answers 502 with an HTML page
- **THEN** the query fails with the router reported unavailable, naming the address and `502`, and no JSON decode error reaches the caller

#### Scenario: A refused token

- **WHEN** a remote relay answers 401 with `code` set to `Unauthorized`
- **THEN** the query fails with the router reported unavailable, naming the address and `Unauthorized`

### Requirement: An internal router with a configured address is not started

`make web`, `make bot`, `make app`, `make test_cities`, `make test_google_routes` and `make test_google` SHALL start only the internal routers that have no configured address.

Each SHALL stop an internal router that has a configured address, if it runs. No container SHALL run a placeholder process in place of a router.

#### Scenario: Both graphs are remote

- **WHEN** `OSRM_TOLL_URL` and `OSRM_OPTIMAL_URL` are set and `make web` runs
- **THEN** `web` and `nginx` run, and neither `osrm-toll` nor `osrm-optimal` has a running container

#### Scenario: One graph is remote

- **WHEN** only `OSRM_OPTIMAL_URL` is set and `make bot` runs
- **THEN** `osrm-toll` runs and `osrm-optimal` does not

#### Scenario: A router from before is stopped

- **WHEN** `osrm-toll` runs, `OSRM_TOLL_URL` is then set, and `make web` runs
- **THEN** `osrm-toll` is stopped

#### Scenario: The pipeline keeps its router

- **WHEN** `OSRM_TOLL_URL` is set and a build step that queries the road network runs
- **THEN** the step starts `osrm-toll` and queries it at `http://osrm-toll:5000`

### Requirement: A deployment with remote routers needs no graph

The application targets SHALL require the graph path only of a router they start. Compose SHALL load the project when `OSRM_TOLL_PATH` or `OSRM_OPTIMAL_PATH` is unset.

A service that mounts an unset path SHALL fail to start, naming the unset variable. It SHALL NOT create a directory for it.

#### Scenario: No graph on the host

- **WHEN** both URLs are set, both graph paths are unset, and `make app` runs
- **THEN** `web`, `bot` and `nginx` start, and no guard refuses for a graph path

#### Scenario: A started router still needs its path

- **WHEN** `OSRM_TOLL_URL` and `OSRM_TOLL_PATH` are both unset and `make web` runs
- **THEN** it stops with a message that names `OSRM_TOLL_PATH`

#### Scenario: A router started by hand without its path

- **WHEN** `OSRM_TOLL_PATH` is unset and `docker compose up osrm-toll` runs
- **THEN** the container does not start, the error names `OSRM_TOLL_PATH`, and no directory is created on the host

### Requirement: Two deployments share routers through three settings

`.env.example` SHALL list `OSRM_TOLL_URL`, `OSRM_OPTIMAL_URL` and `OSRM_ACCESS_TOKEN`, empty, each with a line on its use.

`README.md` SHALL describe the setup. The lender sets the token. The borrower sets both URLs to the lender's `/api/osrm/toll` and `/api/osrm/optimal`, and the same token.

#### Scenario: A borrower follows the README

- **WHEN** an operator sets the three values as the README says, on a host with no graph, and runs `make web`
- **THEN** the page answers a journey with the lender's routes
