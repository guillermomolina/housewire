"""Live E2E isometric opening-mark invariants for Route_25."""
from __future__ import annotations

import unittest

from tests.route_e2e._harness import assert_iso_opening_marks


class TestRoute25(unittest.TestCase):
    def test_iso_opening_mark_layout(self) -> None:
        """Side bocas on mid-depth axes; F/B inside front∩back, no shared axes."""
        assert_iso_opening_marks(self, "Route_25")


if __name__ == "__main__":
    unittest.main()
