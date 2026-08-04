"""Tests for Stair place type."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fixtures import add_place, init_site, save_site
from housewire.house import PLACE_TYPES, is_place_type
from housewire.site import abm
from housewire.site.io import HOUSEWIRE_YAML
from housewire.site.tree import get_place_node


class TestStairPlaceType(unittest.TestCase):
    def test_stair_in_place_types(self) -> None:
        self.assertIn("Stair", PLACE_TYPES)
        self.assertTrue(is_place_type("Stair"))

    def test_create_stair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = init_site(root, type_id="House", label="Site")
            add_place(doc, "Parking", type_id="Floor", label="Parking")
            add_place(doc, "Planta_baja", type_id="Floor", label="Planta baja")
            add_place(
                doc,
                "Escalera_Parking_Planta_baja",
                type_id="Stair",
                label="Escalera Parking — Planta baja",
            )
            save_site(root, doc)

            stair_path = root / HOUSEWIRE_YAML
            reloaded_doc = abm.load_editable(stair_path, root)
            reloaded = get_place_node(
                reloaded_doc, ("Escalera_Parking_Planta_baja",)
            )
            self.assertEqual(reloaded["type"], "Stair")
            self.assertNotIn("connects", reloaded)


if __name__ == "__main__":
    unittest.main()
