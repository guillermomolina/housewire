"""Unit tests for live-canvas route invariant detectors (no Playwright)."""
from __future__ import annotations

import unittest

from housewire.ui.route_quality import (
    assess_live_canvas,
    match_strand_to_tube,
    point_near_polyline,
    shared_horizontal_trunk_length,
)


class TestLiveCanvasInvariantsUnit(unittest.TestCase):
    """Detectors must flag known failure shapes from the reference site."""

    def test_missed_mouth_detected(self) -> None:
        tube = [(593.0, 332.0), (593.0, 308.0), (1147.0, 308.0), (1147.0, 459.5)]
        bad = [
            (593.0, 332.0),
            (593.0, 308.0),
            (1147.0, 308.0),
            (1147.0, 402.0),
            (1152.0, 413.0),
            (1205.0, 511.0),
        ]
        issues = assess_live_canvas([tube], [bad], tube_half_widths=[8.75])
        self.assertTrue(
            any("misses tube" in x and "end mouth" in x for x in issues),
            msg=issues,
        )

    def test_good_mouth_transit_ok(self) -> None:
        tube = [(593.0, 332.0), (593.0, 308.0), (1147.0, 308.0), (1147.0, 459.5)]
        good = [
            (200.0, 452.0),
            (200.0, 332.0),
            (593.0, 332.0),
            (593.0, 308.0),
            (1147.0, 308.0),
            (1147.0, 459.5),
            (1147.0, 505.0),
            (1241.0, 511.0),
        ]
        issues = assess_live_canvas(
            [tube],
            [good],
            tube_half_widths=[8.75],
            bipolar_y_min=900.0,
        )
        self.assertFalse(
            any("misses tube" in x for x in issues),
            msg=issues,
        )

    def test_shared_trunk_detected(self) -> None:
        a = [(660.0, 452.0), (660.0, 420.0), (598.0, 420.0), (593.0, 332.0)]
        b = [(680.0, 452.0), (680.0, 420.0), (598.0, 420.0), (593.0, 332.0)]
        trunks = shared_horizontal_trunk_length(
            [a, b], y_min=400.0, y_max=440.0, min_len=40.0
        )
        self.assertTrue(trunks, msg=trunks)
        issues = assess_live_canvas(
            [[(593.0, 332.0), (700.0, 332.0)]],
            [a, b],
            bipolar_y_min=900.0,
        )
        self.assertTrue(any("shared inbox trunk" in x for x in issues), msg=issues)

    def test_missing_v_detected(self) -> None:
        tube = [(100.0, 100.0), (100.0, 200.0)]
        bad = [(100.0, 100.0), (100.0, 200.0), (200.0, 200.0), (200.0, 452.0)]
        issues = assess_live_canvas(
            [tube], [bad], tube_half_widths=[10.0], bipolar_y_min=430.0
        )
        self.assertTrue(any("missing terminal V" in x for x in issues), msg=issues)

    def test_fat_tube_with_stacked_lanes_detected(self) -> None:
        """Fat tube sized for many lanes while strands stack near the centerline."""
        from housewire.ui.route_quality import highway_road_width, tube_packing_underfill

        tube = [(100.0, 0.0), (100.0, 200.0)]
        # Nine-lane road, but every strand rides near x=100 (lane 0 stacking).
        half = highway_road_width(9) / 2.0
        stacked = [
            [(100.0 + (i % 3 - 1) * 2.5, 20.0), (100.0 + (i % 3 - 1) * 2.5, 180.0)]
            for i in range(6)
        ]
        msg = tube_packing_underfill(tube, stacked, half_width=half)
        self.assertIsNotNone(msg, msg=msg)
        issues = assess_live_canvas(
            [tube],
            stacked,
            tube_half_widths=[half],
            bipolar_y_min=900.0,
        )
        self.assertTrue(any("underfilled" in x for x in issues), msg=issues)

    def test_packed_highway_not_underfilled(self) -> None:
        from housewire.ui.route_quality import (
            highway_lane_offset,
            highway_road_width,
            tube_packing_underfill,
        )

        tube = [(100.0, 0.0), (100.0, 200.0)]
        n = 6
        half = highway_road_width(n) / 2.0
        packed = [
            [
                (100.0 + highway_lane_offset(i, n), 20.0),
                (100.0 + highway_lane_offset(i, n), 180.0),
            ]
            for i in range(n)
        ]
        self.assertIsNone(
            tube_packing_underfill(tube, packed, half_width=half)
        )
        issues = assess_live_canvas(
            [tube],
            packed,
            tube_half_widths=[half],
            bipolar_y_min=900.0,
        )
        self.assertFalse(any("underfilled" in x for x in issues), msg=issues)

    def test_stacked_conduits_flag_colinear_overlap(self) -> None:
        """Distinct tubes on the same corridor must not share a long run."""
        from housewire.ui.route_quality import tubes_colinear_overlap

        a = [(0.0, 100.0), (400.0, 100.0)]
        b = [(0.0, 102.0), (400.0, 102.0)]  # almost stacked; halves 8.75
        issues = tubes_colinear_overlap(
            [a, b], tube_half_widths=[8.75, 8.75], min_overlap=24.0
        )
        self.assertTrue(any("colinear-overlap" in x for x in issues), msg=issues)
        canvas = assess_live_canvas(
            [a, b],
            [
                [(0.0, 100.0), (400.0, 100.0)],
                [(0.0, 102.0), (400.0, 102.0)],
            ],
            tube_half_widths=[8.75, 8.75],
            bipolar_y_min=900.0,
        )
        self.assertTrue(
            any("colinear-overlap" in x for x in canvas), msg=canvas
        )

    def test_parallel_separated_conduits_ok(self) -> None:
        from housewire.ui.route_quality import tubes_colinear_overlap

        # half 8.75+8.75+2.5 = 20 → sep 22 clears
        a = [(0.0, 100.0), (400.0, 100.0)]
        b = [(0.0, 122.0), (400.0, 122.0)]
        self.assertEqual(
            tubes_colinear_overlap(
                [a, b], tube_half_widths=[8.75, 8.75], min_overlap=24.0
            ),
            [],
        )

    def test_crossing_conduits_not_colinear_overlap(self) -> None:
        from housewire.ui.route_quality import tubes_colinear_overlap

        h = [(0.0, 100.0), (400.0, 100.0)]
        v = [(200.0, 0.0), (200.0, 200.0)]
        self.assertEqual(
            tubes_colinear_overlap(
                [h, v], tube_half_widths=[8.75, 8.75], min_overlap=24.0
            ),
            [],
        )

    def test_strand_through_foreign_element_flagged(self) -> None:
        from housewire.ui.route_quality import strands_through_elements

        # Ends land on Left/Right faces; mid boxes are pierced.
        strand = [(92.0, 94.0), (320.0, 94.0)]
        left = (20.0, 80.0, 72.0, 28.0)
        mid = (120.0, 80.0, 72.0, 28.0)
        mid_b = (220.0, 80.0, 72.0, 28.0)
        right = (320.0, 80.0, 72.0, 28.0)
        issues = strands_through_elements([strand], [left, mid, mid_b, right])
        self.assertTrue(any("through element" in x for x in issues), msg=issues)
        self.assertTrue(any("element[1]" in x for x in issues), msg=issues)
        self.assertTrue(any("element[2]" in x for x in issues), msg=issues)
        self.assertFalse(any("element[0]" in x for x in issues), msg=issues)
        self.assertFalse(any("element[3]" in x for x in issues), msg=issues)

    def test_strand_skirting_element_ok(self) -> None:
        from housewire.ui.route_quality import strands_through_elements

        # Corridor below the mid box.
        strand = [(20.0, 130.0), (400.0, 130.0)]
        mid = (120.0, 80.0, 72.0, 28.0)
        self.assertEqual(strands_through_elements([strand], [mid]), [])

    def test_strand_deep_pierce_of_endpoint_element_flagged(self) -> None:
        from housewire.ui.route_quality import strands_through_elements

        # Pin on the north face, corridor under the box → vertical pierce.
        strand = [(50.0, 20.0), (50.0, 120.0)]
        box = (20.0, 40.0, 60.0, 60.0)
        issues = strands_through_elements([strand], [box])
        self.assertTrue(any("through element" in x for x in issues), msg=issues)

    def test_strand_short_landing_on_endpoint_ok(self) -> None:
        from housewire.ui.route_quality import strands_through_elements

        # Short stub just outside / on the north edge — not a body pierce.
        strand = [(50.0, 38.0), (50.0, 20.0)]
        box = (20.0, 40.0, 60.0, 60.0)
        self.assertEqual(strands_through_elements([strand], [box]), [])

    def test_point_near_and_match_helpers(self) -> None:
        tube = [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0)]
        self.assertTrue(point_near_polyline((100.0, 25.0), tube, tol=1.0))
        self.assertFalse(point_near_polyline((50.0, 25.0), tube, tol=1.0))
        strand = [(0.0, 2.0), (100.0, 2.0), (100.0, 50.0)]
        ti, score = match_strand_to_tube(
            strand, [tube, [(500.0, 500.0), (600.0, 600.0)]]
        )
        self.assertEqual(ti, 0)
        self.assertLess(score, 5.0)


if __name__ == "__main__":
    unittest.main()
