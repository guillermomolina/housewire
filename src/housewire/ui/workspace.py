"""In-process UI workspace: multiple site documents (one YAML file per tab)."""
from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from housewire.project.io import require_house_document, save_yaml
from housewire.project.paths import find_site_yaml, is_yaml, list_root_yaml_files
from housewire.project.session import ProjectSession

# Directories copied on Save As (editable site content).
_SAVE_AS_SKIP = frozenset({".git", "out", ".venv", "__pycache__", ".mypy_cache"})


def _doc_id(yaml_path: Path) -> str:
    return str(yaml_path.resolve())


@dataclass
class Document:
    """A complete site (directory + one site YAML of any ``.yml``/``.yaml`` name)."""

    id: str
    root: Path
    session: ProjectSession
    # True when opened from browser file content (temp site on the server).
    browser_origin: bool = False

    @property
    def yaml_path(self) -> Path:
        return self.session.site_yaml()

    @property
    def title(self) -> str:
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
    def session(self) -> ProjectSession | None:
        doc = self.document
        return None if doc is None else doc.session

    def require_session(self) -> ProjectSession:
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
        return {
            "id": doc.id,
            "path": str(doc.root),
            "name": doc.root.name,
            "yaml": yaml_path.name,
            "yaml_path": str(yaml_path),
            "title": doc.title,
            "browser_origin": doc.browser_origin,
            "dirty": bool(dirty_paths),
        }

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
            for path in active.session.dirty_paths():
                try:
                    dirty.append(str(path.relative_to(root)))
                except ValueError:
                    dirty.append(str(path))
        return {
            "documents": docs,
            "active": self.active_id,
            "document": None if active is None else self._doc_payload(active),
            "dirty": dirty,
            "site": None if active is None else str(active.root),
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
            session=ProjectSession(root, site_yaml=yaml_path),
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
