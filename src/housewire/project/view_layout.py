"""Persisted canvas layout: ``view.physical`` / ``view.electrical`` / ``views.physical``."""
from __future__ import annotations

from typing import Any

REPRESENTATIONS = frozenset({"line", "tube"})
_ROTATIONS = frozenset({0, 90, 180, 270})


def _view_layer(obj: dict[str, Any], layer: str) -> dict[str, Any] | None:
    view = obj.get("view")
    if not isinstance(view, dict):
        return None
    layer_map = view.get(layer)
    return layer_map if isinstance(layer_map, dict) else None


def _get_xy(layer: dict[str, Any] | None) -> tuple[float, float] | None:
    if layer is None:
        return None
    x, y = layer.get("x"), layer.get("y")
    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
        fx, fy = float(x), float(y)
        if fx < 0 or fy < 0:
            return None
        return fx, fy
    return None


def _set_xy(
    obj: dict[str, Any],
    layer: str,
    x: float,
    y: float,
    *,
    rotation: int | None = None,
) -> None:
    if not isinstance(obj, dict):
        raise ValueError("object must be a map")
    fx, fy = float(x), float(y)
    if fx < 0 or fy < 0:
        raise ValueError(f"view.{layer} x and y must be >= 0")
    view = obj.get("view")
    if view is None:
        view = {}
        obj["view"] = view
    elif not isinstance(view, dict):
        raise ValueError("view must be a map")
    layer_map = view.get(layer)
    if layer_map is None:
        layer_map = {}
        view[layer] = layer_map
    elif not isinstance(layer_map, dict):
        raise ValueError(f"view.{layer} must be a map")
    layer_map["x"] = fx
    layer_map["y"] = fy
    if rotation is not None:
        rot = int(rotation)
        if rot not in _ROTATIONS:
            raise ValueError("rotation must be 0, 90, 180, or 270")
        layer_map["rotation"] = rot


def get_physical_view(place: dict[str, Any]) -> dict[str, Any] | None:
    """Return ``view.physical`` map or ``None``."""
    return _view_layer(place, "physical")


def get_physical_position(
    place: dict[str, Any],
) -> tuple[float, float] | None:
    """Return ``(x, y)`` if both are non-negative numbers, else ``None``."""
    return _get_xy(get_physical_view(place))


def set_physical_position(
    place: dict[str, Any],
    x: float,
    y: float,
    *,
    rotation: int | None = None,
) -> None:
    """Write ``view.physical.x/y`` (and optional rotation) on a place map.

    Coordinates must be ``>= 0`` (window layout uses parent-local origin).
    """
    _set_xy(place, "physical", x, y, rotation=rotation)


def get_electrical_view(element: dict[str, Any]) -> dict[str, Any] | None:
    """Return ``view.electrical`` map on an element or ``None``."""
    return _view_layer(element, "electrical")


def get_electrical_position(
    element: dict[str, Any],
) -> tuple[float, float] | None:
    """Return element ``view.electrical`` ``(x, y)`` or ``None``."""
    return _get_xy(get_electrical_view(element))


def set_electrical_position(
    element: dict[str, Any],
    x: float,
    y: float,
    *,
    rotation: int | None = None,
) -> None:
    """Write ``view.electrical.x/y`` (and optional rotation) on an element map.

    Coordinates are parent-local (inside the hosting place box) and must be
    ``>= 0``.
    """
    _set_xy(element, "electrical", x, y, rotation=rotation)


def get_electrical_rotation(element: dict[str, Any]) -> int:
    """Return ``view.electrical.rotation`` or ``0``."""
    layer = get_electrical_view(element)
    if layer is None:
        return 0
    rot = layer.get("rotation", 0)
    try:
        value = int(rot)
    except (TypeError, ValueError):
        return 0
    return value if value in _ROTATIONS else 0


def get_physical_page(place: dict[str, Any]) -> dict[str, Any]:
    """Return ``views.physical`` with defaults for page size / representation."""
    views = place.get("views")
    phys: dict[str, Any] = {}
    if isinstance(views, dict) and isinstance(views.get("physical"), dict):
        phys = dict(views["physical"])
    width = phys.get("width", 2000)
    height = phys.get("height", 1400)
    representation = phys.get("representation", "tube")
    if representation not in REPRESENTATIONS:
        representation = "tube"
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
