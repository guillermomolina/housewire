from __future__ import annotations

from pathlib import Path

YAML_EXTENSIONS = (".yaml", ".yml")
EXCLUDED_DIR_NAMES = {".venv", "__pycache__", ".git", "out"}
HOUSEWIRE_NAMES = frozenset({"housewire.yaml", "housewire.yml"})


def is_yaml(path: Path) -> bool:
    return path.suffix.lower() in YAML_EXTENSIONS


def is_housewire_yaml(path: Path) -> bool:
    return path.name.lower() in HOUSEWIRE_NAMES


def is_excluded_path(path: Path, excluded_dirs: set[Path] | None = None) -> bool:
    excluded_dirs = excluded_dirs or set()
    resolved = path.resolve()
    if any(excluded in resolved.parents or resolved == excluded for excluded in excluded_dirs):
        return True
    return any(part in EXCLUDED_DIR_NAMES or part == "out" for part in resolved.parts)


def site_housewire_yaml(site_root: Path) -> Path | None:
    """Return the site-root housewire.yaml / .yml if present."""
    for name in ("housewire.yaml", "housewire.yml"):
        candidate = (site_root / name).resolve()
        if candidate.is_file() and not is_excluded_path(candidate):
            return candidate
    return None


def collect_yaml_from_directory(directory: Path, excluded_dirs: set[Path]) -> list[Path]:
    """Collect the single site housewire.yaml (no per-place YAML scan)."""
    del excluded_dirs  # site root only; kept for call-site compatibility
    found = site_housewire_yaml(directory)
    return [found] if found is not None else []

