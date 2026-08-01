"""Tests for Stair place type."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from housewire.house import PLACE_TYPES, is_place_type
from housewire.project import abm
from housewire.project.io import create_location_index


class TestStairPlaceType(unittest.TestCase):
    def test_stair_in_place_types(self) -> None:
        self.assertIn("Stair", PLACE_TYPES)
        self.assertTrue(is_place_type("Stair"))

    def test_create_stair_with_connects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_location_index(root, type_id="House", label="Site")
            create_location_index(root / "Parking", type_id="Floor", label="Parking")
            create_location_index(
                root / "Planta_baja", type_id="Floor", label="Planta baja"
            )
            stair_path = create_location_index(
                root / "Escalera_Parking_Planta_baja",
                type_id="Stair",
                label="Escalera Parking — Planta baja",
            )
            doc = abm.load_editable(stair_path, root)
            self.assertEqual(doc["type"], "Stair")
            doc["connects"] = ["Parking", "Planta_baja"]
            abm.persist(doc, stair_path, root)
            reloaded = abm.load_editable(stair_path, root)
            self.assertEqual(reloaded["connects"], ["Parking", "Planta_baja"])


if __name__ == "__main__":
    unittest.main()
