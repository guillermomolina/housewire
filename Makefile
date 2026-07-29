PYTHON := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: all prepare install test

install:
	$(PYTHON) -m pip install -e .

prepare:
	python -m venv .venv --prompt housewire
	$(PYTHON) -m pip install -U pip
	$(PYTHON) -m pip install -e .

all:

test:
	$(PYTHON) -m unittest discover -s tests -v
