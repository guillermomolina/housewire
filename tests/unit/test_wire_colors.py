"""Canonical HouseWire conductor color table."""
from __future__ import annotations

import unittest

from housewire.house.wire_colors import (
    CONDUCTOR_COLORS,
    css_for_color,
    is_known_color_code,
    wire_colors_payload,
)


class TestWireColors(unittest.TestCase):
    def test_core_codes(self) -> None:
        for code in ("BN", "BU", "GNYE", "BK", "GY"):
            self.assertTrue(is_known_color_code(code))
            self.assertTrue(css_for_color(code).startswith("#"))

    def test_normalize_case(self) -> None:
        self.assertEqual(css_for_color("bn"), CONDUCTOR_COLORS["BN"]["css"])

    def test_payload_for_ui(self) -> None:
        payload = wire_colors_payload()
        self.assertEqual(payload["standard"], "HouseWire")
        self.assertEqual(payload["letter_standard"], "IEC 60757")
        self.assertIn("BN", payload["colors"])
        self.assertEqual(
            payload["colors"]["GNYE"]["css"], CONDUCTOR_COLORS["GNYE"]["css"]
        )


if __name__ == "__main__":
    unittest.main()
