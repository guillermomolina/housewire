"""Physical diagram opening token extraction."""
from __future__ import annotations

import unittest

from housewire.house.physical import _openings_from_text


class TestOpeningTokens(unittest.TestCase):
    def test_extracts_local_b_ids(self) -> None:
        found = _openings_from_text("abertura B1 ↔ abertura B12 ↔ destino")
        self.assertEqual(found, ["B1", "B12"])

    def test_extracts_legacy_cardinals(self) -> None:
        found = _openings_from_text("abertura W.N ↔ abertura fondo.SE")
        self.assertEqual(found, ["W.N", "fondo.SE"])
