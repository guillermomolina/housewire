"""Interactive project session: logical location navigation (outline + inline)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from housewire.house import is_house_document, is_place_type, place_meta_from_mapping
from housewire.project.io import HOUSEWIRE_YAML, load_yaml
from housewire.project.paths import (
    EXCLUDED_DIR_NAMES,
    is_excluded_path,
    is_housewire_yaml,
    is_yaml,
)

StorageKind = Literal["dir", "inline"]


@dataclass
class DocBuffer:
    """In-memory housewire.yaml for the interactive shell."""

    path: Path
    doc: dict[str, Any]
    dirty: bool = False
    mtime: float | None = None


@dataclass(frozen=True)
class LocationChild:
    """A navigable child location under the current place."""

    name: str
    place_type: str | None
    storage: StorageKind


@dataclass
class LocationCursor:
    """Resolved view of the current logical location.

    ``yaml_path`` is the outline ``housewire.yaml`` that stores this place.
    ``inline_parts`` is the path inside that document's ``elements`` tree
    (empty ⇒ the YAML root *is* the current place).
    ``logical_parts`` is the full path from the project root (outline and inline).
    """

    yaml_path: Path | None
    inline_parts: list[str] = field(default_factory=list)
    logical_parts: list[str] = field(default_factory=list)

    @property
    def is_inline(self) -> bool:
        return bool(self.inline_parts)

    @property
    def storage(self) -> StorageKind:
        return "inline" if self.inline_parts else "dir"


def _housewire_in_dir(
    directory: Path, *, buffers: dict[Path, DocBuffer] | None = None
) -> Path | None:
    for name in (HOUSEWIRE_YAML, "housewire.yml"):
        candidate = (directory / name).resolve()
        if buffers is not None and candidate in buffers:
            return candidate
        if not candidate.is_file():
            continue
        try:
            data = load_yaml(candidate)
        except ValueError:
            continue
        if is_house_document(data):
            return candidate
    return None


def _load_doc(path: Path) -> dict[str, Any] | None:
    try:
        data = load_yaml(path)
    except ValueError:
        return None
    if not is_house_document(data):
        return None
    return data


def place_node_at(doc: dict[str, Any], inline_parts: list[str]) -> dict[str, Any]:
    """Return the place mapping at ``inline_parts`` inside ``doc`` (doc root if empty)."""
    node: dict[str, Any] = doc
    for part in inline_parts:
        elements = node.get("elements") or {}
        if not isinstance(elements, dict) or part not in elements:
            raise ValueError(f"Inline location does not exist: {'/'.join(inline_parts)}")
        child = elements[part]
        if not isinstance(child, dict) or not is_place_type(child.get("type")):
            raise ValueError(f"Not a location (place type): {part}")
        node = child
    return node


def _inline_children(node: dict[str, Any]) -> list[LocationChild]:
    elements = node.get("elements") or {}
    if not isinstance(elements, dict):
        return []
    rows: list[LocationChild] = []
    for name in sorted(elements, key=lambda n: str(n).lower()):
        defn = elements[name]
        if not isinstance(defn, dict):
            continue
        type_id = defn.get("type")
        if not is_place_type(type_id):
            continue
        rows.append(LocationChild(str(name), str(type_id), "inline"))
    return rows


def _outline_children(
    directory: Path,
    *,
    excluded: set[Path],
    load_doc: Any = None,
    buffers: dict[Path, DocBuffer] | None = None,
) -> list[LocationChild]:
    loader = load_doc if load_doc is not None else _load_doc
    rows: list[LocationChild] = []
    seen: set[str] = set()
    if directory.is_dir():
        for child in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
            if not child.is_dir():
                continue
            if child.name in EXCLUDED_DIR_NAMES:
                continue
            if is_excluded_path(child, excluded):
                continue
            meta_path = _housewire_in_dir(child, buffers=buffers)
            if meta_path is None:
                continue
            data = loader(meta_path)
            place_type: str | None = None
            if data is not None:
                meta = place_meta_from_mapping(data)
                if meta is not None and meta.get("type"):
                    place_type = str(meta["type"])
            rows.append(LocationChild(child.name, place_type, "dir"))
            seen.add(child.name)
    # Staged outline locations (in buffer, not yet on disk).
    if buffers:
        host = directory.resolve()
        for path, buf in buffers.items():
            p = path.resolve()
            if p.name not in (HOUSEWIRE_YAML, "housewire.yml"):
                continue
            parent = p.parent
            if parent.parent.resolve() != host:
                continue
            leaf = parent.name
            if leaf in seen or leaf in EXCLUDED_DIR_NAMES:
                continue
            if is_excluded_path(parent, excluded):
                continue
            place_type: str | None = None
            meta = place_meta_from_mapping(buf.doc)
            if meta is not None and meta.get("type"):
                place_type = str(meta["type"])
            rows.append(LocationChild(leaf, place_type, "dir"))
            seen.add(leaf)
    return sorted(rows, key=lambda c: c.name.lower())


class ProjectSession:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        if not self.root.is_dir():
            raise NotADirectoryError(f"Not a project directory: {self.root}")
        self._excluded = {(self.root / "out").resolve()}
        # Logical path from project root (location ids, outline or inline).
        self.logical_parts: list[str] = []
        self.active_yaml: Path | None = None
        self._buffers: dict[Path, DocBuffer] = {}
        # Injectable for tests (default: builtin input).
        self.input_fn = input
        self._sync_from_logical()

    # --- document buffer (shell in-memory edits) ---

    def peek_doc(self, path: Path) -> dict[str, Any] | None:
        """Return buffered doc if loaded, else read from disk (no buffer insert)."""
        key = path.resolve()
        buf = self._buffers.get(key)
        if buf is not None:
            return buf.doc
        return _load_doc(key)

    def ensure_doc(self, path: Path | None = None) -> tuple[Path, dict[str, Any]]:
        """Load hosting yaml into the buffer if needed; return ``(path, doc)``."""
        from housewire.project import abm

        resolved = (path or self.ensure_active_yaml()).resolve()
        buf = self._buffers.get(resolved)
        if buf is None:
            doc = abm.load_editable(resolved, self.root)
            mtime = resolved.stat().st_mtime if resolved.is_file() else None
            buf = DocBuffer(path=resolved, doc=doc, dirty=False, mtime=mtime)
            self._buffers[resolved] = buf
        return resolved, buf.doc

    def stage_outline_location(
        self,
        dir_path: Path,
        *,
        type_id: str,
        subtype: str | None = None,
        notes: str | None = None,
        label: str | None = None,
    ) -> Path:
        """Create an outline location in the dirty buffer (no disk write yet)."""
        from housewire.project.io import build_location_document

        yaml_path = (dir_path / HOUSEWIRE_YAML).resolve()
        if yaml_path.is_file() or yaml_path in self._buffers:
            raise FileExistsError(f"Already exists: {yaml_path}")
        # Collision with an existing sibling dir that already has housewire.yaml
        if dir_path.is_dir() and _housewire_in_dir(dir_path, buffers=self._buffers):
            raise FileExistsError(f"Outline location already exists: {dir_path.name}")
        doc = build_location_document(
            type_id=type_id, subtype=subtype, notes=notes, label=label
        )
        self._buffers[yaml_path] = DocBuffer(
            path=yaml_path, doc=doc, dirty=True, mtime=None
        )
        return yaml_path

    def mark_dirty(self, path: Path | None = None) -> None:
        resolved, _ = self.ensure_doc(path)
        self._buffers[resolved].dirty = True

    def is_dirty(self, path: Path | None = None) -> bool:
        if path is None:
            cursor = self.cursor()
            if cursor.yaml_path is None:
                return False
            path = cursor.yaml_path
        buf = self._buffers.get(path.resolve())
        return bool(buf and buf.dirty)

    def dirty_paths(self) -> list[Path]:
        return [p for p, buf in sorted(self._buffers.items()) if buf.dirty]

    def save(self, path: Path | None = None, *, force: bool = False) -> Path:
        """Validate and write a buffered document to disk."""
        from housewire.project import abm

        resolved, doc = self.ensure_doc(path)
        buf = self._buffers[resolved]
        if not buf.dirty:
            return resolved
        if (
            not force
            and buf.mtime is not None
            and resolved.is_file()
            and resolved.stat().st_mtime != buf.mtime
        ):
            raise ValueError(
                f"{resolved.relative_to(self.root)} changed on disk since load. "
                "Use: save --force  or  reload"
            )
        resolved.parent.mkdir(parents=True, exist_ok=True)
        abm.persist(doc, resolved, self.root)
        buf.dirty = False
        buf.mtime = resolved.stat().st_mtime if resolved.is_file() else None
        return resolved

    def save_all(self, *, force: bool = False) -> list[Path]:
        saved: list[Path] = []
        for path in self.dirty_paths():
            saved.append(self.save(path, force=force))
        return saved

    def reload(self, path: Path | None = None) -> Path:
        """Drop buffer and reload from disk (discards unsaved changes)."""
        from housewire.project import abm

        resolved = (path or self.ensure_active_yaml()).resolve()
        if not resolved.is_file():
            # Staged outline location never written: discard buffer only.
            self._buffers.pop(resolved, None)
            raise ValueError(
                f"{resolved.relative_to(self.root)} does not exist on disk yet "
                "(location only in memory). Use discard or save."
            )
        doc = abm.load_editable(resolved, self.root)
        mtime = resolved.stat().st_mtime if resolved.is_file() else None
        self._buffers[resolved] = DocBuffer(
            path=resolved, doc=doc, dirty=False, mtime=mtime
        )
        return resolved

    def discard(self, path: Path | None = None) -> None:
        """Forget a buffer (next ensure_doc reloads from disk)."""
        if path is None:
            cursor = self.cursor()
            if cursor.yaml_path is None:
                return
            path = cursor.yaml_path
        self._buffers.pop(path.resolve(), None)

    # --- compatibility aliases ---

    @property
    def cwd(self) -> Path:
        """Logical location path as a Path (not always a real directory)."""
        if not self.logical_parts:
            return Path(".")
        return Path(*self.logical_parts)

    @cwd.setter
    def cwd(self, value: Path | str) -> None:
        raw = Path(value)
        if str(raw) in (".", ""):
            self.logical_parts = []
        else:
            self.logical_parts = list(raw.parts)
        self._sync_from_logical()

    def prompt_label(self) -> str:
        rel = "." if not self.logical_parts else "/".join(self.logical_parts)
        dirty = "*" if self.dirty_paths() else ""
        return f"{self.root.name}/{rel}{dirty}"

    def cwd_path(self) -> Path:
        """Filesystem directory of the nearest outline place (hosting yaml's parent)."""
        cursor = self.cursor()
        if cursor.yaml_path is not None:
            return cursor.yaml_path.parent
        return self.root

    def cursor(self) -> LocationCursor:
        return self._resolve_logical(self.logical_parts)

    def _sync_from_logical(self) -> None:
        cursor = self._resolve_logical(self.logical_parts)
        self.active_yaml = cursor.yaml_path

    def _resolve_logical(self, parts: list[str]) -> LocationCursor:
        yaml_path = _housewire_in_dir(self.root, buffers=self._buffers)
        inline_parts: list[str] = []
        walked: list[str] = []
        for part in parts:
            child = self._child_at(yaml_path, inline_parts, part)
            if child is None:
                raise FileNotFoundError(
                    f"Location does not exist: {'/'.join(walked + [part]) or part}"
                )
            walked.append(part)
            if child.storage == "dir":
                if inline_parts:
                    raise ValueError(
                        f"Outline location {part!r} cannot hang under an inline place "
                        f"({'/'.join(walked)}). Use only inline children here."
                    )
                host_dir = (yaml_path.parent if yaml_path else self.root) / part
                next_yaml = _housewire_in_dir(host_dir, buffers=self._buffers)
                if next_yaml is None:
                    raise FileNotFoundError(f"Location without {HOUSEWIRE_YAML}: {part}")
                yaml_path = next_yaml
                inline_parts = []
            else:
                if yaml_path is None:
                    raise ValueError(
                        f"Inline location {part!r} requires {HOUSEWIRE_YAML} on an ancestor"
                    )
                inline_parts = [*inline_parts, part]
        return LocationCursor(
            yaml_path=yaml_path,
            inline_parts=list(inline_parts),
            logical_parts=list(parts),
        )

    def _child_at(
        self,
        yaml_path: Path | None,
        inline_parts: list[str],
        name: str,
    ) -> LocationChild | None:
        children = self._list_children(yaml_path, inline_parts)
        hits = [c for c in children if c.name == name]
        if not hits:
            return None
        if len(hits) > 1:
            kinds = ", ".join(sorted({c.storage for c in hits}))
            raise ValueError(
                f"Ambiguous location {name!r}: exists as {kinds}. "
                "Do not mix the same id as a folder and under elements."
            )
        return hits[0]

    def _list_children(
        self, yaml_path: Path | None, inline_parts: list[str]
    ) -> list[LocationChild]:
        outline: list[LocationChild] = []
        inline: list[LocationChild] = []
        if not inline_parts:
            host_dir = yaml_path.parent if yaml_path is not None else self.root
            outline = _outline_children(
                host_dir,
                excluded=self._excluded,
                load_doc=self.peek_doc,
                buffers=self._buffers,
            )
        if yaml_path is not None:
            doc = self.peek_doc(yaml_path)
            if doc is not None:
                node = place_node_at(doc, inline_parts)
                inline = _inline_children(node)
        # Detect collisions between outline and inline names.
        outline_names = {c.name for c in outline}
        for child in inline:
            if child.name in outline_names:
                raise ValueError(
                    f"Ambiguous location {child.name!r}: exists as dir and inline. "
                    "Do not mix the same id as a folder and under elements."
                )
        return sorted(outline + inline, key=lambda c: c.name.lower())

    def list_locations(self) -> list[tuple[str, str | None]]:
        """Child locations: ``(name, place_type_or_None)`` (outline + inline)."""
        cursor = self.cursor()
        return [(c.name, c.place_type) for c in self._list_children(cursor.yaml_path, cursor.inline_parts)]

    def list_location_children(self) -> list[LocationChild]:
        cursor = self.cursor()
        return self._list_children(cursor.yaml_path, cursor.inline_parts)

    def list_elements(self) -> list[tuple[str, str]]:
        """Non-place elements in the current location: ``(name, type_id)``."""
        cursor = self.cursor()
        if cursor.yaml_path is None:
            return []
        doc = self.peek_doc(cursor.yaml_path)
        if doc is None:
            return []
        node = place_node_at(doc, cursor.inline_parts)
        elements = node.get("elements") or {}
        if not isinstance(elements, dict):
            return []
        rows: list[tuple[str, str]] = []
        for name in sorted(elements, key=lambda n: str(n).lower()):
            defn = elements[name]
            if not isinstance(defn, dict):
                continue
            type_id = defn.get("type")
            if is_place_type(type_id):
                continue
            rows.append((str(name), str(type_id) if type_id else "?"))
        return rows

    def place_node(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Map the loaded hosting document to the current place node."""
        return place_node_at(doc, self.cursor().inline_parts)

    def resolve_under_root(self, raw: str) -> Path:
        """Resolve a filesystem path relative to the nearest outline directory."""
        raw = raw.strip()
        if raw == "" or raw == ".":
            return self.cwd_path()
        candidate = (self.cwd_path() / raw).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(f"Path outside project: {raw}") from exc
        if is_excluded_path(candidate, self._excluded):
            raise ValueError(f"Excluded path: {raw}")
        return candidate

    def compute_cd_parts(self, raw: str | None) -> list[str]:
        """Resolve a ``cd`` argument to logical parts without changing state."""
        if raw is None or raw.strip() == "":
            return []

        text = raw.strip()
        if text.startswith("/"):
            start: list[str] = []
            rest = text.lstrip("/")
        else:
            start = list(self.logical_parts)
            rest = text

        parts = start
        if rest:
            for segment in Path(rest).parts:
                if segment in ("", "."):
                    continue
                if segment == "..":
                    if not parts:
                        raise ValueError("Already at project root")
                    parts = parts[:-1]
                    continue
                cursor = self._resolve_logical(parts)
                child = self._child_at(cursor.yaml_path, cursor.inline_parts, segment)
                if child is None:
                    raise FileNotFoundError(
                        f"Location does not exist: {'/'.join(parts + [segment])}"
                    )
                parts = parts + [segment]
        self._resolve_logical(parts)
        return parts

    def preview_cd(self, raw: str | None) -> LocationCursor:
        return self._resolve_logical(self.compute_cd_parts(raw))

    def cd(self, raw: str | None) -> Path | None:
        """Change logical location (outline dir or inline place) and sync active yaml."""
        self.logical_parts = self.compute_cd_parts(raw)
        self._sync_from_logical()
        return self.active_yaml

    def housewire_yaml_in_cwd(self) -> Path | None:
        return self.cursor().yaml_path

    def try_auto_use_yaml(self) -> Path | None:
        found = self.housewire_yaml_in_cwd()
        self.active_yaml = found
        return found

    def ensure_active_yaml(self) -> Path:
        path = self.cursor().yaml_path
        if path is not None:
            self.active_yaml = path
            return path
        raise ValueError(
            f"No {HOUSEWIRE_YAML} in this location. "
            f"Use: add location <name>  or create {HOUSEWIRE_YAML}"
        )

    def use_yaml(self, name: str) -> Path:
        path = self.resolve_under_root(name)
        if not path.is_file() or not is_yaml(path):
            raise FileNotFoundError(f"Not a YAML file: {name}")
        if not is_housewire_yaml(path):
            raise ValueError(
                f"Only {HOUSEWIRE_YAML} can be edited (one file per Location). "
                f"Got: {path.name}"
            )
        # use only allowed when it matches the hosting yaml of current cursor
        cursor = self.cursor()
        if cursor.yaml_path is not None and path.resolve() != cursor.yaml_path.resolve():
            raise ValueError(
                f"use only activates the {HOUSEWIRE_YAML} of the current location "
                f"({cursor.yaml_path.relative_to(self.root)})"
            )
        self.active_yaml = path
        return path

    def active_path(self) -> Path:
        return self.ensure_active_yaml()
