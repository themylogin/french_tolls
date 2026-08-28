# The paid evaluation: does Google actually drive the route this project
# computes, when given the waypoints it emits?
#
# Its own image, beside builder/, french_tolls/, and www/. It is a fourth kind
# of thing: not a build step, not the application, not the page. Keeping it out
# of builder/ is what stops it ever becoming a prerequisite of a build -- which
# matters here more than anywhere else, because every run of it spends money.
#
# Debian packages only, as builder/Dockerfile does. Nothing here needs a package
# index at build time.
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-yaml \
        python3-requests \
        python3-pyosmium \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
COPY build_test_cities.py fetch_google_routes.py report.py prototype_reinsert.py /work/

# The corridor measure lives in the application's package, not here. Two copies
# could drift apart, and a corridor that disagreed with the one the refinement
# uses would make this report say the refinement worked when it had not. The
# package is mounted at run time rather than copied, so there is exactly one.
ENV PYTHONPATH=/app

# Unbuffered so a sweep of 2 450 requests reports as it goes rather than at the
# end. A run that is spending money should say what it has spent so far.
ENV PYTHONUNBUFFERED=1
