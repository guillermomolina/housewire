"""Live E2E: Route_15 room-to-room tube stays short at shallow depth."""
from __future__ import annotations

import unittest

from tests.route_e2e._harness import (
    assert_named_tube_segment_count,
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
        self.assertEqual(len(data.get("tubes") or []), 1, msg=data)
        # User: 1 segment when aligned (this fixture), at most 3 otherwise.
        assert_named_tube_segment_count(
            self,
            data,
            title_substr="Tube:",
            segments=1,
            max_segments=3,
        )


if __name__ == "__main__":
    unittest.main()
