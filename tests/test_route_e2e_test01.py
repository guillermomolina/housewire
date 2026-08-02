"""E2E route invariants against the live Test_01 canvas.

Synthetic unit tests below always run. The Playwright suite starts
``housewire serve`` on Test_01.yaml when the fixture and playwright exist.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path

from housewire.ui.route_quality import (
    assess_live_canvas,
    match_strand_to_tube,
    point_near_polyline,
    shared_horizontal_trunk_length,
)

REPO = Path(__file__).resolve().parents[1]
TEST01 = REPO / "sites" / "Tests" / "Test_01.yaml"


class TestLiveCanvasInvariantsUnit(unittest.TestCase):
    """Detectors must flag the known Test_01 failure shapes."""

    def test_missed_mouth_detected(self) -> None:
        tube = [(593.0, 332.0), (593.0, 308.0), (1147.0, 308.0), (1147.0, 459.5)]
        # Leaves vertical early into inbox — never reaches end mouth.
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
            bipolar_y_min=900.0,  # disable V check for this fixture
        )
        self.assertFalse(
            any("misses tube" in x for x in issues),
            msg=issues,
        )

    def test_shared_trunk_detected(self) -> None:
        # Two strands crawl the same y=420 into different columns.
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
        # Manhattan into pin at y=452 — no diagonal.
        bad = [(100.0, 100.0), (100.0, 200.0), (200.0, 200.0), (200.0, 452.0)]
        issues = assess_live_canvas(
            [tube], [bad], tube_half_widths=[10.0], bipolar_y_min=430.0
        )
        self.assertTrue(any("missing terminal V" in x for x in issues), msg=issues)

    def test_point_near_and_match_helpers(self) -> None:
        tube = [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0)]
        self.assertTrue(point_near_polyline((100.0, 25.0), tube, tol=1.0))
        self.assertFalse(point_near_polyline((50.0, 25.0), tube, tol=1.0))
        strand = [(0.0, 2.0), (100.0, 2.0), (100.0, 50.0)]
        ti, score = match_strand_to_tube(strand, [tube, [(500.0, 500.0), (600.0, 600.0)]])
        self.assertEqual(ti, 0)
        self.assertLess(score, 5.0)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@unittest.skipUnless(TEST01.is_file(), "sites/Tests/Test_01.yaml not present")
class TestRouteE2ETest01(unittest.TestCase):
    """Live canvas invariants for Test_01 (requires playwright + chromium)."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise unittest.SkipTest(f"playwright not installed: {exc}") from exc

        cls.port = _free_port()
        cls.base = f"http://127.0.0.1:{cls.port}/"
        env = os.environ.copy()
        cls.proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "housewire",
                "serve",
                str(TEST01),
                "--host",
                "127.0.0.1",
                "--port",
                str(cls.port),
            ],
            cwd=str(REPO),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 20.0
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", cls.port), timeout=0.3):
                    break
            except OSError:
                if cls.proc.poll() is not None:
                    raise unittest.SkipTest("housewire serve exited early")
                time.sleep(0.15)
        else:
            cls.proc.kill()
            raise unittest.SkipTest("housewire serve did not start")

    @classmethod
    def tearDownClass(cls) -> None:
        proc = getattr(cls, "proc", None)
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    def test_live_strands_satisfy_route_invariants(self) -> None:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.goto(self.base, wait_until="networkidle")
            page.wait_for_timeout(3500)
            data = page.evaluate(
                """() => {
                  const parse = (d) => {
                    const pts=[]; let x=0,y=0;
                    const re=/([MLHVZmlhvz])([^MLHVZmlhvz]*)/g; let m;
                    while ((m=re.exec(d||''))) {
                      const cmd=m[1], args=m[2].trim().split(/[\\s,]+/).filter(Boolean).map(Number);
                      if (cmd==='M'||cmd==='L') for(let i=0;i+1<args.length;i+=2){x=args[i];y=args[i+1];pts.push([x,y]);}
                      else if (cmd==='H') for(const a of args){x=a;pts.push([x,y]);}
                      else if (cmd==='V') for(const a of args){y=a;pts.push([x,y]);}
                    }
                    return pts;
                  };
                  const svg=document.getElementById('canvas');
                  if (!svg) return {err:'no canvas'};
                  const tubes=[...svg.querySelectorAll('path.edge-tube')].map(el=>{
                    const sw=parseFloat(getComputedStyle(el).strokeWidth)||17.5;
                    return {pts:parse(el.getAttribute('d')), half:sw/2};
                  });
                  const strands=[...svg.querySelectorAll('path')]
                    .filter(el=>parseFloat(el.getAttribute('stroke-width')||0)>=2
                      && (el.getAttribute('stroke')||'').startsWith('#'))
                    .map(el=>({stroke:el.getAttribute('stroke'), pts:parse(el.getAttribute('d'))}));
                  return {
                    ver: document.querySelector('script[src*="app.js"]')?.src || '',
                    tubes: tubes.map(t=>t.pts),
                    halves: tubes.map(t=>t.half),
                    strands: strands.map(s=>s.pts),
                    strokes: strands.map(s=>s.stroke),
                  };
                }"""
            )
            browser.close()

        self.assertNotIn("err", data, msg=data)
        self.assertGreaterEqual(len(data["tubes"]), 1, msg=data)
        self.assertGreaterEqual(len(data["strands"]), 4, msg=data)
        issues = assess_live_canvas(
            data["tubes"],
            data["strands"],
            tube_half_widths=data["halves"],
        )
        self.assertEqual(
            issues,
            [],
            msg=f"ver={data.get('ver')} strokes={data.get('strokes')} issues={issues}",
        )


if __name__ == "__main__":
    unittest.main()
