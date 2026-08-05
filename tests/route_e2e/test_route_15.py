"""Live E2E: Route_15 room-to-room tube stays short at shallow depth."""
from __future__ import annotations

import unittest

from tests.route_e2e._harness import (
    _clean_ortho_pts,
    _ortho_bend_count,
    dump_live_canvas,
    resolve_example_site,
)


class TestRoute15(unittest.TestCase):
    def test_room_conduit_short_at_depth_1(self) -> None:
        """At depth 1/2 rooms collapse; JA↔JB gap is tight — keep ≤3 segments.

        Regression: opposing face stubs crossed and painted a 5-bend C.
        """
        site = resolve_example_site("Route_15")
        if site is None or not site.is_file():
            raise unittest.SkipTest(
                "Route_15 not found (install housewire-examples)"
            )
        data = dump_live_canvas(site, require_tubes=True, depth=1)
        self.assertNotIn("err", data, msg=data)
        self.assertTrue(
            str(data.get("depth_label") or "").strip().startswith("1/"),
            msg=data.get("depth_label"),
        )
        tubes = [t for t in (data.get("tubes") or []) if len(t) >= 2]
        self.assertEqual(len(tubes), 1, msg=data)
        clean = _clean_ortho_pts(tubes[0])
        segs = len(clean) - 1
        bends = _ortho_bend_count(clean)
        self.assertLessEqual(
            segs,
            3,
            msg=f"expected ≤3 segments at depth 1, got {segs}: {clean}",
        )
        self.assertLessEqual(
            bends,
            2,
            msg=f"expected ≤2 bends at depth 1, got {bends}: {clean}",
        )
        # Prefer the colinear 1-segment run when mouths share an axis.
        xs = {round(p[0], 3) for p in clean}
        ys = {round(p[1], 3) for p in clean}
        if len(xs) == 1 or len(ys) == 1:
            self.assertEqual(segs, 1, msg=clean)


if __name__ == "__main__":
    unittest.main()
