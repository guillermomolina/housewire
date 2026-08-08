"""Pytest: path helpers and Playwright browser cache for tests."""
from __future__ import annotations

import os
import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

# Default catalog: installed ``housewire-catalog`` package (see resolve order).
# Optional override via env or local ``catalogs/default`` clone.
if "HOUSEWIRE_CATALOG" not in os.environ:
    _local = _REPO_ROOT / "catalogs" / "default"
    if (_local / "types").is_dir() or (_local / "src" / "housewire_catalog" / "types").is_dir():
        os.environ["HOUSEWIRE_CATALOG"] = str(_local)

# Keep Playwright browsers inside the repo (``make install`` populates this).
# Unittest discovery does not load pytest conftest; set the same default here.
_PLAYWRIGHT_DIR = _REPO_ROOT / ".playwright-browsers"
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(_PLAYWRIGHT_DIR))
