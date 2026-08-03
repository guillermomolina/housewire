"""Live E2E: inbox cables must not pierce foreign element boxes (rule 17)."""
from __future__ import annotations

import unittest

from tests.route_e2e._harness import assert_site_routes_ok


class TestElementAvoidance(unittest.TestCase):
    def test_route_22_skirts_middle_elements(self) -> None:
        assert_site_routes_ok(
            self,
            "Route_22",
            require_tubes=False,
            min_strands=1,
        )


if __name__ == "__main__":
    unittest.main()
