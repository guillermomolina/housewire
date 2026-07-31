from __future__ import annotations

import unittest

from housewire.house.physical import _openings_from_text
from housewire.project import openings as op


class TestOpeningIds(unittest.TestCase):
    def test_side_and_plane_ids(self) -> None:
        self.assertEqual(op.parse_opening_id("N1"), ("N", 1, None))
        self.assertEqual(op.parse_opening_id("B1-2"), ("B", 1, 2))
        self.assertEqual(op.normalize_opening_id("w2"), "W2")

    def test_invalid_id(self) -> None:
        with self.assertRaises(ValueError):
            op.parse_opening_id("B1")
        with self.assertRaises(ValueError):
            op.parse_opening_id("U1")

    def test_grid_spec_int_is_one_row(self) -> None:
        self.assertEqual(op.parse_grid_spec(3), (3, 1))
        self.assertEqual(op.parse_grid_spec("3"), (3, 1))
        self.assertEqual(op.parse_grid_spec("3x2"), (3, 2))

    def test_expand_ns_ew_and_overrides(self) -> None:
        grid = op.expand_opening_grid({"NS": 3, "WE": 2, "B": 2, "N": "3x2"})
        self.assertEqual(grid["N"], (3, 2))
        self.assertEqual(grid["S"], (3, 1))
        self.assertEqual(grid["E"], (2, 1))
        self.assertEqual(grid["W"], (2, 1))
        self.assertEqual(grid["B"], (2, 1))

    def test_ew_alias_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            op.expand_opening_grid({"EW": 2})
        self.assertIn("WE", str(ctx.exception))

    def test_opening_fits_grid(self) -> None:
        grid = op.expand_opening_grid({"NS": 2, "B": "2x1"})
        self.assertTrue(op.opening_fits_grid("N2", grid))
        self.assertFalse(op.opening_fits_grid("N3", grid))
        self.assertTrue(op.opening_fits_grid("B1-2", grid))
        self.assertFalse(op.opening_fits_grid("B2-1", grid))

    def test_declared_list(self) -> None:
        ids = op.declared_opening_ids(["N1", "B1-1"])
        self.assertEqual(ids, {"N1", "B1-1"})

    def test_declared_rejects_map(self) -> None:
        with self.assertRaises(ValueError):
            op.declared_opening_ids({"B1": {"face": "N"}})

    def test_validate_location_openings(self) -> None:
        loc = {
            "opening_grid": {"NS": 1, "B": 1},
            "openings": ["N1", "B1-1"],
        }
        op.validate_location_openings(loc)
        loc["openings"] = ["N2"]
        with self.assertRaises(ValueError):
            op.validate_location_openings(loc)


class TestOpeningsFromText(unittest.TestCase):
    def test_extracts_local_ids(self) -> None:
        found = _openings_from_text("abertura N1 ↔ abertura B1-1 ↔ destino")
        self.assertEqual(found, ["N1", "B1-1"])

    def test_extracts_legacy_opaque_b(self) -> None:
        found = _openings_from_text("abertura B1 ↔ abertura B12")
        self.assertEqual(found, ["B1", "B12"])

    def test_extracts_legacy_cardinals(self) -> None:
        found = _openings_from_text("abertura W.N ↔ abertura fondo.SE")
        self.assertEqual(found, ["W.N", "fondo.SE"])

    def test_extracts_back_lid_front(self) -> None:
        found = _openings_from_text("abertura back ↔ abertura lid.1 ↔ abertura front")
        self.assertEqual(found, ["back", "lid.1", "front"])


if __name__ == "__main__":
    unittest.main()
