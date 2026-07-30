PYTHON := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: all prepare install test

install:
	$(PYTHON) -m pip install -r dev-requirements.txt

prepare:
	python -m venv .venv --prompt housewire
	$(PYTHON) -m pip install -U pip
	$(PYTHON) -m pip install -r dev-requirements.txt

all:

test:
	$(PYTHON) -m pytest tests -q
