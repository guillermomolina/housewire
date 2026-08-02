"""Tests for location / element name prefix convention (``__`` between levels)."""
from __future__ import annotations

import unittest

import yaml as _yaml

from housewire.house import (
    load_catalog,
    location_prefix,
    place_meta_from_mapping,
    prefixed_name,
    validate_house_tree,
)


class TestNamingConvention(unittest.TestCase):
    """``__`` separates location levels and the leaf name uniformly."""

    def test_single_location_level(self) -> None:
        prefix = location_prefix(["Parking"])
        self.assertEqual(prefixed_name(prefix, "Regleta"), "Parking__Regleta")
        self.assertEqual(prefixed_name(prefix, "Linea_test"), "Parking__Linea_test")

    def test_two_location_levels(self) -> None:
        prefix = location_prefix(["Parking", "Caja derivacion 1"])
        self.assertEqual(
            prefixed_name(prefix, "Regleta"),
            "Parking__Caja_derivacion_1__Regleta",
        )

    def test_three_location_levels(self) -> None:
        prefix = location_prefix(["Planta baja", "Recibidor", "Cuadro general"])
        self.assertEqual(
            prefixed_name(prefix, "Regleta"),
            "Planta_baja__Recibidor__Cuadro_general__Regleta",
        )

    def test_no_single_underscore_between_location_and_name(self) -> None:
        prefix = location_prefix(["Parking", "Caja derivacion 1"])
        name = prefixed_name(prefix, "Regleta")
        self.assertNotIn("_1_Regleta", name)

    def test_location_path_list_rejected(self) -> None:
        doc = _yaml.safe_load(
            "schema: house/v2\n"
            "location: [Caja derivacion 1]\n"
            "elements:\n"
            "  Regleta:\n"
            "    type: TerminalStrip\n"
        )
        with self.assertRaises(ValueError) as ctx:
            place_meta_from_mapping(doc)
        self.assertIn("location:", str(ctx.exception))
        self.assertIn("list", str(ctx.exception).lower())

    def test_validate_accepts_prefixed_tree(self) -> None:
        doc = _yaml.safe_load(
            "schema: house/v2\n"
            "elements:\n"
            "  Regleta:\n"
            "    type: TerminalStrip\n"
            "cables:\n"
            "  Linea_test_1:\n"
            "    type: Conductor\n"
            "    subtype: power\n"
            "    section: '1.5 mm2'\n"
            "    color: BN\n"
            "  Linea_test:\n"
            "    type: Cable\n"
            "    subtype: power\n"
            "    contains: [Linea_test_1]\n"
        )
        validate_house_tree(
            doc, catalog=load_catalog(), file_location_parts=["Parking"]
        )


if __name__ == "__main__":
    unittest.main()
