"""Catalog resolution prefers package when no path override exists."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class TestCatalogPackageFallback(unittest.TestCase):
    def test_resolve_uses_housewire_catalog_package(self) -> None:
        try:
            from housewire_catalog import types_dir
        except ImportError as exc:  # pragma: no cover
            raise unittest.SkipTest(f"housewire-catalog not installed: {exc}") from exc

        from housewire.house import resolve_catalog_types_dir

        empty = Path(tempfile.mkdtemp())
        with mock.patch.dict(
            os.environ,
            {"HOUSEWIRE_CATALOGS_DIR": str(empty)},
            clear=False,
        ):
            os.environ.pop("HOUSEWIRE_CATALOG", None)
            resolved = resolve_catalog_types_dir()
        self.assertEqual(resolved.resolve(), types_dir().resolve())
        self.assertTrue(any(resolved.glob("*.yaml")))


if __name__ == "__main__":
    unittest.main()
