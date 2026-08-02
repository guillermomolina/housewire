"""Live E2E routing invariants for Route_17."""
from __future__ import annotations

import unittest

from tests.route_e2e._harness import assert_site_routes_ok


class TestRoute17(unittest.TestCase):
    def test_live_route_invariants(self) -> None:
        assert_site_routes_ok(
            self,
            "Route_17",
            require_tubes=True,
            min_strands=1,
        )


if __name__ == "__main__":
    unittest.main()
