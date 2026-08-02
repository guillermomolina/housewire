"""Pytest: path helpers and default external catalog for tests."""
from __future__ import annotations

import os
import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

# Prefer a local clone; fall back to the committed test mirror.
_CATALOG_CANDIDATES = (
    _REPO_ROOT / "catalogs" / "default",
    _TESTS_DIR / "data" / "catalog",
)
for _candidate in _CATALOG_CANDIDATES:
    if (_candidate / "types").is_dir() or any(_candidate.glob("*.yaml")):
        os.environ.setdefault("HOUSEWIRE_CATALOG", str(_candidate))
        break

# Keep Playwright browsers inside the repo (``make install`` populates this).
# Unittest discovery does not load pytest conftest; set the same default here.
_PLAYWRIGHT_DIR = _REPO_ROOT / ".playwright-browsers"
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(_PLAYWRIGHT_DIR))
