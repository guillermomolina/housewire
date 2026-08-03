"""Live E2E: perpendicular conduit crosses beat long C-detours (rule 15)."""
from __future__ import annotations

import math
import unittest

from tests.route_e2e._harness import assert_site_routes_ok, dump_live_canvas, resolve_example_site


def _poly_len(pts: list[list[float]]) -> float:
    total = 0.0
    for i in range(len(pts) - 1):
        total += math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
    return total


class TestConduitCrossPrefer(unittest.TestCase):
    def test_route_23_no_c_detour_around_crossing(self) -> None:
        assert_site_routes_ok(
            self,
            "Route_23",
            require_tubes=True,
            min_strands=1,
        )
        site = resolve_example_site("Route_23")
        if site is None:
            raise unittest.SkipTest("Route_23 not found")
        data = dump_live_canvas(site, require_tubes=True)
        tubes = [t for t in (data.get("tubes") or []) if len(t) >= 2]
        self.assertGreaterEqual(len(tubes), 2, msg=data)
        # Short cross: each tube stays near its mouth-to-mouth span.
        # A C-detour around the peer tube is typically >2× that span.
        for i, tube in enumerate(tubes):
            span = math.hypot(
                tube[-1][0] - tube[0][0], tube[-1][1] - tube[0][1]
            )
            length = _poly_len(tube)
            self.assertLessEqual(
                length,
                span * 2.2 + 40.0,
                msg=(
                    f"tube[{i}] looks like a C-detour: "
                    f"len={length:.0f} span={span:.0f} pts={tube}"
                ),
            )


if __name__ == "__main__":
    unittest.main()
