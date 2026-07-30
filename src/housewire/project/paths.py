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


def collect_yaml_from_directory(directory: Path, excluded_dirs: set[Path]) -> list[Path]:
    """Collect only housewire.yaml / housewire.yml under the site tree."""
    return sorted(
        path.resolve()
        for path in directory.rglob("*")
        if path.is_file()
        and is_housewire_yaml(path)
        and not is_excluded_path(path, excluded_dirs)
    )
