"""Live E2E: Route_14 Mid→End tube is a single straight segment."""
from __future__ import annotations

import unittest

from tests.route_e2e._harness import (
    _clean_ortho_pts,
    _ortho_bend_count,
    dump_live_canvas,
    resolve_example_site,
)


class TestRoute14(unittest.TestCase):
    def test_tube2_mid_to_end_is_one_segment(self) -> None:
        """Mid.E↔End.W mouths are colinear; no face-stub C in the tight gap."""
        site = resolve_example_site("Route_14")
        if site is None or not site.is_file():
            raise unittest.SkipTest(
                "Route_14 not found (install housewire-examples)"
            )
        data = dump_live_canvas(site, require_tubes=True)
        self.assertNotIn("err", data, msg=data)
        tubes = [t for t in (data.get("tubes") or []) if len(t) >= 2]
        self.assertGreaterEqual(len(tubes), 3, msg=data)
        tube2 = _clean_ortho_pts(tubes[2])
        self.assertEqual(
            len(tube2) - 1,
            1,
            msg=f"Tube2 expected 1 segment, got {tube2}",
        )
        self.assertEqual(_ortho_bend_count(tube2), 0, msg=tube2)


if __name__ == "__main__":
    unittest.main()
