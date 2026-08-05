"""Live E2E: Route_26 back-face conduits are single-segment straight runs."""
from __future__ import annotations

import unittest

from tests.route_e2e._harness import assert_tubes_straight


class TestRoute26(unittest.TestCase):
    def test_back_face_tubes_straight_no_vertices(self) -> None:
        """Four B↔B conduits: axis-aligned and only two path points each."""
        assert_tubes_straight(
            self,
            "Route_26",
            expected=4,
            max_points=2,
        )


if __name__ == "__main__":
    unittest.main()
