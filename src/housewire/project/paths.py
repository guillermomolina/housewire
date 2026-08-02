from __future__ import annotations

from pathlib import Path

YAML_EXTENSIONS = (".yaml", ".yml")
EXCLUDED_DIR_NAMES = {".venv", "__pycache__", ".git", "out"}
# Preferred default filenames when creating a new site document.
HOUSEWIRE_NAMES = frozenset({"housewire.yaml", "housewire.yml"})


def is_yaml(path: Path) -> bool:
    return path.suffix.lower() in YAML_EXTENSIONS


def is_housewire_yaml(path: Path) -> bool:
    """True for the classic default site filenames (not every site YAML)."""
    return path.name.lower() in HOUSEWIRE_NAMES


def is_excluded_path(path: Path, excluded_dirs: set[Path] | None = None) -> bool:
    excluded_dirs = excluded_dirs or set()
    resolved = path.resolve()
    if any(excluded in resolved.parents or resolved == excluded for excluded in excluded_dirs):
        return True
    return any(part in EXCLUDED_DIR_NAMES or part == "out" for part in resolved.parts)


def list_root_yaml_files(site_root: Path) -> list[Path]:
    """YAML files directly under the site root (not recursive)."""
    if not site_root.is_dir():
        return []
    rows: list[Path] = []
    for child in sorted(site_root.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_file():
            continue
        if child.name.endswith(".bak"):
            continue
        if not is_yaml(child) or is_excluded_path(child):
            continue
        rows.append(child.resolve())
    return rows


def split_project_arg(path: Path) -> tuple[Path, Path | None]:
    """Split a CLI project argument into ``(site_root, site_yaml_or_None)``.

    - YAML file → ``(parent, file)``
    - directory → ``(directory, None)`` (caller discovers the site YAML)
    """
    target = path.expanduser().resolve()
    if not target.exists():
        raise FileNotFoundError(f"Path not found: {target}")
    if target.is_file():
        if not is_yaml(target):
            raise ValueError(f"Not a YAML file: {target}")
        return target.parent, target
    if target.is_dir():
        return target, None
    raise ValueError(f"Unsupported project path: {target}")


def find_site_yaml(
    site_root: Path,
    *,
    preferred: str | Path | None = None,
) -> Path | None:
    """Locate the site document YAML under ``site_root``.

    Resolution order:
    1. ``preferred`` name (if given and present)
    2. ``housewire.yaml`` / ``housewire.yml``
    3. the only ``.yaml`` / ``.yml`` file at the site root

    Returns ``None`` when missing or when several non-default YAMLs exist.
    """
    if preferred is not None:
        name = preferred.name if isinstance(preferred, Path) else str(preferred)
        candidate = (site_root / name).resolve()
        if candidate.is_file() and is_yaml(candidate) and not is_excluded_path(candidate):
            return candidate
        return None

    for name in ("housewire.yaml", "housewire.yml"):
        candidate = (site_root / name).resolve()
        if candidate.is_file() and not is_excluded_path(candidate):
            return candidate

    found = list_root_yaml_files(site_root)
    if len(found) == 1:
        return found[0]
    return None


def site_housewire_yaml(site_root: Path) -> Path | None:
    """Return the site-root document YAML if present (any allowed name)."""
    return find_site_yaml(site_root)


def collect_yaml_from_directory(directory: Path, excluded_dirs: set[Path]) -> list[Path]:
    """Collect the single site YAML (no per-place YAML scan)."""
    del excluded_dirs  # site root only; kept for call-site compatibility
    found = find_site_yaml(directory)
    return [found] if found is not None else []
