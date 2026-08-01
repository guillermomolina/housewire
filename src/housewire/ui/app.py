"""FastAPI app: interactive physical floor canvas."""

from pathlib import Path
from typing import Any

from housewire.project.io import HOUSEWIRE_YAML
from housewire.project.session import ProjectSession
from housewire.project.view_layout import get_floor_physical_page, set_floor_physical_page
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
    app = FastAPI(title="housewire UI", version="0.20.0")

    def _session_docs() -> dict[Path, dict[str, Any]]:
        return {p: buf.doc for p, buf in session._buffers.items()}

    def _preload_floor(floor_id: str) -> Path:
        floor_dir = pg.floor_dir(root, floor_id)
        floor_yaml = floor_dir / HOUSEWIRE_YAML
        session.ensure_doc(floor_yaml)
        for _parts, path in pg.iter_place_yaml_under(floor_dir):
            session.ensure_doc(path)
        return floor_dir

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

    @app.get("/api/floors")
    def api_floors() -> dict[str, Any]:
        return {"floors": pg.list_floors(root)}

    @app.get("/api/physical")
    def api_physical(floor: str) -> dict[str, Any]:
        try:
            _preload_floor(floor)
            return pg.build_physical_graph(
                root, floor, session_docs=_session_docs()
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/physical/auto-layout")
    async def api_auto_layout(request: Request) -> dict[str, Any]:
        payload = await _json_body(request)
        floor_id = str(payload.get("floor_id") or "").strip()
        if not floor_id:
            raise HTTPException(400, "floor_id is required")
        force = bool(payload.get("force", False))
        try:
            floor_dir = _preload_floor(floor_id)
            docs = _session_docs()
            updated = pg.apply_auto_layout(
                root, floor_id, session_docs=docs, force=force
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        for node_id in updated:
            parts = tuple(p for p in node_id.split("/") if p)
            yaml_path = (floor_dir.joinpath(*parts) / HOUSEWIRE_YAML).resolve()
            if yaml_path in docs and yaml_path not in session._buffers:
                session.ensure_doc(yaml_path)
                session._buffers[yaml_path].doc = docs[yaml_path]
            session.mark_dirty(yaml_path)
        return {
            "updated": updated,
            "graph": pg.build_physical_graph(
                root, floor_id, session_docs=_session_docs()
            ),
        }

    @app.patch("/api/physical/positions")
    async def api_positions(request: Request) -> dict[str, Any]:
        payload = await _json_body(request)
        floor_id = str(payload.get("floor_id") or "").strip()
        if not floor_id:
            raise HTTPException(400, "floor_id is required")
        positions = payload.get("positions") or {}
        if not isinstance(positions, dict):
            raise HTTPException(400, "positions must be a map")
        try:
            floor_dir = _preload_floor(floor_id)
            docs = _session_docs()
            updated = pg.apply_positions(
                root, floor_id, positions, session_docs=docs
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        for node_id in updated:
            parts = tuple(p for p in node_id.split("/") if p)
            yaml_path = (floor_dir.joinpath(*parts) / HOUSEWIRE_YAML).resolve()
            session.mark_dirty(yaml_path)
        return {"updated": updated}

    @app.patch("/api/physical/page")
    async def api_page(request: Request) -> dict[str, Any]:
        payload = await _json_body(request)
        floor_id = str(payload.get("floor_id") or "").strip()
        if not floor_id:
            raise HTTPException(400, "floor_id is required")
        floor_dir = pg.floor_dir(root, floor_id)
        floor_yaml = floor_dir / HOUSEWIRE_YAML
        _path, doc = session.ensure_doc(floor_yaml)
        try:
            set_floor_physical_page(
                doc,
                width=payload.get("width"),
                height=payload.get("height"),
                representation=payload.get("representation"),
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        session.mark_dirty(floor_yaml)
        return {"page": get_floor_physical_page(doc)}

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
