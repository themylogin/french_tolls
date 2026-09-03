## 1. The directory

- [x] 1.1 Create `download/` with a `.gitignore` that ignores its contents and keeps the directory, and verify `git status` is clean with a file dropped in it
- [x] 1.2 Verify the directory is owned by the invoking user after `make web`, not created as root by Compose

## 2. The mount

- [x] 2.1 Mount `${DOWNLOAD_PATH:-./download}:/download:ro` on the `nginx` service, and verify the container sees the host directory
- [x] 2.2 Verify a deployment with no `DOWNLOAD_PATH` in its environment starts, by running `make web` with the variable unset
- [x] 2.3 Verify the mount is read-only, by attempting a write inside the container and having it refused
- [x] 2.4 Add `DOWNLOAD_PATH` to `.env.example` with its default written out and a line saying what the directory is for

## 3. The location

- [x] 3.1 Add `location /download` serving the mount by `alias`, with `autoindex` off, and verify `nginx -t` passes in the image build as it does today
- [x] 3.2 Place a file in the directory and verify it is served by its exact path with a 200
- [x] 3.3 Verify `/download/` does not enumerate the directory
- [x] 3.4 Verify a path under `/download` naming no file answers 404, and reaches neither the application nor the page's document root
- [x] 3.5 Verify `/api/calculate`, `/api/autocomplete` and the page itself are unaffected, by exercising each against the running front end

## 4. The instructions

- [x] 4.1 Say in `README.md` where the operator puts the file that the download URL serves, next to the `curl` line that fetches it
- [x] 4.2 Verify the README's option 1 now describes a loop that closes: the file this deployment serves is the file the instructions fetch
