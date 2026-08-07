"""Live E2E: Route_32 S→B tube leaves S downward in three segments."""
from __future__ import annotations

import unittest

from tests.route_e2e._harness import (
    assert_named_tube_segment_count,
    assert_tube_geometry_ok,
    dump_live_canvas,
    resolve_example_site,
)


class TestRoute32(unittest.TestCase):
    def test_s_opening_exits_south_before_turning(self) -> None:
        """S1 must leave downward; direct west exit is invalid (three segments)."""
        site = resolve_example_site("Route_32")
        if site is None or not site.is_file():
            raise unittest.SkipTest("Route_32 not found (install housewire-examples)")
        data = dump_live_canvas(site, require_tubes=True)
        self.assertNotIn("err", data, msg=data)
        self.assertEqual(len(data.get("tubes") or []), 1, msg=data)
        assert_tube_geometry_ok(self, data)
        assert_named_tube_segment_count(
            self,
            data,
            title_substr="Conducto_OPEN_Linea_01_01",
            segments=3,
        )
        tube = (data.get("tube_cores") or data.get("tubes") or [])[0]
        self.assertGreater(tube[1][1], tube[0][1], msg=tube)


if __name__ == "__main__":
    unittest.main()
