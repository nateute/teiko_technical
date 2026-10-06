# ---------------------------------------------------------------------------
# Cell-count analysis pipeline
#
#   make setup      create a virtualenv and install requirements.txt
#   make pipeline   load data -> relative frequencies -> response analysis -> subset analysis
#   make dashboard  start the dashboard (API on :3001, web app on :5173)
#
# Common overrides:
#   make pipeline DATA=path/to/your.csv
#   make setup PYTHON=python3.12
# ---------------------------------------------------------------------------
SHELL := /bin/bash
.DEFAULT_GOAL := help

# --- Python ---------------------------------------------------------------
PYTHON       ?= python3
PY_MIN_MAJOR := 3
PY_MIN_MINOR := 10
VENV         := .venv
PY           := $(VENV)/bin/python
STAMP        := $(VENV)/.requirements-installed

# --- Files ----------------------------------------------------------------
DATA ?= cell-count.csv
DB   ?= cell-count.db

# Script names: the first file that exists is used, so either naming works.
# Override any of them, e.g.  make pipeline LOAD_SCRIPT=my_loader.py
LOAD_SCRIPT     ?= $(firstword $(wildcard load_data.py))
ANALYZE_SCRIPT  ?= $(firstword $(wildcard analyze_data.py))
RESPONSE_SCRIPT ?= $(firstword $(wildcard response_comparison.py))
SUBSET_SCRIPT   ?= $(firstword $(wildcard subset_analysis.py))

# Extra flags for the response comparison, e.g. RESPONSE_ARGS="--timepoint 0"
# (empty = pool all timepoints, the script's default)
RESPONSE_ARGS ?=

DASH_DIR := dashboard

.PHONY: help setup pipeline dashboard check-scripts

help:
	@echo "Targets:"
	@echo "  make setup      - check Python >= $(PY_MIN_MAJOR).$(PY_MIN_MINOR), create $(VENV), install requirements.txt"
	@echo "  make pipeline   - run the four analysis scripts in order (writes $(DB))"
	@echo "  make dashboard  - start the dashboard server"

# ===========================================================================
# setup
# ===========================================================================
setup: $(STAMP)

$(STAMP): requirements.txt
	$(PYTHON) -c 'import sys; sys.exit(0 if sys.version_info >= ($(PY_MIN_MAJOR), $(PY_MIN_MINOR)) else 1)' \
		|| { echo "Python >= $(PY_MIN_MAJOR).$(PY_MIN_MINOR) is required (found: $$($(PYTHON) --version 2>&1)). Try: make setup PYTHON=python3.12"; exit 1; }
	@echo "Using $$($(PYTHON) --version)"
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --quiet --upgrade pip
	$(PY) -m pip install -r requirements.txt
	@touch $@

# ===========================================================================
# pipeline  (each step must succeed before the next runs)
# ===========================================================================
check-scripts:
	@test -n "$(LOAD_SCRIPT)"     || { echo "Missing load script (load_data.py)"; exit 1; }
	@test -n "$(ANALYZE_SCRIPT)"  || { echo "Missing analysis script (analyze_data.py)"; exit 1; }
	@test -n "$(RESPONSE_SCRIPT)" || { echo "Missing response script (response_comparison.py)"; exit 1; }
	@test -n "$(SUBSET_SCRIPT)"   || { echo "Missing subset_analysis.py"; exit 1; }
	@test -f "$(DATA)"            || { echo "Input data '$(DATA)' not found. Run: make pipeline DATA=path/to/your.csv"; exit 1; }

pipeline: $(STAMP) check-scripts
	@echo "==> 1/4 Loading data ($(LOAD_SCRIPT))"
	$(PY) $(LOAD_SCRIPT)
	@echo; echo "==> 2/4 Relative frequencies ($(ANALYZE_SCRIPT))"
	$(PY) $(ANALYZE_SCRIPT)
	@echo; echo "==> 3/4 Responder vs non-responder comparison ($(RESPONSE_SCRIPT))"
	$(PY) $(RESPONSE_SCRIPT)
	@echo; echo "==> 4/4 Baseline subset analysis ($(SUBSET_SCRIPT))"
	$(PY) $(SUBSET_SCRIPT)
	@echo; echo "Pipeline complete. Results are in $(DB). Next: make dashboard"

# ===========================================================================
# dashboard
# ===========================================================================
$(DASH_DIR)/node_modules: $(DASH_DIR)/package.json
	@command -v npm >/dev/null || { echo "Node.js 18+ (with npm) is required for the dashboard."; exit 1; }
	cd $(DASH_DIR) && npm install
	@touch $@

dashboard: $(DASH_DIR)/node_modules
	@test -f "$(DB)" || { echo "$(DB) not found. Run 'make pipeline' first."; exit 1; }
	cd $(DASH_DIR) && DB_PATH="$(abspath $(DB))" npm run dev
