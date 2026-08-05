"""Live E2E routing invariants for Route_24 (cross of four straight conduits)."""
from __future__ import annotations

import unittest

from tests.route_e2e._harness import assert_tubes_straight


class TestRoute24(unittest.TestCase):
    def test_live_route_invariants(self) -> None:
        """Four cross conduits between aligned DeviceBoxes — tubes only."""
        assert_tubes_straight(self, "Route_24", expected=4)


if __name__ == "__main__":
    unittest.main()
