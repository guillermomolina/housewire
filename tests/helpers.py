"""Helpers compartidos por los tests."""
from __future__ import annotations

import tempfile
from pathlib import Path

from housewire.project.io import create_empty_house_file


def make_project() -> tuple[tempfile.TemporaryDirectory, Path, Path]:
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    yaml_path = root / "test.yaml"
    create_empty_house_file(yaml_path)
    return tmp, root, yaml_path
