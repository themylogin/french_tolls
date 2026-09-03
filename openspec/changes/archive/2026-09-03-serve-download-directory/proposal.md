## Why

`README.md` tells an operator to install this project by downloading the extract the committed data was built from:

```
curl -o data/france-latest.osm.pbf \
    https://french-tolls.undiscoveredlatitudes.com/download/france-latest.osm.pbf
```

That URL returns 404. Nothing in the deployment serves `/download`, so the first instruction of option 1 fails, and the reader is left to find an extract of the right vintage somewhere else — which is the one thing option 1 exists to avoid, because the committed toll data only matches the extract it was derived from.

The front end already has a container serving the origin the page and the API share. Adding one location to it is the whole change.

## What Changes

- The front end SHALL serve `/download` from a directory on the host, so an operator can publish the extract their committed data was built from.
- The directory SHALL be `DOWNLOAD_PATH`, defaulting to `./download` so that a deployment with no such setting still starts and serves an empty directory rather than failing.
- The mount SHALL be read-only. Nothing in this project writes there; the operator puts files in it.
- `/download` SHALL NOT list its contents. A file resolves by its exact path and `/download/` itself does not enumerate what is there.
- No change to `/api`, to the page, or to any other location.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `web-front-end`: the origin that serves the page and proxies the API also serves a directory of files the operator publishes.

## Impact

- **Modified**: `www/nginx.conf` (one `location`), `docker-compose.yml` (a read-only volume on `nginx`), `.env.example` (`DOWNLOAD_PATH`), `README.md` (say where the file goes).
- **New**: `download/`, an empty directory in the repository with its contents ignored by git, so the default path exists before anything mounts it.
- **Unchanged**: the page, the API proxy, the application image, and every other service. The front end image gains no file — the directory arrives as a mount, not as a layer.
- **Not a secret store.** Whatever is in the directory is served to anyone who knows a filename. It holds what the operator chose to publish and nothing else.
