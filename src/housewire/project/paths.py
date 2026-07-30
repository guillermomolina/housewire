from __future__ import annotations

from pathlib import Path

YAML_EXTENSIONS = (".yaml", ".yml")
EXCLUDED_DIR_NAMES = {".venv", "__pycache__", ".git", "out"}
INDEX_NAMES = frozenset({"index.yaml", "index.yml"})


def is_yaml(path: Path) -> bool:
    return path.suffix.lower() in YAML_EXTENSIONS


def is_index_yaml(path: Path) -> bool:
    return path.name.lower() in INDEX_NAMES


def is_excluded_path(path: Path, excluded_dirs: set[Path] | None = None) -> bool:
    excluded_dirs = excluded_dirs or set()
    resolved = path.resolve()
    if any(excluded in resolved.parents or resolved == excluded for excluded in excluded_dirs):
        return True
    return any(part in EXCLUDED_DIR_NAMES or part == "out" for part in resolved.parts)


def collect_yaml_from_directory(directory: Path, excluded_dirs: set[Path]) -> list[Path]:
    """Collect only index.yaml / index.yml under the site tree (one file per location)."""
    return sorted(
        path.resolve()
        for path in directory.rglob("*")
        if path.is_file()
        and is_index_yaml(path)
        and not is_excluded_path(path, excluded_dirs)
    )
