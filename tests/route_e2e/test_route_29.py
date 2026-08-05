"""Live E2E: Route_29 multi-conductor N↔N conduit must keep lane separation."""
from __future__ import annotations

import unittest

from tests.route_e2e._harness import (
    assert_no_strand_lane_overlap,
    assert_tube_geometry_ok,
    dump_live_canvas,
    resolve_example_site,
)


class TestRoute29(unittest.TestCase):
    def test_three_conductors_in_one_tube_do_not_overlap(self) -> None:
        """Three BN conductors share one N↔N tube; strands must stay parallel.

        Electrical on: inbox/mouth approaches must not collapse onto a shared
        horizontal (colinear strand stack).
        """
        site = resolve_example_site("Route_29")
        if site is None or not site.is_file():
            raise unittest.SkipTest(
                "Route_29 not found (install housewire-examples)"
            )
        data = dump_live_canvas(site, require_tubes=True)
        self.assertNotIn("err", data, msg=data)
        self.assertGreaterEqual(len(data.get("tubes") or []), 1, msg=data)
        self.assertGreaterEqual(len(data.get("strands") or []), 3, msg=data)
        assert_tube_geometry_ok(self, data)
        assert_no_strand_lane_overlap(self, data)


if __name__ == "__main__":
    unittest.main()
