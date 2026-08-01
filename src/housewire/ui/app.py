"""FastAPI app: interactive physical location canvas."""

from pathlib import Path
from typing import Any

from housewire import __version__
from housewire.project.view_layout import get_physical_page, set_physical_page
from housewire.ui import physical_graph as pg
from housewire.ui.workspace import Workspace, create_workspace

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


def create_app(site_root: Path | None = None) -> Any:
    """Build FastAPI app with an in-process workspace (optional initial site)."""
    if FastAPI is None:
        raise RuntimeError(
            "UI extras not installed. Run: pip install 'housewire[ui]'"
        )

    workspace: Workspace = create_workspace(site_root)
    app = FastAPI(title="housewire UI", version=__version__)

    def _session():
        try:
            return workspace.require_session()
        except FileNotFoundError as exc:
            raise HTTPException(409, str(exc)) from exc

    def _root() -> Path:
        try:
            return workspace.require_root()
        except FileNotFoundError as exc:
            raise HTTPException(409, str(exc)) from exc

    def _session_docs() -> dict[Path, dict[str, Any]]:
        session = _session()
        return {p: buf.doc for p, buf in session._buffers.items()}

    def _site_yaml() -> Path:
        return _session().site_yaml()

    def _preload_location(location_id: str) -> Path:
        del location_id
        session = _session()
        session.ensure_doc(_site_yaml())
        return _root()

    def _graph(location_id: str, depth: int = 1) -> dict[str, Any]:
        root = _preload_location(location_id)
        return pg.build_physical_graph(
            root, location_id, depth=depth, session_docs=_session_docs()
        )

    def _touch_site() -> None:
        _session().reconcile_dirty(_site_yaml())

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

    @app.get("/api/workspace")
    def api_workspace() -> dict[str, Any]:
        return workspace.status()

    @app.post("/api/workspace/open")
    async def api_workspace_open(request: Request) -> dict[str, Any]:
        payload = await _json_body(request)
        force = bool(payload.get("force", False))
        path = str(payload.get("path") or "").strip()
        if not path:
            raise HTTPException(400, "path is required")
        try:
            workspace.open_site(Path(path), force=force)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except NotADirectoryError as exc:
            raise HTTPException(400, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return workspace.status()

    @app.post("/api/workspace/open-content")
    async def api_workspace_open_content(request: Request) -> dict[str, Any]:
        """Open a YAML document chosen via the browser file picker."""
        payload = await _json_body(request)
        force = bool(payload.get("force", False))
        filename = str(payload.get("filename") or "").strip()
        content = payload.get("content")
        if not filename:
            raise HTTPException(400, "filename is required")
        if not isinstance(content, str):
            raise HTTPException(400, "content must be a string")
        try:
            workspace.open_yaml_content(filename, content, force=force)
        except ValueError as exc:
            msg = str(exc)
            code = 409 if "unsaved" in msg.lower() else 400
            raise HTTPException(code, msg) from exc
        return workspace.status()

    @app.get("/api/workspace/yaml")
    def api_workspace_yaml() -> dict[str, str]:
        try:
            return workspace.yaml_export()
        except FileNotFoundError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/workspace/close")
    async def api_workspace_close(request: Request) -> dict[str, Any]:
        payload = await _json_body(request)
        force = bool(payload.get("force", False))
        try:
            workspace.close(force=force)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return workspace.status()

    @app.post("/api/workspace/save-as")
    async def api_workspace_save_as(request: Request) -> dict[str, Any]:
        payload = await _json_body(request)
        path = str(payload.get("path") or "").strip()
        if not path:
            raise HTTPException(400, "path is required")
        force = bool(payload.get("force", False))
        try:
            workspace.save_as(Path(path), force=force)
        except FileNotFoundError as exc:
            raise HTTPException(409, str(exc)) from exc
        except FileExistsError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except OSError as exc:
            raise HTTPException(400, str(exc)) from exc
        return workspace.status()

    @app.get("/api/locations")
    def api_locations() -> dict[str, Any]:
        return {"locations": pg.list_canvas_locations(_root())}

    @app.get("/api/outline")
    def api_outline() -> dict[str, Any]:
        return {"nodes": pg.list_site_outline(_root())}

    @app.get("/api/catalog")
    def api_catalog() -> dict[str, Any]:
        from housewire.house import load_catalog

        root = _root()
        cat = load_catalog(root)
        types = {
            type_id: {
                "id": type_id,
                "kind": data.get("kind"),
                "title": data.get("title"),
                "icon": data.get("icon") or "fa-circle",
            }
            for type_id, data in sorted(cat.items())
            if isinstance(data, dict)
        }
        return {"types": types}

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
                _session(), canvas_location_id=location, place_id=id
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
        session = _session()
        root = _root()
        try:
            _preload_location(location_id)
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
        site = _site_yaml()
        if site in docs:
            if site not in session._buffers:
                session.ensure_doc(site)
            session._buffers[site].doc = docs[site]
        _touch_site()
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
            _preload_location(location_id)
            docs = _session_docs()
            updated = pg.apply_positions(
                _root(), location_id, positions, session_docs=docs
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        _touch_site()
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
            _preload_location(location_id)
            docs = _session_docs()
            updated = pg.apply_electrical_positions(
                _root(), location_id, positions, session_docs=docs
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        _touch_site()
        return {"updated": updated}

    @app.post("/api/electrical/auto-layout")
    async def api_electrical_auto_layout(request: Request) -> dict[str, Any]:
        payload = await _json_body(request)
        location_id = str(payload.get("location_id") or "").strip()
        if not location_id:
            raise HTTPException(400, "location_id is required")
        force = bool(payload.get("force", False))
        depth = _depth_from(payload)
        session = _session()
        try:
            _preload_location(location_id)
            docs = _session_docs()
            updated = pg.apply_electrical_auto_layout(
                _root(),
                location_id,
                session_docs=docs,
                depth=depth,
                force=force,
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        site = _site_yaml()
        if site in docs:
            if site not in session._buffers:
                session.ensure_doc(site)
            session._buffers[site].doc = docs[site]
        _touch_site()
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
        session = _session()
        loc_yaml = _site_yaml()
        _path, doc = session.ensure_doc(loc_yaml)
        from housewire.project.tree import get_place_node, logical_parts_from_id

        place = get_place_node(doc, logical_parts_from_id(location_id))
        try:
            set_physical_page(
                place,
                width=payload.get("width"),
                height=payload.get("height"),
                representation=payload.get("representation"),
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        session.mark_dirty(loc_yaml)
        return {"page": get_physical_page(place)}

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
                _session(),
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
                _session(),
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
                _session(),
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
        session = _session()
        root = _root()
        try:
            saved = [str(p.relative_to(root)) for p in session.save_all()]
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        yaml_path = session.site_yaml()
        try:
            text = yaml_path.read_text(encoding="utf-8")
        except OSError:
            text = workspace.yaml_export()["content"]
        doc = workspace.document
        return {
            "saved": saved,
            "filename": yaml_path.name,
            "yaml": text,
            "browser_origin": bool(doc and doc.browser_origin),
        }

    @app.get("/api/status")
    def api_status() -> dict[str, Any]:
        return workspace.status()

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
