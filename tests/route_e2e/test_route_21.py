"""Live E2E routing invariants for Route_21 (reference site)."""
from __future__ import annotations

import unittest

from tests.route_e2e._harness import (
    assert_named_tube_segment_count,
    assert_tube_geometry_ok,
    assert_site_routes_ok,
    dump_live_canvas,
    resolve_example_site,
)


class TestRoute21(unittest.TestCase):
    def test_live_route_invariants(self) -> None:
        assert_site_routes_ok(
            self,
            "Route_21",
            require_tubes=True,
            min_strands=4,
        )

    def test_conducto_lampara_at_most_three_segments(self) -> None:
        """N→B lamp conduit: mark-to-mark ≤3 segments (not contour+iso stubs)."""
        site = resolve_example_site("Route_21")
        if site is None or not site.is_file():
            raise unittest.SkipTest(
                "Route_21 not found (install housewire-examples)"
            )
        data = dump_live_canvas(site, require_tubes=True, depth=2)
        self.assertNotIn("err", data, msg=data)
        assert_tube_geometry_ok(self, data)
        assert_named_tube_segment_count(
            self,
            data,
            title_substr="Conducto lampara",
            max_segments=3,
        )


if __name__ == "__main__":
    unittest.main()
