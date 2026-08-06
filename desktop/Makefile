# Electron shell for HouseWire.
#
# Prefer the system Electron binary (e.g. Arch ``pacman -S electron`` →
# /usr/bin/electron). No npm electron package is required: ``require("electron")``
# is provided by that runtime when you launch ``electron .``.

ELECTRON ?= electron
HOUSEWIRE_PYTHON ?= $(abspath ../.venv/bin/python)

.PHONY: prepare install run start check-electron

check-electron:
	@command -v $(ELECTRON) >/dev/null 2>&1 || { \
		echo "Electron not found on PATH (tried: $(ELECTRON))."; \
		echo "Arch: pacman -S electron"; \
		echo "Or: ELECTRON=/usr/bin/electron43 make run"; \
		exit 1; \
	}

# No Node package download needed when using system Electron.
prepare install: check-electron
	@echo "Using $$($(ELECTRON) --version 2>/dev/null || echo unknown) at $$(command -v $(ELECTRON))"

# Cursor/agent shells sometimes set ELECTRON_RUN_AS_NODE=1, which breaks the GUI.
run start: check-electron
	env -u ELECTRON_RUN_AS_NODE -u ELECTRON_NO_ATTACH_CONSOLE \
		HOUSEWIRE_PYTHON="$(HOUSEWIRE_PYTHON)" \
		$(ELECTRON) .
