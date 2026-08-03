"""Live E2E: distinct conduits must not colinear-stack (routing rule 15).

Strands riding inside their own tube stroke are fine; two painted tubes
sharing a long mid-run corridor must stay half_a+half_b+lane_gap apart.
"""
from __future__ import annotations

import unittest

from tests.route_e2e._harness import assert_site_routes_ok


class TestConduitOverlap(unittest.TestCase):
    def test_route_21_no_colinear_tube_stack(self) -> None:
        assert_site_routes_ok(
            self,
            "Route_21",
            require_tubes=True,
            min_strands=4,
        )

    def test_route_17_no_colinear_tube_stack(self) -> None:
        # Parallel parking-style conduits in a shared parent corridor.
        assert_site_routes_ok(
            self,
            "Route_17",
            require_tubes=True,
            min_strands=1,
        )


if __name__ == "__main__":
    unittest.main()
