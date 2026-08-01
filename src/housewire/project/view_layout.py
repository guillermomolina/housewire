"""Persisted canvas layout: ``view.physical`` / ``views.physical`` on places."""
from __future__ import annotations

from typing import Any

REPRESENTATIONS = frozenset({"line", "tube"})


def get_physical_view(place: dict[str, Any]) -> dict[str, Any] | None:
    """Return ``view.physical`` map or ``None``."""
    view = place.get("view")
    if not isinstance(view, dict):
        return None
    phys = view.get("physical")
    return phys if isinstance(phys, dict) else None


def get_physical_position(
    place: dict[str, Any],
) -> tuple[float, float] | None:
    """Return ``(x, y)`` if both are numeric, else ``None``."""
    phys = get_physical_view(place)
    if phys is None:
        return None
    x, y = phys.get("x"), phys.get("y")
    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
        return float(x), float(y)
    return None


def set_physical_position(
    place: dict[str, Any],
    x: float,
    y: float,
    *,
    rotation: int | None = None,
) -> None:
    """Write ``view.physical.x/y`` (and optional rotation) on a place map."""
    if not isinstance(place, dict):
        raise ValueError("place must be a map")
    view = place.get("view")
    if view is None:
        view = {}
        place["view"] = view
    elif not isinstance(view, dict):
        raise ValueError("view must be a map")
    phys = view.get("physical")
    if phys is None:
        phys = {}
        view["physical"] = phys
    elif not isinstance(phys, dict):
        raise ValueError("view.physical must be a map")
    phys["x"] = float(x)
    phys["y"] = float(y)
    if rotation is not None:
        rot = int(rotation)
        if rot not in (0, 90, 180, 270):
            raise ValueError("rotation must be 0, 90, 180, or 270")
        phys["rotation"] = rot


def get_physical_page(place: dict[str, Any]) -> dict[str, Any]:
    """Return ``views.physical`` with defaults for page size / representation."""
    views = place.get("views")
    phys: dict[str, Any] = {}
    if isinstance(views, dict) and isinstance(views.get("physical"), dict):
        phys = dict(views["physical"])
    width = phys.get("width", 2000)
    height = phys.get("height", 1400)
    representation = phys.get("representation", "line")
    if representation not in REPRESENTATIONS:
        representation = "line"
    return {
        "width": float(width),
        "height": float(height),
        "representation": representation,
    }


def set_physical_page(
    place: dict[str, Any],
    *,
    width: float | None = None,
    height: float | None = None,
    representation: str | None = None,
) -> None:
    """Update ``views.physical`` page settings on a place (canvas root)."""
    if not isinstance(place, dict):
        raise ValueError("place must be a map")
    views = place.get("views")
    if views is None:
        views = {}
        place["views"] = views
    elif not isinstance(views, dict):
        raise ValueError("views must be a map")
    phys = views.get("physical")
    if phys is None:
        phys = {}
        views["physical"] = phys
    elif not isinstance(phys, dict):
        raise ValueError("views.physical must be a map")
    if width is not None:
        phys["width"] = float(width)
    if height is not None:
        phys["height"] = float(height)
    if representation is not None:
        if representation not in REPRESENTATIONS:
            raise ValueError(
                f"representation must be one of: {', '.join(sorted(REPRESENTATIONS))}"
            )
        phys["representation"] = representation
