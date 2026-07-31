"""Tests for Cable/Conduit catalog expansion (type/subtype/label)."""
from __future__ import annotations

import unittest

from housewire.house import (
    expand_cable,
    expand_conduit,
    house_document_to_wireviz,
    load_catalog,
)


class TestCableCatalog(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_catalog()

    def test_catalog_has_cable_and_conduit(self) -> None:
        self.assertEqual(self.catalog["Cable"]["kind"], "cable_type")
        self.assertEqual(self.catalog["Conduit"]["kind"], "conduit_type")

    def test_expand_cable_defaults_from_subtype(self) -> None:
        out = expand_cable({"type": "Cable", "subtype": "earth"}, self.catalog)
        self.assertEqual(out["type"], "Cable")
        self.assertEqual(out["subtype"], "earth")
        self.assertEqual(out["colors"], ["GNYE"])
        self.assertEqual(out["section"], "1.5 mm2")

    def test_expand_cable_legacy_kind(self) -> None:
        out = expand_cable({"kind": "dc"}, self.catalog)
        self.assertEqual(out["type"], "Cable")
        self.assertEqual(out["subtype"], "dc")
        self.assertEqual(out["colors"], ["RD", "BK"])

    def test_expand_cable_instance_overrides_defaults(self) -> None:
        out = expand_cable(
            {"type": "Cable", "subtype": "power", "colors": ["GY", "BU"], "section": "2.5 mm2"},
            self.catalog,
        )
        self.assertEqual(out["colors"], ["GY", "BU"])
        self.assertEqual(out["section"], "2.5 mm2")

    def test_expand_conduit_legacy_type_as_size(self) -> None:
        out = expand_conduit(
            {"kind": "conduit", "type": "M20", "contains": ["L1"]},
            self.catalog,
        )
        self.assertEqual(out["type"], "Conduit")
        self.assertEqual(out["subtype"], "M20")
        self.assertEqual(out["contains"], ["L1"])

    def test_wireviz_uses_subtype_as_cable_type(self) -> None:
        doc = {
            "schema": "house/v1",
            "type": "Floor",
            "elements": {"A": {"type": "Socket"}},
            "cables": {
                "L1": {
                    "type": "Cable",
                    "subtype": "power",
                    "section": "1.5 mm2",
                    "colors": ["BN", "BU"],
                    "label": "Feed",
                }
            },
        }
        wv = house_document_to_wireviz(doc, catalog=self.catalog, file_location_parts=["Z"])
        cable = next(iter(wv["cables"].values()))
        self.assertEqual(cable["type"], "power")
        self.assertIn("label: Feed", cable["notes"])

    def test_cable_type_rejected_as_element(self) -> None:
        doc = {
            "schema": "house/v1",
            "elements": {"Bad": {"type": "Cable", "subtype": "power"}},
        }
        with self.assertRaises(ValueError) as ctx:
            house_document_to_wireviz(doc, catalog=self.catalog, file_location_parts=[])
        self.assertIn("cables:", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
