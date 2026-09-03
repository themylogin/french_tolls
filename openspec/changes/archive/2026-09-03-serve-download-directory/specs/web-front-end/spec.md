## ADDED Requirements

### Requirement: The origin serves a directory the operator publishes

Whatever serves the page SHALL also serve `/download` from a directory on the host, so that a deployment can publish the files its own instructions point at.

`README.md` tells an operator to fetch the extract the committed data was built from at `/download/france-latest.osm.pbf`. The committed toll data matches that extract and no other, so an installation that cannot obtain it has to rebuild every artefact from a different one. The instruction and the thing it fetches belong to the same deployment.

The directory SHALL be named by `DOWNLOAD_PATH`, defaulting to `./download`. A deployment that sets nothing SHALL still start, serving an empty directory: an unset variable that stops the front end would take the page down over a file nobody asked for.

The directory SHALL be mounted read-only. Nothing in this project writes to it, and a served path that the server can also write to is a larger promise than the feature needs.

`/download` SHALL NOT enumerate its contents. A request for an exact path SHALL be answered and a request for the directory itself SHALL NOT list what is in it. The instructions name the file, so nothing needs the index, and a listing publishes every name in the directory to anyone who asks for it.

Requests under `/download` SHALL NOT be proxied to the application, and SHALL NOT be served from the image's own document root.

#### Scenario: The published extract is fetchable

- **WHEN** an operator places `france-latest.osm.pbf` in the directory and a visitor requests `/download/france-latest.osm.pbf`
- **THEN** the file is served

#### Scenario: A deployment that sets nothing still starts

- **WHEN** the front end starts with no `DOWNLOAD_PATH` in the environment
- **THEN** it serves the page and the API as before, and `/download` resolves against the default directory

#### Scenario: The directory is not listed

- **WHEN** a visitor requests `/download/`
- **THEN** the response does not enumerate the directory's contents

#### Scenario: A file that is not there

- **WHEN** a visitor requests a path under `/download` that names no file
- **THEN** the response is 404, and the request reaches neither the application nor the page's document root

#### Scenario: The server cannot write there

- **WHEN** the front end container is running
- **THEN** the directory is mounted read-only
