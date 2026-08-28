## Context

See `proposal.md` — Why. The facts that shape the approach:

- `www/` is three files, 28 KB: `index.html`, `index.js`, `style.css`. No build step, no bundler, no npm. Bootstrap, the Google Maps loader, and Swetrix come from CDNs at run time.
- `index.js` fetches `'/api/calculate'` and `"/api/autocomplete"` — relative, so the origin serving the page must answer both.
- `api.py` registers exactly two routes and returns 404 for anything else. It is out of scope to change.
- `web` currently publishes `127.0.0.1:${FRENCH_TOLLS_PORT:-8080}:8080`.
- `index.js:80` renders each passage cost with `Intl.NumberFormat(...).format(route.peages[i].cost)`. `format` coerces its argument with ToNumber, and `Number(null)` is `0`, so a null cost renders `0,00 €`.
- `index.js:59` guards the route total with `if (route.cost)`, so a genuinely free route shows no total at all. That is existing behaviour and is left alone.
- The page's deep-link fragment is `{"from": {...}, "to": {...}}`, and `bot.py` builds exactly that shape for its "Open comparison map" link.

## Goals / Non-Goals

**Goals:**

- One published port, serving the page and the API from one origin.
- An image that serves the page with no host directory mounted.
- A passage with no amount that does not read as a free one.

**Non-Goals:**

- Any change to `api.py`, or to any Python module. nginx serves the files, so the application never learns they exist.
- TLS, HTTP/2, rate limiting, or authentication. This still expects a reverse proxy in front of it in production; what is added here is the origin, not the edge.
- A build step for the page. Three static files need none, and adding one would put a toolchain between an edit and the result.
- Changing what the page looks like, beyond the cost cell.
- Serving Bootstrap or the Maps loader locally. They are CDN dependencies today and that is a separate decision.

## Decisions

### nginx, not aiohttp's static handler

`aiohttp.web.static` would have served the files from the existing container with no new image. Rejected because it puts static file serving — range requests, conditional GETs, content types, caching headers — into a single-threaded application whose event loop is otherwise spending its time on 100-request routing searches. A slow client fetching a stylesheet would compete with a route calculation for the same loop.

The cost is a second image and a proxy rule. Both are small and neither has to change when the page does.

*Alternative also rejected:* serving the page from a CDN or object store with the API on its own domain. It removes the proxy but adds CORS, a preflight on every calculate, and an address the page has to be built with.

### The proxy rule

```
location /api/ { proxy_pass http://web:8080; }
location /     { root /usr/share/nginx/html; try_files $uri $uri/ =404; }
```

`web:8080` is the Compose service name, resolved on the Compose network, which is how every other consumer in this project reaches a service it depends on.

`try_files ... =404` rather than a fallback to `index.html`: the page is not a single-page application with client-side routes, and a catch-all would answer a mistyped asset path with HTML that the browser then fails to parse as CSS.

`proxy_read_timeout` SHALL exceed the application's own worst case. A route search is bounded at 500 requests of 2–11 ms, so the application answers well inside a second, but the first request after a restart also loads 12 MB of YAML. 60 s is generous and still bounded.

### `web` stops publishing

With nginx as the origin, a published application port serves the API without the page — a URL that 404s for anything a visitor would want. Removing it also means one place to point a firewall rule or a reverse proxy at.

`FRENCH_TOLLS_PORT` keeps its name and moves to `nginx`, so `127.0.0.1:8080` still answers; it is answered by a different container.

*Risk accepted:* anything currently pointing at the aiohttp port directly stops working. Recorded in the proposal as breaking.

### Baking the page in

`COPY . /usr/share/nginx/html/` from the `www/` build context, with a `.dockerignore` excluding the Dockerfile and the nginx config so they are not served as files. The image is then self-contained: no bind mount, and no deployment step that copies a directory alongside it.

The cost is a rebuild for every edit. For three files behind a `make` target that is a second, and the alternative — an image whose contents depend on the host — is what this project already avoids for the pipeline's own artefacts.

### Cache headers

`index.html` is fetched fresh every time; `index.js` and `style.css` are already cache-busted by the `?2` and `?3` query strings in the page's own markup. So: `no-cache` for HTML, a long `max-age` for everything else. The page's existing `<meta http-equiv="cache-control">` tags do nothing useful — meta cache directives are ignored by browsers — and are left alone rather than removed, since the change is not about tidying the markup.

### The cost cell

One edit in `index.js`, at the passage row:

```js
const cost = route.peages[i].cost;
const cell = cost === null || cost === undefined
    ? '<span title="' + encodeHTML(route.peages[i].reason || 'not priced') + '">—</span>'
    : new Intl.NumberFormat('fr-FR', {style: 'currency', currency: 'EUR'}).format(cost);
```

An em dash rather than `?` or `n/a`: it reads as "no value here" in a numeric column without looking like an error, and it cannot be mistaken for an amount. `encodeHTML` already exists in the file and is used for the Maps links.

The check is against `null` and `undefined` specifically, not falsiness. A passage that genuinely costs `0` — which the tariff data does not currently contain but could — must still render as `0,00 €`.

## Risks / Trade-offs

- **A second image to keep in step.** The nginx config names `web:8080`; renaming the service breaks it silently at run time. → The proxy is exercised by the verification step, which loads the page and calculates a route end to end rather than checking that the container started.
- **The page is served with no integrity guarantee for its CDN dependencies.** Bootstrap carries an SRI hash; the Maps loader and Swetrix do not. → Unchanged by this work — the same scripts load from the same places whoever serves the page. Worth a separate change, not this one.
- **Removing the application's published port during a deploy.** Between `web` restarting without its port and `nginx` starting, the site is down. → Seconds, on a service with no uptime requirement stated anywhere, and `make web` brings both up in one command.
- **Nothing tests the page.** The unit suite covers the algorithm and deliberately depends on nothing; a browser test would need a browser. → The verification tasks load the page and calculate a real route by hand. That is a check performed once at apply time, not a regression test, and this change does not pretend otherwise.

## Migration Plan

1. Add `www/Dockerfile`, `www/nginx.conf`, `www/.dockerignore`.
2. Add the `nginx` service; remove `ports` from `web`.
3. Edit the cost cell in `index.js`.
4. `make web` — builds both images, starts both services plus the routers.
5. Verify by loading the page, calculating Lyon → Paris, and confirming the map draws, the passages list, an unpriced passage shows a dash, and the three Maps links open.
6. Repoint anything that addressed the aiohttp port directly at the nginx port. On this host that is nothing: the port was published to `127.0.0.1` only.

Rollback is restoring `ports` on `web` and removing the `nginx` service; the page then has no origin again, which is where it started. The three files under `www/` are unmodified except for the cost cell, and are backed up alongside the previous changes' files.

## Open Questions

None.
