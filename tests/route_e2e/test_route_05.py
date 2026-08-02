"""Live E2E routing invariants for Route_05."""
from __future__ import annotations

import unittest

from tests.route_e2e._harness import assert_site_routes_ok


class TestRoute05(unittest.TestCase):
    def test_live_route_invariants(self) -> None:
        assert_site_routes_ok(
            self,
            "Route_05",
            require_tubes=True,
            min_strands=1,
        )


if __name__ == "__main__":
    unittest.main()
