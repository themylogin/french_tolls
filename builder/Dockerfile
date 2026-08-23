# Toolchain for the PBF extraction (step 3) and the route search (step 4).
# Everything comes from Debian packages so the image build needs no pip index.
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        osmium-tool \
        python3 \
        python3-pyosmium \
        python3-yaml \
        python3-requests \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
COPY build_osm_toll_booths.py build_route_set.py booth_groups.py /work/

# Unbuffered so progress lines appear as the step runs rather than at exit.
ENV PYTHONUNBUFFERED=1
