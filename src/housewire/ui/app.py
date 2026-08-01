"""FastAPI app: interactive physical location canvas."""

from pathlib import Path
from typing import Any

from housewire.project.io import HOUSEWIRE_YAML
from housewire.project.session import ProjectSession
from housewire.project.view_layout import get_physical_page, set_physical_page
from housewire.ui import physical_graph as pg

STATIC_DIR = Path(__file__).resolve().parent / "static"

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles
except ImportError:  # pragma: no cover - optional extra
    FastAPI = None  # type: ignore[misc, assignment]
    HTTPException = None  # type: ignore[misc, assignment]
    Request = None  # type: ignore[misc, assignment]
    FileResponse = None  # type: ignore[misc, assignment]
    StaticFiles = None  # type: ignore[misc, assignment]


def create_app(site_root: Path) -> Any:
    """Build FastAPI app bound to one site directory."""
    if FastAPI is None:
        raise RuntimeError(
            "UI extras not installed. Run: pip install 'housewire[ui]'"
        )

    root = site_root.resolve()
    session = ProjectSession(root)
    app = FastAPI(title="housewire UI", version="0.22.0")

    def _session_docs() -> dict[Path, dict[str, Any]]:
        return {p: buf.doc for p, buf in session._buffers.items()}

    def _preload_location(location_id: str) -> Path:
        loc_dir = pg.location_dir(root, location_id)
        loc_yaml = loc_dir / HOUSEWIRE_YAML
        session.ensure_doc(loc_yaml)
        for _parts, path in pg.iter_place_yaml_under(
            loc_dir, session_docs=_session_docs()
        ):
            session.ensure_doc(path)
        return loc_dir

    def _graph(location_id: str, depth: int = 1) -> dict[str, Any]:
        _preload_location(location_id)
        return pg.build_physical_graph(
            root, location_id, depth=depth, session_docs=_session_docs()
        )

    def _depth_from(payload: dict[str, Any] | None = None, raw: int | None = None) -> int:
        value = raw if raw is not None else (payload or {}).get("depth", 1)
        try:
            depth = int(value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "depth must be an integer") from exc
        if depth < 1:
            raise HTTPException(400, "depth must be >= 1")
        return depth

    async def _json_body(request: Request) -> dict[str, Any]:
        data = await request.json()
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise HTTPException(400, "JSON body must be an object")
        return data

    @app.get("/")
    def index() -> FileResponse:
        index_path = STATIC_DIR / "index.html"
        if not index_path.is_file():
            raise HTTPException(404, "UI static files missing")
        return FileResponse(index_path)

    @app.get("/api/locations")
    def api_locations() -> dict[str, Any]:
        return {"locations": pg.list_canvas_locations(root)}

    @app.get("/api/outline")
    def api_outline() -> dict[str, Any]:
        return {"nodes": pg.list_site_outline(root)}

    @app.get("/api/physical")
    def api_physical(location: str, depth: int = 1) -> dict[str, Any]:
        try:
            return _graph(location, _depth_from(raw=depth))
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/place")
    def api_place(location: str, id: str) -> dict[str, Any]:
        from housewire.project.recipe_actions import place_detail

        try:
            _preload_location(location)
            return place_detail(
                session, canvas_location_id=location, place_id=id
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/physical/auto-layout")
    async def api_auto_layout(request: Request) -> dict[str, Any]:
        payload = await _json_body(request)
        location_id = str(payload.get("location_id") or "").strip()
        if not location_id:
            raise HTTPException(400, "location_id is required")
        force = bool(payload.get("force", False))
        depth = _depth_from(payload)
        try:
            loc_dir = _preload_location(location_id)
            docs = _session_docs()
            updated = pg.apply_auto_layout(
                root,
                location_id,
                session_docs=docs,
                depth=depth,
                force=force,
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        for node_id in updated:
            parts = tuple(p for p in node_id.split("/") if p)
            yaml_path = (loc_dir.joinpath(*parts) / HOUSEWIRE_YAML).resolve()
            if yaml_path in docs and yaml_path not in session._buffers:
                session.ensure_doc(yaml_path)
                session._buffers[yaml_path].doc = docs[yaml_path]
            session.reconcile_dirty(yaml_path)
        return {
            "updated": updated,
            "graph": _graph(location_id, depth),
        }

    @app.patch("/api/physical/positions")
    async def api_positions(request: Request) -> dict[str, Any]:
        payload = await _json_body(request)
        location_id = str(payload.get("location_id") or "").strip()
        if not location_id:
            raise HTTPException(400, "location_id is required")
        positions = payload.get("positions") or {}
        if not isinstance(positions, dict):
            raise HTTPException(400, "positions must be a map")
        try:
            loc_dir = _preload_location(location_id)
            docs = _session_docs()
            updated = pg.apply_positions(
                root, location_id, positions, session_docs=docs
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        for node_id in updated:
            parts = tuple(p for p in node_id.split("/") if p)
            yaml_path = (loc_dir.joinpath(*parts) / HOUSEWIRE_YAML).resolve()
            # Undo/redo back to disk positions should clear dirty.
            session.reconcile_dirty(yaml_path)
        return {"updated": updated}

    @app.patch("/api/electrical/positions")
    async def api_electrical_positions(request: Request) -> dict[str, Any]:
        payload = await _json_body(request)
        location_id = str(payload.get("location_id") or "").strip()
        if not location_id:
            raise HTTPException(400, "location_id is required")
        positions = payload.get("positions") or {}
        if not isinstance(positions, dict):
            raise HTTPException(400, "positions must be a map")
        try:
            loc_dir = _preload_location(location_id)
            docs = _session_docs()
            updated = pg.apply_electrical_positions(
                root, location_id, positions, session_docs=docs
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        touched: set[Path] = set()
        for node_id in updated:
            place_parts, _ename = pg.split_element_node_id(str(node_id))
            yaml_path = (
                (loc_dir / HOUSEWIRE_YAML).resolve()
                if not place_parts
                else (loc_dir.joinpath(*place_parts) / HOUSEWIRE_YAML).resolve()
            )
            touched.add(yaml_path)
        for yaml_path in touched:
            session.reconcile_dirty(yaml_path)
        return {"updated": updated}

    @app.post("/api/electrical/auto-layout")
    async def api_electrical_auto_layout(request: Request) -> dict[str, Any]:
        payload = await _json_body(request)
        location_id = str(payload.get("location_id") or "").strip()
        if not location_id:
            raise HTTPException(400, "location_id is required")
        force = bool(payload.get("force", False))
        depth = _depth_from(payload)
        try:
            loc_dir = _preload_location(location_id)
            docs = _session_docs()
            updated = pg.apply_electrical_auto_layout(
                root,
                location_id,
                session_docs=docs,
                depth=depth,
                force=force,
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        touched: set[Path] = set()
        for node_id in updated:
            place_parts, _ename = pg.split_element_node_id(str(node_id))
            yaml_path = (
                (loc_dir / HOUSEWIRE_YAML).resolve()
                if not place_parts
                else (loc_dir.joinpath(*place_parts) / HOUSEWIRE_YAML).resolve()
            )
            if yaml_path in docs and yaml_path not in session._buffers:
                session.ensure_doc(yaml_path)
                session._buffers[yaml_path].doc = docs[yaml_path]
            touched.add(yaml_path)
        for yaml_path in touched:
            session.reconcile_dirty(yaml_path)
        return {
            "updated": updated,
            "graph": _graph(location_id, depth),
        }

    @app.patch("/api/physical/page")
    async def api_page(request: Request) -> dict[str, Any]:
        payload = await _json_body(request)
        location_id = str(payload.get("location_id") or "").strip()
        if not location_id:
            raise HTTPException(400, "location_id is required")
        loc_dir = pg.location_dir(root, location_id)
        loc_yaml = loc_dir / HOUSEWIRE_YAML
        _path, doc = session.ensure_doc(loc_yaml)
        try:
            set_physical_page(
                doc,
                width=payload.get("width"),
                height=payload.get("height"),
                representation=payload.get("representation"),
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        session.mark_dirty(loc_yaml)
        return {"page": get_physical_page(doc)}

    @app.post("/api/recipes/socket")
    async def api_recipe_socket(request: Request) -> dict[str, Any]:
        from housewire.project.recipe_actions import run_socket_recipe

        payload = await _json_body(request)
        location_id = str(payload.get("location_id") or "").strip()
        name = str(payload.get("name") or "").strip()
        from_ref = str(payload.get("from") or "").strip()
        strip = str(payload.get("strip") or "").strip()
        if not location_id or not name or not from_ref or not strip:
            raise HTTPException(
                400, "location_id, name, from, and strip are required"
            )
        try:
            _preload_location(location_id)
            result = run_socket_recipe(
                session,
                name=name,
                from_ref=from_ref,
                strip=strip,
                pins=payload.get("pins"),
                to_opening=payload.get("to_opening"),
                colors=payload.get("colors"),
                section=payload.get("section"),
                label=payload.get("label"),
                notes=payload.get("notes"),
                canvas_location_id=location_id,
            )
            return {
                "result": result,
                "graph": _graph(location_id, _depth_from(payload)),
            }
        except (ValueError, FileExistsError, FileNotFoundError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/recipes/lamp")
    async def api_recipe_lamp(request: Request) -> dict[str, Any]:
        from housewire.project.recipe_actions import run_lamp_recipe

        payload = await _json_body(request)
        location_id = str(payload.get("location_id") or "").strip()
        name = str(payload.get("name") or "").strip()
        from_ref = str(payload.get("from") or "").strip()
        strip = str(payload.get("strip") or "").strip()
        pins = payload.get("pins")
        if not location_id or not name or not from_ref or not strip or not pins:
            raise HTTPException(
                400, "location_id, name, from, strip, and pins are required"
            )
        try:
            _preload_location(location_id)
            result = run_lamp_recipe(
                session,
                name=name,
                from_ref=from_ref,
                strip=strip,
                pins=pins,
                to_pins=payload.get("to_pins"),
                to_opening=payload.get("to_opening"),
                colors=payload.get("colors"),
                section=payload.get("section"),
                label=payload.get("label"),
                notes=payload.get("notes"),
                canvas_location_id=location_id,
            )
            return {
                "result": result,
                "graph": _graph(location_id, _depth_from(payload)),
            }
        except (ValueError, FileExistsError, FileNotFoundError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/recipes/feed")
    async def api_recipe_feed(request: Request) -> dict[str, Any]:
        from housewire.project.recipe_actions import run_feed_recipe

        payload = await _json_body(request)
        location_id = str(payload.get("location_id") or "").strip()
        name = str(payload.get("name") or "").strip()
        from_ref = str(payload.get("from") or "").strip()
        to_ref = str(payload.get("to") or "").strip()
        from_pin = str(payload.get("from_pin") or "").strip()
        to_pin = str(payload.get("to_pin") or "").strip()
        if not all([location_id, name, from_ref, to_ref, from_pin, to_pin]):
            raise HTTPException(
                400,
                "location_id, name, from, to, from_pin, and to_pin are required",
            )
        try:
            _preload_location(location_id)
            result = run_feed_recipe(
                session,
                name=name,
                from_ref=from_ref,
                to_ref=to_ref,
                from_pin=from_pin,
                to_pin=to_pin,
                colors=payload.get("colors"),
                section=payload.get("section"),
                notes=payload.get("notes"),
                canvas_location_id=location_id,
            )
            return {
                "result": result,
                "graph": _graph(location_id, _depth_from(payload)),
            }
        except (ValueError, FileExistsError, FileNotFoundError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/save")
    def api_save() -> dict[str, Any]:
        try:
            saved = [str(p.relative_to(root)) for p in session.save_all()]
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"saved": saved}

    @app.get("/api/status")
    def api_status() -> dict[str, Any]:
        dirty = [str(p.relative_to(root)) for p in session.dirty_paths()]
        return {"dirty": dirty, "site": str(root)}

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    return app


def run_serve(
    site_root: Path, *, host: str = "127.0.0.1", port: int = 8765
) -> None:
    """Run uvicorn for the UI."""
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError(
            "UI extras not installed. Run: pip install 'housewire[ui]'"
        ) from exc
    app = create_app(site_root)
    print(f"housewire UI → http://{host}:{port}/  (site: {site_root})")
    uvicorn.run(app, host=host, port=port, log_level="info")
