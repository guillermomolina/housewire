"""Tests for sprite AABB physical bounds migration."""
from __future__ import annotations

import unittest

from housewire.site.view_layout import (
    BOUNDS_SPRITE,
    ISO_DEPTH,
    get_physical_bounds,
    get_physical_position,
    get_physical_size,
    migrate_place_physical_to_sprite,
    migrate_site_physical_to_sprite,
)


class TestSpriteBoundsMigration(unittest.TestCase):
    def test_iso_leaf_migrates_once(self) -> None:
        place = {
            "type": "DeviceBox",
            "opening_grid": {"NS": 1},
            "view": {"physical": {"x": 40.0, "y": 60.0, "w": 200.0, "h": 140.0}},
        }
        self.assertTrue(migrate_place_physical_to_sprite(place))
        self.assertEqual(get_physical_bounds(place), BOUNDS_SPRITE)
        self.assertEqual(
            get_physical_position(place),
            (40.0 - ISO_DEPTH, 60.0 - ISO_DEPTH),
        )
        self.assertEqual(
            get_physical_size(place),
            (200.0 + ISO_DEPTH, 140.0 + ISO_DEPTH),
        )
        self.assertFalse(migrate_place_physical_to_sprite(place))

    def test_non_iso_unchanged(self) -> None:
        place = {
            "type": "Room",
            "view": {"physical": {"x": 10.0, "y": 20.0, "w": 400.0, "h": 300.0}},
        }
        self.assertFalse(migrate_place_physical_to_sprite(place))
        self.assertEqual(get_physical_position(place), (10.0, 20.0))
        self.assertIsNone(get_physical_bounds(place))

    def test_site_renormalizes_negatives(self) -> None:
        site = {
            "type": "House",
            "elements": {
                "Box": {
                    "type": "DeviceBox",
                    "opening_grid": {"N": 1},
                    "view": {
                        "physical": {"x": 10.0, "y": 5.0, "w": 100.0, "h": 80.0}
                    },
                }
            },
        }
        n = migrate_site_physical_to_sprite(site)
        self.assertEqual(n, 1)
        box = site["elements"]["Box"]
        pos = get_physical_position(box)
        assert pos is not None
        self.assertGreaterEqual(pos[0], 0.0)
        self.assertGreaterEqual(pos[1], 0.0)
        self.assertEqual(get_physical_bounds(box), BOUNDS_SPRITE)


if __name__ == "__main__":
    unittest.main()
