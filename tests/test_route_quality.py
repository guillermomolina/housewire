"""Regression: cable routes must stay separated AND free of needless C/Z/long diagonals.

The live Lampara/Caja bugs this suite must catch:
- long boca→element diagonals
- Manhattan Z into unique terminals
- stacked lanes / overlap
- sheath color WH must stay true white (#ffffff)
"""
from __future__ import annotations

import unittest

from housewire.house.wire_colors import CONDUCTOR_COLORS, css_for_color
from housewire.ui.route_quality import (
    LANE_PITCH,
    MIN_LANE_SEPARATION,
    OUTLINE_EXTRA,
    TERMINAL_DIAG_MAX,
    approach_point_before_pin,
    assess_bundle,
    count_c_jogs,
    count_long_diagonals,
    count_z_jogs,
    max_diagonal_length,
    offset_ortho,
    parallel_highway_bundle,
    perpendicular_shared_terminal_entry,
    polyline_hugs_rect_border,
    shared_terminal_entry_is_v,
    strands_overlap,
)


def _manhattan_pin_join(
    pin: tuple[float, float], lane: tuple[float, float]
) -> list[tuple[float, float]]:
    stub = (pin[0], pin[1] - 10.0)
    corner = (lane[0], stub[1])
    return [pin, stub, corner, lane]


def _short_diagonal_pin_join(
    pin: tuple[float, float], lane: tuple[float, float]
) -> list[tuple[float, float]]:
    stub = (pin[0], pin[1] - 6.0)
    return [pin, stub, lane]


def _lampara_like_bundle(*, mode: str) -> list[list[tuple[float, float]]]:
    """Three lanes into a top-terminal strip.

    mode:
      - ``long_diag``: boca→pin diagonal (live 0.34.8 bug)
      - ``manhattan_z``: stub + Z into pin
      - ``short_diag``: short diagonal on single-cable pins (now forbidden)
      - ``manhattan``: Manhattan spine + stub (single cable, no diagonal)
      - ``multi_v``: two cables on one pin with V diagonals
    """
    center = [(200.0, 40.0), (200.0, 120.0), (320.0, 120.0)]
    lanes = parallel_highway_bundle(center, 3)
    pins = [(300.0, 100.0), (320.0, 100.0), (340.0, 100.0)]
    boca = (200.0, 40.0)
    out: list[list[tuple[float, float]]] = []
    if mode == "multi_v":
        pin = (320.0, 100.0)
        a = [pin, (320.0, 94.0), (312.0, 82.0), (312.0, 120.0), (200.0, 120.0), boca]
        b = [pin, (320.0, 94.0), (328.0, 82.0), (328.0, 120.0), (200.0, 120.0), boca]
        return [a, b]
    for i, lane_poly in enumerate(lanes):
        if mode == "long_diag":
            strand = [boca, pins[i]]
        elif mode == "manhattan_z":
            join = lane_poly[-1]
            lead = _manhattan_pin_join(pins[i], join)
            strand = list(lane_poly) + list(reversed(lead))[1:]
        elif mode == "short_diag":
            pin = pins[i]
            under = (pin[0], pin[1] + 14.0)
            spine = list(lane_poly)
            if abs(spine[-1][0] - under[0]) > 1e-6:
                spine.append((under[0], spine[-1][1]))
            spine.append(under)
            stub = (pin[0], pin[1] - 6.0)
            near = (pin[0] + 8.0, pin[1] + 8.0)
            strand = spine + [near, stub, pin]
        else:
            # manhattan: extend lane to pin x, then vertical into pin (no diag/C).
            pin = pins[i]
            strand = list(lane_poly)
            last = strand[-1]
            if abs(last[0] - pin[0]) > 1e-6:
                strand.append((pin[0], last[1]))
            if abs(strand[-1][1] - pin[1]) > 1e-6 or abs(strand[-1][0] - pin[0]) > 1e-6:
                strand.append(pin)
        out.append(strand)
    return out


class TestRouteQualityDetectors(unittest.TestCase):
    def test_parallel_highway_lanes_do_not_overlap(self) -> None:
        center = [(0.0, 0.0), (0.0, 80.0), (120.0, 80.0), (120.0, 140.0)]
        bundle = parallel_highway_bundle(center, 3)
        self.assertFalse(strands_overlap(bundle))
        self.assertEqual(assess_bundle(bundle), [])

    def test_coincident_strands_flag_overlap(self) -> None:
        a = [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0)]
        self.assertTrue(strands_overlap([a, a]))
        self.assertTrue(any("overlap" in x for x in assess_bundle([a, a])))

    def test_almost_stacked_lanes_flag_overlap(self) -> None:
        a = [(0.0, 0.0), (80.0, 0.0)]
        b = [(0.0, 1.0), (80.0, 1.0)]
        self.assertLess(1.0, MIN_LANE_SEPARATION)
        self.assertTrue(strands_overlap([a, b]))

    def test_screenshot_style_terminal_z_is_detected(self) -> None:
        z = [
            (280.0, 130.0),
            (310.0, 130.0),
            (310.0, 118.0),
            (298.0, 118.0),
            (298.0, 100.0),
        ]
        self.assertGreaterEqual(count_z_jogs(z), 1)
        self.assertTrue(any("Z jog" in x for x in assess_bundle([z])))

    def test_long_boca_to_element_diagonal_detected(self) -> None:
        # Live Lampara bug: diagonal from mouth straight to the luminaire pin.
        long_diag = [(200.0, 40.0), (340.0, 160.0)]
        self.assertGreater(max_diagonal_length(long_diag), TERMINAL_DIAG_MAX)
        self.assertGreaterEqual(count_long_diagonals(long_diag), 1)
        issues = assess_bundle([long_diag])
        self.assertTrue(any("long diagonal" in x for x in issues), msg=issues)

    def test_short_terminal_diagonal_forbidden_without_v(self) -> None:
        # Single-cable terminals must stay Manhattan (no short diagonal).
        short = [(100.0, 100.0), (100.0, 94.0), (112.0, 88.0)]
        self.assertLessEqual(max_diagonal_length(short), TERMINAL_DIAG_MAX)
        self.assertEqual(count_long_diagonals(short), 0)
        issues = assess_bundle([short])
        self.assertTrue(
            any("diagonal" in x for x in issues),
            msg=issues,
        )

    def test_short_v_diagonal_allowed_with_flag(self) -> None:
        short = [(100.0, 100.0), (100.0, 94.0), (112.0, 88.0)]
        self.assertEqual(
            assess_bundle([short], allow_terminal_v=True),
            [],
        )

    def test_clean_l_has_no_z(self) -> None:
        clean = [(0.0, 0.0), (0.0, 50.0), (80.0, 50.0)]
        self.assertEqual(count_z_jogs(clean), 0)
        self.assertEqual(assess_bundle([clean]), [])

    def test_short_c_hook_detected(self) -> None:
        c = [(10.0, 20.0), (10.0, 8.0), (10.0, 20.0), (40.0, 20.0)]
        self.assertGreaterEqual(count_c_jogs(c), 1)
        self.assertTrue(any("C jog" in x for x in assess_bundle([c])))

    def test_lane_pitch_matches_ui_constants(self) -> None:
        self.assertEqual(LANE_PITCH, 5.0)
        bundle = parallel_highway_bundle([(0.0, 0.0), (100.0, 0.0)], 2)
        self.assertAlmostEqual(
            abs(bundle[1][0][1] - bundle[0][0][1]), LANE_PITCH, places=5
        )


class TestBothInvariantsTogether(unittest.TestCase):
    def test_long_diag_bundle_rejected(self) -> None:
        bad = _lampara_like_bundle(mode="long_diag")
        issues = assess_bundle(bad)
        self.assertTrue(
            any("long diagonal" in x for x in issues),
            msg=f"expected long diagonal, got {issues}",
        )

    def test_manhattan_terminal_rejoin_is_rejected(self) -> None:
        bad = _lampara_like_bundle(mode="manhattan_z")
        issues = assess_bundle(bad)
        self.assertTrue(
            any("Z jog" in x for x in issues),
            msg=f"expected Z on Manhattan terminal rejoin, got {issues}",
        )

    def test_short_diag_on_single_pins_rejected(self) -> None:
        bad = _lampara_like_bundle(mode="short_diag")
        issues = assess_bundle(bad)
        self.assertTrue(
            any("diagonal" in x for x in issues),
            msg=f"expected diagonal on single-cable pins, got {issues}",
        )

    def test_manhattan_single_cable_bundle_ok(self) -> None:
        good = _lampara_like_bundle(mode="manhattan")
        for poly in good:
            self.assertEqual(count_long_diagonals(poly), 0, msg=poly)
            self.assertEqual(
                assess_bundle([poly]),
                [],
                msg=poly,
            )
        # Parallel highway spine (before pin leads) stays separated.
        highway = [poly[:3] for poly in good]
        self.assertFalse(strands_overlap(highway))
        self.assertEqual(assess_bundle(highway), [])

    def test_multi_cable_terminal_v_ok(self) -> None:
        good = _lampara_like_bundle(mode="multi_v")
        pin = (320.0, 100.0)
        issues = assess_bundle(
            good,
            allow_terminal_v=True,
            allow_crossings=True,
            shared_terminals=[(pin, "N", good)],
        )
        self.assertFalse(
            any("perpendicular" in x for x in issues), msg=issues
        )
        self.assertFalse(any("long diagonal" in x for x in issues), msg=issues)

    def test_separated_but_with_z_still_rejected(self) -> None:
        center = [(0.0, 0.0), (0.0, 60.0), (100.0, 60.0)]
        bundle = parallel_highway_bundle(center, 2)
        s0 = list(bundle[0])
        x, y = s0[-1]
        s0.extend([(x + 10, y), (x + 10, y + 8), (x + 30, y + 8)])
        issues = assess_bundle([s0, bundle[1]])
        self.assertTrue(any("Z jog" in x for x in issues), msg=issues)

    def test_offset_of_pin_inbox_l_creates_detectable_z_when_manhattan_rejoined(
        self,
    ) -> None:
        pin = (320.0, 100.0)
        center_tail = [pin, (320.0, 90.0), (200.0, 90.0), (200.0, 40.0)]
        off = offset_ortho(center_tail, LANE_PITCH)
        bad_lead = _manhattan_pin_join(pin, off[0])
        strand = bad_lead + off[1:]
        self.assertGreaterEqual(count_z_jogs(strand), 1)


class TestElementBorderAndVEntry(unittest.TestCase):
    def test_segment_on_regleta_top_edge_is_hug(self) -> None:
        # Live bug: offset spine starts on the N face → horizontal on the border.
        rect = (100.0, 100.0, 80.0, 40.0)  # Regleta-like
        pin = (140.0, 100.0)
        along_edge = [
            (110.0, 100.0),
            (170.0, 100.0),
            (170.0, 60.0),
        ]
        self.assertTrue(
            polyline_hugs_rect_border(along_edge, rect, ignore_near=[pin])
        )
        issues = assess_bundle(
            [along_edge],
            element_rects=[rect],
        )
        self.assertTrue(any("hugs element" in x for x in issues), msg=issues)

    def test_lifted_spine_above_face_is_not_hug(self) -> None:
        rect = (100.0, 100.0, 80.0, 40.0)
        pin = (140.0, 100.0)
        clear = [
            (140.0, 100.0),
            (140.0, 92.0),
            (170.0, 92.0),
            (170.0, 60.0),
        ]
        self.assertFalse(
            polyline_hugs_rect_border(clear, rect, ignore_near=[pin])
        )
        self.assertEqual(
            assess_bundle([clear], element_rects=[rect], shared_terminals=[(pin, "N", [clear])]),
            [],
        )

    def test_perpendicular_stack_on_shared_terminal_detected(self) -> None:
        # Two strands on Luminaire.N1: stub then axis-aligned (no V).
        pin = (320.0, 160.0)
        face = "N"
        a = [(320.0, 160.0), (320.0, 154.0), (320.0, 130.0)]
        b = [(320.0, 160.0), (320.0, 154.0), (320.0, 120.0)]
        approaches = [(320.0, 154.0), (320.0, 154.0)]
        self.assertTrue(
            perpendicular_shared_terminal_entry(pin, face, approaches)
        )
        self.assertFalse(shared_terminal_entry_is_v(pin, face, approaches))
        issues = assess_bundle(
            [a, b],
            allow_crossings=True,
            shared_terminals=[(pin, face, [a, b])],
        )
        self.assertTrue(
            any("perpendicular entry" in x for x in issues), msg=issues
        )

    def test_v_fan_on_shared_terminal_ok(self) -> None:
        pin = (320.0, 160.0)
        face = "N"
        a = [(320.0, 160.0), (320.0, 154.0), (312.0, 140.0), (312.0, 100.0)]
        b = [(320.0, 160.0), (320.0, 154.0), (328.0, 140.0), (328.0, 100.0)]
        approaches = [(312.0, 140.0), (328.0, 140.0)]
        self.assertTrue(shared_terminal_entry_is_v(pin, face, approaches))
        self.assertFalse(
            perpendicular_shared_terminal_entry(pin, face, approaches)
        )
        issues = assess_bundle(
            [a, b],
            allow_z=True,
            allow_terminal_v=True,
            allow_crossings=True,
            shared_terminals=[(pin, face, [a, b])],
        )
        self.assertFalse(
            any("perpendicular" in x for x in issues), msg=issues
        )

    def test_opening_forbids_diagonals(self) -> None:
        from housewire.ui.route_quality import (
            count_diagonals_near_point,
            ensure_manhattan_near_point,
            manhattan_join_end,
            opening_approach_is_manhattan,
        )

        mouth = (200.0, 40.0)
        # Diagonal into the opening (forbidden: one cable, Manhattan only).
        bad = [(200.0, 40.0), (220.0, 60.0), (220.0, 100.0)]
        self.assertGreaterEqual(count_diagonals_near_point(bad, mouth), 1)
        self.assertFalse(opening_approach_is_manhattan(bad, mouth))
        issues = assess_bundle([bad], openings=[mouth], allow_terminal_v=True)
        self.assertTrue(
            any("opening" in x for x in issues), msg=issues
        )
        # Manhattan stub out of the mouth (no Z).
        good = [(200.0, 40.0), (200.0, 80.0), (240.0, 80.0)]
        self.assertTrue(opening_approach_is_manhattan(good, mouth))
        self.assertEqual(
            assess_bundle([good], openings=[mouth]),
            [],
        )

    def test_screenshot_opening_funnel_snap_is_detected_and_fixed(self) -> None:
        """Live Cuadro bug: horizontal then diagonal snap into the S opening."""
        from housewire.ui.route_quality import (
            count_diagonals_near_point,
            ensure_manhattan_near_point,
            manhattan_join_end,
            opening_approach_is_manhattan,
            strands_meet_at_opening,
        )

        mouth = (200.0, 200.0)
        # Brown/green style: corridor then forced snap to mouth (= diagonal).
        brown_snap = [
            (120.0, 120.0),
            (120.0, 160.0),
            (160.0, 160.0),
            mouth,  # diagonal from (160,160) → (200,200)
        ]
        green_snap = [
            (280.0, 120.0),
            (280.0, 160.0),
            (240.0, 160.0),
            mouth,
        ]
        self.assertGreaterEqual(
            count_diagonals_near_point(brown_snap, mouth), 1
        )
        self.assertGreaterEqual(
            count_diagonals_near_point(green_snap, mouth), 1
        )
        issues = assess_bundle(
            [brown_snap, green_snap],
            openings=[mouth],
            allow_crossings=True,
            min_separation=0.5,
        )
        self.assertTrue(any("opening" in x for x in issues), msg=issues)

        # Fix path: parallel lane crossings (rule 13) + Manhattan join.
        brown_cross = (195.0, 200.0)
        green_cross = (205.0, 200.0)
        brown_fix = manhattan_join_end(
            brown_snap[:-1], brown_cross, face="S"
        )
        green_fix = manhattan_join_end(
            green_snap[:-1], green_cross, face="S"
        )
        self.assertTrue(opening_approach_is_manhattan(brown_fix, brown_cross))
        self.assertTrue(opening_approach_is_manhattan(green_fix, green_cross))
        self.assertEqual(
            count_diagonals_near_point(brown_fix, brown_cross), 0
        )
        self.assertEqual(
            count_diagonals_near_point(green_fix, green_cross), 0
        )
        self.assertFalse(
            strands_meet_at_opening(
                [brown_fix, green_fix], mouth, min_separation=MIN_LANE_SEPARATION
            )
        )
        self.assertEqual(
            assess_bundle(
                [brown_fix, green_fix],
                openings=[mouth],
                min_separation=MIN_LANE_SEPARATION,
                allow_crossings=True,
            ),
            [],
        )

        # Safety net: rewrite an already-snapped diagonal near the mouth.
        rewritten = ensure_manhattan_near_point(brown_snap, mouth)
        self.assertEqual(count_diagonals_near_point(rewritten, mouth), 0)

    def test_screenshot_jagged_terminal_diags_detected_and_clean_v_ok(self) -> None:
        """Live Regleta bug: multi-diagonal / spike at the pin instead of one V."""
        from housewire.ui.route_quality import (
            terminal_lead_issues,
            terminal_v_lead,
        )

        pin = (340.0, 160.0)
        face = "N"
        lane = (340.0, 100.0)
        # Screenshot-style jagged green: diagonal, spike out, diagonal back.
        jagged = [
            pin,
            (340.0, 154.0),
            (348.0, 140.0),  # first diag
            (360.0, 110.0),  # spike + second diag
            (340.0, 120.0),  # back
            lane,
        ]
        issues = terminal_lead_issues(jagged, pin, multi_cable=True)
        self.assertTrue(
            any("diagonal" in x or "spike" in x or "perpendicular" in x for x in issues),
            msg=issues,
        )

        clean = terminal_v_lead(pin, face, lane, slot=1, slot_count=2)
        self.assertEqual(terminal_lead_issues(clean, pin, multi_cable=True), [])
        # Sibling slot fans the other way — still one diagonal each.
        clean0 = terminal_v_lead(pin, face, lane, slot=0, slot_count=2)
        self.assertEqual(terminal_lead_issues(clean0, pin, multi_cable=True), [])
        from housewire.ui.route_quality import shared_terminal_entry_is_v

        a0 = approach_point_before_pin(clean0, pin)
        a1 = approach_point_before_pin(clean, pin)
        assert a0 is not None and a1 is not None
        self.assertTrue(shared_terminal_entry_is_v(pin, face, [a0, a1]))

    def test_screenshot_v_must_touch_pin_not_next_segment(self) -> None:
        """Diagonals in the next segment + 90° into the pin (live Regleta)."""
        from housewire.ui.route_quality import (
            count_diagonals_away_from_pin,
            count_out_and_back,
            terminal_entry_is_perpendicular,
            terminal_lead_issues,
            terminal_v_lead,
        )

        pin = (200.0, 160.0)
        face = "N"
        # Bad: vertical into pin (90°), diagonal far above (tramo siguiente).
        bad = [
            pin,
            (200.0, 140.0),  # perpendicular stub
            (200.0, 120.0),
            (160.0, 80.0),  # diagonal away from pin
            (120.0, 80.0),
        ]
        self.assertTrue(terminal_entry_is_perpendicular(bad, pin))
        self.assertGreaterEqual(count_diagonals_away_from_pin(bad, pin), 1)
        issues = terminal_lead_issues(bad, pin, multi_cable=True)
        self.assertTrue(any("perpendicular" in x for x in issues), msg=issues)
        self.assertTrue(any("away from pin" in x for x in issues), msg=issues)

        # Out-and-back on the same vertical (ida y vuelta).
        back = [
            (200.0, 40.0),
            (200.0, 100.0),
            (200.0, 60.0),  # reverses toward start
            (240.0, 60.0),
        ]
        self.assertGreaterEqual(count_out_and_back(back), 1)
        issues_b = terminal_lead_issues(
            [pin, (200.0, 148.0), (200.0, 100.0), (200.0, 130.0), (240.0, 130.0)],
            pin,
            multi_cable=False,
        )
        self.assertTrue(any("out-and-back" in x for x in issues_b), msg=issues_b)

        good = terminal_v_lead(pin, face, (200.0, 80.0), slot=0, slot_count=2)
        self.assertFalse(terminal_entry_is_perpendicular(good, pin))
        self.assertEqual(count_diagonals_away_from_pin(good, pin), 0)
        self.assertEqual(terminal_lead_issues(good, pin, multi_cable=True), [])

    def test_outline_extra_is_thin(self) -> None:
        # Rim must stay a hairline beyond the tube (was roadW+2.5).
        self.assertLessEqual(OUTLINE_EXTRA, 1.25)
        self.assertGreater(OUTLINE_EXTRA, 0.0)

    def test_screenshot_style_inbox_crossings_flagged(self) -> None:
        # Two inbox corridors that properly cross (X) inside the box.
        a = [(100.0, 140.0), (100.0, 80.0), (200.0, 80.0), (200.0, 40.0)]
        b = [(160.0, 140.0), (160.0, 100.0), (80.0, 100.0), (80.0, 40.0)]
        # Force a clear mid-run X: horizontal vs vertical.
        c = [(50.0, 90.0), (250.0, 90.0)]
        d = [(150.0, 40.0), (150.0, 140.0)]
        issues = assess_bundle([c, d])
        self.assertTrue(any("cross" in x for x in issues), msg=issues)
        issues_ab = assess_bundle([a, b], min_separation=0.5)
        self.assertTrue(
            any("cross" in x for x in issues_ab) or any("overlap" in x for x in issues_ab),
            msg=issues_ab,
        )


class TestConductorPaletteContrast(unittest.TestCase):
    def test_wh_is_true_white(self) -> None:
        self.assertEqual(css_for_color("WH"), "#ffffff")
        self.assertEqual(CONDUCTOR_COLORS["WH"]["css"], "#ffffff")

    def test_bk_is_true_black(self) -> None:
        self.assertEqual(css_for_color("BK"), "#1a1a1a")
        self.assertEqual(CONDUCTOR_COLORS["BK"]["css"], "#1a1a1a")

    def test_black_conduit_gets_white_outline(self) -> None:
        from housewire.ui.route_quality import contrast_outline_css

        self.assertEqual(contrast_outline_css("#1a1a1a"), "#ffffff")
        self.assertEqual(contrast_outline_css(css_for_color("BK")), "#ffffff")

    def test_white_fill_gets_dark_outline(self) -> None:
        from housewire.ui.route_quality import contrast_outline_css

        self.assertEqual(contrast_outline_css("#ffffff"), "#0d1117")

    def test_same_color_nesting_needs_contrast_rim(self) -> None:
        """BK jacket in BK conduit (or WH in WH) must get the thin rim."""
        from housewire.ui.route_quality import needs_nested_contrast_rim

        bk = css_for_color("BK")
        wh = css_for_color("WH")
        bu = css_for_color("BU")
        self.assertTrue(
            needs_nested_contrast_rim(bk, bk, inner_code="BK", outer_code="BK")
        )
        self.assertTrue(
            needs_nested_contrast_rim(wh, wh, inner_code="WH", outer_code="WH")
        )
        # Distinct colors with clear luminance gap → no rim required.
        self.assertFalse(
            needs_nested_contrast_rim(bu, bk, inner_code="BU", outer_code="BK")
        )
        self.assertFalse(
            needs_nested_contrast_rim(bk, wh, inner_code="BK", outer_code="WH")
        )
        # Black tube vs light canvas → no rim; vs dark canvas → rim.
        self.assertFalse(needs_nested_contrast_rim(bk, "#f6f8fa"))
        self.assertTrue(needs_nested_contrast_rim(bk, "#1a1d21"))

    def test_similar_luminance_nesting_needs_rim_without_matching_codes(
        self,
    ) -> None:
        from housewire.ui.route_quality import needs_nested_contrast_rim

        # Two dark greys without IEC codes still need a rim.
        self.assertTrue(needs_nested_contrast_rim("#1a1a1a", "#222222"))
        self.assertFalse(needs_nested_contrast_rim("#1a1a1a", "#ffffff"))

    def test_jacket_spans_contiguous_cable_lanes_not_centerline(self) -> None:
        """WH sheath around BK+BU must sit on their lane mid, not tube center.

        Highway of 3 strands: GNYE @0, BK @1, BU @2 → jacket mid ≠ 0.
        """
        from housewire.ui.route_quality import (
            cable_lanes_are_contiguous,
            highway_lane_offset,
            jacket_mid_offset,
        )

        self.assertTrue(cable_lanes_are_contiguous([1, 2]))
        self.assertFalse(cable_lanes_are_contiguous([0, 2]))
        mid = jacket_mid_offset(1, 2, 3)
        self.assertNotAlmostEqual(mid, 0.0, places=5)
        self.assertAlmostEqual(
            mid,
            (highway_lane_offset(1, 3) + highway_lane_offset(2, 3)) / 2,
            places=5,
        )


class TestCrossingsAndJacketGaps(unittest.TestCase):
    def test_crossing_lanes_at_corner_detected(self) -> None:
        # Proper X crossing of two ortho polylines.
        a = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0)]
        b = [(50.0, -10.0), (50.0, 50.0), (150.0, 50.0)]
        parallel_ok = [(0.0, 0.0), (0.0, 50.0), (80.0, 50.0)]
        parallel_ok2 = [(5.0, 0.0), (5.0, 45.0), (80.0, 45.0)]
        from housewire.ui.route_quality import count_strand_crossings

        self.assertEqual(count_strand_crossings([parallel_ok, parallel_ok2]), 0)
        self.assertGreaterEqual(count_strand_crossings([a, b]), 1)
        issues = assess_bundle([a, b])
        self.assertTrue(any("cross" in x for x in issues), msg=issues)

    def test_parallel_bundle_has_no_crossings(self) -> None:
        from housewire.ui.route_quality import count_strand_crossings

        center = [(0.0, 0.0), (0.0, 80.0), (120.0, 80.0)]
        bundle = parallel_highway_bundle(center, 3)
        self.assertEqual(count_strand_crossings(bundle), 0)
        self.assertEqual(assess_bundle(bundle), [])

    def test_gapped_jacket_pieces_detected(self) -> None:
        from housewire.ui.route_quality import jacket_path_is_gapped

        continuous = [
            [(0.0, 0.0), (50.0, 0.0)],
            [(50.0, 0.0), (100.0, 0.0)],
        ]
        gapped = [
            [(0.0, 0.0), (40.0, 0.0)],
            [(80.0, 0.0), (120.0, 0.0)],
        ]
        self.assertFalse(jacket_path_is_gapped(continuous))
        self.assertTrue(jacket_path_is_gapped(gapped))


class TestConduitColorFromYaml(unittest.TestCase):
    def test_test01_conduit_colors_reach_graph(self) -> None:
        from pathlib import Path

        from housewire.ui.physical_graph import build_physical_graph

        root = Path(__file__).resolve().parents[1] / "sites" / "Tests"
        if not root.is_dir() or not any(root.glob("*.yaml")):
            self.skipTest("sites/Tests fixture not present")
        graph = build_physical_graph(root, "Habitacion")
        by_id = {e["id"]: e for e in graph.get("edges") or []}
        self.assertIn("Conducto_lampara", by_id)
        self.assertEqual(by_id["Conducto_lampara"].get("color"), "BK")
        self.assertIn("Conducto_interruptor", by_id)
        self.assertEqual(by_id["Conducto_interruptor"].get("color"), "BK")


class TestElbowAndOpeningLaneBundle(unittest.TestCase):
    """Cable-in-cable elbow + opening: lanes must keep shape (no peel/squash)."""

    # pin → mouth (start), exterior L elbow, mouth → pin (end as pin→mouth).
    START_TAIL = [(-60.0, -40.0), (0.0, -40.0), (0.0, 0.0)]
    EXTERIOR = [(0.0, 0.0), (100.0, 0.0), (100.0, 80.0)]
    END_TAIL = [(160.0, 80.0), (100.0, 80.0)]  # pin → mouth at end

    def test_continuous_offset_keeps_elbow_separation(self) -> None:
        from housewire.ui.route_quality import (
            count_strand_crossings,
            hop_lanes_continuous,
            min_polyline_separation,
        )

        bundle = hop_lanes_continuous(
            self.START_TAIL, self.EXTERIOR, self.END_TAIL, 2
        )
        self.assertGreaterEqual(
            min_polyline_separation(bundle[0], bundle[1]), MIN_LANE_SEPARATION
        )
        self.assertFalse(strands_overlap(bundle))
        self.assertEqual(count_strand_crossings(bundle), 0)
        self.assertEqual(assess_bundle(bundle), [])

    def test_flipped_inbox_offset_overlaps_at_opening(self) -> None:
        """Live bug: -laneDist on pin→mouth + +laneDist on exterior."""
        from housewire.ui.route_quality import (
            count_strand_crossings,
            hop_lanes_flipped_inbox,
            min_polyline_separation,
        )

        bad = hop_lanes_flipped_inbox(
            self.START_TAIL, self.EXTERIOR, self.END_TAIL, 2
        )
        self.assertLess(
            min_polyline_separation(bad[0], bad[1]), MIN_LANE_SEPARATION
        )
        self.assertTrue(strands_overlap(bad))
        self.assertGreaterEqual(count_strand_crossings(bad), 1)
        issues = assess_bundle(bad)
        self.assertTrue(
            any("overlap" in x or "cross" in x for x in issues), msg=issues
        )

    def test_three_strand_elbow_bundle_stays_parallel(self) -> None:
        from housewire.ui.route_quality import (
            count_strand_crossings,
            hop_lanes_continuous,
        )

        # Nested conduit look: GNYE + BK + BU through an L.
        bundle = hop_lanes_continuous(
            self.START_TAIL, self.EXTERIOR, self.END_TAIL, 3
        )
        self.assertFalse(strands_overlap(bundle))
        self.assertEqual(count_strand_crossings(bundle), 0)
        self.assertEqual(assess_bundle(bundle), [])


class TestOutAndBackAndMultiCableV(unittest.TestCase):
    def test_screenshot_ida_y_vuelta_above_regleta_detected(self) -> None:
        """Down → right → U-turn left → down (same horizontal twice)."""
        from housewire.ui.route_quality import count_out_and_back, terminal_lead_issues

        pin = (200.0, 160.0)
        path = [
            pin,
            (200.0, 140.0),
            (240.0, 140.0),
            (180.0, 140.0),  # reverses on same y
            (180.0, 100.0),
        ]
        self.assertGreaterEqual(count_out_and_back(path), 1)
        issues = terminal_lead_issues(path, pin, multi_cable=True)
        self.assertTrue(any("out-and-back" in x for x in issues), msg=issues)

    def test_stacked_inbox_corridors_flag_overlap(self) -> None:
        """Two colored wires painted on the same inbox run (screenshot)."""
        blue = [
            (200.0, 40.0),
            (200.0, 100.0),
            (260.0, 100.0),
            (260.0, 140.0),
            (220.0, 160.0),
        ]
        gnye = [
            (200.0, 40.0),
            (200.0, 100.0),
            (260.0, 100.0),
            (260.0, 140.0),
            (240.0, 160.0),
        ]
        self.assertTrue(strands_overlap([blue, gnye]))
        issues = assess_bundle(
            [blue, gnye],
            allow_terminal_v=True,
            allow_crossings=True,
            min_separation=MIN_LANE_SEPARATION,
        )
        self.assertTrue(any("overlap" in x for x in issues), msg=issues)

    def test_continuous_hop_with_v_leads_ok_for_shared_terminals(self) -> None:
        from housewire.ui.route_quality import (
            attach_v_leads,
            hop_lanes_continuous,
            terminal_lead_issues,
        )

        start_tail = [(320.0, 160.0), (320.0, 120.0), (200.0, 120.0), (200.0, 40.0)]
        exterior = [(200.0, 40.0), (80.0, 40.0), (80.0, 0.0)]
        end_tail = [(80.0, -80.0), (80.0, 0.0)]
        spines = hop_lanes_continuous(start_tail, exterior, end_tail, 2)
        self.assertFalse(strands_overlap(spines))
        pin_s = (320.0, 160.0)
        pin_e = (80.0, -80.0)
        for i, spine in enumerate(spines):
            strand = attach_v_leads(
                spine,
                pin_s,
                "N",
                i,
                pin_e,
                "S",
                i,
                slot_count=2,
            )
            near_s = strand[: min(6, len(strand))]
            near_e = list(reversed(strand))[: min(6, len(strand))]
            self.assertEqual(
                terminal_lead_issues(near_s, pin_s, multi_cable=True), []
            )
            self.assertEqual(
                terminal_lead_issues(near_e, pin_e, multi_cable=True), []
            )


class TestSymmetricVAndNoPrematureMerge(unittest.TestCase):
    """Regleta N2: both blacks diagonal V; meet only at the pin."""

    def test_asymmetric_v_one_diagonal_one_straight_detected(self) -> None:
        from housewire.ui.route_quality import (
            shared_terminal_both_arms_diagonal,
        )

        pin = (200.0, 160.0)
        # Live bug: left arm diagonal, right arm vertical into the pin.
        left = [
            pin,
            (188.0, 146.0),
            (188.0, 120.0),
            (120.0, 120.0),
        ]
        right = [
            pin,
            (200.0, 140.0),  # straight up — missing the other V arm
            (200.0, 100.0),
            (260.0, 100.0),
        ]
        self.assertFalse(shared_terminal_both_arms_diagonal([left, right], pin))
        issues = assess_bundle(
            [left, right],
            allow_terminal_v=True,
            allow_crossings=True,
            shared_terminals=[(pin, "N", [left, right])],
            min_separation=0.5,
        )
        self.assertTrue(
            any("asymmetric" in x or "perpendicular" in x for x in issues),
            msg=issues,
        )

    def test_premature_merge_before_pin_detected(self) -> None:
        from housewire.ui.route_quality import strands_merge_before_pin

        pin = (200.0, 160.0)
        # Two blues stacked on the same vertical, only split at the pin.
        a = [pin, (200.0, 140.0), (200.0, 100.0), (160.0, 100.0)]
        b = [pin, (200.0, 140.0), (200.0, 100.0), (240.0, 100.0)]
        self.assertTrue(strands_merge_before_pin([a, b], pin))
        issues = assess_bundle(
            [a, b],
            allow_terminal_v=True,
            allow_crossings=True,
            shared_terminals=[(pin, "N", [a, b])],
        )
        self.assertTrue(any("merge before" in x for x in issues), msg=issues)

    def test_symmetric_v_leads_do_not_merge_before_pin(self) -> None:
        from housewire.ui.route_quality import (
            shared_terminal_both_arms_diagonal,
            strands_merge_before_pin,
            terminal_v_lead,
        )

        pin = (200.0, 160.0)
        face = "N"
        lane_l = (180.0, 100.0)
        lane_r = (220.0, 100.0)
        a = terminal_v_lead(pin, face, lane_l, slot=0, slot_count=2)
        b = terminal_v_lead(pin, face, lane_r, slot=1, slot_count=2)
        self.assertTrue(shared_terminal_both_arms_diagonal([a, b], pin))
        self.assertFalse(strands_merge_before_pin([a, b], pin))
        issues = assess_bundle(
            [a, b],
            allow_terminal_v=True,
            allow_crossings=True,
            allow_z=True,
            shared_terminals=[(pin, face, [a, b])],
        )
        self.assertFalse(
            any("asymmetric" in x or "merge before" in x for x in issues),
            msg=issues,
        )

    def test_strip_short_z_preserves_terminal_v_diagonal(self) -> None:
        """Old stripShortZJogs treated pin→tip→L as a Z and collapsed the V."""
        from housewire.ui.route_quality import (
            is_diagonal_segment,
            strip_short_z_jogs,
            terminal_entry_is_perpendicular,
        )

        pin = (200.0, 160.0)
        tip = (188.0, 146.0)
        # Path shaped like the live merge after tip: diag then short ortho L.
        path = [
            pin,
            tip,
            (200.0, 146.0),
            (200.0, 100.0),
            (120.0, 100.0),
        ]
        stripped = strip_short_z_jogs(path)
        self.assertTrue(is_diagonal_segment(stripped[0], stripped[1]))
        self.assertFalse(terminal_entry_is_perpendicular(stripped, pin))


class TestMouthExitAndTubeEnvelope(unittest.TestCase):
    """Hard invariants: inside tube, through mouth, no mid-run overlap, no box hug."""

    START_MOUTH = (100.0, 200.0)
    END_MOUTH = (300.0, 80.0)
    EXTERIOR = [(100.0, 200.0), (300.0, 200.0), (300.0, 80.0)]
    PIN_S = (100.0, 260.0)
    PINS_E = [(320.0, 100.0), (340.0, 100.0), (360.0, 100.0)]
    INWARD_S = (0.0, 1.0)
    INWARD_E = (0.0, 1.0)

    def _good_lanes(self, n: int = 3):
        from housewire.ui.route_quality import build_hop_lane, highway_lane_offset

        return [
            build_hop_lane(
                self.PIN_S,
                self.START_MOUTH,
                self.EXTERIOR,
                self.END_MOUTH,
                self.PINS_E[i],
                highway_lane_offset(i, n),
                self.INWARD_S,
                self.INWARD_E,
            )
            for i in range(n)
        ]

    def _tube_only_lanes(self, n: int = 3):
        from housewire.ui.route_quality import (
            highway_lane_offset,
            offset_ortho,
        )

        out = []
        for i in range(n):
            d = highway_lane_offset(i, n)
            tube = (
                offset_ortho(self.EXTERIOR, d)
                if abs(d) > 1e-9
                else [(float(p[0]), float(p[1])) for p in self.EXTERIOR]
            )
            out.append(tube)
        return out

    def test_raw_continuous_offset_exits_before_mouth(self) -> None:
        from housewire.ui.route_quality import (
            parallel_highway_bundle,
            strand_exits_before_mouth,
        )

        center = [
            (100.0, 40.0),
            (100.0, 200.0),
            (180.0, 200.0),
            (180.0, 220.0),
        ]
        mouth = (100.0, 200.0)
        raw = parallel_highway_bundle(center, 3)
        self.assertTrue(strand_exits_before_mouth(raw[0], mouth))
        self.assertTrue(strand_exits_before_mouth(raw[2], mouth))

    def test_force_through_mouth_anti_pattern_collapses_lanes(self) -> None:
        """0.34.20 anti-pattern: offset whole centerline then forceThroughMouth."""
        from housewire.ui.route_quality import hop_lanes_through_mouths

        center = [
            (100.0, 230.0),
            (100.0, 200.0),
            (300.0, 200.0),
            (300.0, 80.0),
            (340.0, 80.0),
        ]
        broken = hop_lanes_through_mouths(
            center, [self.START_MOUTH, self.END_MOUTH], 3
        )
        self.assertTrue(
            strands_overlap(
                broken,
                min_separation=MIN_LANE_SEPARATION,
                ignore_near=[self.START_MOUTH, self.END_MOUTH],
            ),
            msg="forceThroughMouth on a continuous offset must not be treated as OK",
        )

    def test_build_hop_lane_tube_stays_inside_conduit(self) -> None:
        from housewire.ui.route_quality import (
            clip_poly_between_points,
            highway_road_width,
            strand_outside_tube,
        )

        half = highway_road_width(3) / 2.0
        for lane in self._good_lanes(3):
            tube = clip_poly_between_points(
                lane, [self.START_MOUTH, self.END_MOUTH]
            )
            self.assertGreaterEqual(len(tube), 2, msg=lane)
            self.assertFalse(
                strand_outside_tube(tube, self.EXTERIOR, half_width=half),
                msg=tube,
            )

    def test_tube_only_lanes_stay_separated(self) -> None:
        """Parallel tube lanes (the hop exterior) must not stack mid-run."""
        lanes = self._tube_only_lanes(3)
        self.assertFalse(
            strands_overlap(
                lanes,
                min_separation=MIN_LANE_SEPARATION,
            ),
            msg=lanes,
        )

    def test_build_hop_lane_passes_near_both_mouths(self) -> None:
        from housewire.ui.route_quality import highway_road_width

        half = highway_road_width(3) / 2.0
        for lane in self._good_lanes(3):
            for mouth in (self.START_MOUTH, self.END_MOUTH):
                d = min(
                    ((p[0] - mouth[0]) ** 2 + (p[1] - mouth[1]) ** 2) ** 0.5
                    for p in lane
                )
                self.assertLessEqual(d, half + 0.5, msg=(mouth, lane, d))

    def test_multi_cable_opening_lanes_do_not_meet_at_mouth(self) -> None:
        """Rule 13: parallel openings never collapse onto the center boca."""
        from housewire.ui.route_quality import strands_meet_at_opening

        lanes = self._good_lanes(3)
        for mouth in (self.START_MOUTH, self.END_MOUTH):
            self.assertFalse(
                strands_meet_at_opening(lanes, mouth),
                msg=(mouth, lanes),
            )
        issues = assess_bundle(
            lanes,
            openings=[self.START_MOUTH, self.END_MOUTH],
            min_separation=MIN_LANE_SEPARATION,
            allow_crossings=True,
            allow_z=True,
            allow_c=True,
        )
        self.assertFalse(
            any("meet at mouth" in x for x in issues),
            msg=issues,
        )

    def test_build_hop_lane_no_early_mouth_exit(self) -> None:
        from housewire.ui.route_quality import (
            highway_road_width,
            strand_exits_before_mouth,
        )

        half = highway_road_width(3) / 2.0
        for lane in self._good_lanes(3):
            for mouth in (self.START_MOUTH, self.END_MOUTH):
                self.assertFalse(
                    strand_exits_before_mouth(
                        lane,
                        mouth,
                        tube_centerline=self.EXTERIOR,
                        tube_half_width=half,
                    ),
                    msg=(mouth, lane),
                )

    def test_converge_keeps_offset_arrival_near_mouth(self) -> None:
        """Pop threshold must not erase the offset lane at mouth latitude."""
        from housewire.ui.route_quality import converge_lane_to_mouth

        mouth = (1147.0, 459.5)
        # Offset lane arrives 5px beside the mouth (typical laneDist).
        lane = [(1147.0, 308.0), (1152.0, 308.0), (1152.0, 459.5)]
        out = converge_lane_to_mouth(lane, mouth, at_start=False)
        self.assertTrue(
            any(abs(p[1] - 459.5) < 0.5 and abs(p[0] - 1152.0) < 0.5 for p in out),
            msg=out,
        )
        self.assertLessEqual(
            min(((p[0] - mouth[0]) ** 2 + (p[1] - mouth[1]) ** 2) ** 0.5 for p in out),
            1.5,
            msg=out,
        )

    def test_assess_bundle_flags_outside_tube_and_early_exit(self) -> None:
        from housewire.ui.route_quality import highway_road_width

        exterior = [(0.0, 0.0), (200.0, 0.0)]
        brown = [(0.0, 40.0), (200.0, 40.0)]
        mouth = (0.0, 0.0)
        early = [(5.0, -20.0), (5.0, -5.0), (80.0, -5.0), (80.0, 40.0)]
        issues = assess_bundle(
            [brown, early],
            openings=[mouth],
            tube_centerline=exterior,
            tube_half_width=highway_road_width(3) / 2.0,
            min_separation=0.5,
            allow_crossings=True,
        )
        self.assertTrue(any("outside conduit" in x for x in issues), msg=issues)
        self.assertTrue(
            any("exits before opening" in x for x in issues), msg=issues
        )

    def test_assess_bundle_flags_place_border_hug(self) -> None:
        place = (50.0, 50.0, 200.0, 150.0)
        along = [(60.0, 50.0), (180.0, 50.0), (180.0, 80.0)]
        issues = assess_bundle([along], place_rects=[place])
        self.assertTrue(any("hugs place" in x for x in issues), msg=issues)

    def test_strand_outside_tube_detected(self) -> None:
        from housewire.ui.route_quality import (
            highway_road_width,
            strand_outside_tube,
        )

        tube = [(0.0, 0.0), (100.0, 0.0), (100.0, 80.0)]
        half = highway_road_width(3) / 2.0
        brown = [(0.0, 40.0), (100.0, 40.0), (100.0, 80.0)]
        self.assertTrue(strand_outside_tube(brown, tube, half_width=half))
        inside = [(0.0, 2.0), (100.0, 2.0), (100.0, 80.0)]
        self.assertFalse(strand_outside_tube(inside, tube, half_width=half))

    def test_brown_and_gnye_overlap_detected(self) -> None:
        bn = [(120.0, 100.0), (200.0, 100.0), (200.0, 140.0)]
        gnye = [(120.0, 100.0), (200.0, 100.0), (200.0, 160.0)]
        self.assertTrue(strands_overlap([bn, gnye]))
        issues = assess_bundle([bn, gnye], min_separation=MIN_LANE_SEPARATION)
        self.assertTrue(any("overlap" in x for x in issues), msg=issues)

    def test_good_tube_lanes_pass_assess_bundle(self) -> None:
        from housewire.ui.route_quality import highway_road_width

        lanes = self._tube_only_lanes(3)
        half = highway_road_width(3) / 2.0
        issues = assess_bundle(
            lanes,
            openings=[self.START_MOUTH, self.END_MOUTH],
            tube_centerline=self.EXTERIOR,
            tube_half_width=half,
            allow_z=True,
            allow_c=True,
            allow_crossings=True,
            min_separation=MIN_LANE_SEPARATION,
        )
        self.assertFalse(
            any("outside conduit" in x for x in issues), msg=issues
        )
        self.assertFalse(
            any("exits before opening" in x for x in issues), msg=issues
        )
        self.assertFalse(any("overlap" in x for x in issues), msg=issues)


class TestBipolarVAndLiftPreservesDiagonal(unittest.TestCase):
    """Bipolar terminals must keep a V; ensureOrthoPoly must not flatten it."""

    def test_bipolar_terminal_v_leads_both_diagonal(self) -> None:
        from housewire.ui.route_quality import (
            shared_terminal_both_arms_diagonal,
            strands_merge_before_pin,
            terminal_entry_is_perpendicular,
            terminal_v_lead,
        )

        pin = (200.0, 160.0)
        face = "N"
        a = terminal_v_lead(pin, face, (160.0, 100.0), slot=0, slot_count=2)
        b = terminal_v_lead(pin, face, (240.0, 100.0), slot=1, slot_count=2)
        self.assertFalse(terminal_entry_is_perpendicular(a, pin))
        self.assertFalse(terminal_entry_is_perpendicular(b, pin))
        self.assertTrue(shared_terminal_both_arms_diagonal([a, b], pin))
        self.assertFalse(strands_merge_before_pin([a, b], pin))
        issues = assess_bundle(
            [a, b],
            allow_terminal_v=True,
            allow_crossings=True,
            allow_z=True,
            shared_terminals=[(pin, face, [a, b])],
        )
        self.assertFalse(
            any(
                "asymmetric" in x or "perpendicular" in x or "merge before" in x
                for x in issues
            ),
            msg=issues,
        )

    def test_ensure_ortho_poly_destroys_v_anti_pattern(self) -> None:
        """Always running ensureOrthoPoly on a V chain (pre-0.34.24 bug)."""
        from housewire.ui.route_quality import (
            ensure_ortho_poly,
            shared_terminal_both_arms_diagonal,
            terminal_v_lead,
        )

        pin = (200.0, 160.0)
        face = "N"
        a = terminal_v_lead(pin, face, (160.0, 100.0), slot=0, slot_count=2)
        b = terminal_v_lead(pin, face, (240.0, 100.0), slot=1, slot_count=2)
        broken = [ensure_ortho_poly(a), ensure_ortho_poly(b)]
        self.assertFalse(
            shared_terminal_both_arms_diagonal(broken, pin),
            msg=broken,
        )

    def test_lift_offset_spine_preserves_bipolar_v(self) -> None:
        from housewire.ui.route_quality import (
            lift_offset_spine_from_pin,
            shared_terminal_both_arms_diagonal,
            terminal_v_lead,
        )

        pin = (200.0, 160.0)
        face = "N"
        a = terminal_v_lead(pin, face, (160.0, 100.0), slot=0, slot_count=2)
        b = terminal_v_lead(pin, face, (240.0, 100.0), slot=1, slot_count=2)
        lifted = [
            lift_offset_spine_from_pin(a, pin, face),
            lift_offset_spine_from_pin(b, pin, face),
        ]
        self.assertTrue(
            shared_terminal_both_arms_diagonal(lifted, pin),
            msg=lifted,
        )

    def test_inbox_stacked_corridor_still_flagged(self) -> None:
        """Two strands on the same inbox L (screenshot Caja / Lampara)."""
        shared = [
            (100.0, 200.0),
            (100.0, 140.0),
            (180.0, 140.0),
            (180.0, 100.0),
        ]
        a = list(shared)
        b = list(shared)
        self.assertTrue(strands_overlap([a, b]))
        issues = assess_bundle([a, b], min_separation=MIN_LANE_SEPARATION)
        self.assertTrue(any("overlap" in x for x in issues), msg=issues)

    def test_join_to_stub_collapses_inbox_lanes(self) -> None:
        from housewire.ui.route_quality import (
            highway_lane_offset,
            min_polyline_separation,
            mouth_fan_join_anti_pattern,
            mouth_fan_join_correct,
            mouth_fan_pts,
        )

        mouth = (200.0, 200.0)
        inward = (0.0, 1.0)
        pin = (200.0, 260.0)
        dists = [highway_lane_offset(i, 3) for i in range(3)]
        bad = mouth_fan_join_anti_pattern(mouth, inward, dists, pin, "N")
        good = mouth_fan_join_correct(mouth, inward, dists, pin, "N")
        tips = [mouth_fan_pts(mouth, inward, d)[-1] for d in dists]
        for i, tip in enumerate(tips):
            self.assertTrue(
                any(
                    ((p[0] - tip[0]) ** 2 + (p[1] - tip[1]) ** 2) ** 0.5 < 1.5
                    for p in good[i]
                ),
                msg=(i, tip, good[i]),
            )
        # Anti-pattern never visits the outer fan tips — all hug the stub.
        stub = mouth_fan_pts(mouth, inward, 0.0)[-1]
        for i, tip in enumerate(tips):
            if abs(dists[i]) < 1e-9:
                continue
            self.assertFalse(
                any(
                    ((p[0] - tip[0]) ** 2 + (p[1] - tip[1]) ** 2) ** 0.5 < 1.5
                    for p in bad[i]
                ),
                msg=(i, tip, bad[i]),
            )
            self.assertTrue(
                any(
                    ((p[0] - stub[0]) ** 2 + (p[1] - stub[1]) ** 2) ** 0.5 < 1.5
                    for p in bad[i]
                ),
                msg=(i, stub, bad[i]),
            )

        def far(poly):
            out = []
            for p in poly:
                if (
                    ((p[0] - mouth[0]) ** 2 + (p[1] - mouth[1]) ** 2) ** 0.5 > 22
                    and ((p[0] - pin[0]) ** 2 + (p[1] - pin[1]) ** 2) ** 0.5 > 22
                ):
                    out.append(p)
            return out

        good_far = [far(p) for p in good]
        if all(len(p) >= 2 for p in good_far):
            sep = min(
                min_polyline_separation(good_far[i], good_far[j])
                for i in range(3)
                for j in range(i + 1, 3)
            )
            self.assertGreaterEqual(sep, MIN_LANE_SEPARATION, msg=good_far)

    def test_ensure_vertex_near_splices_missed_mouth(self) -> None:
        from housewire.ui.route_quality import ensure_vertex_near

        mouth = (200.0, 100.0)
        # Offset lane skips the mouth (continues past on a parallel).
        skipped = [(100.0, 105.0), (300.0, 105.0), (300.0, 160.0)]
        fixed = ensure_vertex_near(skipped, mouth, tol=1.5)
        d = min(
            ((p[0] - mouth[0]) ** 2 + (p[1] - mouth[1]) ** 2) ** 0.5
            for p in fixed
        )
        self.assertLessEqual(d, 1.5, msg=fixed)

    def test_shared_rail_y_trunk_detected_column_join_ok(self) -> None:
        """V rails share a Y; joining along that Y stacks every lane."""
        from housewire.ui.route_quality import (
            join_lead_to_fan_tip,
            shared_rail_y_join_anti_pattern,
            terminal_v_lead,
        )

        pin = (200.0, 160.0)
        face = "N"
        # Three bipolar-style leads into fan tips at different latitudes.
        leads = [
            terminal_v_lead(pin, face, (160.0, 100.0), 0, 3),
            terminal_v_lead(pin, face, (200.0, 100.0), 1, 3),
            terminal_v_lead(pin, face, (240.0, 100.0), 2, 3),
        ]
        tips = [(100.0, 120.0), (100.0, 100.0), (100.0, 80.0)]
        bad = shared_rail_y_join_anti_pattern(leads, tips)
        good = [join_lead_to_fan_tip(leads[i], tips[i], "N") for i in range(3)]
        rail_y = leads[0][-1][1]
        tip_xs = {float(t[0]) for t in tips}

        def horiz_at_rail_toward_tip(poly: list) -> bool:
            """True if poly travels horizontally on rail_y into the tip column."""
            for a, b in zip(poly, poly[1:]):
                if abs(a[1] - rail_y) > 0.5 or abs(b[1] - rail_y) > 0.5:
                    continue
                if abs(a[0] - b[0]) < 1.0:
                    continue
                lo, hi = sorted((a[0], b[0]))
                if any(lo - 0.5 <= tx <= hi + 0.5 for tx in tip_xs):
                    return True
            return False

        self.assertTrue(all(horiz_at_rail_toward_tip(p) for p in bad), msg=bad)
        # Face column-first: when tip.y != rail_y, do not crawl on rail_y.
        for lead, tip, poly in zip(leads, tips, good):
            if abs(float(tip[1]) - rail_y) < 0.5:
                continue
            self.assertFalse(horiz_at_rail_toward_tip(poly), msg=(tip, poly))
            rail = (float(lead[-1][0]), float(lead[-1][1]))
            self.assertIn(
                (rail[0], float(tip[1])),
                [(float(p[0]), float(p[1])) for p in poly],
                msg=poly,
            )

    def test_mouth_fan_tips_have_distinct_depths(self) -> None:
        from housewire.ui.route_quality import highway_lane_offset, mouth_fan_pts

        mouth = (200.0, 200.0)
        inward = (0.0, 1.0)
        dists = [highway_lane_offset(i, 3) for i in range(3)]
        tips = [mouth_fan_pts(mouth, inward, d)[-1] for d in dists]
        ys = {round(t[1], 3) for t in tips}
        self.assertGreaterEqual(len(ys), 2, msg=tips)


if __name__ == "__main__":
    unittest.main()
