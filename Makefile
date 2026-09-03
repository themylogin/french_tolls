# Toll booth route set pipeline.
#
#   make all   -> download_pbf -> setup_osrm -> build_osm_toll_booths
#                 -> build_route_set -> build_vinci_toll_booths
#                 -> build_vinci_prices -> build_booth_sides
#                 -> build_vinci_direct_prices -> build_toll_extent
#                 -> build_segment_weights -> apply_segment_weights
#                 -> build_cost_cutting
#
# The first four steps are skipped when their output is already in place.
# Skipping is existence-based, not timestamp-based: prerequisites are declared
# order-only (the `|` in the rules below) so re-touching an upstream file never
# triggers a fresh half-hour of OSRM preprocessing.
#
# Steps 5, 6 and 8 are resumable rather than skipped: each always runs, reads its
# own output to see what is left, and does nothing when that output is complete.
# Step 7 is checkpointed like the first four -- its work divides into no units
# worth keeping, and a whole run is two minutes.
#
# The sixth needs no OSRM graph at all. The seventh needs the graph and no key;
# the eighth needs both. The ninth and tenth need the graph and no key; the
# eleventh needs neither -- it copies files and runs one preprocessing container.
# The twelfth needs the untouched graph and no key.
#
# There are two graphs. $(OSRM_TOLL_PATH) holds the untouched one, served as
# `osrm-toll`, and every step above queries it. $(OSRM_OPTIMAL_PATH) holds the
# toll-weighted copy the tenth step assembles, served as `osrm-optimal`.
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
DRIVE_WAYS   := $(DATA_DIR)/drive_ways.osm.pbf
EXTENT_WAYS  := $(DATA_DIR)/extent_ways.osm.pbf
WIDE_WAYS    := $(DATA_DIR)/extent_wide_ways.osm.pbf
SNAP         := $(DATA_DIR)/endpoint_snap.json
ROUTE_SET    := $(DATA_DIR)/route_set.yaml
UNCOVERED    := $(DATA_DIR)/uncovered_booths.json
EXCLUDED     := $(DATA_DIR)/excluded_booths.json
BLACKLIST    := $(DATA_DIR)/nodes_blacklist.yaml
PATCH        := builder/patch_car_profile.py
VINCI        := $(DATA_DIR)/vinci_toll_booth.yaml
PRICES       := $(DATA_DIR)/vinci_price.yaml
SIDES        := $(DATA_DIR)/bidirectional_booth_sides.yaml
REJECTED     := $(DATA_DIR)/vinci_routes_rejected.sqlite3
SEGMENTS     := $(DATA_DIR)/segment_weights.csv
CUTTING      := $(DATA_DIR)/cost-cutting.yaml
SEG_REPORT   := $(DATA_DIR)/segment_weights_report.json
TEST_CITIES  := $(DATA_DIR)/test_cities.yaml
GOOGLE_DIR   := $(DATA_DIR)/google_routes

# Two graphs. $(OSRM_DIR) is the untouched one -- the road network as OSM
# describes it -- and it is what `setup_osrm` builds and what every step that
# reasons about the road network queries. $(OPT_DIR) is the toll-weighted copy
# that `apply_segment_weights` assembles; nothing in the pipeline queries it.
OSRM_DIR   := $(strip $(OSRM_TOLL_PATH))
OSRM_BASE  := $(OSRM_DIR)/france-latest
OSRM_STAMP := $(OSRM_DIR)/.setup.stamp

OPT_DIR    := $(strip $(OSRM_OPTIMAL_PATH))
OPT_STAMP  := $(OPT_DIR)/.applied.stamp

# The routing profile, copied out of the image and patched so that the nodes in
# $(BLACKLIST) are impassable, and so that a gate keeps its penalty only where an
# allowed highway class carries it. `lib/` comes across too: car.lua requires it,
# and osrm-extract resolves those requires relative to the profile it is given.
PROFILE_DIR  := $(OSRM_DIR)/profile
PROFILE      := $(PROFILE_DIR)/car.lua
PROFILE_ORIG := $(PROFILE_DIR)/car.lua.orig

# Marker for the builder image. Kept under data/ so it is git-ignored and is
# removed by `make clean` along with everything else the pipeline produces.
BUILDER_STAMP := $(DATA_DIR)/.builder-image.stamp

# Peak preprocessing footprint is the ~10 GB graph plus a transient 4.7 GB copy
# of the extract, and the toll-weighted graph is a second full copy of the first.
# So the two graphs and the peak together want about 25 GB, and the margin guards
# against finding out 40 minutes into extract. Both numbers are checked where
# they apply: the whole figure before preprocessing, the copy alone before it.
MIN_FREE_GB     := 25
MIN_FREE_OPT_GB := 12

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
RUN_OSRM    := $(COMPOSE) run --rm --user $(HOST_USER) osrm-toll-tools

.PHONY: all download_pbf setup_osrm build_osm_toll_booths build_route_set \
        build_vinci_toll_booths build_vinci_prices build_booth_sides \
        build_vinci_direct_prices build_toll_extent \
        build_segment_weights apply_segment_weights build_cost_cutting \
        guard-osrm-path guard-osrm-optimal-path guard-osrm-paths-differ \
        guard-ulys-key guard-ulys-passage-date guard-eur-per-hour \
        update_route_set clean clean-osrm \
        web bot app app-down test clean-cache requirements \
        test_cities test_google_routes test_google

all: download_pbf setup_osrm build_osm_toll_booths build_route_set \
     build_vinci_toll_booths build_vinci_prices build_booth_sides \
     build_vinci_direct_prices build_toll_extent \
     build_segment_weights apply_segment_weights build_cost_cutting

# --------------------------------------------------------------------------
# Configuration guard
# --------------------------------------------------------------------------
# Without this an unset OSRM_TOLL_PATH silently resolves $(OSRM_STAMP) to
# "/.setup.stamp" and the pipeline starts writing a 10 GB graph into /.
guard-osrm-path:
	@if [ -z "$(OSRM_DIR)" ]; then \
	    echo "ERROR: OSRM_TOLL_PATH is unset or empty."; \
	    echo "       Copy .env.example to .env and point OSRM_TOLL_PATH at an"; \
	    echo "       absolute path outside this repository with ~$(MIN_FREE_GB) GB free."; \
	    echo "       A tree set up before the toll weighting existed has this graph"; \
	    echo "       under OSRM_OPTIMAL_PATH; move it aside and name it here."; \
	    exit 1; \
	fi
	@case "$(OSRM_DIR)" in \
	    /*) ;; \
	    *)  echo "ERROR: OSRM_TOLL_PATH must be an absolute path (got '$(OSRM_DIR)')."; \
	        exit 1;; \
	esac

# The toll-weighted graph's path, checked by the two steps that write or serve it.
# Kept separate from guard-osrm-path so that a tree which has not yet configured
# the second graph can still run steps 1 to 8.
guard-osrm-optimal-path:
	@if [ -z "$(OPT_DIR)" ]; then \
	    echo "ERROR: OSRM_OPTIMAL_PATH is unset or empty."; \
	    echo "       Copy .env.example to .env and point OSRM_OPTIMAL_PATH at an"; \
	    echo "       absolute path with ~$(MIN_FREE_OPT_GB) GB free. It must not be"; \
	    echo "       the same directory as OSRM_TOLL_PATH."; \
	    exit 1; \
	fi
	@case "$(OPT_DIR)" in \
	    /*) ;; \
	    *)  echo "ERROR: OSRM_OPTIMAL_PATH must be an absolute path (got '$(OPT_DIR)')."; \
	        exit 1;; \
	esac

# The toll-weighted graph is built by copying the untouched one. Pointing both
# variables at one directory would therefore overwrite the untouched graph with a
# weighted copy of itself -- and every step from 4 to 9 would go on querying it,
# with answers that look entirely normal. Refused before anything is copied.
guard-osrm-paths-differ: guard-osrm-path guard-osrm-optimal-path
	@toll=$$(cd "$(OSRM_DIR)" 2>/dev/null && pwd -P || echo "$(OSRM_DIR)"); \
	opt=$$(cd "$(OPT_DIR)" 2>/dev/null && pwd -P || echo "$(OPT_DIR)"); \
	if [ "$$toll" = "$$opt" ]; then \
	    echo "ERROR: OSRM_TOLL_PATH and OSRM_OPTIMAL_PATH name the same directory:"; \
	    echo "         $$toll"; \
	    echo "       The toll-weighted graph is a copy of the untouched one, so this"; \
	    echo "       would overwrite the graph every other step queries."; \
	    exit 1; \
	fi

# Checked before step 5 does any work: the route search that precedes the first
# request takes minutes, and finding out afterwards that the key is missing
# wastes all of it.
# What a driver's hour is worth. No default here on purpose: the number lives in
# .env and nowhere else, and a fallback in this file would weight the graph at a
# rate the route service does not share.
guard-eur-per-hour:
	@if [ -z "$(strip $(EUR_PER_HOUR))" ]; then \
	    echo "ERROR: EUR_PER_HOUR is unset or empty."; \
	    echo "       Copy .env.example to .env and set it. Step 10 weights the"; \
	    echo "       toll-weighted graph with it and the route service reads the"; \
	    echo "       same setting, so there is no default anywhere else."; \
	    exit 1; \
	fi

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
# service also bind-mounts ${OSRM_TOLL_PATH}, so an unset variable otherwise
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
#
# Every previous `.osrm.*` file is removed before anything is built. Until the
# blacklist made this step re-runnable it effectively ran once, so a partial
# graph left by a killed run was not a case that arose; now it is. osrm-extract
# and osrm-partition write some files and reuse others, so a survivor from an
# older graph is silently mixed into the new one.
#
# $(BLACKLIST) and $(PATCH) are the two exceptions, and they are deliberate.
# Once the blacklist and the gate rule are compiled into the profile the graph
# *is* those rules, and a stale graph would keep routing over a node they call
# impassable -- which nothing downstream could detect, because every later step
# now trusts the router instead of checking. So these two are real
# prerequisites: editing either costs a rebuild.
#
# $(PBF) stays order-only all the same, even though the gate scan reads it.
# Re-downloading France is a deliberate act with its own consequences, and
# keying half an hour of preprocessing to a 4.8 GB file's timestamp is the trap
# the order-only rule was written for.
$(OSRM_STAMP): $(BLACKLIST) $(PATCH) | $(PBF)
	@if [ -f "$(OSRM_STAMP)" ]; then \
	    echo "==> setup_osrm: $? changed; the graph has the old rules"; \
	    echo "    compiled in, so extract, partition and customize must run"; \
	    echo "    again. This takes 30-40 minutes."; \
	fi
	@echo "==> setup_osrm: clearing any previous graph"
	@rm -rf "$(OSRM_DIR)"/france-latest.osrm* "$(PROFILE_DIR)"
	@mkdir -p "$(PROFILE_DIR)"
	@echo "==> setup_osrm: taking the routing profile out of the image"
	$(COMPOSE) run --rm --user $(HOST_USER) --entrypoint sh osrm-toll-tools -c \
	    "cp /opt/car.lua /osrm/profile/car.lua.orig && cp -r /opt/lib /osrm/profile/"
	@echo "==> setup_osrm: patching it with $(BLACKLIST) and the gate rule"
	$(RUN_BUILDER) python3 patch_car_profile.py \
	    --profile /osrm/profile/car.lua.orig \
	    --blacklist /data/nodes_blacklist.yaml \
	    --pbf /data/france-latest.osm.pbf \
	    --out /osrm/profile/car.lua
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
	$(RUN_OSRM) osrm-extract -p /osrm/profile/car.lua /osrm/france-latest.osm.pbf
	@echo "==> setup_osrm: osrm-partition"
	$(RUN_OSRM) osrm-partition /osrm/france-latest.osrm
	@echo "==> setup_osrm: osrm-customize"
	$(RUN_OSRM) osrm-customize /osrm/france-latest.osrm
	@echo "==> setup_osrm: releasing extract copy"
	@rm -f "$(OSRM_BASE).osm.pbf"
	@echo "==> setup_osrm: restarting osrm-toll onto the new graph"
	@# osrm-routed maps the graph at startup, and `compose up -d` leaves a
	@# running container alone. Replacing the files under a live server leaves
	@# it serving the old graph, and every answer looks perfectly normal --
	@# which is exactly how a blacklisted node kept appearing in routes after
	@# it had been compiled out.
	$(COMPOSE) restart osrm-toll 2>/dev/null || true
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
	@echo "==> build_route_set: starting osrm-toll"
	$(COMPOSE) up -d osrm-toll
	$(RUN_BUILDER) python3 build_route_set.py \
	    --filtered /data/filtered.osm.pbf \
	    --booths /data/osm_toll_booths.yaml \
	    --plazas /data/plazas.osm.pbf \
	    --no-access /data/no_access_ways.osm.pbf \
	    --snap /data/endpoint_snap.json \
	    --out /data/route_set.yaml \
	    --uncovered /data/uncovered_booths.json \
	    --overrides /data/osm_toll_booths_overrides.yaml \
	    --osrm http://osrm-toll:5000

# Extend an existing route set after the inventory changes. Unlike the four
# steps this always runs: build_route_set.py loads data/route_set.yaml, keeps
# the routes already there, and searches only for the groups they miss.
update_route_set: guard-osrm-path | $(BOOTHS) $(OSRM_STAMP) $(BUILDER_STAMP)
	@echo "==> update_route_set: extending $(ROUTE_SET)"
	$(COMPOSE) up -d osrm-toll
	$(RUN_BUILDER) python3 build_route_set.py \
	    --filtered /data/filtered.osm.pbf \
	    --booths /data/osm_toll_booths.yaml \
	    --plazas /data/plazas.osm.pbf \
	    --no-access /data/no_access_ways.osm.pbf \
	    --snap /data/endpoint_snap.json \
	    --out /data/route_set.yaml \
	    --uncovered /data/uncovered_booths.json \
	    --overrides /data/osm_toll_booths_overrides.yaml \
	    --osrm http://osrm-toll:5000

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
	$(COMPOSE) up -d osrm-toll
	$(RUN_BUILDER) python3 build_vinci_toll_booths.py \
	    --filtered /data/filtered.osm.pbf \
	    --booths /data/osm_toll_booths.yaml \
	    --excluded /data/excluded_booths.json \
	    --route-set /data/route_set.yaml \
	    --overrides /data/osm_toll_booths_overrides.yaml \
	    --out /data/vinci_toll_booth.yaml \
	    --osrm http://osrm-toll:5000 \
	    $(VINCI_ARGS)

# --------------------------------------------------------------------------
# Step 6 -- build_vinci_prices
# --------------------------------------------------------------------------
# Resumable like step 5, and always executes for the same reason.
#
# The only step that needs neither the OSRM graph nor the extract: it builds
# every request from data/route_set.yaml and data/vinci_toll_booth.yaml, both
# committed. So it never starts osrm-toll. guard-osrm-path stays all the
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

# --------------------------------------------------------------------------
# Step 7 -- build_booth_sides
# --------------------------------------------------------------------------
# Which side of a two-way booth is the toll network and which the free road.
#
# Checkpointed rather than resumable: the work divides into no units worth
# keeping, and a complete run is about two minutes of local routing.
#
# Its position is forced. The probe reads the enter/exit roles out of the price
# file, which step 6 produces, so it cannot run earlier. It asks nothing of the
# operator -- only of the router -- so it needs the graph and not the key.
build_booth_sides: guard-osrm-path $(SIDES)
	@echo "==> build_booth_sides: $(SIDES)"

$(SIDES): | $(PRICES) $(VINCI) $(BOOTHS) $(ROUTE_SET) $(FILTERED_PBF) $(BUILDER_STAMP)
	@echo "==> build_booth_sides: starting osrm-toll"
	$(COMPOSE) up -d osrm-toll
	$(RUN_BUILDER) python3 build_booth_sides.py \
	    --booths /data/osm_toll_booths.yaml \
	    --prices /data/vinci_price.yaml \
	    --gares /data/vinci_toll_booth.yaml \
	    --route-set /data/route_set.yaml \
	    --places /data/filtered.osm.pbf \
	    --out /data/bidirectional_booth_sides.yaml \
	    --osrm http://osrm-toll:5000

# --------------------------------------------------------------------------
# Step 8 -- build_vinci_direct_prices
# --------------------------------------------------------------------------
# Resumable like steps 5 and 6, and always executes for the same reason.
#
# Unlike step 6 this one does need the graph: it decides which entrance/exit
# pairs are askable by routing between the booths themselves, and a run without
# the router would ask about nothing and look complete.
#
# The rejection database is not listed as a prerequisite and is not cleaned by
# `clean`: the script creates it on first use, and it is the record of a quarter
# of a million routing decisions. Deleting it costs about seven minutes of
# routing to rebuild, so `make clean` leaving it alone is deliberate.
build_vinci_direct_prices: guard-osrm-path guard-ulys-key \
                           guard-ulys-passage-date \
                           | $(PRICES) $(VINCI) $(BOOTHS) $(SIDES) $(BUILDER_STAMP)
	@echo "==> build_vinci_direct_prices: $(PRICES), $(REJECTED)"
	$(COMPOSE) up -d osrm-toll
	$(RUN_BUILDER) python3 build_vinci_direct_prices.py \
	    --booths /data/osm_toll_booths.yaml \
	    --gares /data/vinci_toll_booth.yaml \
	    --overrides /data/osm_toll_booths_overrides.yaml \
	    --out /data/vinci_price.yaml \
	    --sides /data/bidirectional_booth_sides.yaml \
	    --rejected /data/vinci_routes_rejected.sqlite3 \
	    --osrm http://osrm-toll:5000 \
	    $(DIRECT_ARGS)

# --------------------------------------------------------------------------
# Step 9 -- build_toll_extent
# --------------------------------------------------------------------------
# Where the tolled road begins and ends at each priced booth.
#
# Resumable rather than checkpointed, and always executes: it reads
# data/vinci_price.yaml for the booths it has already measured and does only the
# rest, writing after each one. So an interrupted run repeats at most one booth,
# and a run against a complete file issues no request at all.
#
# Its position is forced. It reads the enter/exit roles the eighth step settles
# and writes into the same file, so it cannot run earlier; the ninth divides each
# tariff by the distance between what it records, so it cannot run later.
#
# It starts no service. The extent is derived from an extract and the routing
# profile, so this step needs neither the router nor a key, a date or a network.
# $(OSRM_STAMP) is a prerequisite for the profile alone: the patched graph's
# pristine `car.lua.orig` is what says which roads a car may drive, and the
# extent graph has to admit exactly what the router does.
#
# The extract is this step's own. The grouping carve reaches 2 km around a
# booth, and a tolled slip road can run four times that -- a region that leaves
# the carve has no junction to stop at, and stopping anyway is a fabrication.
# $(DRIVE_WAYS) and $(EXTENT_WAYS) are cut on first use and kept, like every
# other extract the pipeline derives from the source.
build_toll_extent: guard-osrm-path | $(PRICES) $(VINCI) $(BOOTHS) $(SIDES) \
                   $(PBF) $(OSRM_STAMP) $(BUILDER_STAMP)
	@echo "==> build_toll_extent: $(PRICES)"
	$(RUN_BUILDER) python3 build_toll_extent.py \
	    --out /data/vinci_price.yaml \
	    --booths /data/osm_toll_booths.yaml \
	    --gares /data/vinci_toll_booth.yaml \
	    --sides /data/bidirectional_booth_sides.yaml \
	    --pbf /data/france-latest.osm.pbf \
	    --ways /data/extent_ways.osm.pbf \
	    --drive-ways /data/drive_ways.osm.pbf \
	    --wide-ways /data/extent_wide_ways.osm.pbf \
	    --profile /osrm/profile/car.lua.orig \
	    --blacklist /data/nodes_blacklist.yaml \
	    --overrides /data/osm_toll_booths_overrides.yaml \
	    $(EXTENT_ARGS)

# --------------------------------------------------------------------------
# Step 10 -- build_segment_weights
# --------------------------------------------------------------------------
# Spread every tariff over the road segments it pays for, and write the OSRM
# segment speed file.
#
# Checkpointed on the file itself. Its work divides into no resumable unit: the
# aggregation is over all pairs at once, so a partial file is a wrong file
# rather than an incomplete one, and a whole run is under two minutes of local
# routing.
#
# It needs the untouched graph and nothing else -- no key, no date, no network.
#
# The four artefacts it reads are real prerequisites, not order-only, for the
# same reason $(BLACKLIST) is one of $(OSRM_STAMP): this file *is* those prices
# spread over the road, so a rebuilt price file that left it alone would weight
# the graph by tariffs that no longer exist -- and nothing downstream could tell.
# That is what a `make clean; make all` did: it repriced every booth, then
# skipped this step and the next one, and reported success.
#
# Keying this to their timestamps is safe because the steps that write them
# leave them untouched when they learn nothing (see write_state in
# build_vinci_prices.py), so a `make all` with nothing to do still skips here.
build_segment_weights: guard-osrm-path guard-eur-per-hour build_toll_extent $(SEGMENTS)
	@echo "==> build_segment_weights: $(SEGMENTS)"

$(SEGMENTS): guard-eur-per-hour $(OSRM_STAMP) $(PRICES) $(VINCI) $(BOOTHS) $(SIDES) | $(PBF) $(BUILDER_STAMP)
	@echo "==> build_segment_weights: starting osrm-toll"
	$(COMPOSE) up -d osrm-toll
	$(RUN_BUILDER) python3 build_segment_weights.py \
	    --prices /data/vinci_price.yaml \
	    --booths /data/osm_toll_booths.yaml \
	    --gares /data/vinci_toll_booth.yaml \
	    --sides /data/bidirectional_booth_sides.yaml \
	    --out /data/segment_weights.csv \
	    --report /data/segment_weights_report.json \
	    --ways /data/france-latest.osm.pbf \
	    --osrm http://osrm-toll:5000 \
	    --wage-eur-per-hour $(EUR_PER_HOUR) \
	    $(SEGMENT_ARGS)

# --------------------------------------------------------------------------
# Step 11 -- apply_segment_weights
# --------------------------------------------------------------------------
# Assemble the toll-weighted graph: copy the untouched one, then customize the
# copy with the segment speed file.
#
# The copy is not an optimisation to skip. `osrm-customize` rewrites the
# customized layer in place, so customizing an already-customized graph layers
# one update under another; only a fresh copy differs from the untouched graph
# in exactly the rows of the file.
#
# Hardlinking the files osrm-customize does not write was considered and
# rejected: which files those are is not documented, and a wrong guess corrupts
# the untouched graph through the link.
apply_segment_weights: guard-osrm-paths-differ guard-eur-per-hour $(OPT_STAMP)
	@echo "==> apply_segment_weights: $(OPT_STAMP)"

$(OPT_STAMP): $(SEGMENTS) $(OSRM_STAMP) | $(BUILDER_STAMP)
	@if [ ! -f "$(SEGMENTS)" ]; then \
	    echo "ERROR: $(SEGMENTS) is missing."; \
	    echo "       Run build_segment_weights first. Without it this step would"; \
	    echo "       produce a copy indistinguishable from the untouched graph."; \
	    exit 1; \
	fi
	@mkdir -p "$(OPT_DIR)"
	@free_gb=$$(df -Pk "$(OPT_DIR)" | awk 'NR==2 {print int($$4/1024/1024)}'); \
	if [ "$$free_gb" -lt $(MIN_FREE_OPT_GB) ]; then \
	    echo "ERROR: only $${free_gb} GB free at $(OPT_DIR); need ~$(MIN_FREE_OPT_GB) GB."; \
	    echo "       The toll-weighted graph is a full copy of the untouched one,"; \
	    echo "       and a copy that cannot finish would fill the disk instead."; \
	    exit 1; \
	fi; \
	echo "==> apply_segment_weights: $${free_gb} GB free at $(OPT_DIR)"
	@echo "==> apply_segment_weights: stopping osrm-optimal"
	@# osrm-routed maps the graph at startup, so the files must not move under
	@# a live server. The same trap the setup step documents.
	$(COMPOSE) stop osrm-optimal 2>/dev/null || true
	@echo "==> apply_segment_weights: clearing the previous toll-weighted graph"
	@rm -f "$(OPT_DIR)"/france-latest.osrm* "$(OPT_STAMP)"
	@echo "==> apply_segment_weights: copying the untouched graph"
	@cp -a "$(OSRM_DIR)"/france-latest.osrm* "$(OPT_DIR)"/
	@echo "==> apply_segment_weights: osrm-customize --segment-speed-file"
	$(COMPOSE) run --rm --user $(HOST_USER) osrm-optimal-tools \
	    osrm-customize /osrm/france-latest.osrm \
	    --segment-speed-file /data/segment_weights.csv
	@echo "==> apply_segment_weights: starting osrm-optimal"
	$(COMPOSE) up -d osrm-optimal
	@echo "==> apply_segment_weights: acceptance check"
	$(RUN_BUILDER) python3 build_segment_weights.py --verify \
	    --prices /data/vinci_price.yaml \
	    --booths /data/osm_toll_booths.yaml \
	    --gares /data/vinci_toll_booth.yaml \
	    --sides /data/bidirectional_booth_sides.yaml \
	    --out /data/segment_weights.csv \
	    --report /data/segment_weights_report.json \
	    --osrm http://osrm-toll:5000 \
	    --osrm-optimal http://osrm-optimal:5000 \
	    --wage-eur-per-hour $(EUR_PER_HOUR)
	@touch $@

# --------------------------------------------------------------------------
# Step 12 -- build_cost_cutting
# --------------------------------------------------------------------------
# Where leaving the motorway and rejoining it buys two cheaper tickets than the
# one the operator sells for the whole run.
#
# Checkpointed on the file itself, like step 10, and for the same reason: the
# search is over all pairs at once, so a partial file is a wrong file rather
# than an incomplete one.
#
# The three artefacts it reads are real prerequisites, not order-only ones. This
# file *is* those tariffs read as arbitrage, so a repriced booth that left it
# alone would advise splits at prices the operator no longer charges, and
# nothing downstream could tell -- the same trap $(SEGMENTS) was in.
#
# It needs the untouched graph and nothing else: no key, no date, no network,
# and not the toll-weighted graph. What it measures is how the road runs, not
# what the graph has been made to charge for it. So it is ordered last for
# convenience rather than necessity and may be run any time after step 9.
build_cost_cutting: guard-osrm-path $(CUTTING)
	@echo "==> build_cost_cutting: $(CUTTING)"

$(CUTTING): $(PRICES) $(VINCI) $(BOOTHS) | $(OSRM_STAMP) $(BUILDER_STAMP)
	@echo "==> build_cost_cutting: starting osrm-toll"
	$(COMPOSE) up -d osrm-toll
	$(RUN_BUILDER) python3 build_cost_cutting.py \
	    --prices /data/vinci_price.yaml \
	    --gares /data/vinci_toll_booth.yaml \
	    --booths /data/osm_toll_booths.yaml \
	    --overrides /data/osm_toll_booths_overrides.yaml \
	    --out /data/cost-cutting.yaml \
	    --osrm http://osrm-toll:5000 \
	    $(CUTTING_ARGS)

# Step 5 is phony and resumable, so it has no file target for step 6 to depend
# on. This rule supplies one. It fires only when the mapping is absent, so a
# tree that already has it never re-enters step 5 and never starts the routing
# service -- which is what keeps step 6 independent of OSRM. Whether a mapping
# that exists is complete is step 5's business, not step 6's.
$(VINCI):
	$(MAKE) build_vinci_toll_booths

# Step 6 is phony and resumable for the same reason, so step 7 needs the same
# rule. It fires only when the price file is absent. Whether a price file that
# exists is complete is step 6's business, not step 7's -- and step 7 takes its
# source and target booths from that file, so running against a partial one
# simply enumerates a smaller grid.
$(PRICES):
	$(MAKE) build_vinci_prices

# --------------------------------------------------------------------------
# Builder image (internal prerequisite -- not one of the six steps)
# --------------------------------------------------------------------------
$(BUILDER_STAMP): builder/Dockerfile builder/build_osm_toll_booths.py builder/build_route_set.py builder/booth_groups.py builder/build_vinci_toll_booths.py builder/build_vinci_prices.py builder/build_booth_sides.py builder/build_vinci_direct_prices.py builder/build_toll_extent.py builder/build_segment_weights.py builder/patch_car_profile.py builder/overrides.py builder/osmurl.py builder/build_cost_cutting.py
	@mkdir -p $(DATA_DIR)
	$(COMPOSE) build builder
	@touch $@

# --------------------------------------------------------------------------
# Housekeeping
# --------------------------------------------------------------------------
clean:
	rm -f $(BOOTHS) $(ROUTE_SET) $(UNCOVERED) $(EXCLUDED) $(VINCI) $(PRICES) $(SIDES) \
	      $(FILTERED_PBF) $(PLAZAS) $(NO_ACCESS) $(DRIVE_WAYS) $(EXTENT_WAYS) \
	      $(WIDE_WAYS) \
	      $(SNAP) $(BUILDER_STAMP)

# Drops both graphs, about 9 GB each. The extract in data/ is kept, and so is
# $(SEGMENTS): it is a deliverable rather than part of a graph, and reclaiming
# disk must not cost a committed artefact.
clean-osrm: guard-osrm-path guard-osrm-optimal-path
	$(COMPOSE) down --remove-orphans || true
	rm -rf "$(OSRM_DIR)"/france-latest.osrm* "$(OSRM_STAMP)" \
	       "$(OSRM_DIR)"/*.osm.pbf "$(PROFILE_DIR)"
	rm -rf "$(OPT_DIR)"/france-latest.osrm* "$(OPT_STAMP)"

# --------------------------------------------------------------------------
# The application (not one of the eleven steps)
# --------------------------------------------------------------------------
# The web service, the bot, and the test suite read what the pipeline publishes
# and are never invoked by it. They sit behind Compose profiles, so a plain
# `docker compose up` still starts the two query services and nothing else.
#
# Every one of them needs the routers running: `web` and `bot` answer from them,
# and the suite measures them. The recipes bring the routers up first rather
# than failing on a connection refused.
# Brings up the application and the front end together. The page is the point
# of the web service, and `web` publishes no port of its own, so starting one
# without the other leaves nothing a browser can reach.
web: guard-osrm-paths-differ
	$(COMPOSE) up -d osrm-toll osrm-optimal
	$(COMPOSE) --profile app up -d --build web nginx

bot: guard-osrm-paths-differ
	@if [ -z "$(TELEGRAM_BOT_TOKEN)" ]; then \
	    echo "ERROR: TELEGRAM_BOT_TOKEN is unset or empty."; \
	    echo "       Copy .env.example to .env and set it to the token BotFather"; \
	    echo "       issued. The bot polls Telegram and cannot start without one."; \
	    exit 1; \
	fi
	$(COMPOSE) up -d osrm-toll osrm-optimal
	$(COMPOSE) --profile app up -d --build bot

app: web bot

app-down:
	$(COMPOSE) --profile app down

# The unit test suite. A one-shot run, so it gets its own profile: `--profile
# app up` must not start it as a service.
#
# No prerequisites on purpose. The suite reaches no routing service and reads
# nothing under data/, so it needs neither the graphs nor a configured .env: a
# fresh checkout can run it before the pipeline has ever been run.
#
# --no-TTY keeps the output readable when make is not on a terminal, and the
# exit status is pytest's, so a failing suite fails the target.
test:
	$(COMPOSE) --profile test run --rm --no-TTY tests
	$(COMPOSE) --profile test run --rm --no-TTY builder-tests

# Drops the store: the autocomplete answers and the month's request count.
#
# A PIPELINE REBUILD NO LONGER NEEDS THIS. It used to, and that was the whole
# reason the target existed: route answers and refinements were kept under the
# two endpoints, so a rebuilt price file reached a journey answered before it and
# a stale toll total looked exactly like a correct one. Neither is stored now, so
# every journey is priced against the artefacts as they are and there is nothing
# a rebuild can leave behind.
#
# What it still drops costs money to replace. Each autocomplete row was a paid
# LocationIQ request, and the request count is what the monthly ceiling is
# enforced against -- dropping it mid-month lets the ceiling be reached twice.
# So run this to reset a deployment, not as routine maintenance.
clean-cache:
	$(COMPOSE) --profile app down
	docker volume rm $$(basename $$(pwd))_cache || true

# Recompiles requirements.txt from pyproject.toml.
#
# In a container on the interpreter the image runs, because a resolution is
# specific to a Python version and this host has neither that version nor uv.
# Resolving against whatever happens to be installed here would pin a set the
# image cannot install.
#
# Run it after changing a dependency in pyproject.toml, and commit both files.
requirements:
	$(DOCKER) run --rm -v "$$(pwd)/pyproject.toml:/in/pyproject.toml:ro" \
	    ghcr.io/astral-sh/uv:python3.11-bookworm-slim \
	    sh -c 'mkdir -p /build && cp /in/pyproject.toml /build/ && cd /build \
	           && uv pip compile pyproject.toml -o requirements.txt >/dev/null 2>&1 \
	           && cat requirements.txt' > requirements.txt

# --------------------------------------------------------------------------
# The paid evaluation (not one of the eleven steps, and not part of `test`)
# --------------------------------------------------------------------------
# Measures whether Google actually drives the route this project computes when
# it is given the waypoints this project emits.
#
# Deliberately reachable only by name. None of these is a prerequisite of `all`
# or of `test`: `test` runs the unit suite and costs nothing, and every request
# made here is billed. A measurement that can be triggered by habit is a
# measurement that will be paid for by habit.
RUN_EVAL := $(COMPOSE) --profile evaluation run --rm --no-TTY --user $(HOST_USER) evaluation

# Fifty cities spread over mainland France, chosen from the extract and written
# to data/test_cities.yaml. Free, incremental, and reproducible.
test_cities: guard-osrm-path
	$(COMPOSE) up -d osrm-toll osrm-optimal
	$(RUN_EVAL) python3 build_test_cities.py $(ARGS)

# Buys the Google routes. COSTS MONEY. It counts what is outstanding, says what
# that costs, and refuses to spend anything without --yes:
#
#   make test_google_routes                      # says what it would cost
#   make test_google_routes ARGS="--limit 10 --yes"   # buys ten
#   make test_google_routes ARGS="--yes"              # buys the rest
#
# Incremental at the granularity of one journey: a pair already on disk is never
# requested again, and a request that fails writes nothing, so it is simply
# outstanding next time.
test_google_routes: guard-osrm-paths-differ | $(TEST_CITIES)
	$(COMPOSE) up -d osrm-toll osrm-optimal
	$(COMPOSE) --profile app up -d web
	$(RUN_EVAL) python3 fetch_google_routes.py $(ARGS)

# The report. Free, and makes no request to Google: it reads what was bought.
test_google: guard-osrm-paths-differ
	$(COMPOSE) up -d osrm-toll osrm-optimal
	$(COMPOSE) --profile app up -d web
	$(RUN_EVAL) python3 report.py $(ARGS)
