PYTHON := .venv/bin/python
PIP := .venv/bin/pip
PLAYWRIGHT_BROWSERS_PATH := $(CURDIR)/.playwright-browsers
export PLAYWRIGHT_BROWSERS_PATH

.PHONY: all prepare install test test-route-e2e

# Editable install with dev tools + UI extras (see pyproject.toml).
EXTRAS := .[dev,ui,examples]

install:
	$(PYTHON) -m pip install -U pip
	$(PYTHON) -m pip install -e packages/housewire-examples
	$(PYTHON) -m pip install -e "$(EXTRAS)"
	mkdir -p "$(PLAYWRIGHT_BROWSERS_PATH)"
	$(PYTHON) -m playwright install chromium

prepare:
	python -m venv .venv --prompt HouseWire
	$(MAKE) install

all:

test:
	$(PYTHON) -m pytest tests -q

# Live route E2E only (needs Chromium from ``make install``).
test-route-e2e:
	$(PYTHON) -m pytest tests/route_e2e tests/test_route_e2e_test01.py -v
