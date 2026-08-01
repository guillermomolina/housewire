"""Tests for place id / name / label helpers."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from housewire.house import (
    location_id_from_name,
    place_label,
    place_meta_from_mapping,
    place_name,
)
from housewire.project.io import create_location_index
from housewire.project import abm


class TestPlaceNameLabel(unittest.TestCase):
    def test_fallbacks(self) -> None:
        self.assertEqual(place_name(None, "Caja_4"), "Caja_4")
        self.assertEqual(place_name({"name": "CD4"}, "Caja_4"), "CD4")
        self.assertEqual(place_name({"label": "Caja 4"}, "Caja_4"), "Caja_4")
        self.assertEqual(place_label({"label": "Caja 4"}, "Caja_4"), "Caja 4")
        self.assertEqual(place_label({"name": "CD4"}, "Caja_4"), "CD4")
        self.assertEqual(
            place_label({"name": "CD4", "label": "Caja 4"}, "Caja_4"),
            "Caja 4",
        )

    def test_meta_includes_name(self) -> None:
        meta = place_meta_from_mapping(
            {"type": "JunctionBox", "name": "CD4", "label": "Caja 4"}
        )
        assert meta is not None
        self.assertEqual(meta["name"], "CD4")
        self.assertEqual(meta["label"], "Caja 4")

    def test_create_with_name_and_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Box_1"
            create_location_index(
                root,
                type_id="JunctionBox",
                working_name="B1",
                label="Box one",
            )
            doc = abm.load_editable(root / "housewire.yaml", Path(tmp))
            self.assertEqual(doc["name"], "B1")
            self.assertEqual(doc["label"], "Box one")

    def test_spaced_name_sets_label_not_working_name(self) -> None:
        leaf_id, auto_label = location_id_from_name("Caja derivacion 6")
        self.assertEqual(leaf_id, "Caja_derivacion_6")
        self.assertEqual(auto_label, "Caja derivacion 6")


if __name__ == "__main__":
    unittest.main()
