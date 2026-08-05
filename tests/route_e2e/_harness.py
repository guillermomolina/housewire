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
    return {pts:parse(el.getAttribute('d')), half:sw/2};
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
  return {
    ver: document.querySelector('script[src*="app.js"]')?.src || '',
    tubes: tubes.map(t=>t.pts),
    halves: tubes.map(t=>t.half),
    strands: strands.map(s=>s.pts),
    strokes: strands.map(s=>s.stroke),
    elements,
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


def _prepare_route_canvas(page) -> None:
    """Enable Electrical and deepen so tubes/strands/elements are painted.

    Session defaults are depth 1 + electrical off (quiet editing view); live
    route E2E needs the full nested diagram with cables visible.
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


def dump_live_canvas(
    site: Path,
    *,
    wait_ms: int = 2000,
    require_tubes: bool = True,
) -> dict:
    """Start serve, load the site, return tubes/strands dump."""
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
            _prepare_route_canvas(page)
            page.wait_for_timeout(wait_ms)
            # Wait until the canvas has painted tubes and/or strands (avoids
            # empty dumps when outline/graph finishes after networkidle).
            try:
                page.wait_for_function(
                    """(needTubes) => {
                      const body = document.body?.innerText || '';
                      if (body.includes('No locations with children found')) {
                        return true; // let dump report err
                      }
                      const tubes = document.querySelectorAll('path.edge-tube').length;
                      const strands = [...document.querySelectorAll('#canvas path')]
                        .filter(el => parseFloat(el.getAttribute('stroke-width')||0) >= 2
                          && (el.getAttribute('stroke')||'').startsWith('#')).length;
                      return strands > 0 && (!needTubes || tubes > 0);
                    }""",
                    require_tubes,
                    timeout=15000,
                )
            except Exception:
                pass
            data = page.evaluate(_DUMP_JS)
            browser.close()
        return data
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def assert_site_routes_ok(
    test: unittest.TestCase,
    site_name: str,
    *,
    require_tubes: bool = True,
    min_strands: int = 1,
) -> None:
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
    tubes = [t for t in (data.get("tubes") or []) if len(t) >= 2]
    halves = data.get("halves") or []
    # Keep half-widths aligned with non-empty tubes.
    if halves and len(halves) == len(data.get("tubes") or []):
        halves = [
            h
            for t, h in zip(data.get("tubes") or [], halves, strict=False)
            if len(t) >= 2
        ]
    issues = assess_live_site(
        tubes,
        data.get("strands") or [],
        tube_half_widths=halves or None,
        require_tubes=require_tubes,
        element_rects=[
            (float(e["x"]), float(e["y"]), float(e["w"]), float(e["h"]))
            for e in (data.get("elements") or [])
            if e.get("w") and e.get("h")
        ]
        or None,
    )
    test.assertEqual(
        issues,
        [],
        msg=f"site={site_name} ver={data.get('ver')} issues={issues}",
    )


def assert_tubes_straight(
    test: unittest.TestCase,
    site_name: str,
    *,
    expected: int,
    tol: float = 3.0,
) -> None:
    """Each painted tube centerline must be a single horizontal or vertical run."""
    site = resolve_example_site(site_name)
    if site is None or not site.is_file():
        raise unittest.SkipTest(
            f"{site_name} not found (install housewire-examples)"
        )
    data = dump_live_canvas(site, require_tubes=True)
    test.assertNotIn("err", data, msg=data)
    tubes = [t for t in (data.get("tubes") or []) if len(t) >= 2]
    test.assertEqual(len(tubes), expected, msg=data)
    bad: list[tuple[int, list]] = []
    for i, pts in enumerate(tubes):
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        horiz = max(xs) - min(xs) < tol
        vert = max(ys) - min(ys) < tol
        if not (horiz or vert):
            bad.append((i, pts))
    test.assertEqual(bad, [], msg=f"non-straight tubes: {bad}")
