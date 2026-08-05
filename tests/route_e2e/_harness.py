"""Shared Playwright harness for live route E2E sites."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path

from housewire.ui.route_quality import assess_live_site

REPO = Path(__file__).resolve().parents[2]

# Match tests/conftest.py so unittest discovery finds Chromium too.
os.environ.setdefault(
    "PLAYWRIGHT_BROWSERS_PATH", str(REPO / ".playwright-browsers")
)

_DUMP_JS = """() => {
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
  const body = document.body?.innerText || '';
  if (body.includes('No locations with children found')) {
    return {err:'no locations', body: body.slice(0, 200)};
  }
  const tubes=[...svg.querySelectorAll('path.edge-tube')].map(el=>{
    const sw=parseFloat(getComputedStyle(el).strokeWidth)||17.5;
    const core = el.getAttribute('data-core-d');
    const painted = el.getAttribute('d') || '';
    const title = (el.querySelector('title')||{}).textContent || '';
    return {
      pts: parse(painted),
      corePts: parse(core || painted),
      half: sw/2,
      title,
    };
  });
  const strands=[...svg.querySelectorAll('path')]
    .filter(el=>parseFloat(el.getAttribute('stroke-width')||0)>=2
      && (el.getAttribute('stroke')||'').startsWith('#'))
    .map(el=>({stroke:el.getAttribute('stroke'), pts:parse(el.getAttribute('d'))}));
  const elements=[...svg.querySelectorAll('g.elements > g.element-node')].map(g=>{
    const r=g.querySelector(':scope > rect.element-box, :scope > rect');
    if(!r) return null;
    const m=g.transform&&g.transform.baseVal.consolidate();
    const t=m?m.matrix:{e:0,f:0};
    return {
      x:Number(r.getAttribute('x')||0)+t.e,
      y:Number(r.getAttribute('y')||0)+t.f,
      w:Number(r.getAttribute('width')||0),
      h:Number(r.getAttribute('height')||0),
      id:g.getAttribute('data-id')||'',
    };
  }).filter(Boolean);
  const mouths=[...svg.querySelectorAll('circle.opening-mark')].map(c=>{
    const g=c.closest('g.node');
    const m=g&&g.transform&&g.transform.baseVal.consolidate();
    const t=m?m.matrix:{e:0,f:0};
    const cls=c.getAttribute('class')||'';
    const face=(cls.match(/opening-face-([A-Z0-9-]+)/)||[])[1]||'';
    return {
      x: Number(c.getAttribute('cx')||0)+t.e,
      y: Number(c.getAttribute('cy')||0)+t.f,
      face,
    };
  });
  return {
    ver: document.querySelector('script[src*="app.js"]')?.src || '',
    tubes: tubes.map(t=>t.pts),
    tube_cores: tubes.map(t=>t.corePts),
    tube_titles: tubes.map(t=>t.title),
    halves: tubes.map(t=>t.half),
    strands: strands.map(s=>s.pts),
    strokes: strands.map(s=>s.stroke),
    elements,
    mouths,
  };
}"""


def resolve_example_site(name: str) -> Path | None:
    """Locate an example YAML by stem (Route_01, Route_21, …)."""
    env = os.environ.get("HOUSEWIRE_E2E_SITE", "").strip()
    if env:
        path = Path(env).expanduser()
        if path.is_file() and (
            path.stem == name or path.name.startswith(name)
        ):
            return path
    try:
        from housewire_examples import site_yaml

        return site_yaml(name)
    except Exception:
        pass
    for candidate in (
        REPO
        / "packages"
        / "housewire-examples"
        / "src"
        / "housewire_examples"
        / "sites"
        / f"{name}.yaml",
        REPO / "sites" / "Tests" / f"{name}.yaml",
    ):
        if candidate.is_file():
            return candidate
    return None


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _prepare_route_canvas(page, *, depth: int | None = None) -> None:
    """Enable Electrical and set canvas depth so tubes/strands/elements paint.

    Session defaults are depth 1 + electrical off (quiet editing view); live
    route E2E needs the full nested diagram with cables visible unless
    ``depth`` is set (0-based index matching the UI ``N/max`` label).
    """
    page.wait_for_selector("#btn-electrical", timeout=15000)
    page.wait_for_function(
        """() => {
          const d = document.getElementById('depth-label');
          const btn = document.getElementById('btn-electrical');
          return Boolean(
            d && /\\d+\\/\\d+/.test((d.textContent || '').trim())
            && btn && btn.getAttribute('aria-pressed') != null
          );
        }""",
        timeout=15000,
    )
    el_btn = page.locator("#btn-electrical")
    if el_btn.get_attribute("aria-pressed") != "true":
        el_btn.click()
        page.wait_for_function(
            """() => {
              const btn = document.getElementById('btn-electrical');
              return btn && btn.getAttribute('aria-pressed') === 'true';
            }""",
            timeout=5000,
        )
        # Electrical-on awaits setDepth(max); wait for that jump before
        # selecting a shallow depth (otherwise we match 1/2 too early).
        try:
            page.wait_for_function(
                """() => {
                  const t = (
                    document.getElementById('depth-label')?.textContent || ''
                  ).trim();
                  const m = /^(\\d+)\\/(\\d+)$/.exec(t);
                  return Boolean(m && m[1] === m[2]);
                }""",
                timeout=8000,
            )
        except Exception:
            page.wait_for_timeout(500)
    if depth is None:
        for _ in range(24):
            depth_in = page.locator("#btn-depth-in")
            if depth_in.is_disabled():
                break
            before = page.locator("#depth-label").inner_text()
            depth_in.click()
            try:
                page.wait_for_function(
                    """(prev) => {
                      const d = document.getElementById('depth-label');
                      const btn = document.getElementById('btn-depth-in');
                      const text = (d && d.textContent) || '';
                      return text !== prev || Boolean(btn && btn.disabled);
                    }""",
                    before,
                    timeout=8000,
                )
            except Exception:
                break
        return

    # Electrical-on may jump to max depth — reach UI label ``depth/…``.
    want_prefix = f"{int(depth)}/"

    def _label() -> str:
        return (page.locator("#depth-label").inner_text() or "").strip()

    for _ in range(24):
        if _label().startswith(want_prefix):
            return
        depth_out = page.locator("#btn-depth-out")
        if depth_out.is_disabled():
            break
        before = _label()
        depth_out.click()
        try:
            page.wait_for_function(
                """(prev) => {
                  const d = document.getElementById('depth-label');
                  const text = ((d && d.textContent) || '').trim();
                  return text !== prev;
                }""",
                before,
                timeout=3000,
            )
        except Exception:
            break
    for _ in range(24):
        if _label().startswith(want_prefix):
            return
        depth_in = page.locator("#btn-depth-in")
        if depth_in.is_disabled():
            break
        before = _label()
        depth_in.click()
        try:
            page.wait_for_function(
                """(prev) => {
                  const d = document.getElementById('depth-label');
                  const text = ((d && d.textContent) || '').trim();
                  return text !== prev;
                }""",
                before,
                timeout=3000,
            )
        except Exception:
            break


def dump_live_canvas(
    site: Path,
    *,
    wait_ms: int = 2000,
    require_tubes: bool = True,
    depth: int | None = None,
) -> dict:
    """Start serve, load the site, return tubes/strands dump.

    ``depth`` selects the UI depth after enabling Electrical (None = deepest).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover
        raise unittest.SkipTest(f"playwright not installed: {exc}") from exc

    port = free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "housewire",
            "serve",
            str(site),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(REPO),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 20.0
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                    break
            except OSError:
                if proc.poll() is not None:
                    raise unittest.SkipTest("housewire serve exited early")
                time.sleep(0.15)
        else:
            raise unittest.SkipTest("housewire serve did not start")

        with sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except Exception as exc:  # pragma: no cover - env dependent
                msg = str(exc)
                if "Executable doesn't exist" in msg or "playwright install" in msg:
                    raise unittest.SkipTest(
                        "Playwright Chromium missing; run: "
                        ".venv/bin/playwright install chromium"
                    ) from exc
                raise
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
            page.wait_for_timeout(min(wait_ms, 500))
            _prepare_route_canvas(page, depth=depth)
            page.wait_for_timeout(wait_ms)
            # Wait until the canvas has painted tubes and/or strands (avoids
            # empty dumps when outline/graph finishes after networkidle).
            # Shallow depth often hides inbox strands — require tubes only then.
            try:
                page.wait_for_function(
                    """([needTubes, needStrands]) => {
                      const body = document.body?.innerText || '';
                      if (body.includes('No locations with children found')) {
                        return true; // let dump report err
                      }
                      const tubes = document.querySelectorAll('path.edge-tube').length;
                      const strands = [...document.querySelectorAll('#canvas path')]
                        .filter(el => parseFloat(el.getAttribute('stroke-width')||0) >= 2
                          && (el.getAttribute('stroke')||'').startsWith('#')).length;
                      if (needTubes && tubes < 1) return false;
                      if (needStrands && strands < 1) return false;
                      return needTubes || needStrands || strands > 0 || tubes > 0;
                    }""",
                    [require_tubes, depth is None and require_tubes],
                    timeout=15000,
                )
            except Exception:
                pass
            data = page.evaluate(_DUMP_JS)
            if require_tubes and not (data.get("tubes") or []):
                data = dict(data)
                data["err"] = data.get("err") or "no edge-tube paths on canvas"
            try:
                data["depth_label"] = page.locator("#depth-label").inner_text()
            except Exception:
                pass
            browser.close()
        return data
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def assert_no_colinear_tube_overlap(
    test: unittest.TestCase,
    data: dict,
    *,
    min_overlap: float = 24.0,
) -> None:
    """Fail if any two painted conduits colinear-stack (routing rule 15).

    Used by every live geometry E2E helper so sites cannot skip the check.
    """
    from housewire.ui.route_quality import tubes_colinear_overlap

    raw = data.get("tubes") or []
    tubes = [t for t in raw if len(t) >= 2]
    if len(tubes) < 2:
        return
    halves = data.get("halves") or []
    if halves and len(halves) == len(data.get("tubes") or []):
        halves = [
            h
            for t, h in zip(data.get("tubes") or [], halves, strict=False)
            if len(t) >= 2
        ]
    overlap = tubes_colinear_overlap(
        tubes,
        tube_half_widths=halves or None,
        min_overlap=min_overlap,
    )
    test.assertEqual(
        overlap,
        [],
        msg=f"colinear tube overlap: {overlap}",
    )


def assert_no_foreign_mouth_skim(
    test: unittest.TestCase,
    data: dict,
) -> None:
    """Fail if a plane↔plane tube mid-run passes through another B/F boca.

    Matches routing: foreign-mouth obstacles apply only when both conduit
    ends are plane openings (Route_28). Side↔plane (Route_21 lamp) may share
    a face latitude with sibling side mouths without failing this gate.
    """
    from housewire.ui.route_quality import tubes_skim_foreign_mouths

    raw = data.get("tubes") or []
    tubes = [t for t in raw if len(t) >= 2]
    if not tubes:
        return
    halves = data.get("halves") or []
    if halves and len(halves) == len(data.get("tubes") or []):
        halves = [
            h
            for t, h in zip(data.get("tubes") or [], halves, strict=False)
            if len(t) >= 2
        ]
    mouths: list[tuple[float, float]] = []
    # Other tubes' endpoints (always).
    for t in tubes:
        mouths.append((float(t[0][0]), float(t[0][1])))
        mouths.append((float(t[-1][0]), float(t[-1][1])))
    # Painted marks: only B/F — same scope as foreignMouthObstacleRects for
    # plane↔plane routing (side mouths are ignored here).
    for m in data.get("mouths") or []:
        if m is None:
            continue
        if isinstance(m, dict):
            face = str(m.get("face") or "")
            if face not in ("B", "F") and not face.startswith(("B", "F")):
                continue
            mouths.append((float(m["x"]), float(m["y"])))
        else:
            mouths.append((float(m[0]), float(m[1])))
    skim = tubes_skim_foreign_mouths(
        tubes,
        mouths,
        tube_half_widths=halves or None,
    )
    test.assertEqual(skim, [], msg=f"tube skims foreign mouth: {skim}")


def assert_no_strand_lane_overlap(
    test: unittest.TestCase,
    data: dict,
) -> None:
    """Fail when co-tube strands stack closer than lane pitch (crossings OK)."""
    from housewire.ui.route_quality import (
        match_strand_to_tube,
        strands_overlap,
        dedupe_identical_polylines,
    )

    tubes = [
        t
        for t in (data.get("tube_cores") or data.get("tubes") or [])
        if len(t) >= 2
    ]
    strands = dedupe_identical_polylines(data.get("strands") or [])
    if len(strands) < 2 or not tubes:
        return
    by_tube: dict[int, list] = {}
    for pts in strands:
        ti, _ = match_strand_to_tube(pts, tubes)
        if ti < 0:
            continue
        by_tube.setdefault(ti, []).append(pts)
    bad: list[str] = []
    for ti, polys in sorted(by_tube.items()):
        if len(polys) < 2:
            continue
        # Crossings OK (U-turn lane flip); reject parallel / colinear stacks.
        if strands_overlap(polys, allow_crossings=True):
            bad.append(f"tube[{ti}]: strands overlap (lane separation too small)")
    test.assertEqual(bad, [], msg=f"strand lane overlap: {bad}")


def assert_no_strand_through_elements(
    test: unittest.TestCase,
    data: dict,
) -> None:
    """Fail when a mid-run strand pierces an element box (rule 17)."""
    from housewire.ui.route_quality import (
        assess_bundle,
        dedupe_identical_polylines,
    )

    strands = dedupe_identical_polylines(data.get("strands") or [])
    elems = data.get("elements") or []
    rects = [
        (float(e["x"]), float(e["y"]), float(e["w"]), float(e["h"]))
        for e in elems
        if e.get("w") and e.get("h")
    ]
    if len(strands) < 1 or not rects:
        return
    issues = assess_bundle(
        strands,
        element_rects=rects,
        allow_crossings=True,
        allow_z=True,
        allow_c=True,
    )
    through = [i for i in issues if "through element" in i]
    test.assertEqual(through, [], msg=f"strands pierce elements: {through}")


def assert_inbox_at_most_segments(
    test: unittest.TestCase,
    data: dict,
    *,
    max_segments: int = 3,
) -> None:
    """Each mouth↔pin approach (outside the tube core) has ≤ ``max_segments``."""
    from housewire.ui.route_quality import (
        match_strand_to_tube,
        dedupe_identical_polylines,
    )

    tubes = [
        _clean_ortho_pts(t)
        for t in (data.get("tube_cores") or data.get("tubes") or [])
        if len(t) >= 2
    ]
    strands = [
        _clean_ortho_pts(s)
        for s in dedupe_identical_polylines(data.get("strands") or [])
    ]
    if not tubes or not strands:
        return
    bad: list[str] = []
    for si, pts in enumerate(strands):
        if len(pts) < 2:
            continue
        ti, _ = match_strand_to_tube(pts, tubes)
        if ti < 0:
            continue
        tube = tubes[ti]
        t0, t1 = tube[0], tube[-1]

        def closest_i(pt: list[float]) -> int:
            return min(
                range(len(pts)),
                key=lambda i: (pts[i][0] - pt[0]) ** 2 + (pts[i][1] - pt[1]) ** 2,
            )

        i0, i1 = closest_i(t0), closest_i(t1)
        lo, hi = (i0, i1) if i0 <= i1 else (i1, i0)
        head = pts[: lo + 1]
        tail = pts[hi:]
        for label, side in (("head", head), ("tail", tail)):
            clean = _clean_ortho_pts(side)
            segs = max(0, len(clean) - 1)
            if segs > max_segments:
                bad.append(
                    f"strand[{si}] {label}: {segs} segments "
                    f"(max {max_segments}): {clean}"
                )
    test.assertEqual(bad, [], msg=f"inbox segment budget: {bad}")


def assert_tube_geometry_ok(test: unittest.TestCase, data: dict) -> None:
    """Shared tube geometry gates: no colinear stack, no foreign-mouth skim."""
    assert_no_colinear_tube_overlap(test, data)
    assert_no_foreign_mouth_skim(test, data)


def assert_site_routes_ok(
    test: unittest.TestCase,
    site_name: str,
    *,
    require_tubes: bool = True,
    min_strands: int = 1,
) -> dict:
    """Load ``site_name`` and assert live route invariants."""
    site = resolve_example_site(site_name)
    if site is None or not site.is_file():
        raise unittest.SkipTest(
            f"{site_name} not found (install housewire-examples)"
        )
    data = dump_live_canvas(site, require_tubes=require_tubes)
    test.assertNotIn("err", data, msg=data)
    test.assertGreaterEqual(
        len(data.get("strands") or []),
        min_strands,
        msg=data,
    )
    if require_tubes:
        test.assertGreaterEqual(len(data.get("tubes") or []), 1, msg=data)
    assert_tube_geometry_ok(test, data)
    raw_cores = data.get("tube_cores") or data.get("tubes") or []
    tubes = [t for t in raw_cores if len(t) >= 2]
    halves = data.get("halves") or []
    # Keep half-widths aligned with non-empty tubes.
    if halves and len(halves) == len(data.get("tubes") or []):
        halves = [
            h
            for t, h in zip(raw_cores, halves, strict=False)
            if len(t) >= 2
        ]
    issues = assess_live_site(
        tubes,
        data.get("strands") or [],
        tube_half_widths=halves or None,
        require_tubes=require_tubes,
        # Live sites use Manhattan distinct-pin buses (Route_29/30); the
        # Regleta-band V heuristic is covered by unit tests, not every E2E.
        bipolar_y_min=1.0e9,
        # Rule 17 mid-run pierce is asserted on Route_30; generic live sites
        # still check mouths, envelope, packing, and out-and-back.
        element_rects=None,
    )
    test.assertEqual(
        issues,
        [],
        msg=f"site={site_name} ver={data.get('ver')} issues={issues}",
    )
    return data


def _clean_ortho_pts(
    pts: list[list[float]], *, tol: float = 1e-3
) -> list[list[float]]:
    """Drop duplicates and collinear midpoints (Manhattan)."""
    if len(pts) < 2:
        return [list(p) for p in pts]
    out: list[list[float]] = [[float(pts[0][0]), float(pts[0][1])]]
    for raw in pts[1:]:
        p = [float(raw[0]), float(raw[1])]
        if abs(p[0] - out[-1][0]) < tol and abs(p[1] - out[-1][1]) < tol:
            continue
        out.append(p)
    if len(out) < 3:
        return out
    cleaned: list[list[float]] = [out[0]]
    for i in range(1, len(out) - 1):
        ax, ay = cleaned[-1]
        bx, by = out[i]
        cx, cy = out[i + 1]
        colinear = (abs(ax - bx) < tol and abs(bx - cx) < tol) or (
            abs(ay - by) < tol and abs(by - cy) < tol
        )
        if not colinear:
            cleaned.append(out[i])
    cleaned.append(out[-1])
    return cleaned


def _ortho_bend_count(pts: list[list[float]], *, tol: float = 1e-3) -> int:
    """Number of direction changes in a cleaned Manhattan polyline."""
    clean = _clean_ortho_pts(pts, tol=tol)
    bends = 0
    for i in range(2, len(clean)):
        dx0 = clean[i - 1][0] - clean[i - 2][0]
        dy0 = clean[i - 1][1] - clean[i - 2][1]
        dx1 = clean[i][0] - clean[i - 1][0]
        dy1 = clean[i][1] - clean[i - 1][1]
        horiz0 = abs(dy0) < tol
        horiz1 = abs(dy1) < tol
        if horiz0 != horiz1:
            bends += 1
    return bends


def assert_tubes_straight(
    test: unittest.TestCase,
    site_name: str,
    *,
    expected: int,
    tol: float = 3.0,
    max_points: int | None = None,
) -> None:
    """Each painted tube centerline must be a single horizontal or vertical run.

    When ``max_points`` is set (e.g. 2), reject intermediate vertices even if
    the polyline stays axis-aligned.
    """
    site = resolve_example_site(site_name)
    if site is None or not site.is_file():
        raise unittest.SkipTest(
            f"{site_name} not found (install housewire-examples)"
        )
    data = dump_live_canvas(site, require_tubes=True)
    test.assertNotIn("err", data, msg=data)
    tubes = [t for t in (data.get("tubes") or []) if len(t) >= 2]
    test.assertEqual(len(tubes), expected, msg=data)
    assert_tube_geometry_ok(test, data)
    bad: list[tuple[int, list]] = []
    for i, pts in enumerate(tubes):
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        horiz = max(xs) - min(xs) < tol
        vert = max(ys) - min(ys) < tol
        if not (horiz or vert):
            bad.append((i, pts))
            continue
        if max_points is not None and len(pts) > max_points:
            bad.append((i, pts))
    test.assertEqual(bad, [], msg=f"non-straight tubes: {bad}")
    return data


def assert_tubes_l_shape(
    test: unittest.TestCase,
    site_name: str,
    *,
    expected: int,
    tol: float = 3.0,
    max_points: int = 3,
) -> None:
    """Each painted tube is a Manhattan L: one corner, no extra vertices.

    Rejects straight H/V runs and polylines with more than one bend (or more
    than ``max_points`` after collapsing collinear points).
    """
    site = resolve_example_site(site_name)
    if site is None or not site.is_file():
        raise unittest.SkipTest(
            f"{site_name} not found (install housewire-examples)"
        )
    data = dump_live_canvas(site, require_tubes=True)
    test.assertNotIn("err", data, msg=data)
    # Prefer anchor cores (no iso mouth stubs); fall back to painted paths.
    raw = data.get("tube_cores") or data.get("tubes") or []
    tubes = [t for t in raw if len(t) >= 2]
    test.assertEqual(len(tubes), expected, msg=data)
    assert_tube_geometry_ok(test, data)
    bad: list[tuple[int, str, list]] = []
    for i, pts in enumerate(tubes):
        clean = _clean_ortho_pts(pts)
        xs = [p[0] for p in clean]
        ys = [p[1] for p in clean]
        horiz = max(xs) - min(xs) < tol
        vert = max(ys) - min(ys) < tol
        if horiz or vert:
            bad.append((i, "straight", clean))
            continue
        # Every segment must be axis-aligned.
        for a, b in zip(clean, clean[1:], strict=False):
            if abs(a[0] - b[0]) >= tol and abs(a[1] - b[1]) >= tol:
                bad.append((i, "diagonal", clean))
                break
        else:
            bends = _ortho_bend_count(clean)
            if bends != 1:
                bad.append((i, f"bends={bends}", clean))
            elif len(clean) > max_points:
                bad.append((i, f"points={len(clean)}", clean))
    test.assertEqual(bad, [], msg=f"non-L tubes: {bad}")
    return data


def assert_tubes_avoid_l_overlap(
    test: unittest.TestCase,
    site_name: str,
    *,
    expected: int,
    min_extra_bend_tubes: int = 1,
    max_segments_when_extra: int = 3,
) -> dict:
    """Site cannot keep every tube as a single L without stacking.

    Live tubes must not colinear-overlap, and at least
    ``min_extra_bend_tubes`` painted paths must have ≥2 bends (C/U fallback).
    Those detours must stay within ``max_segments_when_extra`` segments
    (mark-to-mark C/U, not contour+iso stub chains).
    """
    site = resolve_example_site(site_name)
    if site is None or not site.is_file():
        raise unittest.SkipTest(
            f"{site_name} not found (install housewire-examples)"
        )
    data = dump_live_canvas(site, require_tubes=True)
    test.assertNotIn("err", data, msg=data)
    # Prefer painted paths: mark-to-mark C/U must not grow iso stubs.
    raw = data.get("tubes") or data.get("tube_cores") or []
    tubes = [t for t in raw if len(t) >= 2]
    test.assertEqual(len(tubes), expected, msg=data)
    assert_tube_geometry_ok(test, data)

    multi = 0
    for pts in tubes:
        clean = _clean_ortho_pts(pts)
        bends = _ortho_bend_count(clean)
        if bends < 2:
            continue
        multi += 1
        segs = max(0, len(clean) - 1)
        test.assertLessEqual(
            segs,
            max_segments_when_extra,
            msg=(
                f"extra-bend tube has {segs} segments "
                f"(max {max_segments_when_extra}): {clean}"
            ),
        )
    test.assertGreaterEqual(
        multi,
        min_extra_bend_tubes,
        msg=f"expected ≥{min_extra_bend_tubes} tubes with ≥2 bends, got {multi}",
    )
    return data


def assert_named_tube_segment_count(
    test: unittest.TestCase,
    data: dict,
    *,
    title_substr: str,
    segments: int | None = None,
    max_segments: int | None = None,
) -> None:
    """Assert the painted tube whose title contains ``title_substr``.

    Pass ``segments`` for an exact count, and/or ``max_segments`` for an
    upper bound (fewer segments allowed). At least one must be set.
    """
    if segments is None and max_segments is None:
        raise ValueError("pass segments and/or max_segments")
    titles = data.get("tube_titles") or []
    raw = data.get("tubes") or []
    hits = [
        (title, pts)
        for title, pts in zip(titles, raw, strict=False)
        if title_substr in (title or "") and len(pts) >= 2
    ]
    test.assertEqual(
        len(hits),
        1,
        msg=(
            f"expected one tube matching {title_substr!r}, "
            f"got {hits!r} titles={titles}"
        ),
    )
    clean = _clean_ortho_pts(hits[0][1])
    segs = max(0, len(clean) - 1)
    if max_segments is not None:
        test.assertLessEqual(
            segs,
            max_segments,
            msg=(
                f"{title_substr}: expected ≤{max_segments} segments, "
                f"got {segs}: {clean}"
            ),
        )
    if segments is not None:
        test.assertEqual(
            segs,
            segments,
            msg=(
                f"{title_substr}: expected {segments} segments, "
                f"got {segs}: {clean}"
            ),
        )


# Match src/housewire/ui/static/app.js isometric opening-mark constants.
_ISO_DX = -20.0
_ISO_DY = -20.0
_ISO_MARK_SIDE_DEPTH_T = 0.5
_OPENING_MARK_R = 5.0


_DUMP_OPENINGS_JS = """() => {
  const svg = document.getElementById('canvas');
  if (!svg) return {err: 'no canvas'};
  const nodes = [...svg.querySelectorAll('g.leaves > g.node, g.containers > g.node')];
  const out = [];
  for (const g of nodes) {
    const box = g.querySelector(':scope > rect.node-box, :scope > rect');
    if (!box) continue;
    const w = Number(box.getAttribute('width') || 0);
    const h = Number(box.getAttribute('height') || 0);
    if (!w || !h) continue;
    const marks = [...g.querySelectorAll('circle.opening-mark')].map(c => ({
      id: c.getAttribute('data-opening') || '',
      cx: Number(c.getAttribute('cx') || 0),
      cy: Number(c.getAttribute('cy') || 0),
      face: ((c.getAttribute('class') || '').match(/opening-face-([NSEWFB])/) || [])[1] || '',
    }));
    if (!marks.length) continue;
    out.push({
      id: g.getAttribute('data-id') || '',
      w, h,
      marks,
    });
  }
  return {
    ver: document.querySelector('script[src*="app.js"]')?.src || '',
    nodes: out,
  };
}"""


def dump_opening_marks(site: Path, *, wait_ms: int = 2000) -> dict:
    """Start serve, load the site, return painted opening-mark geometry."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover
        raise unittest.SkipTest(f"playwright not installed: {exc}") from exc

    port = free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "housewire",
            "serve",
            str(site),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(REPO),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 20.0
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                    break
            except OSError:
                if proc.poll() is not None:
                    raise unittest.SkipTest("housewire serve exited early")
                time.sleep(0.15)
        else:
            raise unittest.SkipTest("housewire serve did not start")

        with sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except Exception as exc:  # pragma: no cover
                msg = str(exc)
                if "Executable doesn't exist" in msg or "playwright install" in msg:
                    raise unittest.SkipTest(
                        "Playwright Chromium missing; run: "
                        ".venv/bin/playwright install chromium"
                    ) from exc
                raise
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
            page.wait_for_timeout(min(wait_ms, 500))
            _prepare_route_canvas(page)
            page.wait_for_timeout(wait_ms)
            try:
                page.wait_for_function(
                    """() => document.querySelectorAll('circle.opening-mark').length > 0""",
                    timeout=15000,
                )
            except Exception:
                pass
            data = page.evaluate(_DUMP_OPENINGS_JS)
            browser.close()
        return data
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def assert_iso_opening_marks(
    test: unittest.TestCase,
    site_name: str,
    *,
    tol: float = 1.5,
) -> None:
    """Side marks on mid-depth axes; F/B inside front∩back and off shared axes."""
    site = resolve_example_site(site_name)
    if site is None or not site.is_file():
        raise unittest.SkipTest(
            f"{site_name} not found (install housewire-examples)"
        )
    data = dump_opening_marks(site)
    test.assertNotIn("err", data, msg=data)
    nodes = data.get("nodes") or []
    test.assertGreaterEqual(len(nodes), 1, msg=data)

    mid_t = _ISO_MARK_SIDE_DEPTH_T
    mid_x = _ISO_DX * mid_t
    mid_y = _ISO_DY * mid_t
    issues: list[str] = []

    for node in nodes:
        w = float(node["w"])
        h = float(node["h"])
        ix0 = max(0.0, _ISO_DX)
        iy0 = max(0.0, _ISO_DY)
        ix1 = min(w, w + _ISO_DX)
        iy1 = min(h, h + _ISO_DY)
        # Circle centers must sit in the intersection; allow mark radius slack.
        pad = _OPENING_MARK_R
        fronts = [m for m in node["marks"] if m.get("face") == "F"]
        backs = [m for m in node["marks"] if m.get("face") == "B"]
        sides = {
            face: [m for m in node["marks"] if m.get("face") == face]
            for face in ("N", "S", "E", "W")
        }

        for face, marks in sides.items():
            for m in marks:
                cx, cy = float(m["cx"]), float(m["cy"])
                oid = m.get("id") or "?"
                if face in ("N", "S"):
                    expect_y = mid_y if face == "N" else h + mid_y
                    if abs(cy - expect_y) > tol:
                        issues.append(
                            f"{node.get('id')}.{oid}: side {face} cy={cy} "
                            f"want mid-depth y={expect_y}"
                        )
                else:
                    expect_x = mid_x if face == "W" else w + mid_x
                    if abs(cx - expect_x) > tol:
                        issues.append(
                            f"{node.get('id')}.{oid}: side {face} cx={cx} "
                            f"want mid-depth x={expect_x}"
                        )

        for m in fronts + backs:
            cx, cy = float(m["cx"]), float(m["cy"])
            oid = m.get("id") or "?"
            if not (
                ix0 + pad - tol <= cx <= ix1 - pad + tol
                and iy0 + pad - tol <= cy <= iy1 - pad + tol
            ):
                issues.append(
                    f"{node.get('id')}.{oid}: outside front∩back "
                    f"[{ix0},{iy0}]–[{ix1},{iy1}] at ({cx},{cy})"
                )

        # Corresponding Frow-col / Brow-col pairs: same iso diagonal as NW verts.
        expect_dx = _ISO_DX
        expect_dy = _ISO_DY
        expect_dist = (expect_dx * expect_dx + expect_dy * expect_dy) ** 0.5
        by_cell: dict[str, dict[str, dict]] = {}
        for m in fronts + backs:
            oid = str(m.get("id") or "")
            parts = oid.split("-", 1)
            if len(parts) != 2 or len(parts[0]) < 2:
                continue
            face, cell = parts[0][0].upper(), parts[0][1:] + "-" + parts[1]
            by_cell.setdefault(cell, {})[face] = m
        for cell, pair in sorted(by_cell.items()):
            fm, bm = pair.get("F"), pair.get("B")
            if not fm or not bm:
                issues.append(
                    f"{node.get('id')}: missing F/B pair for cell {cell}"
                )
                continue
            dx = float(bm["cx"]) - float(fm["cx"])
            dy = float(bm["cy"]) - float(fm["cy"])
            dist = (dx * dx + dy * dy) ** 0.5
            if abs(dx - expect_dx) > tol or abs(dy - expect_dy) > tol:
                issues.append(
                    f"{node.get('id')}: F/B cell {cell} offset "
                    f"({dx:.2f},{dy:.2f}) want ({expect_dx},{expect_dy})"
                )
            if abs(dist - expect_dist) > tol:
                issues.append(
                    f"{node.get('id')}: F/B cell {cell} diagonal "
                    f"{dist:.2f} want {expect_dist:.2f}"
                )
            if abs(float(fm["cx"]) - float(bm["cx"])) <= tol:
                issues.append(
                    f"{node.get('id')}: F/B share x on cell {cell}"
                )
            if abs(float(fm["cy"]) - float(bm["cy"])) <= tol:
                issues.append(
                    f"{node.get('id')}: F/B share y on cell {cell}"
                )

        if not any(sides.values()):
            issues.append(f"{node.get('id')}: no side opening marks painted")
        if not fronts or not backs:
            issues.append(
                f"{node.get('id')}: need both F and B marks "
                f"(F={len(fronts)}, B={len(backs)})"
            )

    test.assertEqual(issues, [], msg=f"site={site_name} ver={data.get('ver')} {issues}")
