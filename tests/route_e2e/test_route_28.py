"""Live E2E: Route_28 cannot use only L paths without tube stacking."""
from __future__ import annotations

import unittest

from tests.route_e2e._harness import assert_tubes_avoid_l_overlap


class TestRoute28(unittest.TestCase):
    def test_back_face_tubes_avoid_l_colinear_overlap(self) -> None:
        """L-only would stack; live routes stay clear and use extra bends."""
        assert_tubes_avoid_l_overlap(
            self,
            "Route_28",
            expected=4,
            min_extra_bend_tubes=1,
        )


if __name__ == "__main__":
    unittest.main()
