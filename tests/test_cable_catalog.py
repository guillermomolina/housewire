"""Tests for Cable/Conduit/Conductor catalog expansion (type/subtype)."""
from __future__ import annotations

import unittest

from housewire.house import (
    expand_cable,
    expand_conductor,
    expand_conduit,
    load_catalog,
    validate_house_tree,
)


class TestCableCatalog(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_catalog()

    def test_catalog_has_link_types(self) -> None:
        self.assertEqual(self.catalog["Cable"]["kind"], "cable_type")
        self.assertEqual(self.catalog["Conduit"]["kind"], "conduit_type")
        self.assertEqual(self.catalog["Conductor"]["kind"], "conductor_type")

    def test_expand_cable_sheath_defaults(self) -> None:
        out = expand_cable({"type": "Cable", "subtype": "Earth"}, self.catalog)
        self.assertEqual(out["type"], "Cable")
        self.assertEqual(out["subtype"], "Earth")
        self.assertEqual(out["color"], "GNYE")

    def test_expand_cable_legacy_kind(self) -> None:
        out = expand_cable({"kind": "DC"}, self.catalog)
        self.assertEqual(out["type"], "Cable")
        self.assertEqual(out["subtype"], "DC")
        self.assertEqual(out["color"], "BK")

    def test_expand_conductor_defaults(self) -> None:
        out = expand_conductor(
            {"type": "Conductor", "subtype": "Earth"}, self.catalog
        )
        self.assertEqual(out["color"], "GNYE")
        self.assertEqual(out["section"], "1.5 mm2")

    def test_expand_conduit_legacy_type_as_size(self) -> None:
        out = expand_conduit(
            {"kind": "conduit", "type": "M20", "contains": ["L1"]},
            self.catalog,
        )
        self.assertEqual(out["type"], "Conduit")
        self.assertEqual(out["subtype"], "M20")
        self.assertEqual(out["contains"], ["L1"])

    def test_expand_preserves_install_on_conduit_and_cable(self) -> None:
        conduit = expand_conduit(
            {
                "type": "Conduit",
                "subtype": "Tube",
                "from": "A.N1",
                "to": "B.S1",
                "contains": ["L1"],
                "install": "surface",
            },
            self.catalog,
        )
        self.assertEqual(conduit["install"], "surface")
        cable = expand_cable(
            {
                "type": "Cable",
                "contains": ["L1_1"],
                "install": "flush",
                "color": "WH",
            },
            self.catalog,
        )
        self.assertEqual(cable["install"], "flush")
        legacy = expand_conduit(
            {
                "type": "Conduit",
                "from": "A.N1",
                "to": "B.S1",
                "contains": ["L1"],
                "install": "in_wall",
            },
            self.catalog,
        )
        self.assertEqual(legacy["install"], "flush")

    def test_validate_accepts_sheath_and_conductors(self) -> None:
        doc = {
            "schema": "house/v2",
            "type": "Floor",
            "elements": {"A": {"type": "Socket"}},
            "cables": {
                "L1_1": {
                    "type": "Conductor",
                    "subtype": "Power",
                    "section": "1.5 mm2",
                    "color": "BN",
                    "from": "A.N1",
                    "to": "A.N",
                },
                "L1": {
                    "type": "Cable",
                    "subtype": "Power",
                    "contains": ["L1_1"],
                    "label": "Feed",
                },
            },
        }
        validate_house_tree(
            doc, catalog=self.catalog, file_location_parts=["Z"]
        )

    def test_cable_type_rejected_as_element(self) -> None:
        doc = {
            "schema": "house/v2",
            "elements": {"Bad": {"type": "Cable", "subtype": "Power"}},
        }
        with self.assertRaises(ValueError) as ctx:
            validate_house_tree(
                doc, catalog=self.catalog, file_location_parts=[]
            )
        self.assertIn("cables:", str(ctx.exception).lower())

    def test_v1_schema_rejected(self) -> None:
        doc = {"schema": "house/v1", "elements": {}}
        with self.assertRaises(ValueError) as ctx:
            validate_house_tree(
                doc, catalog=self.catalog, file_location_parts=[]
            )
        self.assertIn("house/v1", str(ctx.exception))
        self.assertIn("house/v2", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
