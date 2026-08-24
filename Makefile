# Toll booth route set pipeline.
#
#   make all   -> download_pbf -> setup_osrm -> build_osm_toll_booths
#                 -> build_route_set -> build_vinci_toll_booths
#                 -> build_vinci_prices
#
# The first four steps are skipped when their output is already in place.
# Skipping is existence-based, not timestamp-based: prerequisites are declared
# order-only (the `|` in the rules below) so re-touching an upstream file never
# triggers a fresh half-hour of OSRM preprocessing.
#
# The fifth and sixth steps are resumable rather than skipped: each always runs,
# reads its own output to see what is left, and does nothing when that output is
# complete. The sixth needs no OSRM graph at all.
#
# All work runs in containers. The host needs only Docker, Compose, and coreutils.

SHELL := /bin/bash
.DELETE_ON_ERROR:

# Local configuration. Missing .env is not fatal here -- the guard below prints
# something far more useful than "no rule to make target".
-include .env
export

DATA_DIR     := data
PBF_URL      := https://download.geofabrik.de/europe/france-latest.osm.pbf
PBF          := $(DATA_DIR)/france-latest.osm.pbf
FILTERED_PBF := $(DATA_DIR)/filtered.osm.pbf
BOOTHS       := $(DATA_DIR)/osm_toll_booths.yaml
PLAZAS       := $(DATA_DIR)/plazas.osm.pbf
NO_ACCESS    := $(DATA_DIR)/no_access_ways.osm.pbf
SNAP         := $(DATA_DIR)/endpoint_snap.json
ROUTE_SET    := $(DATA_DIR)/route_set.yaml
UNCOVERED    := $(DATA_DIR)/uncovered_booths.json
EXCLUDED     := $(DATA_DIR)/excluded_booths.json
VINCI        := $(DATA_DIR)/vinci_toll_booth.yaml
PRICES       := $(DATA_DIR)/vinci_price.yaml

OSRM_DIR   := $(strip $(OSRM_OPTIMAL_PATH))
OSRM_BASE  := $(OSRM_DIR)/france-latest
OSRM_STAMP := $(OSRM_DIR)/.setup.stamp

# Marker for the builder image. Kept under data/ so it is git-ignored and is
# removed by `make clean` along with everything else the pipeline produces.
BUILDER_STAMP := $(DATA_DIR)/.builder-image.stamp

# Peak preprocessing footprint is ~30 GB (transient 4.7 GB extract copy plus the
# ~25 GB graph); the margin guards against finding out 40 minutes into extract.
MIN_FREE_GB := 40

# Overridable so a host whose docker socket is not group-accessible can run
#   make DOCKER="sudo -n docker"
# without editing anything. (The tidier fix is to give your user access to
# /var/run/docker.sock; this exists so the pipeline is not blocked on that.)
DOCKER  ?= docker
COMPOSE ?= $(DOCKER) compose

# Containers write into bind-mounted ./data and $(OSRM_DIR). Running them as the
# invoking user keeps those outputs owned by that user -- otherwise every file
# lands as root and the plain `mv`/`rm`/`touch` in these recipes fails.
HOST_USER   := $(shell id -u):$(shell id -g)
RUN_BUILDER := $(COMPOSE) run --rm --user $(HOST_USER) builder
RUN_OSRM    := $(COMPOSE) run --rm --user $(HOST_USER) osrm-tools

.PHONY: all download_pbf setup_osrm build_osm_toll_booths build_route_set \
        build_vinci_toll_booths build_vinci_prices guard-osrm-path \
        guard-ulys-key guard-ulys-passage-date update_route_set \
        clean clean-osrm

all: download_pbf setup_osrm build_osm_toll_booths build_route_set \
     build_vinci_toll_booths build_vinci_prices

# --------------------------------------------------------------------------
# Configuration guard
# --------------------------------------------------------------------------
# Without this an unset OSRM_OPTIMAL_PATH silently resolves $(OSRM_STAMP) to
# "/.setup.stamp" and the pipeline starts writing a 25 GB graph into /.
guard-osrm-path:
	@if [ -z "$(OSRM_DIR)" ]; then \
	    echo "ERROR: OSRM_OPTIMAL_PATH is unset or empty."; \
	    echo "       Copy .env.example to .env and point OSRM_OPTIMAL_PATH at an"; \
	    echo "       absolute path outside this repository with ~$(MIN_FREE_GB) GB free."; \
	    exit 1; \
	fi
	@case "$(OSRM_DIR)" in \
	    /*) ;; \
	    *)  echo "ERROR: OSRM_OPTIMAL_PATH must be an absolute path (got '$(OSRM_DIR)')."; \
	        exit 1;; \
	esac

# Checked before step 5 does any work: the route search that precedes the first
# request takes minutes, and finding out afterwards that the key is missing
# wastes all of it.
guard-ulys-key:
	@if [ -z "$(strip $(ULYS_SUBSCRIPTION_KEY))" ]; then \
	    echo "ERROR: ULYS_SUBSCRIPTION_KEY is unset or empty."; \
	    echo "       Copy .env.example to .env and set it; see the comment there"; \
	    echo "       for where to read the key from."; \
	    exit 1; \
	fi

# Checked before step 6 does any work, for the same reason: one date prices the
# whole file, so discovering it is missing after 700 requests would mean
# discarding all of them.
guard-ulys-passage-date:
	@if [ -z "$(strip $(ULYS_PASSAGE_DATE))" ]; then \
	    echo "ERROR: ULYS_PASSAGE_DATE is unset or empty."; \
	    echo "       Copy .env.example to .env and set it; see the comment there"; \
	    echo "       for what the value means."; \
	    exit 1; \
	fi

# --------------------------------------------------------------------------
# Step 1 -- download_pbf
# --------------------------------------------------------------------------
# The guard is a prerequisite of every step, not just the OSRM ones: the builder
# service also bind-mounts ${OSRM_OPTIMAL_PATH}, so an unset variable otherwise
# surfaces as Compose's "invalid spec: :/osrm: empty section between colons".
download_pbf: guard-osrm-path $(PBF)
	@echo "==> download_pbf: $(PBF)"

# Downloaded to a temporary name and renamed only on success, so an interrupted
# transfer can never be mistaken for a complete extract by the existence check.
$(PBF): | $(BUILDER_STAMP)
	@mkdir -p $(DATA_DIR)
	@echo "==> download_pbf: fetching $(PBF_URL)"
	$(RUN_BUILDER) curl --fail --location --retry 3 --continue-at - \
	    --output /data/france-latest.osm.pbf.part "$(PBF_URL)"
	@mv $(DATA_DIR)/france-latest.osm.pbf.part $@
	@ls -lh $@

# --------------------------------------------------------------------------
# Step 2 -- setup_osrm
# --------------------------------------------------------------------------
setup_osrm: guard-osrm-path $(OSRM_STAMP)
	@echo "==> setup_osrm: $(OSRM_STAMP)"

# Order-only on the extract: presence is required, modification time is not.
$(OSRM_STAMP): | $(PBF)
	@mkdir -p "$(OSRM_DIR)"
	@free_gb=$$(df -Pk "$(OSRM_DIR)" | awk 'NR==2 {print int($$4/1024/1024)}'); \
	if [ "$$free_gb" -lt $(MIN_FREE_GB) ]; then \
	    echo "ERROR: only $${free_gb} GB free at $(OSRM_DIR); need ~$(MIN_FREE_GB) GB."; \
	    echo "       Preprocessing peaks around 30 GB and would fail partway through."; \
	    exit 1; \
	fi; \
	echo "==> setup_osrm: $${free_gb} GB free at $(OSRM_DIR)"
	@echo "==> setup_osrm: staging extract"
	@rm -f "$(OSRM_DIR)"/*.osm.pbf
	@cp -l $(PBF) "$(OSRM_BASE).osm.pbf" 2>/dev/null \
	    || cp $(PBF) "$(OSRM_BASE).osm.pbf"
	@echo "==> setup_osrm: osrm-extract"
	$(RUN_OSRM) osrm-extract -p /opt/car.lua /osrm/france-latest.osm.pbf
	@echo "==> setup_osrm: osrm-partition"
	$(RUN_OSRM) osrm-partition /osrm/france-latest.osrm
	@echo "==> setup_osrm: osrm-customize"
	$(RUN_OSRM) osrm-customize /osrm/france-latest.osrm
	@echo "==> setup_osrm: releasing extract copy"
	@rm -f "$(OSRM_BASE).osm.pbf"
	@touch $@

# --------------------------------------------------------------------------
# Step 3 -- build_osm_toll_booths
# --------------------------------------------------------------------------
build_osm_toll_booths: guard-osrm-path $(BOOTHS)
	@echo "==> build_osm_toll_booths: $(BOOTHS)"

# Produces the published inventory plus the filtered extract that step 4 reads
# its endpoint candidates from, so both steps consume one parse.
#
# The override file is deliberately NOT a prerequisite: making it one would key
# this step to a modification time, and re-touching an upstream file must never
# trigger the expensive work. Editing overrides means deleting $(BOOTHS) and
# running this step again, which reuses the two carved extracts and takes about
# a minute rather than repeating the passes over the 4.7 GB source.
$(BOOTHS): | $(PBF) $(BUILDER_STAMP)
	@echo "==> build_osm_toll_booths"
	$(RUN_BUILDER) python3 build_osm_toll_booths.py \
	    --pbf /data/france-latest.osm.pbf \
	    --filtered /data/filtered.osm.pbf \
	    --out /data/osm_toll_booths.yaml \
	    --plazas /data/plazas.osm.pbf \
	    --excluded /data/excluded_booths.json \
	    --overrides /data/osm_toll_booths_overrides.yaml \
	    --no-access /data/no_access_ways.osm.pbf

# --------------------------------------------------------------------------
# Step 4 -- build_route_set
# --------------------------------------------------------------------------
build_route_set: guard-osrm-path $(ROUTE_SET)
	@echo "==> build_route_set: $(ROUTE_SET)"

$(ROUTE_SET): | $(BOOTHS) $(OSRM_STAMP) $(BUILDER_STAMP)
	@echo "==> build_route_set: starting osrm-optimal"
	$(COMPOSE) up -d osrm-optimal
	$(RUN_BUILDER) python3 build_route_set.py \
	    --filtered /data/filtered.osm.pbf \
	    --booths /data/osm_toll_booths.yaml \
	    --plazas /data/plazas.osm.pbf \
	    --no-access /data/no_access_ways.osm.pbf \
	    --snap /data/endpoint_snap.json \
	    --out /data/route_set.yaml \
	    --uncovered /data/uncovered_booths.json \
	    --overrides /data/osm_toll_booths_overrides.yaml \
	    --osrm http://osrm-optimal:5000

# Extend an existing route set after the inventory changes. Unlike the four
# steps this always runs: build_route_set.py loads data/route_set.yaml, keeps
# the routes already there, and searches only for the groups they miss.
update_route_set: guard-osrm-path | $(BOOTHS) $(OSRM_STAMP) $(BUILDER_STAMP)
	@echo "==> update_route_set: extending $(ROUTE_SET)"
	$(COMPOSE) up -d osrm-optimal
	$(RUN_BUILDER) python3 build_route_set.py \
	    --filtered /data/filtered.osm.pbf \
	    --booths /data/osm_toll_booths.yaml \
	    --plazas /data/plazas.osm.pbf \
	    --no-access /data/no_access_ways.osm.pbf \
	    --snap /data/endpoint_snap.json \
	    --out /data/route_set.yaml \
	    --uncovered /data/uncovered_booths.json \
	    --overrides /data/osm_toll_booths_overrides.yaml \
	    --osrm http://osrm-optimal:5000

# --------------------------------------------------------------------------
# Step 5 -- build_vinci_toll_booths
# --------------------------------------------------------------------------
# The only resumable step, so unlike the first four it is phony and always
# executes. It reads data/vinci_toll_booth.yaml to learn which routes it has
# already queried and asks about the rest; on a complete file it issues no
# request at all. A file target would instead leave a partial run -- one killed
# halfway through 747 requests -- permanently unfinished, because the pipeline
# skips on existence rather than on content.
build_vinci_toll_booths: guard-osrm-path guard-ulys-key | $(ROUTE_SET) $(BUILDER_STAMP)
	@echo "==> build_vinci_toll_booths: $(VINCI)"
	$(COMPOSE) up -d osrm-optimal
	$(RUN_BUILDER) python3 build_vinci_toll_booths.py \
	    --filtered /data/filtered.osm.pbf \
	    --booths /data/osm_toll_booths.yaml \
	    --excluded /data/excluded_booths.json \
	    --route-set /data/route_set.yaml \
	    --overrides /data/osm_toll_booths_overrides.yaml \
	    --out /data/vinci_toll_booth.yaml \
	    --osrm http://osrm-optimal:5000 \
	    $(VINCI_ARGS)

# --------------------------------------------------------------------------
# Step 6 -- build_vinci_prices
# --------------------------------------------------------------------------
# Resumable like step 5, and always executes for the same reason.
#
# The only step that needs neither the OSRM graph nor the extract: it builds
# every request from data/route_set.yaml and data/vinci_toll_booth.yaml, both
# committed. So it never starts osrm-optimal. guard-osrm-path stays all the
# same -- the builder service bind-mounts $(OSRM_DIR), so an unset path breaks
# the mount before the script gets a chance to run.
build_vinci_prices: guard-osrm-path guard-ulys-key guard-ulys-passage-date \
                    | $(ROUTE_SET) $(VINCI) $(BUILDER_STAMP)
	@echo "==> build_vinci_prices: $(PRICES)"
	$(RUN_BUILDER) python3 build_vinci_prices.py \
	    --route-set /data/route_set.yaml \
	    --booths /data/osm_toll_booths.yaml \
	    --gares /data/vinci_toll_booth.yaml \
	    --overrides /data/osm_toll_booths_overrides.yaml \
	    --out /data/vinci_price.yaml \
	    $(PRICE_ARGS)

# Step 5 is phony and resumable, so it has no file target for step 6 to depend
# on. This rule supplies one. It fires only when the mapping is absent, so a
# tree that already has it never re-enters step 5 and never starts the routing
# service -- which is what keeps step 6 independent of OSRM. Whether a mapping
# that exists is complete is step 5's business, not step 6's.
$(VINCI):
	$(MAKE) build_vinci_toll_booths

# --------------------------------------------------------------------------
# Builder image (internal prerequisite -- not one of the six steps)
# --------------------------------------------------------------------------
$(BUILDER_STAMP): builder/Dockerfile builder/build_osm_toll_booths.py builder/build_route_set.py builder/booth_groups.py builder/build_vinci_toll_booths.py builder/build_vinci_prices.py builder/overrides.py
	@mkdir -p $(DATA_DIR)
	$(COMPOSE) build builder
	@touch $@

# --------------------------------------------------------------------------
# Housekeeping
# --------------------------------------------------------------------------
clean:
	rm -f $(BOOTHS) $(ROUTE_SET) $(UNCOVERED) $(EXCLUDED) $(VINCI) $(PRICES) \
	      $(FILTERED_PBF) $(PLAZAS) $(NO_ACCESS) $(SNAP) $(BUILDER_STAMP)

# Drops the ~25 GB graph. The extract in data/ is kept.
clean-osrm: guard-osrm-path
	$(COMPOSE) down --remove-orphans || true
	rm -f "$(OSRM_DIR)"/france-latest.osrm* "$(OSRM_STAMP)" "$(OSRM_DIR)"/*.osm.pbf
