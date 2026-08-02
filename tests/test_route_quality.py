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

        # Fix path: drop snapped mouth, Manhattan-join (arrive vertically).
        brown_fix = manhattan_join_end(
            brown_snap[:-1], mouth, face="S"
        )
        green_fix = manhattan_join_end(
            green_snap[:-1], mouth, face="S"
        )
        self.assertTrue(opening_approach_is_manhattan(brown_fix, mouth))
        self.assertTrue(opening_approach_is_manhattan(green_fix, mouth))
        self.assertEqual(
            count_diagonals_near_point(brown_fix, mouth), 0
        )
        self.assertEqual(
            count_diagonals_near_point(green_fix, mouth), 0
        )
        self.assertEqual(
            assess_bundle(
                [brown_fix],
                openings=[mouth],
            ),
            [],
        )
        self.assertEqual(
            assess_bundle(
                [green_fix],
                openings=[mouth],
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
            any("diagonal" in x or "spike" in x for x in issues),
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


if __name__ == "__main__":
    unittest.main()