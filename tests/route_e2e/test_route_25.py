"""Live E2E isometric opening-mark invariants for Route_25."""
from __future__ import annotations

import unittest

from tests.route_e2e._harness import (
    assert_iso_opening_marks,
    assert_tube_geometry_ok,
    dump_live_canvas,
    resolve_example_site,
)


class TestRoute25(unittest.TestCase):
    def test_iso_opening_mark_layout(self) -> None:
        """Side bocas on mid-depth axes; F/B inside front∩back, no shared axes."""
        assert_iso_opening_marks(self, "Route_25")
        site = resolve_example_site("Route_25")
        if site is None or not site.is_file():
            raise unittest.SkipTest(
                "Route_25 not found (install housewire-examples)"
            )
        data = dump_live_canvas(site, require_tubes=False)
        self.assertNotIn("err", data, msg=data)
        assert_tube_geometry_ok(self, data)


if __name__ == "__main__":
    unittest.main()
