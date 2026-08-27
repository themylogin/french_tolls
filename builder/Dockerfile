# Toolchain for the PBF extraction (step 3), the route search (step 4), the
# gare mapping (step 5), the pricing (step 6), the booth sides (step 7), the
# direct pricing (step 8), the toll extents (step 9), and the segment
# weights (step 10).
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
COPY build_osm_toll_booths.py build_route_set.py booth_groups.py \
     build_vinci_toll_booths.py build_vinci_prices.py \
     build_booth_sides.py build_vinci_direct_prices.py \
     build_toll_extent.py build_segment_weights.py \
     patch_car_profile.py overrides.py osmurl.py /work/

# Unbuffered so progress lines appear as the step runs rather than at exit.
ENV PYTHONUNBUFFERED=1
