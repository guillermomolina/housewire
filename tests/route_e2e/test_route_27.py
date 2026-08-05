"""Live E2E: Route_27 back-face conduits are single-corner Manhattan L runs."""
from __future__ import annotations

import unittest

from tests.route_e2e._harness import assert_tubes_l_shape


class TestRoute27(unittest.TestCase):
    def test_back_face_tubes_single_l_vertex(self) -> None:
        """Four B↔B conduits: one bend each (≤3 path points after cleanup)."""
        assert_tubes_l_shape(
            self,
            "Route_27",
            expected=4,
            max_points=3,
        )


if __name__ == "__main__":
    unittest.main()
