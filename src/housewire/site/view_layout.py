"""Persisted canvas layout: ``view.physical`` / ``view.electrical`` / ``views.physical``."""
from __future__ import annotations

from typing import Any

REPRESENTATIONS = frozenset({"Line", "Tube"})
_ROTATIONS = frozenset({0, 90, 180, 270})


def _view_layer(obj: dict[str, Any], layer: str) -> dict[str, Any] | None:
    view = obj.get("view")
    if not isinstance(view, dict):
        return None
    layer_map = view.get(layer)
    return layer_map if isinstance(layer_map, dict) else None


def _get_xy(
    layer: dict[str, Any] | None, *, allow_negative: bool = False
) -> tuple[float, float] | None:
    if layer is None:
        return None
    x, y = layer.get("x"), layer.get("y")
    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
        fx, fy = float(x), float(y)
        if not allow_negative and (fx < 0 or fy < 0):
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
    allow_negative: bool = False,
) -> None:
    if not isinstance(obj, dict):
        raise ValueError("object must be a map")
    fx, fy = float(x), float(y)
    if not allow_negative and (fx < 0 or fy < 0):
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


def normalize_view_xy_siblings(
    nodes: list[dict[str, Any]], *, layer: str
) -> tuple[float, float]:
    """Shift ``view.{layer}`` x/y on siblings so all are ``>= 0``.

    Returns ``(dx, dy)`` applied (non-negative). Nodes without both x and y are
    skipped. Persistent layout keeps a parent-local origin at the content
    top-left; transient negatives from drag/resize are renormalized on commit.
    """
    positioned: list[tuple[dict[str, Any], float, float]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        raw = _get_xy(_view_layer(node, layer), allow_negative=True)
        if raw is None:
            continue
        positioned.append((node, raw[0], raw[1]))
    if not positioned:
        return 0.0, 0.0
    min_x = min(x for _n, x, _y in positioned)
    min_y = min(y for _n, _x, y in positioned)
    dx = -min_x if min_x < 0 else 0.0
    dy = -min_y if min_y < 0 else 0.0
    if dx == 0.0 and dy == 0.0:
        return 0.0, 0.0
    for node, x, y in positioned:
        _set_xy(node, layer, x + dx, y + dy)
    return dx, dy


def grow_view_size_by(
    obj: dict[str, Any], layer: str, dx: float, dy: float
) -> None:
    """Grow locked ``view.{layer}`` w/h by ``(dx, dy)`` when size is set."""
    if dx == 0.0 and dy == 0.0:
        return
    size = _get_wh(_view_layer(obj, layer))
    if size is None:
        return
    _set_wh(obj, layer, size[0] + float(dx), size[1] + float(dy))


def shift_place_origin(place: dict[str, Any], dx: float, dy: float) -> None:
    """Expand a place box toward N/W: move ``x``/``y`` by ``(-dx,-dy)`` and grow w/h.

    Used when children were shifted out of negative local coordinates so the
    west/north wall moves with the content instead of only growing east/south.
    """
    if dx == 0.0 and dy == 0.0:
        return
    raw = _get_xy(get_physical_view(place), allow_negative=True)
    if raw is not None:
        set_physical_position(
            place,
            raw[0] - float(dx),
            raw[1] - float(dy),
            allow_negative=True,
        )
    grow_view_size_by(place, "physical", dx, dy)


def _get_wh(layer: dict[str, Any] | None) -> tuple[float, float] | None:
    if layer is None:
        return None
    w, h = layer.get("w"), layer.get("h")
    if isinstance(w, (int, float)) and isinstance(h, (int, float)):
        fw, fh = float(w), float(h)
        if fw <= 0 or fh <= 0:
            return None
        return fw, fh
    return None


def _set_wh(obj: dict[str, Any], layer: str, w: float, h: float) -> None:
    layer_map = _ensure_view_layer(obj, layer)
    fw, fh = float(w), float(h)
    if fw <= 0 or fh <= 0:
        raise ValueError(f"view.{layer} w and h must be > 0")
    layer_map["w"] = fw
    layer_map["h"] = fh


def _clear_wh(obj: dict[str, Any], layer: str) -> None:
    layer_map = _view_layer(obj, layer)
    if layer_map is None:
        return
    layer_map.pop("w", None)
    layer_map.pop("h", None)
    if not layer_map:
        view = obj.get("view")
        if isinstance(view, dict):
            view.pop(layer, None)
            if not view:
                obj.pop("view", None)


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
    allow_negative: bool = False,
) -> None:
    """Write ``view.physical.x/y`` (and optional rotation) on a place map.

    Coordinates must be ``>= 0`` unless ``allow_negative`` (transient drag
    values before :func:`normalize_view_xy_siblings`).
    """
    _set_xy(
        place,
        "physical",
        x,
        y,
        rotation=rotation,
        allow_negative=allow_negative,
    )


def get_physical_size(place: dict[str, Any]) -> tuple[float, float] | None:
    """Return ``view.physical`` ``(w, h)`` when both are positive, else ``None``."""
    return _get_wh(get_physical_view(place))


def set_physical_size(place: dict[str, Any], w: float, h: float) -> None:
    """Write ``view.physical.w/h`` (canvas box size; must be ``> 0``)."""
    _set_wh(place, "physical", w, h)


def clear_physical_size(place: dict[str, Any]) -> None:
    """Drop ``view.physical.w/h`` so the next graph build auto-sizes."""
    _clear_wh(place, "physical")


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
    allow_negative: bool = False,
) -> None:
    """Write ``view.electrical.x/y`` (and optional rotation) on an element map.

    Coordinates are parent-local (inside the hosting place box) and must be
    ``>= 0`` unless ``allow_negative`` (transient before normalize).
    """
    _set_xy(
        element,
        "electrical",
        x,
        y,
        rotation=rotation,
        allow_negative=allow_negative,
    )


def get_electrical_size(element: dict[str, Any]) -> tuple[float, float] | None:
    """Return ``view.electrical`` ``(w, h)`` when both are positive, else ``None``."""
    return _get_wh(get_electrical_view(element))


def set_electrical_size(element: dict[str, Any], w: float, h: float) -> None:
    """Write ``view.electrical.w/h`` (element box size; must be ``> 0``)."""
    _set_wh(element, "electrical", w, h)


def clear_electrical_size(element: dict[str, Any]) -> None:
    """Drop ``view.electrical.w/h`` so the next graph build auto-sizes."""
    _clear_wh(element, "electrical")


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


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError(f"expected boolean, got {value!r}")


def _get_flips(layer: dict[str, Any] | None) -> tuple[bool, bool]:
    if layer is None:
        return False, False
    return bool(layer.get("flip_ns")), bool(layer.get("flip_we"))


def _ensure_view_layer(obj: dict[str, Any], layer: str) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise ValueError("object must be a map")
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
    return layer_map


def _set_flips(
    obj: dict[str, Any],
    layer: str,
    *,
    flip_ns: bool | None = None,
    flip_we: bool | None = None,
) -> None:
    """Write flip flags; drop keys when false to keep YAML tidy."""
    layer_map = _ensure_view_layer(obj, layer)
    cur_ns, cur_we = _get_flips(layer_map)
    ns = cur_ns if flip_ns is None else bool(flip_ns)
    we = cur_we if flip_we is None else bool(flip_we)
    if ns:
        layer_map["flip_ns"] = True
    else:
        layer_map.pop("flip_ns", None)
    if we:
        layer_map["flip_we"] = True
    else:
        layer_map.pop("flip_we", None)
    # Drop empty layer if only flips were present and both cleared — keep x/y.
    if not layer_map:
        view = obj.get("view")
        if isinstance(view, dict):
            view.pop(layer, None)
            if not view:
                obj.pop("view", None)


def get_physical_flips(place: dict[str, Any]) -> tuple[bool, bool]:
    """Return ``(flip_ns, flip_we)`` from ``view.physical`` (default false)."""
    return _get_flips(get_physical_view(place))


def set_physical_flips(
    place: dict[str, Any],
    *,
    flip_ns: bool | None = None,
    flip_we: bool | None = None,
) -> None:
    """Write ``view.physical.flip_ns`` / ``flip_we`` (omit when false)."""
    _set_flips(place, "physical", flip_ns=flip_ns, flip_we=flip_we)


def get_electrical_flips(element: dict[str, Any]) -> tuple[bool, bool]:
    """Return ``(flip_ns, flip_we)`` from ``view.electrical`` (default false)."""
    return _get_flips(get_electrical_view(element))


def set_electrical_flips(
    element: dict[str, Any],
    *,
    flip_ns: bool | None = None,
    flip_we: bool | None = None,
) -> None:
    """Write ``view.electrical.flip_ns`` / ``flip_we`` (omit when false)."""
    _set_flips(element, "electrical", flip_ns=flip_ns, flip_we=flip_we)


def parse_flip_field(raw: Any) -> bool:
    """Parse a Properties-panel flip value to bool."""
    return _parse_bool(raw)


def get_physical_page(place: dict[str, Any]) -> dict[str, Any]:
    """Return ``views.physical`` with defaults for page size / representation."""
    views = place.get("views")
    phys: dict[str, Any] = {}
    if isinstance(views, dict) and isinstance(views.get("physical"), dict):
        phys = dict(views["physical"])
    width = phys.get("width", 2000)
    height = phys.get("height", 1400)
    representation = phys.get("representation", "Tube")
    if representation not in REPRESENTATIONS:
        representation = "Tube"
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
