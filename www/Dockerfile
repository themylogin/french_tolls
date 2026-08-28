# The browser page, and the server that fronts the whole project.
#
# Its own image rather than a handler inside the application: serving static
# files means range requests, conditional GETs, content types and caching, and
# putting that into a single-threaded event loop makes a slow client fetching a
# stylesheet compete with a route calculation for the same loop.
#
# The page is copied in rather than mounted, so a running container needs no
# copy of www/ on the host and a deployment carries one image instead of an
# image plus a directory that has to arrive with it.
FROM nginx:1.27-alpine

# Replaces the packaged default server, which would otherwise also listen on 80
# and answer first.
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/french-tolls.conf

# The base image ships its own index.html and 50x.html here. The first is
# overwritten by the COPY below, the second would linger as a page this project
# never serves, so the root starts empty and holds only what is named.
RUN rm -rf /usr/share/nginx/html/*

# The page, named file by file rather than copied wholesale.
#
# Everything under the served root is reachable as a URL, so what goes there is
# an allowlist: a file added to www/ is not published until it is named here.
# That is one line of friction against serving something by accident -- a note
# to self, a key, a backup of the page with a different name.
COPY index.html index.js style.css /usr/share/nginx/html/

# Fails the build rather than the first request when the config is wrong.
RUN nginx -t
