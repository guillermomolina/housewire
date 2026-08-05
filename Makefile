PYTHON := .venv/bin/python
PIP := .venv/bin/pip
PLAYWRIGHT_BROWSERS_PATH := $(CURDIR)/.playwright-browsers
export PLAYWRIGHT_BROWSERS_PATH

# Local clone of housewire-catalog (optional); falls back to git via extras.
CATALOG_LOCAL := catalogs/default

# Parallel workers for live route E2E (each spins serve + Chromium).
E2E_WORKERS ?= 4

.PHONY: all prepare install test test-route-e2e test-route-e2e-smoke bundle-ui

# Editable install with dev tools + UI + examples + catalog.
EXTRAS := .[dev,ui,examples,catalog]

install:
	$(PYTHON) -m pip install -U pip
	@if [ -f "$(CATALOG_LOCAL)/pyproject.toml" ]; then \
		$(PYTHON) -m pip install -e "$(CATALOG_LOCAL)"; \
	fi
	$(PYTHON) -m pip install -e packages/housewire-examples
	$(PYTHON) -m pip install -e "$(EXTRAS)"
	mkdir -p "$(PLAYWRIGHT_BROWSERS_PATH)"
	$(PYTHON) -m playwright install chromium

prepare:
	python -m venv .venv --prompt HouseWire
	$(MAKE) install

all:

# Concatenate ``src/housewire/ui/static/app/*.js`` → ``app.js`` (served IIFE).
bundle-ui:
	$(PYTHON) scripts/bundle_ui_app.py

test: test-unit test-route-e2e

test-unit:
	$(PYTHON) -m pytest tests --ignore=tests/route_e2e -q

# Full live route suite (Chromium from ``make install``).
test-route-e2e:
	$(PYTHON) -m pytest tests/route_e2e -v -n $(E2E_WORKERS) --dist loadfile

# Cheap PR smoke: detectors + a few representative sites.
test-route-e2e-smoke:
	$(PYTHON) -m pytest \
		tests/route_e2e/test_invariants_unit.py \
		tests/route_e2e/test_route_02.py \
		tests/route_e2e/test_route_08.py \
		tests/route_e2e/test_route_21.py \
		-v -n $(E2E_WORKERS) --dist loadfile
