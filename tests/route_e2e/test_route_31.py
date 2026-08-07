"""Live E2E: Route_31 N↔N conduit must skirt Device_mechanism_box (rule 17)."""
from __future__ import annotations

import unittest

from tests.route_e2e._harness import (
    assert_no_tube_through_leaves,
    assert_tube_geometry_ok,
    dump_live_canvas,
    resolve_example_site,
)


class TestRoute31(unittest.TestCase):
    def test_conduit_skirts_upper_device_box(self) -> None:
        """Offset N↔N mouths: tube must not cut through the upper DeviceBox.

        Regression: iso mouth≠anchor cleared both endpoints as obstacles, so
        Conducto_OPEN_Linea_01_01 dropped vertically through Device_mechanism_box.
        Sprite AABB (bounds: sprite) includes the iso NW depth so the tube must
        clear the full painted hull.
        """
        site = resolve_example_site("Route_31")
        if site is None or not site.is_file():
            raise unittest.SkipTest(
                "Route_31 not found (install housewire-examples)"
            )
        data = dump_live_canvas(site, require_tubes=True)
        self.assertNotIn("err", data, msg=data)
        self.assertEqual(len(data.get("tubes") or []), 1, msg=data)
        titles = data.get("tube_titles") or []
        self.assertTrue(
            any("Conducto_OPEN_Linea_01_01" in (t or "") for t in titles),
            msg=titles,
        )
        assert_tube_geometry_ok(self, data)
        assert_no_tube_through_leaves(
            self, data, leaf_id="Device_mechanism_box"
        )
        assert_no_tube_through_leaves(
            self, data, leaf_id="Device_mechanism_box_1"
        )


if __name__ == "__main__":
    unittest.main()
