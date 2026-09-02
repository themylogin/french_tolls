## Context

See `proposal.md` — Why. The front end is one nginx container built from `www/`, serving the page from the image and proxying `/api` to the application over the Compose network. It mounts nothing today.

Three things about that shape decide this change: the image carries its own files, so a directory of operator content has to arrive as a mount; Compose cannot mount conditionally, so the variable needs a value in every deployment; and Docker creates a missing bind-mount source itself, as root, which is a trap rather than a convenience.

## Goals

- Make the URL in `README.md` resolve.
- Leave a deployment that sets nothing working exactly as before.
- Serve what the operator put there and nothing else.

## Non-Goals

- Uploading, or any write path. The operator puts files in the directory by whatever means they already use to reach the host.
- Serving the pipeline's `data/` directory. See below.
- Access control. Anyone who knows a filename gets the file; that is what publishing means.

## Decisions

### The default is `./download`, not `./data`

`data/` already holds `france-latest.osm.pbf` — the very file the README points at — so pointing `/download` there would need no operator step at all. It is still wrong. `data/` also holds every artefact the pipeline writes, including files no one chose to publish, and a rule that serves the pipeline's working directory publishes whatever a later step happens to put in it. The set of things served should be a decision, not a side effect.

`./download` starts empty and holds exactly what was put there. An operator following the README copies or links the extract into it, which is one step, and that step is the decision to publish.

### The directory is committed empty, with its contents ignored

Compose creates a missing bind-mount source as a root-owned directory. That is a poor first experience — `make web` succeeds, `/download` returns 404 for everything, and the operator cannot write to the directory that was made for them without `sudo`.

So `download/` exists in the repository with a `.gitignore` that ignores its contents and keeps the directory itself. The default path then always resolves to a directory the operator owns.

### An unset variable defaults rather than fails

The pipeline's idiom for an unset path is to stop with a message — `guard-osrm-path` exists because an empty `OSRM_TOLL_PATH` silently writes a 10 GB graph into `/`. That reasoning does not carry here. The failure mode of an unset `DOWNLOAD_PATH` is a bind mount of `:/download`, which Compose rejects, taking down the page and the API over a directory that most deployments will never use.

The page is the product; the download is an accessory. Defaulting keeps the accessory from being able to break the product.

### No listing

`autoindex` stays off, so `/download/` does not enumerate. The README names the file, so nothing needs an index, and a listing turns "publish this extract" into "publish the name of everything in this directory".

The consequence to accept: an operator who forgets the exact filename gets a 403 rather than a menu. The filename is in the README, next to the URL.

### The location is `alias`, not a second document root

`location /download` serves from the mount by `alias`, so the page's own root is untouched and the URL prefix is not required to exist inside the image. `try_files` in `location /` already answers everything else, and the more specific prefix wins — no ordering subtlety and no interaction with the `/api` proxy.

## Risks / Trade-offs

- **A deployment publishes something by accident.** → The directory starts empty, is separate from every directory the pipeline writes, and is filled only by hand. Nothing in this project writes to it.
- **The served file is large and nginx is also serving the page.** → The extract is about 4.8 GB. nginx serves static files from disk without buffering them into memory, and the download shares the container with a page that is three files; a transfer competes for bandwidth, not for the application, which is a separate container.
- **The default path is inside the repository, so a checkout can carry a 4.8 GB file into a rebuild.** → The contents are git-ignored, and `.dockerignore` already excludes everything the front end image does not name.
- **Someone points `DOWNLOAD_PATH` at `/` or at `data/`.** → It is their host and their choice; the design records why the default does not.

## Migration Plan

1. Add the location to `www/nginx.conf` and the read-only volume to the `nginx` service.
2. Create `download/` with a `.gitignore` that keeps the directory and ignores its contents.
3. Add `DOWNLOAD_PATH` to `.env.example` with the default written out.
4. Say in `README.md` that the file the download URL serves is the one to place there.
5. `make web` rebuilds the front end image; existing deployments need no `.env` change.

Rollback is removing the location and the volume; nothing else depends on either.

## Open Questions

None.
