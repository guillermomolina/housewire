"""In-process UI workspace: one active site document (File unit)."""
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


@dataclass
class Document:
    """A complete site (directory + one site YAML of any ``.yml``/``.yaml`` name)."""

    root: Path
    session: ProjectSession
    # True when opened from browser file content (temp site on the server).
    browser_origin: bool = False


@dataclass
class Workspace:
    """Mutable workspace holding zero or one active document (for now)."""

    document: Document | None = None
    # Reserved for multi-doc later.
    documents: dict[str, Document] = field(default_factory=dict)
    _browser_temps: list[Path] = field(default_factory=list)

    @property
    def active(self) -> Document | None:
        return self.document

    @property
    def root(self) -> Path | None:
        return None if self.document is None else self.document.root

    @property
    def session(self) -> ProjectSession | None:
        return None if self.document is None else self.document.session

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

    def status(self) -> dict[str, Any]:
        if self.document is None:
            return {
                "document": None,
                "dirty": [],
                "site": None,
            }
        root = self.document.root
        sess = self.document.session
        yaml_path = sess.site_yaml()
        dirty = []
        for path in sess.dirty_paths():
            try:
                dirty.append(str(path.relative_to(root)))
            except ValueError:
                dirty.append(str(path))
        return {
            "document": {
                "id": str(root),
                "path": str(root),
                "name": root.name,
                "yaml": yaml_path.name,
                "yaml_path": str(yaml_path),
                "browser_origin": self.document.browser_origin,
            },
            "dirty": dirty,
            "site": str(root),
        }

    def yaml_export(self) -> dict[str, str]:
        """Return current site YAML text (from buffer) and filename."""
        session = self.require_session()
        path, doc = session.ensure_doc()
        text = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
        return {"filename": path.name, "content": text}

    def _guard_dirty(self, *, force: bool) -> None:
        if self.document is not None and self.document.session.dirty_paths():
            if not force:
                raise ValueError(
                    "Active document has unsaved changes. "
                    "Save, or open with force=true to discard."
                )

    def open_site(
        self,
        path: Path,
        *,
        force: bool = False,
        browser_origin: bool = False,
    ) -> Document:
        """Load ``path`` as the active document.

        ``path`` may be a site directory or a ``.yaml``/``.yml`` file at the
        site root (any filename).
        """
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

        self._guard_dirty(force=force)
        doc = Document(
            root=root,
            session=ProjectSession(root, site_yaml=yaml_path),
            browser_origin=browser_origin,
        )
        self.document = doc
        self.documents = {str(root): doc}
        return doc

    def open_yaml_content(
        self,
        filename: str,
        content: str,
        *,
        force: bool = False,
    ) -> Document:
        """Open YAML text from a browser file picker as a temp site document."""
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

        self._guard_dirty(force=force)
        root = Path(tempfile.mkdtemp(prefix="housewire-open-"))
        self._browser_temps.append(root)
        yaml_path = root / name
        save_yaml(yaml_path, data, backup=False)
        return self.open_site(yaml_path, force=True, browser_origin=True)

    def close(self, *, force: bool = False) -> None:
        """Unload the active document."""
        if self.document is None:
            return
        if self.document.session.dirty_paths() and not force:
            raise ValueError(
                "Active document has unsaved changes. "
                "Save, or close with force=true to discard."
            )
        self.document = None
        self.documents.clear()

    def save_as(self, dest: Path, *, force: bool = False) -> Document:
        """Duplicate the active site to ``dest`` and open the copy."""
        if self.document is None:
            raise FileNotFoundError("No document open to Save As")
        src = self.document.root
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
        src_sess = self.document.session
        yaml_name = src_sess.site_yaml().name
        try:
            _path, doc = src_sess.ensure_doc()
        except ValueError:
            doc = None
        new_doc = self.open_site(target / yaml_name, force=True)
        if doc is not None:
            yaml_path = new_doc.session.site_yaml()
            new_doc.session.ensure_doc(yaml_path)
            new_doc.session._buffers[yaml_path.resolve()].doc = doc
            new_doc.session.mark_dirty(yaml_path)
            new_doc.session.save(yaml_path)
        return new_doc


def create_workspace(initial_site: Path | None = None) -> Workspace:
    """Create a workspace, optionally opening ``initial_site``."""
    ws = Workspace()
    if initial_site is not None:
        ws.open_site(Path(initial_site), force=True)
    return ws
