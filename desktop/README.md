# HouseWire desktop (Electron)

Minimal Electron shell that embeds ``housewire serve`` and exposes native
Open / Save As dialogs so the UI can use real filesystem paths.

## Requirements

- **System Electron** on ``PATH`` (recommended on Arch: ``pacman -S electron``).
  This app does **not** download the npm ``electron`` package binary.
- HouseWire in the repo ``.venv``: ``make prepare`` from the repo root
  (or ``pip install -e '.[ui]'``)

Optional: ``ELECTRON=/usr/bin/electron43`` if you need a specific Arch package.

The shell hides Electron's default menu (so only the in-app menu remains) and
uses ``desktop/icon.png`` as the window icon. Desktop-only items: Open recent,
Quit, Full screen. The window title is ``[*]filename.yaml — HouseWire``.

## Run

From the repo root:

```bash
make desktop
```

Or from this directory:

```bash
make prepare   # checks that electron is on PATH
make run
```

Optional: ``HOUSEWIRE_PYTHON=/path/to/python make run``.

If you previously ran ``npm install`` here, you can remove the unused tree:

```bash
rm -rf node_modules package-lock.json
```

For browser-only testing (no Electron), use:

```bash
housewire serve            # empty workspace
housewire serve "$SITE"    # open a site on startup
```

See [docs/ui-workspace.md](../docs/ui-workspace.md) for Web vs Desktop file I/O.
