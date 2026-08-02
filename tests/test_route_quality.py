"""Regression: cable routes must stay separated AND free of needless C/Z jogs."""
from __future__ import annotations

import unittest

from housewire.ui.route_quality import (
    LANE_PITCH,
    MIN_LANE_SEPARATION,
    assess_bundle,
    count_c_jogs,
    count_z_jogs,
    parallel_highway_bundle,
    strands_overlap,
)


class TestRouteQualityDetectors(unittest.TestCase):
    def test_parallel_highway_lanes_do_not_overlap(self) -> None:
        center = [(0.0, 0.0), (0.0, 80.0), (120.0, 80.0), (120.0, 140.0)]
        bundle = parallel_highway_bundle(center, 3)
        self.assertEqual(len(bundle), 3)
        self.assertFalse(strands_overlap(bundle))
        issues = assess_bundle(bundle)
        self.assertEqual(issues, [], msg=issues)

    def test_coincident_strands_flag_overlap(self) -> None:
        a = [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0)]
        b = [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0)]
        self.assertTrue(strands_overlap([a, b]))
        issues = assess_bundle([a, b])
        self.assertTrue(any("overlap" in x for x in issues))

    def test_almost_stacked_lanes_flag_overlap(self) -> None:
        # Separation well under a lane pitch → must fail.
        a = [(0.0, 0.0), (80.0, 0.0)]
        b = [(0.0, 1.0), (80.0, 1.0)]
        self.assertLess(1.0, MIN_LANE_SEPARATION)
        self.assertTrue(strands_overlap([a, b]))

    def test_short_z_jog_detected(self) -> None:
        # Horizontal, short vertical, continue horizontal (classic Z).
        z = [
            (0.0, 0.0),
            (40.0, 0.0),
            (40.0, 12.0),
            (70.0, 12.0),
            (70.0, 40.0),
        ]
        self.assertGreaterEqual(count_z_jogs(z), 1)
        issues = assess_bundle([z])
        self.assertTrue(any("Z jog" in x for x in issues))

    def test_clean_l_has_no_z(self) -> None:
        clean = [(0.0, 0.0), (0.0, 50.0), (80.0, 50.0)]
        self.assertEqual(count_z_jogs(clean), 0)
        self.assertEqual(assess_bundle([clean]), [])

    def test_short_c_hook_detected(self) -> None:
        # Out then reverse on the same axis (C / out-and-back stub).
        c = [(10.0, 20.0), (10.0, 8.0), (10.0, 20.0), (40.0, 20.0)]
        self.assertGreaterEqual(count_c_jogs(c), 1)
        issues = assess_bundle([c])
        self.assertTrue(any("C jog" in x for x in issues))

    def test_shared_terminal_fan_may_allow_z(self) -> None:
        z = [
            (0.0, 0.0),
            (40.0, 0.0),
            (40.0, 10.0),
            (55.0, 10.0),
        ]
        self.assertEqual(assess_bundle([z], allow_z=True), [])
        self.assertTrue(any("Z" in x for x in assess_bundle([z], allow_z=False)))

    def test_lane_pitch_matches_ui_constants(self) -> None:
        # Guard against silently shrinking separation in one place only.
        self.assertEqual(LANE_PITCH, 5.0)
        bundle = parallel_highway_bundle(
            [(0.0, 0.0), (100.0, 0.0)], 2
        )
        # Neighbor centerlines should be about one pitch apart.
        y0 = bundle[0][0][1]
        y1 = bundle[1][0][1]
        self.assertAlmostEqual(abs(y1 - y0), LANE_PITCH, places=5)


class TestBothInvariantsTogether(unittest.TestCase):
    """The circular bug: fixing overlap must not reintroduce C/Z, and vice versa."""

    def test_good_three_strand_lamp_run(self) -> None:
        center = [
            (200.0, 100.0),
            (200.0, 40.0),
            (500.0, 40.0),
            (500.0, 120.0),
        ]
        bundle = parallel_highway_bundle(center, 3)
        # Unique terminals → neither overlap nor C/Z allowed.
        self.assertEqual(assess_bundle(bundle), [])

    def test_bad_stacked_run_rejected(self) -> None:
        stacked = [(0.0, 0.0), (0.0, 40.0), (90.0, 40.0)]
        issues = assess_bundle([stacked, stacked, stacked])
        self.assertTrue(any("overlap" in x for x in issues))

    def test_separated_but_with_z_still_rejected(self) -> None:
        center = [(0.0, 0.0), (0.0, 60.0), (100.0, 60.0)]
        bundle = parallel_highway_bundle(center, 2)
        # Graft a Z onto strand 0 near the end.
        s0 = list(bundle[0])
        x, y = s0[-1]
        s0.extend([(x + 10, y), (x + 10, y + 8), (x + 30, y + 8)])
        issues = assess_bundle([s0, bundle[1]])
        self.assertTrue(
            any("Z jog" in x for x in issues),
            msg=f"expected Z issue, got {issues}",
        )


if __name__ == "__main__":
    unittest.main()
