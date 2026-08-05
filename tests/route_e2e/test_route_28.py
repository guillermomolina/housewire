"""Live E2E: Route_28 cannot use only L paths without tube stacking."""
from __future__ import annotations

import unittest

from tests.route_e2e._harness import (
    assert_named_tube_segment_count,
    assert_tubes_avoid_l_overlap,
)


class TestRoute28(unittest.TestCase):
    def test_back_face_tubes_avoid_l_colinear_overlap(self) -> None:
        """L-only would stack; live routes stay clear and use extra bends."""
        data = assert_tubes_avoid_l_overlap(
            self,
            "Route_28",
            expected=4,
            min_extra_bend_tubes=1,
            max_segments_when_extra=3,
        )
        # Conducto_OPEN_Linea_03_01 is the C/U detour — exactly three segments.
        assert_named_tube_segment_count(
            self,
            data,
            title_substr="Conducto_OPEN_Linea_03_01",
            segments=3,
        )


if __name__ == "__main__":
    unittest.main()
