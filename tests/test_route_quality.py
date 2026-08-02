"""Regression: cable routes must stay separated AND free of needless C/Z jogs.

Synthetic highway bundles alone are not enough — the live bug was a Manhattan
rejoin from an offset lane onto a terminal strip (short Z into each pin).
These tests encode that failure mode so it cannot pass unnoticed again.
"""
from __future__ import annotations

import unittest

from housewire.ui.route_quality import (
    LANE_PITCH,
    MIN_LANE_SEPARATION,
    assess_bundle,
    count_c_jogs,
    count_z_jogs,
    offset_ortho,
    parallel_highway_bundle,
    strands_overlap,
)


def _manhattan_pin_join(pin: tuple[float, float], lane: tuple[float, float]) -> list[tuple[float, float]]:
    """Old bad terminal join: HV then VH-style L (creates Z with offset lanes)."""
    # Stub "out" then L to lane — classic source of short Z near N-face pins.
    stub = (pin[0], pin[1] - 10.0)
    corner = (lane[0], stub[1])
    return [pin, stub, corner, lane]


def _diagonal_pin_join(pin: tuple[float, float], lane: tuple[float, float]) -> list[tuple[float, float]]:
    """Current terminal join: short stub + single diagonal (no Z)."""
    stub = (pin[0], pin[1] - 6.0)
    if abs(stub[0] - lane[0]) < 1e-9 or abs(stub[1] - lane[1]) < 1e-9:
        return [pin, stub, lane]
    return [pin, stub, lane]


def _lampara_like_bundle(*, diagonal: bool) -> list[list[tuple[float, float]]]:
    """Three lanes approaching a top-terminal strip (screenshot geometry)."""
    # Shared exterior highway (vertical then horizontal), then per-lane join.
    center = [(200.0, 40.0), (200.0, 120.0), (320.0, 120.0)]
    lanes = parallel_highway_bundle(center, 3)
    pins = [(300.0, 100.0), (320.0, 100.0), (340.0, 100.0)]
    out: list[list[tuple[float, float]]] = []
    for i, lane_poly in enumerate(lanes):
        join = lane_poly[-1]
        lead = (
            _diagonal_pin_join(pins[i], join)
            if diagonal
            else _manhattan_pin_join(pins[i], join)
        )
        # highway → reverse lead so path ends on the pin
        strand = list(lane_poly) + list(reversed(lead))[1:]
        out.append(strand)
    return out


class TestRouteQualityDetectors(unittest.TestCase):
    def test_parallel_highway_lanes_do_not_overlap(self) -> None:
        center = [(0.0, 0.0), (0.0, 80.0), (120.0, 80.0), (120.0, 140.0)]
        bundle = parallel_highway_bundle(center, 3)
        self.assertEqual(len(bundle), 3)
        self.assertFalse(strands_overlap(bundle))
        self.assertEqual(assess_bundle(bundle), [])

    def test_coincident_strands_flag_overlap(self) -> None:
        a = [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0)]
        self.assertTrue(strands_overlap([a, a]))
        issues = assess_bundle([a, a])
        self.assertTrue(any("overlap" in x for x in issues))

    def test_almost_stacked_lanes_flag_overlap(self) -> None:
        a = [(0.0, 0.0), (80.0, 0.0)]
        b = [(0.0, 1.0), (80.0, 1.0)]
        self.assertLess(1.0, MIN_LANE_SEPARATION)
        self.assertTrue(strands_overlap([a, b]))

    def test_screenshot_style_terminal_z_is_detected(self) -> None:
        # Blue wire Z from the Lampara screenshot: approach, jog, into pin.
        z = [
            (280.0, 130.0),
            (310.0, 130.0),
            (310.0, 118.0),
            (298.0, 118.0),
            (298.0, 100.0),
        ]
        self.assertGreaterEqual(count_z_jogs(z), 1)
        issues = assess_bundle([z])
        self.assertTrue(any("Z jog" in x for x in issues), msg=issues)

    def test_clean_l_has_no_z(self) -> None:
        clean = [(0.0, 0.0), (0.0, 50.0), (80.0, 50.0)]
        self.assertEqual(count_z_jogs(clean), 0)
        self.assertEqual(assess_bundle([clean]), [])

    def test_short_c_hook_detected(self) -> None:
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
        self.assertEqual(LANE_PITCH, 5.0)
        bundle = parallel_highway_bundle([(0.0, 0.0), (100.0, 0.0)], 2)
        y0 = bundle[0][0][1]
        y1 = bundle[1][0][1]
        self.assertAlmostEqual(abs(y1 - y0), LANE_PITCH, places=5)


class TestBothInvariantsTogether(unittest.TestCase):
    """The circular bug: fixing overlap must not reintroduce C/Z, and vice versa."""

    def test_manhattan_terminal_rejoin_is_rejected(self) -> None:
        """This is the live Lampara failure mode — must not be 'green'."""
        bad = _lampara_like_bundle(diagonal=False)
        issues = assess_bundle(bad)
        self.assertTrue(
            any("Z jog" in x for x in issues),
            msg=f"expected Z on Manhattan terminal rejoin, got {issues}",
        )

    def test_diagonal_terminal_rejoin_keeps_lanes_and_no_z(self) -> None:
        good = _lampara_like_bundle(diagonal=True)
        # Diagonals are terminal-only; Z detector is ortho-only, so no Z flag.
        # Lanes stay separated on the shared highway portion.
        highway = [poly[:3] for poly in good]
        self.assertFalse(strands_overlap(highway))
        self.assertEqual(assess_bundle(highway), [])
        for poly in good:
            self.assertEqual(count_z_jogs(poly), 0, msg=poly)

    def test_bad_stacked_run_rejected(self) -> None:
        stacked = [(0.0, 0.0), (0.0, 40.0), (90.0, 40.0)]
        issues = assess_bundle([stacked, stacked, stacked])
        self.assertTrue(any("overlap" in x for x in issues))

    def test_separated_but_with_z_still_rejected(self) -> None:
        center = [(0.0, 0.0), (0.0, 60.0), (100.0, 60.0)]
        bundle = parallel_highway_bundle(center, 2)
        s0 = list(bundle[0])
        x, y = s0[-1]
        s0.extend([(x + 10, y), (x + 10, y + 8), (x + 30, y + 8)])
        issues = assess_bundle([s0, bundle[1]])
        self.assertTrue(
            any("Z jog" in x for x in issues),
            msg=f"expected Z issue, got {issues}",
        )

    def test_offset_of_pin_inbox_l_creates_detectable_z_when_manhattan_rejoined(
        self,
    ) -> None:
        """Full-chain parallel of pin→L then Manhattan rejoin — the 0.34.7 bug."""
        pin = (320.0, 100.0)
        # Centerline inbox: pin up-stub then over to highway join.
        center_tail = [pin, (320.0, 90.0), (200.0, 90.0), (200.0, 40.0)]
        off = offset_ortho(center_tail, LANE_PITCH)
        # Reattach with Manhattan from true pin to offset start (bad).
        bad_lead = _manhattan_pin_join(pin, off[0])
        strand = bad_lead + off[1:]
        self.assertGreaterEqual(count_z_jogs(strand), 1)


if __name__ == "__main__":
    unittest.main()
