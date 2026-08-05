"""In-process UI workspace: multiple site documents (one YAML file per tab)."""
from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from housewire.house import pascal_case_token
from housewire.site.io import create_site_document, require_house_document, save_yaml
from housewire.site.paths import find_site_yaml, is_yaml, list_root_yaml_files
from housewire.site.session import SiteSession

# Directories copied on Save As (editable site content).
_SAVE_AS_SKIP = frozenset({".git", "out", ".venv", "__pycache__", ".mypy_cache"})


def _doc_id(yaml_path: Path) -> str:
    return str(yaml_path.resolve())


@dataclass
class Document:
    """A complete site (directory + one site YAML of any ``.yml``/``.yaml`` name)."""

    id: str
    root: Path
    session: SiteSession
    # True when opened from browser file content (temp site on the server).
    browser_origin: bool = False
    # Optional tab label (e.g. localized "New site"); falls back to YAML name.
    display_title: str | None = None
    # File → New: stay dirty until the first Save (even if buffer matches disk).
    force_dirty: bool = False

    @property
    def yaml_path(self) -> Path:
        return self.session.site_yaml()

    @property
    def title(self) -> str:
        if self.display_title:
            return self.display_title
        return self.yaml_path.name


@dataclass
class Workspace:
    """Mutable workspace holding zero or more documents; one is active."""

    documents: dict[str, Document] = field(default_factory=dict)
    active_id: str | None = None
    _browser_temps: list[Path] = field(default_factory=list)
    # Insertion order for tab strip.
    _order: list[str] = field(default_factory=list)

    @property
    def document(self) -> Document | None:
        if self.active_id is None:
            return None
        return self.documents.get(self.active_id)

    @property
    def active(self) -> Document | None:
        return self.document

    @property
    def root(self) -> Path | None:
        doc = self.document
        return None if doc is None else doc.root

    @property
    def session(self) -> SiteSession | None:
        doc = self.document
        return None if doc is None else doc.session

    def require_session(self) -> SiteSession:
        if self.document is None:
            raise FileNotFoundError(
                "No document open. Open a site YAML (File → Open) "
                "or start serve with a site path."
            )
        return self.document.session

    def require_root(self) -> Path:
        if self.document is None:
            raise FileNotFoundError(
                "No document open. Open a site YAML (File → Open) "
                "or start serve with a site path."
            )
        return self.document.root

    def _doc_payload(self, doc: Document) -> dict[str, Any]:
        yaml_path = doc.yaml_path
        dirty_paths = doc.session.dirty_paths()
        dirty = bool(dirty_paths) or doc.force_dirty
        return {
            "id": doc.id,
            "path": str(doc.root),
            "name": doc.root.name,
            "yaml": yaml_path.name,
            "yaml_path": str(yaml_path),
            "title": doc.title,
            "browser_origin": doc.browser_origin,
            "dirty": dirty,
        }

    def clear_force_dirty(self, doc_id: str | None = None) -> None:
        """Clear File → New sticky dirty (after a successful Save)."""
        target = doc_id if doc_id is not None else self.active_id
        if target is None:
            return
        doc = self.documents.get(target)
        if doc is not None:
            doc.force_dirty = False

    def status(self) -> dict[str, Any]:
        docs = [
            self._doc_payload(self.documents[i])
            for i in self._order
            if i in self.documents
        ]
        active = self.document
        dirty: list[str] = []
        if active is not None:
            root = active.root
            seen: set[str] = set()
            for path in active.session.dirty_paths():
                try:
                    rel = str(path.relative_to(root))
                except ValueError:
                    rel = str(path)
                dirty.append(rel)
                seen.add(rel)
            if active.force_dirty:
                yaml_name = active.yaml_path.name
                if yaml_name not in seen:
                    dirty.append(yaml_name)
        return {
            "documents": docs,
            "active": self.active_id,
            "document": None if active is None else self._doc_payload(active),
            "dirty": dirty,
            "site": None if active is None else str(active.root),
            **(
                active.session.edit_flags()
                if active is not None
                else {"can_undo": False, "can_redo": False, "can_reset": False}
            ),
        }

    def yaml_export(self) -> dict[str, str]:
        """Return current site YAML text (from buffer) and filename."""
        session = self.require_session()
        path, doc = session.ensure_doc()
        text = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
        return {"filename": path.name, "content": text}

    def activate(self, doc_id: str) -> Document:
        """Switch the active document tab."""
        doc = self.documents.get(doc_id)
        if doc is None:
            raise FileNotFoundError(f"No open document: {doc_id}")
        self.active_id = doc_id
        return doc

    def _register(self, doc: Document) -> Document:
        if doc.id not in self.documents:
            self.documents[doc.id] = doc
            self._order.append(doc.id)
        else:
            self.documents[doc.id] = doc
        self.active_id = doc.id
        return doc

    def open_site(
        self,
        path: Path,
        *,
        force: bool = False,
        browser_origin: bool = False,
    ) -> Document:
        """Open ``path`` as a document tab (activate if already open).

        ``path`` may be a site directory or a ``.yaml``/``.yml`` file at the
        site root (any filename). ``force`` is kept for API compatibility and
        ignored when adding/switching tabs (each document has its own dirty).
        """
        del force  # multi-doc: opening another file does not discard others
        target = path.expanduser().resolve()
        if target.is_file():
            if not is_yaml(target):
                raise ValueError(f"Not a YAML file: {target}")
            root = target.parent
            yaml_path = target
        elif target.is_dir():
            root = target
            yaml_path = find_site_yaml(root)
            if yaml_path is None:
                found = list_root_yaml_files(root)
                if len(found) > 1:
                    names = ", ".join(p.name for p in found)
                    raise FileNotFoundError(
                        f"Multiple YAML files in {root}; open one explicitly "
                        f"({names})"
                    )
                raise FileNotFoundError(
                    f"No .yaml/.yml file in {root}"
                )
        else:
            raise FileNotFoundError(f"Path not found: {target}")

        doc_id = _doc_id(yaml_path)
        existing = self.documents.get(doc_id)
        if existing is not None:
            self.active_id = doc_id
            return existing

        doc = Document(
            id=doc_id,
            root=root,
            session=SiteSession(root, site_yaml=yaml_path),
            browser_origin=browser_origin,
        )
        return self._register(doc)

    def open_yaml_content(
        self,
        filename: str,
        content: str,
        *,
        force: bool = False,
    ) -> Document:
        """Open YAML text from a browser file picker as a new document tab."""
        del force
        name = Path(filename).name
        if not is_yaml(Path(name)):
            raise ValueError(f"Not a YAML filename: {filename}")
        try:
            data = yaml.safe_load(content) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("YAML does not contain a valid object")
        require_house_document(data, Path(name))

        root = Path(tempfile.mkdtemp(prefix="housewire-open-"))
        self._browser_temps.append(root)
        yaml_path = root / name
        save_yaml(yaml_path, data, backup=False)
        return self.open_site(yaml_path, force=True, browser_origin=True)

    def new_site(
        self,
        *,
        type_id: str = "House",
        label: str | None = None,
        locale: str | None = None,
    ) -> Document:
        """Create an empty site tab (temp dir + localized YAML name).

        The new document stays dirty until Save / Save as. Tab text is the
        YAML filename (technical stem + ``.yaml``). Root ``name``/``label``
        follow ``locale`` (``es`` → ``Nuevo sitio`` / ``NuevoSitio.yaml``).
        """
        loc = str(locale or "en").strip().lower()
        if loc.startswith("es"):
            human = "Nuevo sitio"
        else:
            human = "New site"
        root_label = label or human
        tech_id = pascal_case_token(root_label)
        yaml_name = f"{tech_id}.yaml"
        root = Path(tempfile.mkdtemp(prefix="housewire-new-"))
        self._browser_temps.append(root)
        yaml_path = create_site_document(
            root,
            type_id=type_id,
            label=root_label,
            working_name=root_label,
            yaml_name=yaml_name,
        )
        doc = self.open_site(yaml_path, force=True, browser_origin=True)
        registered = self.documents[doc.id]
        # Tab shows the real filename (with .yaml), not a title without suffix.
        registered.display_title = None
        registered.force_dirty = True
        registered.session.mark_dirty(yaml_path)
        return registered

    def close(self, *, force: bool = False, doc_id: str | None = None) -> None:
        """Unload one document tab (active if ``doc_id`` omitted)."""
        target_id = doc_id if doc_id is not None else self.active_id
        if target_id is None:
            return
        doc = self.documents.get(target_id)
        if doc is None:
            return
        if doc.session.dirty_paths() and not force:
            raise ValueError(
                "Document has unsaved changes. "
                "Save, or close with force=true to discard."
            )
        del self.documents[target_id]
        if target_id in self._order:
            self._order.remove(target_id)
        if self.active_id == target_id:
            self.active_id = self._order[-1] if self._order else None

    def save_as(self, dest: Path, *, force: bool = False) -> Document:
        """Duplicate the active site to ``dest`` and open it as a new tab."""
        if self.document is None:
            raise FileNotFoundError("No document open to Save As")
        src = self.document.root
        src_sess = self.document.session
        yaml_name = src_sess.site_yaml().name
        try:
            _path, live = src_sess.ensure_doc()
        except ValueError:
            live = None

        target = dest.expanduser().resolve()
        if target.exists():
            if not force:
                raise FileExistsError(f"Destination already exists: {target}")
            if target == src:
                raise ValueError("Save As destination must differ from the current site")
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=False)
        for child in src.iterdir():
            if child.name in _SAVE_AS_SKIP:
                continue
            dest_child = target / child.name
            if child.is_dir():
                shutil.copytree(
                    child,
                    dest_child,
                    ignore=shutil.ignore_patterns(*_SAVE_AS_SKIP, "*.pyc"),
                )
            else:
                shutil.copy2(child, dest_child)

        new_doc = self.open_site(target / yaml_name, force=True)
        if live is not None:
            yaml_path = new_doc.session.site_yaml()
            new_doc.session.ensure_doc(yaml_path)
            new_doc.session._buffers[yaml_path.resolve()].doc = live
            new_doc.session.mark_dirty(yaml_path)
            new_doc.session.save(yaml_path)
        return new_doc


def create_workspace(initial_site: Path | None = None) -> Workspace:
    """Create a workspace, optionally opening ``initial_site``."""
    ws = Workspace()
    if initial_site is not None:
        ws.open_site(Path(initial_site), force=True)
    return ws
