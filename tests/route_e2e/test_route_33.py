"""Live E2E: Route_33 N→S tube must skirt both device boxes."""
from __future__ import annotations

import unittest

from tests.route_e2e._harness import (
    assert_named_tube_segment_count,
    assert_no_tube_through_leaves,
    assert_tube_geometry_ok,
    dump_live_canvas,
    resolve_example_site,
)


class TestRoute33(unittest.TestCase):
    def test_s_opening_is_approached_from_below_without_crossing_boxes(self) -> None:
        """The N→S path needs five segments around the two adjacent boxes."""
        site = resolve_example_site("Route_33")
        if site is None or not site.is_file():
            raise unittest.SkipTest("Route_33 not found (install housewire-examples)")

        data = dump_live_canvas(site, require_tubes=True)
        self.assertNotIn("err", data, msg=data)
        self.assertEqual(len(data.get("tubes") or []), 1, msg=data)
        assert_tube_geometry_ok(self, data)
        assert_named_tube_segment_count(
            self, data, title_substr="Conducto", segments=5
        )
        assert_no_tube_through_leaves(
            self, data, leaf_id="Caja_de_mecanismo"
        )
        assert_no_tube_through_leaves(
            self, data, leaf_id="Caja_de_mecanismo_1"
        )

        tube = (data.get("tube_cores") or data.get("tubes") or [])[0]
        # The S mouth is reached from below, never from its left.
        self.assertGreater(tube[-2][1], tube[-1][1], msg=tube)


if __name__ == "__main__":
    unittest.main()
