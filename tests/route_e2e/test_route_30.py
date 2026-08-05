"""Live E2E: Route_30 nine conductors in one aligned S↔N conduit."""
from __future__ import annotations

import unittest

from tests.route_e2e._harness import (
    assert_inbox_at_most_segments,
    assert_named_tube_segment_count,
    assert_no_strand_lane_overlap,
    assert_no_strand_through_elements,
    assert_tube_geometry_ok,
    dump_live_canvas,
    resolve_example_site,
)


class TestRoute30(unittest.TestCase):
    def test_nine_conductors_straight_tube_short_inbox(self) -> None:
        """Aligned boxes: short tube, ≤3-seg mouth↔pin, no element pierce.

        Upper strip must attach on the south face toward the boca (mirror of
        the lower strip's north face), not wrap around to the far terminals.
        """
        site = resolve_example_site("Route_30")
        if site is None or not site.is_file():
            raise unittest.SkipTest(
                "Route_30 not found (install housewire-examples)"
            )
        data = dump_live_canvas(site, require_tubes=True)
        self.assertNotIn("err", data, msg=data)
        self.assertGreaterEqual(len(data.get("tubes") or []), 1, msg=data)
        self.assertGreaterEqual(len(data.get("strands") or []), 9, msg=data)
        assert_tube_geometry_ok(self, data)
        assert_named_tube_segment_count(
            self,
            data,
            title_substr="Conducto_OPEN_Linea_01_01",
            segments=1,
        )
        assert_inbox_at_most_segments(self, data, max_segments=3)
        assert_no_strand_through_elements(self, data)
        assert_no_strand_lane_overlap(self, data)


if __name__ == "__main__":
    unittest.main()
