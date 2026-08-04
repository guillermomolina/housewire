"""Closed catalog subtype validation."""
from __future__ import annotations

import unittest

import yaml as _yaml

from housewire.house import load_catalog, validate_house_tree


class TestClosedCatalogSubtype(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_catalog()

    def test_junction_box_requires_known_subtype(self) -> None:
        doc = _yaml.safe_load(
            "schema: house/v2\n"
            "type: JunctionBox\n"
            "subtype: IP40\n"
            "elements: {}\n"
        )
        validate_house_tree(
            doc, catalog=self.catalog, file_location_parts=["Box"]
        )

    def test_unknown_junction_box_subtype_rejected(self) -> None:
        doc = _yaml.safe_load(
            "schema: house/v2\n"
            "type: JunctionBox\n"
            "subtype: '100x100 IP40'\n"
            "elements: {}\n"
        )
        with self.assertRaises(ValueError) as ctx:
            validate_house_tree(
                doc, catalog=self.catalog, file_location_parts=["Box"]
            )
        self.assertIn("unknown subtype", str(ctx.exception).lower())

    def test_mcb_free_subtype_rejected(self) -> None:
        doc = _yaml.safe_load(
            "schema: house/v2\n"
            "type: House\n"
            "elements:\n"
            "  MT:\n"
            "    type: MCB\n"
            "    subtype: C10\n"
        )
        with self.assertRaises(ValueError) as ctx:
            validate_house_tree(
                doc, catalog=self.catalog, file_location_parts=[]
            )
        self.assertIn("does not define catalog subtypes", str(ctx.exception))

    def test_conduit_unknown_subtype_rejected(self) -> None:
        doc = _yaml.safe_load(
            "schema: house/v2\n"
            "type: House\n"
            "elements:\n"
            "  A:\n"
            "    type: JunctionBox\n"
            "    subtype: IP40\n"
            "    openings: [N1]\n"
            "  B:\n"
            "    type: JunctionBox\n"
            "    subtype: IP40\n"
            "    openings: [N1]\n"
            "cables:\n"
            "  T1:\n"
            "    type: Conduit\n"
            "    subtype: not-a-tube\n"
            "    from: A.N1\n"
            "    to: B.N1\n"
        )
        with self.assertRaises(ValueError) as ctx:
            validate_house_tree(
                doc, catalog=self.catalog, file_location_parts=[]
            )
        self.assertIn("unknown subtype", str(ctx.exception).lower())
