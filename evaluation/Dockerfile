# The paid evaluation: does Google actually drive the route this project
# computes, when given the waypoints it emits?
#
# Its own image, beside builder/, french_tolls/, and www/. It is a fourth kind
# of thing: not a build step, not the application, not the page. Keeping it out
# of builder/ is what stops it ever becoming a prerequisite of a build -- which
# matters here more than anywhere else, because every run of it spends money.
#
# Debian for pyosmium, which is compiled and has no practical wheel; the
# application's own dependencies from an index, because this image imports the
# application's package and has to be able to import what that package imports.
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-venv \
        python3-requests \
        python3-pyosmium \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# The application's pinned list, installed here too.
#
# Not used directly: the evaluation speaks urllib and reads YAML. It is
# installed because `french_tolls.refine` imports aiohttp *and the store* at
# module level, and the drift and waypoint-placement functions this imports live
# in that module. Installing the list is cheaper than splitting the application's
# module to suit a consumer, and the whole point of importing rather than copying
# is that the algorithm cannot drift between the two.
#
# --system-site-packages, unlike the application's own image: pyosmium comes from
# Debian above and the venv has to see it. The pinned packages shadow the
# distribution's where both have one, so what `french_tolls` imports here is what
# it imports there.
#
# This image builds from the repository root rather than from `evaluation/`: the
# list has to be the application's own or the two can drift, and a COPY cannot
# reach outside its context. The root .dockerignore is what keeps that context
# small.
COPY requirements.txt /tmp/requirements.txt
RUN python3 -m venv --system-site-packages /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt
ENV PATH="/opt/venv/bin:${PATH}"

WORKDIR /work
COPY evaluation/build_test_cities.py evaluation/fetch_google_routes.py \
     evaluation/report.py evaluation/prototype_reinsert.py /work/

# The corridor measure lives in the application's package, not here. Two copies
# could drift apart, and a corridor that disagreed with the one the refinement
# uses would make this report say the refinement worked when it had not. The
# package is mounted at run time rather than copied, so there is exactly one.
ENV PYTHONPATH=/app

# Unbuffered so a sweep of 2 450 requests reports as it goes rather than at the
# end. A run that is spending money should say what it has spent so far.
ENV PYTHONUNBUFFERED=1
