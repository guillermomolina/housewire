#!/usr/bin/env python3
"""Migrate example / site YAMLs to sprite AABB physical bounds.

Rewrites iso leaves: x/y -= 20, w/h += 20, bounds: sprite.
Run from the repo root:

  .venv/bin/python scripts/migrate_sprite_bounds.py packages/housewire-examples/src/housewire_examples/sites
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from housewire.site.io import load_yaml, save_yaml  # noqa: E402
from housewire.site.view_layout import migrate_site_physical_to_sprite  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: migrate_sprite_bounds.py <dir-or-yaml>...", file=sys.stderr)
        return 2
    paths: list[Path] = []
    for arg in argv[1:]:
        p = Path(arg).expanduser().resolve()
        if p.is_dir():
            paths.extend(sorted(p.glob("*.yaml")))
            paths.extend(sorted(p.glob("*.yml")))
        elif p.is_file():
            paths.append(p)
        else:
            print(f"skip missing {p}", file=sys.stderr)
    n_files = 0
    for path in paths:
        doc = load_yaml(path)
        changed = migrate_site_physical_to_sprite(doc)
        if not changed:
            continue
        save_yaml(path, doc)
        n_files += 1
        print(f"{path}: migrated {changed} place(s)")
    print(f"updated {n_files} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
