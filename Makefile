PYTHON := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: all prepare install test

# Editable install with dev tools + UI extras (see pyproject.toml).
EXTRAS := .[dev,ui]

install:
	$(PYTHON) -m pip install -U pip
	$(PYTHON) -m pip install -e "$(EXTRAS)"

prepare:
	python -m venv .venv --prompt HouseWire
	$(MAKE) install

all:

test:
	$(PYTHON) -m pytest tests -q
