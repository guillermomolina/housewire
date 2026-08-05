"""Compact smoke E2E for early route fixtures (01–20 class).

Full per-site modules for Route_01…Route_20 were redundant: same
``assert_site_routes_ok`` harness. Keep a small representative set here;
targeted regressions live in Route_21+ and ``test_conduit_*`` /
``test_element_avoidance``.
"""
from __future__ import annotations

import unittest

from tests.route_e2e._harness import assert_site_routes_ok

# (site, require_tubes, min_strands, why)
_SMOKE: tuple[tuple[str, bool, int, str], ...] = (
    ("Route_01", False, 1, "same-box, no conduit"),
    ("Route_03", True, 1, "twin conductors in one tube"),
    ("Route_06", True, 1, "lamp via plane boca"),
    ("Route_07", True, 1, "bipolar V at terminal"),
    ("Route_12", True, 1, "switch + lamp room subset"),
)


class TestRouteSmoke(unittest.TestCase):
    def test_early_route_smoke(self) -> None:
        for site, require_tubes, min_strands, _why in _SMOKE:
            with self.subTest(site=site):
                assert_site_routes_ok(
                    self,
                    site,
                    require_tubes=require_tubes,
                    min_strands=min_strands,
                )


if __name__ == "__main__":
    unittest.main()
