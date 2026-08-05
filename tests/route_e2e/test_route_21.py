"""Live E2E routing invariants for Route_21 (reference site)."""
from __future__ import annotations

import unittest

from tests.route_e2e._harness import (
    _clean_ortho_pts,
    _ortho_bend_count,
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
        # Titles are not in the dump — match by geometry: longest tube to the
        # lamp is the one ending farthest east (painted B mouth).
        tubes = [t for t in (data.get("tubes") or []) if len(t) >= 2]
        self.assertGreaterEqual(len(tubes), 3, msg=data)
        lamp = max(tubes, key=lambda t: max(p[0] for p in t))
        clean = _clean_ortho_pts(lamp)
        segs = len(clean) - 1
        self.assertLessEqual(
            segs,
            3,
            msg=f"Conducto_lampara expected ≤3 segments, got {segs}: {clean}",
        )
        self.assertLessEqual(_ortho_bend_count(clean), 2, msg=clean)


if __name__ == "__main__":
    unittest.main()
