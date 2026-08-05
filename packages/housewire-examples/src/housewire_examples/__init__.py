"""Public example sites for HouseWire demos and E2E."""

from __future__ import annotations

import os
import tempfile
from importlib import resources
from pathlib import Path

__version__ = "0.2.3"

_SITES = resources.files("housewire_examples").joinpath("sites")


def iter_site_names() -> list[str]:
    """Return example site stems (e.g. ``Route_21``)."""
    names: list[str] = []
    for entry in _SITES.iterdir():
        if entry.name.endswith(".yaml"):
            names.append(entry.name[: -len(".yaml")])
    return sorted(names)


def site_yaml(name: str = "Route_21") -> Path:
    """Return a filesystem path to an example site YAML.

    Raises ``FileNotFoundError`` if ``name`` is unknown. When the resource
    lives inside a zip wheel, the file is materialized under a temp cache.
    Default is ``Route_21`` (reference panel + room).
    """
    stem = name.removesuffix(".yaml")
    resource = _SITES.joinpath(f"{stem}.yaml")
    if not resource.is_file():
        known = ", ".join(iter_site_names()) or "(none)"
        raise FileNotFoundError(
            f"Unknown example site {name!r}. Available: {known}"
        )
    # On-disk installs (editable / extracted wheel): use the real path.
    try:
        path = Path(os.fspath(resource))  # type: ignore[arg-type]
        if path.is_file():
            return path.resolve()
    except (TypeError, OSError, ValueError):
        pass
    cache = Path(tempfile.gettempdir()) / "housewire-examples"
    cache.mkdir(parents=True, exist_ok=True)
    dest = cache / f"{stem}.yaml"
    dest.write_bytes(resource.read_bytes())
    return dest.resolve()
