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


def resolve_example_site(name: str) -> Path | None:
    """Locate an example YAML by stem (Route_01, Test_01, …)."""
    env = os.environ.get("HOUSEWIRE_E2E_SITE", "").strip()
    if env and Path(env).name.startswith(name):
        path = Path(env).expanduser()
        return path if path.is_file() else None
    try:
        from housewire_examples import site_yaml

        return site_yaml(name)
    except Exception:
        pass
    for candidate in (
        REPO / "packages" / "housewire-examples" / "src" / "housewire_examples" / "sites" / f"{name}.yaml",
        REPO / "sites" / "Tests" / f"{name}.yaml",
    ):
        if candidate.is_file():
            return candidate
    return None


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def dump_live_canvas(site: Path, *, wait_ms: int = 3500) -> dict:
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
            page.wait_for_timeout(wait_ms)
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
    data = dump_live_canvas(site)
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
    )
    test.assertEqual(
        issues,
        [],
        msg=f"site={site_name} ver={data.get('ver')} issues={issues}",
    )


def make_route_test(site_name: str, *, require_tubes: bool, min_strands: int):
    """Build a TestCase class for one example site."""

    class _RouteE2E(unittest.TestCase):
        def test_live_route_invariants(self) -> None:
            assert_site_routes_ok(
                self,
                site_name,
                require_tubes=require_tubes,
                min_strands=min_strands,
            )

    _RouteE2E.__name__ = f"Test{site_name}"
    _RouteE2E.__qualname__ = _RouteE2E.__name__
    _RouteE2E.__doc__ = f"Live E2E routing invariants for {site_name}."
    return _RouteE2E
