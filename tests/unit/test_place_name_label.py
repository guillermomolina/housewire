"""Tests for place id / name / label helpers."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.unit.fixtures import add_place, init_site, save_site
from housewire.house import (
    location_id_from_name,
    place_label,
    place_meta_from_mapping,
    place_name,
)
from housewire.site import abm
from housewire.site.io import HOUSEWIRE_YAML
from housewire.site.tree import get_place_node


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
            root = Path(tmp)
            doc = init_site(root, type_id="House")
            add_place(
                doc,
                "Box_1",
                type_id="JunctionBox",
                working_name="B1",
                label="Box one",
            )
            save_site(root, doc)
            loaded = abm.load_editable(root / HOUSEWIRE_YAML, root)
            box = get_place_node(loaded, ("Box_1",))
            self.assertEqual(box["name"], "B1")
            self.assertEqual(box["label"], "Box one")

    def test_spaced_name_sets_label_not_working_name(self) -> None:
        leaf_id, auto_label = location_id_from_name("Caja derivacion 6")
        self.assertEqual(leaf_id, "Caja_derivacion_6")
        self.assertEqual(auto_label, "Caja derivacion 6")


if __name__ == "__main__":
    unittest.main()
