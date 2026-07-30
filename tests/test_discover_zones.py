"""Zone discovery is path-based, not place-type or site-layout specific."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from housewire.cli import discover_zones


class TestDiscoverZones(unittest.TestCase):
    def test_groups_by_top_level_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "MyHouse"
            root.mkdir()
            files = [
                root / "housewire.yaml",
                root / "Parking" / "housewire.yaml",
                root / "Parking" / "Caja 1" / "housewire.yaml",
                root / "Planta baja" / "Recibidor" / "housewire.yaml",
            ]
            for path in files:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("schema: house/v1\n", encoding="utf-8")

            zones = discover_zones(root, files)
            self.assertEqual(set(zones), {"MyHouse", "Parking", "Planta baja"})
            self.assertEqual(zones["MyHouse"], [root / "housewire.yaml"])
            self.assertEqual(len(zones["Parking"]), 2)
            self.assertEqual(len(zones["Planta baja"]), 1)
