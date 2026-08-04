"""FastAPI app: interactive physical location canvas."""

from contextvars import ContextVar
from pathlib import Path
from typing import Any

from housewire import (
    __author__,
    __copyright__,
    __license__,
    __repository__,
    __title__,
    __version__,
)
from housewire.i18n import normalize_locale
from housewire.site.view_layout import get_physical_page, set_physical_page
from housewire.ui import physical_graph as pg
from housewire.ui.workspace import Workspace, create_workspace

STATIC_DIR = Path(__file__).resolve().parent / "static"
_request_locale: ContextVar[str] = ContextVar("housewire_request_locale", default="en")

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import FileResponse, HTMLResponse
    from fastapi.staticfiles import StaticFiles
except ImportError:  # pragma: no cover - optional extra
    FastAPI = None  # type: ignore[misc, assignment]
    HTTPException = None  # type: ignore[misc, assignment]
    Request = None  # type: ignore[misc, assignment]
    FileResponse = None  # type: ignore[misc, assignment]
    HTMLResponse = None  # type: ignore[misc, assignment]
    StaticFiles = None  # type: ignore[misc, assignment]


def create_app(site_root: Path | None = None) -> Any:
    """Build FastAPI app with an in-process workspace (optional initial site)."""
    if FastAPI is None:
        raise RuntimeError(
            "UI extras not installed. Run: pip install 'housewire[ui]'"
        )

    workspace: Workspace = create_workspace(site_root)
    app = FastAPI(title=f"{__title__} UI", version=__version__)

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

    def _locale_from_request(
        request: Request | None = None,
        *,
        body: dict[str, Any] | None = None,
        raw: str | None = None,
    ) -> str:
        if raw is not None and str(raw).strip():
            return normalize_locale(raw)
        if body and body.get("lang") is not None:
            return normalize_locale(body.get("lang"))
        if request is not None:
            q = request.query_params.get("lang")
            if q:
                return normalize_locale(q)
            accept = request.headers.get("accept-language") or ""
            if accept:
                first = accept.split(",", 1)[0].split(";", 1)[0]
                return normalize_locale(first)
        return normalize_locale(None)

    def _set_request_locale(locale: str) -> None:
        _request_locale.set(normalize_locale(locale))

    @app.middleware("http")
    async def _locale_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        _set_request_locale(_locale_from_request(request))
        return await call_next(request)

    def _graph(
        location_id: str, depth: int = 1, *, locale: str | None = None
    ) -> dict[str, Any]:
        root = _preload_location(location_id)
        loc = locale if locale is not None else _request_locale.get()
        return pg.build_physical_graph(
            root,
            location_id,
            depth=depth,
            session_docs=_session_docs(),
            locale=loc,
        )

    def _touch_site() -> None:
        _session().reconcile_dirty(_site_yaml())

    def _edit_meta() -> dict[str, Any]:
        session = _session()
        flags = session.edit_flags(_site_yaml())
        dirty = bool(session.dirty_paths())
        return {**flags, "dirty": dirty}

    def _begin_edit() -> None:
        _session().prepare_edit(_site_yaml())

    def _end_edit() -> dict[str, Any]:
        session = _session()
        session.commit_edit(_site_yaml())
        _touch_site()
        return _edit_meta()

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
    def index() -> HTMLResponse:
        index_path = STATIC_DIR / "index.html"
        if not index_path.is_file():
            raise HTTPException(404, "UI static files missing")
        html = index_path.read_text(encoding="utf-8")
        # Bust caches with the live package version (index.html may lag).
        html = html.replace("?v=0.35.1", f"?v={__version__}")
        html = html.replace("?v=__VERSION__", f"?v={__version__}")
        return HTMLResponse(
            html,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
            },
        )

    @app.get("/api/about")
    def api_about(request: Request) -> dict[str, Any]:
        """Program identity for Help → About (and CLI/docs consumers)."""
        from housewire.i18n import about_description_for

        locale = _locale_from_request(request)
        return {
            "title": __title__,
            "version": __version__,
            "author": __author__,
            "description": about_description_for(locale),
            "license": __license__,
            "copyright": __copyright__,
            "repository": __repository__,
            "lang": locale,
        }

    @app.get("/api/wire-colors")
    def api_wire_colors() -> dict[str, Any]:
        """Canonical HouseWire conductor color palette (IEC 60757 letter codes)."""
        from housewire.house.wire_colors import wire_colors_payload

        return wire_colors_payload()

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
        """Open a YAML document chosen via the browser file picker (new tab)."""
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

    @app.post("/api/workspace/activate")
    async def api_workspace_activate(request: Request) -> dict[str, Any]:
        payload = await _json_body(request)
        doc_id = str(payload.get("id") or "").strip()
        if not doc_id:
            raise HTTPException(400, "id is required")
        try:
            workspace.activate(doc_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
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
        raw_id = payload.get("id")
        doc_id = str(raw_id).strip() if raw_id else None
        try:
            workspace.close(force=force, doc_id=doc_id or None)
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
        return {
            "locations": pg.list_canvas_locations(
                _root(),
                site_yaml=_site_yaml(),
                session_docs=_session_docs(),
            )
        }

    @app.get("/api/outline")
    def api_outline(request: Request) -> dict[str, Any]:
        locale = _locale_from_request(request)
        _set_request_locale(locale)
        return {
            "nodes": pg.list_site_outline(
                _root(),
                site_yaml=_site_yaml(),
                session_docs=_session_docs(),
                locale=locale,
            )
        }

    @app.get("/api/catalog")
    def api_catalog(request: Request) -> dict[str, Any]:
        from housewire.house import (
            catalog_type_description,
            catalog_type_label,
            load_catalog,
        )

        root = _root()
        cat = load_catalog(root)
        locale = _locale_from_request(request)
        _set_request_locale(locale)
        types = {
            type_id: {
                "type": type_id,
                "kind": data.get("kind"),
                "label": catalog_type_label(type_id, catalog=cat, locale=locale),
                "description": catalog_type_description(
                    type_id, catalog=cat, locale=locale
                ),
                "subtypes": (
                    [
                        {
                            "subtype": str(sub_id),
                            "label": catalog_type_label(
                                type_id,
                                catalog=cat,
                                subtype=str(sub_id),
                                locale=locale,
                            ),
                            "description": catalog_type_description(
                                type_id,
                                catalog=cat,
                                subtype=str(sub_id),
                                locale=locale,
                            ),
                        }
                        for sub_id in sorted(
                            (data.get("subtypes") or {}).keys(), key=lambda s: str(s)
                        )
                    ]
                    if isinstance(data.get("subtypes"), dict)
                    else []
                ),
                "icon": data.get("icon") or "circle",
            }
            for type_id, data in sorted(cat.items())
            if isinstance(data, dict)
        }
        return {"types": types, "lang": locale}

    @app.get("/api/physical")
    def api_physical(
        request: Request, location: str, depth: int = 1
    ) -> dict[str, Any]:
        try:
            locale = _locale_from_request(request)
            _set_request_locale(locale)
            return _graph(location, _depth_from(raw=depth), locale=locale)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/place")
    def api_place(location: str, id: str) -> dict[str, Any]:
        from housewire.site.recipe_actions import place_detail

        try:
            _preload_location(location)
            return place_detail(
                _session(), canvas_location_id=location, place_id=id
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.patch("/api/place/properties")
    async def api_place_properties(request: Request) -> dict[str, Any]:
        from housewire.site.recipe_actions import update_place_properties

        payload = await _json_body(request)
        location_id = str(payload.get("location_id") or "").strip()
        place_id = str(payload.get("id") or "").strip()
        if not location_id or not place_id:
            raise HTTPException(400, "location_id and id are required")
        fields = payload.get("fields")
        if not isinstance(fields, dict):
            raise HTTPException(400, "fields must be an object")
        element = payload.get("element")
        element_id = str(element).strip() if element is not None else None
        if element_id == "":
            element_id = None
        depth = _depth_from(payload)
        try:
            _preload_location(location_id)
            _begin_edit()
            detail = update_place_properties(
                _session(),
                canvas_location_id=location_id,
                place_id=place_id,
                fields=fields,
                element=element_id,
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        meta = _end_edit()
        return {
            "detail": detail,
            "graph": _graph(location_id, depth),
            **meta,
        }

    @app.get("/api/cable")
    def api_cable(id: str) -> dict[str, Any]:
        from housewire.site.cable_actions import cable_detail

        cable_id = str(id or "").strip()
        if not cable_id:
            raise HTTPException(400, "id is required")
        try:
            session = _session()
            session.ensure_doc(_site_yaml())
            return cable_detail(session, cable_id=cable_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.patch("/api/cable/properties")
    async def api_cable_properties(request: Request) -> dict[str, Any]:
        from housewire.site.cable_actions import update_cable_properties

        payload = await _json_body(request)
        cable_id = str(payload.get("id") or "").strip()
        location_id = str(payload.get("location_id") or ".").strip() or "."
        if not cable_id:
            raise HTTPException(400, "id is required")
        fields = payload.get("fields")
        if not isinstance(fields, dict):
            raise HTTPException(400, "fields must be an object")
        depth = _depth_from(payload)
        try:
            _preload_location(location_id)
            _begin_edit()
            detail = update_cable_properties(
                _session(), cable_id=cable_id, fields=fields
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        meta = _end_edit()
        return {
            "detail": detail,
            "graph": _graph(location_id, depth),
            **meta,
        }

    @app.post("/api/cable/conduit")
    async def api_cable_conduit(request: Request) -> dict[str, Any]:
        from housewire.site.cable_actions import insert_conduit

        payload = await _json_body(request)
        location_id = str(payload.get("location_id") or ".").strip() or "."
        from_ref = str(payload.get("from") or "").strip()
        to_ref = str(payload.get("to") or "").strip()
        if not from_ref or not to_ref:
            raise HTTPException(400, "from and to openings are required")
        depth = _depth_from(payload)
        contains = payload.get("contains")
        try:
            _preload_location(location_id)
            _begin_edit()
            detail = insert_conduit(
                _session(),
                from_ref=from_ref,
                to_ref=to_ref,
                owner_id=str(payload.get("owner_id") or location_id).strip()
                or location_id,
                name=(str(payload["name"]).strip() if payload.get("name") else None),
                subtype=(
                    str(payload["subtype"]).strip()
                    if payload.get("subtype")
                    else None
                ),
                label=(str(payload["label"]).strip() if payload.get("label") else None),
                notes=(str(payload["notes"]).strip() if payload.get("notes") else None),
                contains=list(contains) if isinstance(contains, list) else None,
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        meta = _end_edit()
        return {
            "detail": detail,
            "graph": _graph(location_id, depth),
            **meta,
        }

    @app.post("/api/cable/conductor")
    async def api_cable_conductor(request: Request) -> dict[str, Any]:
        from housewire.site.cable_actions import insert_conductor

        payload = await _json_body(request)
        location_id = str(payload.get("location_id") or ".").strip() or "."
        from_ref = str(payload.get("from") or "").strip()
        to_ref = str(payload.get("to") or "").strip()
        if not from_ref or not to_ref:
            raise HTTPException(400, "from and to terminals are required")
        depth = _depth_from(payload)
        try:
            _preload_location(location_id)
            _begin_edit()
            detail = insert_conductor(
                _session(),
                from_ref=from_ref,
                to_ref=to_ref,
                owner_id=str(payload.get("owner_id") or location_id).strip()
                or location_id,
                name=(str(payload["name"]).strip() if payload.get("name") else None),
                color=(str(payload["color"]).strip() if payload.get("color") else None),
                section=(
                    str(payload["section"]).strip() if payload.get("section") else None
                ),
                subtype=(
                    str(payload["subtype"]).strip()
                    if payload.get("subtype")
                    else None
                ),
                label=(str(payload["label"]).strip() if payload.get("label") else None),
                notes=(str(payload["notes"]).strip() if payload.get("notes") else None),
                conduit_id=(
                    str(payload["conduit_id"]).strip()
                    if payload.get("conduit_id")
                    else None
                ),
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        meta = _end_edit()
        return {
            "detail": detail,
            "graph": _graph(location_id, depth),
            **meta,
        }

    @app.post("/api/cable/sheath")
    async def api_cable_sheath(request: Request) -> dict[str, Any]:
        from housewire.site.cable_actions import insert_sheath

        payload = await _json_body(request)
        location_id = str(payload.get("location_id") or ".").strip() or "."
        contains = payload.get("contains")
        if not isinstance(contains, list) or not contains:
            raise HTTPException(400, "contains must be a non-empty list")
        depth = _depth_from(payload)
        try:
            _preload_location(location_id)
            _begin_edit()
            detail = insert_sheath(
                _session(),
                contains=[str(x) for x in contains],
                owner_id=str(payload.get("owner_id") or location_id).strip()
                or location_id,
                name=(str(payload["name"]).strip() if payload.get("name") else None),
                color=(str(payload["color"]).strip() if payload.get("color") else None),
                subtype=(
                    str(payload["subtype"]).strip()
                    if payload.get("subtype")
                    else None
                ),
                section=(
                    str(payload["section"]).strip() if payload.get("section") else None
                ),
                label=(str(payload["label"]).strip() if payload.get("label") else None),
                notes=(str(payload["notes"]).strip() if payload.get("notes") else None),
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        meta = _end_edit()
        return {
            "detail": detail,
            "graph": _graph(location_id, depth),
            **meta,
        }

    @app.get("/api/cable/open-runs")
    def api_cable_open_runs(owner_id: str | None = None) -> dict[str, Any]:
        from housewire.site.cable_actions import list_open_runs

        try:
            session = _session()
            session.ensure_doc(_site_yaml())
            return {"open_runs": list_open_runs(session, owner_id=owner_id)}
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/cable/open")
    async def api_cable_open(request: Request) -> dict[str, Any]:
        from housewire.site.cable_actions import open_run

        payload = await _json_body(request)
        location_id = str(payload.get("location_id") or ".").strip() or "."
        leaves = str(payload.get("leaves") or "").strip()
        if not leaves:
            raise HTTPException(400, "leaves opening is required")
        depth = _depth_from(payload)
        colors = payload.get("colors")
        try:
            _preload_location(location_id)
            _begin_edit()
            detail = open_run(
                _session(),
                leaves=leaves,
                owner_id=str(payload.get("owner_id") or location_id).strip()
                or location_id,
                colors=list(colors) if isinstance(colors, list) else None,
                section=(
                    str(payload["section"]).strip() if payload.get("section") else None
                ),
                subtype=(
                    str(payload["subtype"]).strip()
                    if payload.get("subtype")
                    else None
                ),
                label=(str(payload["label"]).strip() if payload.get("label") else None),
                notes=(str(payload["notes"]).strip() if payload.get("notes") else None),
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        meta = _end_edit()
        return {
            "detail": detail,
            "graph": _graph(location_id, depth),
            **meta,
        }

    @app.post("/api/cable/claim")
    async def api_cable_claim(request: Request) -> dict[str, Any]:
        from housewire.site.cable_actions import claim_run

        payload = await _json_body(request)
        location_id = str(payload.get("location_id") or ".").strip() or "."
        cable_id = str(payload.get("id") or "").strip()
        enter = str(payload.get("enter") or "").strip()
        if not cable_id or not enter:
            raise HTTPException(400, "id and enter are required")
        depth = _depth_from(payload)
        try:
            _preload_location(location_id)
            _begin_edit()
            detail = claim_run(
                _session(),
                cable_id=cable_id,
                enter=enter,
                exit=(str(payload["exit"]).strip() if payload.get("exit") else None),
                conduit_name=(
                    str(payload["conduit_name"]).strip()
                    if payload.get("conduit_name")
                    else None
                ),
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        meta = _end_edit()
        return {
            "detail": detail,
            "graph": _graph(location_id, depth),
            **meta,
        }

    @app.post("/api/cable/land")
    async def api_cable_land(request: Request) -> dict[str, Any]:
        from housewire.site.cable_actions import land_run

        payload = await _json_body(request)
        location_id = str(payload.get("location_id") or ".").strip() or "."
        cable_id = str(payload.get("id") or "").strip()
        from_ref = str(payload.get("from") or "").strip()
        to_ref = str(payload.get("to") or "").strip()
        if not cable_id or not from_ref or not to_ref:
            raise HTTPException(400, "id, from, and to are required")
        depth = _depth_from(payload)
        try:
            _preload_location(location_id)
            _begin_edit()
            detail = land_run(
                _session(),
                cable_id=cable_id,
                from_ref=from_ref,
                to_ref=to_ref,
                as_name=(
                    str(payload["as_name"]).strip() if payload.get("as_name") else None
                ),
                notes=(str(payload["notes"]).strip() if payload.get("notes") else None),
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        meta = _end_edit()
        return {
            "detail": detail,
            "graph": _graph(location_id, depth),
            **meta,
        }

    @app.post("/api/edit/undo")
    async def api_edit_undo(request: Request) -> dict[str, Any]:
        payload = await _json_body(request)
        location_id = str(payload.get("location_id") or "").strip() or "."
        depth = _depth_from(payload)
        session = _session()
        _preload_location(location_id)
        changed = session.undo_edit(_site_yaml())
        return {
            "changed": changed,
            "graph": _graph(location_id, depth),
            **_edit_meta(),
        }

    @app.post("/api/edit/redo")
    async def api_edit_redo(request: Request) -> dict[str, Any]:
        payload = await _json_body(request)
        location_id = str(payload.get("location_id") or "").strip() or "."
        depth = _depth_from(payload)
        session = _session()
        _preload_location(location_id)
        changed = session.redo_edit(_site_yaml())
        return {
            "changed": changed,
            "graph": _graph(location_id, depth),
            **_edit_meta(),
        }

    @app.post("/api/edit/reset")
    async def api_edit_reset(request: Request) -> dict[str, Any]:
        payload = await _json_body(request)
        location_id = str(payload.get("location_id") or "").strip() or "."
        depth = _depth_from(payload)
        session = _session()
        _preload_location(location_id)
        changed = session.reset_edits(_site_yaml())
        return {
            "changed": changed,
            "graph": _graph(location_id, depth),
            **_edit_meta(),
        }

    @app.post("/api/edit/delete")
    async def api_edit_delete(request: Request) -> dict[str, Any]:
        from housewire.site.delete_selection import (
            delete_selection,
            suggest_location_after_delete,
        )

        payload = await _json_body(request)
        raw_ids = payload.get("ids") or []
        if not isinstance(raw_ids, list) or not raw_ids:
            raise HTTPException(400, "ids must be a non-empty list")
        ids = [str(x).strip() for x in raw_ids if str(x).strip()]
        if not ids:
            raise HTTPException(400, "ids must be a non-empty list")
        location_id = str(payload.get("location_id") or ".").strip() or "."
        depth = _depth_from(payload)
        session = _session()
        try:
            _preload_location(location_id)
            _begin_edit()
            _path, doc = session.ensure_doc(_site_yaml())
            result = delete_selection(doc, ids)
            session.mark_dirty(_site_yaml())
            meta = _end_edit()
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        new_location = suggest_location_after_delete(
            location_id, deleted_places=result.deleted_places
        )
        return {
            "deleted": result.deleted,
            "severed": result.severed,
            "relocated": result.relocated,
            "location": new_location,
            "graph": _graph(new_location, depth),
            **meta,
        }

    @app.post("/api/edit/copy")
    async def api_edit_copy(request: Request) -> dict[str, Any]:
        from housewire.site.clipboard import pack_selection

        payload = await _json_body(request)
        raw_ids = payload.get("ids") or []
        if not isinstance(raw_ids, list) or not raw_ids:
            raise HTTPException(400, "ids must be a non-empty list")
        ids = [str(x).strip() for x in raw_ids if str(x).strip()]
        if not ids:
            raise HTTPException(400, "ids must be a non-empty list")
        session = _session()
        try:
            _path, doc = session.ensure_doc(_site_yaml())
            clip = pack_selection(doc, ids)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"payload": clip}

    @app.post("/api/edit/cut")
    async def api_edit_cut(request: Request) -> dict[str, Any]:
        from housewire.site.clipboard import pack_selection
        from housewire.site.delete_selection import (
            delete_selection,
            suggest_location_after_delete,
        )

        payload = await _json_body(request)
        raw_ids = payload.get("ids") or []
        if not isinstance(raw_ids, list) or not raw_ids:
            raise HTTPException(400, "ids must be a non-empty list")
        ids = [str(x).strip() for x in raw_ids if str(x).strip()]
        if not ids:
            raise HTTPException(400, "ids must be a non-empty list")
        location_id = str(payload.get("location_id") or ".").strip() or "."
        depth = _depth_from(payload)
        session = _session()
        try:
            _preload_location(location_id)
            _begin_edit()
            _path, doc = session.ensure_doc(_site_yaml())
            clip = pack_selection(doc, ids)
            result = delete_selection(doc, ids)
            session.mark_dirty(_site_yaml())
            meta = _end_edit()
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        new_location = suggest_location_after_delete(
            location_id, deleted_places=result.deleted_places
        )
        return {
            "payload": clip,
            "deleted": result.deleted,
            "location": new_location,
            "graph": _graph(new_location, depth),
            **meta,
        }

    @app.post("/api/edit/paste")
    async def api_edit_paste(request: Request) -> dict[str, Any]:
        from housewire.site.clipboard import paste_payload

        body = await _json_body(request)
        parent_id = str(body.get("parent_id") or ".").strip() or "."
        clip = body.get("payload")
        if not isinstance(clip, dict):
            raise HTTPException(400, "payload must be an object")
        location_id = str(body.get("location_id") or ".").strip() or "."
        depth = _depth_from(body)
        session = _session()
        try:
            _preload_location(location_id)
            _begin_edit()
            _path, doc = session.ensure_doc(_site_yaml())
            mode = body.get("mode")
            locale = _locale_from_request(request, body=body)
            _set_request_locale(locale)
            result = paste_payload(
                doc,
                parent_id=parent_id,
                payload=clip,
                mode=str(mode) if mode is not None else None,
                locale=locale,
            )
            session.mark_dirty(_site_yaml())
            meta = _end_edit()
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        return {
            "created": result.created,
            "renamed": result.renamed,
            "graph": _graph(location_id, depth, locale=locale),
            **meta,
        }

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
            _begin_edit()
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
        meta = _end_edit()
        return {
            "updated": updated,
            "graph": _graph(location_id, depth),
            **meta,
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
            _begin_edit()
            docs = _session_docs()
            updated = pg.apply_positions(
                _root(), location_id, positions, session_docs=docs
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        meta = _end_edit()
        return {"updated": updated, **meta}

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
            _begin_edit()
            docs = _session_docs()
            updated = pg.apply_electrical_positions(
                _root(), location_id, positions, session_docs=docs
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        meta = _end_edit()
        return {"updated": updated, **meta}

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
            _begin_edit()
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
        meta = _end_edit()
        return {
            "updated": updated,
            "graph": _graph(location_id, depth),
            **meta,
        }

    @app.patch("/api/physical/page")
    async def api_page(request: Request) -> dict[str, Any]:
        payload = await _json_body(request)
        location_id = str(payload.get("location_id") or "").strip()
        if not location_id:
            raise HTTPException(400, "location_id is required")
        session = _session()
        loc_yaml = _site_yaml()
        _begin_edit()
        _path, doc = session.ensure_doc(loc_yaml)
        from housewire.site.tree import get_place_node, logical_parts_from_id

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
        meta = _end_edit()
        return {"page": get_physical_page(place), **meta}

    @app.post("/api/recipes/socket")
    async def api_recipe_socket(request: Request) -> dict[str, Any]:
        from housewire.site.recipe_actions import run_socket_recipe

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
            _begin_edit()
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
            meta = _end_edit()
            return {
                "result": result,
                "graph": _graph(location_id, _depth_from(payload)),
                **meta,
            }
        except (ValueError, FileExistsError, FileNotFoundError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/recipes/lamp")
    async def api_recipe_lamp(request: Request) -> dict[str, Any]:
        from housewire.site.recipe_actions import run_lamp_recipe

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
            _begin_edit()
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
            meta = _end_edit()
            return {
                "result": result,
                "graph": _graph(location_id, _depth_from(payload)),
                **meta,
            }
        except (ValueError, FileExistsError, FileNotFoundError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/recipes/feed")
    async def api_recipe_feed(request: Request) -> dict[str, Any]:
        from housewire.site.recipe_actions import run_feed_recipe

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
            _begin_edit()
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
            meta = _end_edit()
            return {
                "result": result,
                "graph": _graph(location_id, _depth_from(payload)),
                **meta,
            }
        except (ValueError, FileExistsError, FileNotFoundError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/insert/catalog-item")
    async def api_insert_catalog_item(request: Request) -> dict[str, Any]:
        from housewire.site.recipe_actions import insert_catalog_item

        body = await _json_body(request)
        location_id = str(body.get("location_id") or ".").strip() or "."
        place_id = str(body.get("place_id") or ".").strip() or "."
        type_id = str(body.get("type_id") or "").strip()
        if not type_id:
            raise HTTPException(400, "type_id is required")
        depth = _depth_from(body)
        try:
            _preload_location(location_id)
            _begin_edit()
            result = insert_catalog_item(
                _session(),
                canvas_location_id=location_id,
                place_id=place_id,
                type_id=type_id,
                subtype=body.get("subtype"),
                id=body.get("id"),
                name=body.get("name"),
                label=body.get("label"),
                notes=body.get("notes"),
                x=body.get("x"),
                y=body.get("y"),
                w=body.get("w"),
                h=body.get("h"),
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        meta = _end_edit()
        return {
            "result": result,
            "graph": _graph(location_id, depth),
            **meta,
        }

    @app.post("/api/save")
    def api_save() -> dict[str, Any]:
        session = _session()
        root = _root()
        try:
            saved = [str(p.relative_to(root)) for p in session.save_all()]
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        # Even if nothing was dirty, align baseline with the on-disk doc.
        session.mark_edit_baseline(_site_yaml())
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
            **_edit_meta(),
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
    print(
        f"{__title__} UI → http://{host}:{port}/  "
        f"(site: {site_root.expanduser().resolve()})"
    )
    uvicorn.run(app, host=host, port=port, log_level="info")
