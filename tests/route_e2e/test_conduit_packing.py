"""Live E2E: conduit road width must match packed strand lanes.

Catches fat empty conduits where the tube is sized for N wires but strands
stack near the centerline (multi-hop route buckets each painted as lane 0).
"""
from __future__ import annotations

import unittest

from tests.route_e2e._harness import assert_site_routes_ok


class TestConduitPacking(unittest.TestCase):
    def test_route_21_no_underfilled_tubes(self) -> None:
        assert_site_routes_ok(
            self,
            "Route_21",
            require_tubes=True,
            min_strands=4,
        )


if __name__ == "__main__":
    unittest.main()
