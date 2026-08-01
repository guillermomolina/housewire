"""Interactive project session: nested place navigation in one housewire.yaml."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from housewire.house import is_house_document, is_place_type
from housewire.project.io import HOUSEWIRE_YAML, load_yaml
from housewire.project.paths import find_site_yaml, is_excluded_path, is_yaml
from housewire.project.tree import get_place_node, iter_place_children, site_yaml_path


@dataclass
class DocBuffer:
    """In-memory housewire.yaml for the interactive shell."""

    path: Path
    doc: dict[str, Any]
    dirty: bool = False
    mtime: float | None = None


def _docs_equivalent(a: Any, b: Any) -> bool:
    """Deep equality treating int/float numbers as equal when values match."""
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a) != set(b):
            return False
        return all(_docs_equivalent(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(_docs_equivalent(x, y) for x, y in zip(a, b, strict=True))
    return a == b


@dataclass(frozen=True)
class LocationChild:
    """A navigable child place under the current place."""

    name: str
    place_type: str | None


@dataclass
class LocationCursor:
    """Resolved view of the current logical place inside the site YAML."""

    yaml_path: Path | None
    logical_parts: list[str] = field(default_factory=list)

    @property
    def inline_parts(self) -> list[str]:
        """Alias: path inside the single document's ``elements`` tree."""
        return list(self.logical_parts)


# Back-compat alias used by older call sites / tests.
place_node_at = get_place_node


def _load_doc(path: Path) -> dict[str, Any] | None:
    try:
        data = load_yaml(path)
    except ValueError:
        return None
    if not is_house_document(data):
        return None
    return data


class ProjectSession:
    def __init__(self, root: Path, *, site_yaml: Path | None = None) -> None:
        self.root = root.resolve()
        if not self.root.is_dir():
            raise NotADirectoryError(f"Not a project directory: {self.root}")
        self._excluded = {(self.root / "out").resolve()}
        self.logical_parts: list[str] = []
        self.active_yaml: Path | None = None
        self._buffers: dict[Path, DocBuffer] = {}
        self.input_fn = input
        self._site_yaml = self._resolve_initial_site_yaml(site_yaml)
        self._sync_from_logical()

    def _resolve_initial_site_yaml(self, site_yaml: Path | None) -> Path:
        if site_yaml is not None:
            path = site_yaml.resolve()
            if path.parent != self.root:
                raise ValueError(
                    f"Site YAML must be at the site root ({self.root}), got {path}"
                )
            if not is_yaml(path):
                raise ValueError(f"Not a YAML file: {path}")
            return path
        found = find_site_yaml(self.root)
        if found is not None:
            return found
        return site_yaml_path(self.root)

    def site_yaml(self) -> Path:
        return self._site_yaml

    def peek_doc(self, path: Path | None = None) -> dict[str, Any] | None:
        """Return buffered doc if loaded, else read from disk (no buffer insert)."""
        key = (path or self.site_yaml()).resolve()
        buf = self._buffers.get(key)
        if buf is not None:
            return buf.doc
        return _load_doc(key)

    def ensure_doc(self, path: Path | None = None) -> tuple[Path, dict[str, Any]]:
        """Load the site yaml into the buffer if needed; return ``(path, doc)``."""
        from housewire.project import abm

        resolved = (path or self.ensure_active_yaml()).resolve()
        site = self.site_yaml()
        if resolved != site:
            # Allow activating another root YAML as the document.
            if resolved.parent == self.root and is_yaml(resolved) and resolved.is_file():
                self._site_yaml = resolved
                site = resolved
            else:
                raise ValueError(
                    f"Only the site YAML can be edited "
                    f"(got {resolved.relative_to(self.root)}; active is {site.name})"
                )
        buf = self._buffers.get(resolved)
        if buf is None:
            doc = abm.load_editable(resolved, self.root)
            mtime = resolved.stat().st_mtime if resolved.is_file() else None
            buf = DocBuffer(path=resolved, doc=doc, dirty=False, mtime=mtime)
            self._buffers[resolved] = buf
        return resolved, buf.doc

    def mark_dirty(self, path: Path | None = None) -> None:
        resolved, _ = self.ensure_doc(path)
        self._buffers[resolved].dirty = True

    def reconcile_dirty(self, path: Path | None = None) -> bool:
        """Set dirty from buffer vs disk; clear when they match. Return dirty."""
        from housewire.project import abm

        resolved, doc = self.ensure_doc(path)
        buf = self._buffers[resolved]
        if not resolved.is_file():
            buf.dirty = True
            return True
        disk = abm.load_editable(resolved, self.root)
        buf.dirty = not _docs_equivalent(doc, disk)
        return buf.dirty

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
            self._buffers.pop(resolved, None)
            raise ValueError(
                f"{resolved.relative_to(self.root)} does not exist on disk yet. "
                "Use discard or save."
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
        """Filesystem directory of the site (single YAML lives at site root)."""
        return self.root

    def cursor(self) -> LocationCursor:
        return self._resolve_logical(self.logical_parts)

    def _sync_from_logical(self) -> None:
        cursor = self._resolve_logical(self.logical_parts)
        self.active_yaml = cursor.yaml_path

    def _site_yaml_if_present(self) -> Path | None:
        site = self.site_yaml()
        if site in self._buffers or site.is_file():
            return site
        # Discover if the preferred path was a default that does not exist yet.
        found = find_site_yaml(self.root)
        if found is not None:
            self._site_yaml = found
            return found
        return None

    def _resolve_logical(self, parts: list[str]) -> LocationCursor:
        yaml_path = self._site_yaml_if_present()
        if not parts:
            return LocationCursor(yaml_path=yaml_path, logical_parts=[])
        if yaml_path is None:
            raise FileNotFoundError(
                f"Location does not exist: {'/'.join(parts)} "
                f"(no .yaml/.yml at site root)"
            )
        doc = self.peek_doc(yaml_path)
        if doc is None:
            raise FileNotFoundError(
                f"Cannot read site YAML for location {'/'.join(parts)}"
            )
        # Validate the full path exists as nested places.
        get_place_node(doc, parts)
        return LocationCursor(yaml_path=yaml_path, logical_parts=list(parts))

    def _list_children(self, parts: list[str]) -> list[LocationChild]:
        yaml_path = self._site_yaml_if_present()
        if yaml_path is None:
            return []
        doc = self.peek_doc(yaml_path)
        if doc is None:
            return []
        try:
            node = get_place_node(doc, parts)
        except ValueError:
            return []
        return [
            LocationChild(name, str(defn.get("type")) if defn.get("type") else None)
            for name, defn in iter_place_children(node)
        ]

    def list_locations(self) -> list[tuple[str, str | None]]:
        """Child places: ``(name, place_type_or_None)``."""
        return [(c.name, c.place_type) for c in self._list_children(self.logical_parts)]

    def list_location_children(self) -> list[LocationChild]:
        return self._list_children(self.logical_parts)

    def list_elements(self) -> list[tuple[str, str]]:
        """Non-place elements in the current location: ``(name, type_id)``."""
        yaml_path = self._site_yaml_if_present()
        if yaml_path is None:
            return []
        doc = self.peek_doc(yaml_path)
        if doc is None:
            return []
        try:
            node = get_place_node(doc, self.logical_parts)
        except ValueError:
            return []
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
        """Map the loaded site document to the current place node."""
        return get_place_node(doc, self.logical_parts)

    def resolve_under_root(self, raw: str) -> Path:
        """Resolve a filesystem path relative to the site root."""
        raw = raw.strip()
        if raw == "" or raw == ".":
            return self.root
        candidate = (self.root / raw).resolve()
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
                children = {c.name for c in self._list_children(parts)}
                if segment not in children:
                    raise FileNotFoundError(
                        f"Location does not exist: {'/'.join(parts + [segment])}"
                    )
                parts = parts + [segment]
        self._resolve_logical(parts)
        return parts

    def preview_cd(self, raw: str | None) -> LocationCursor:
        return self._resolve_logical(self.compute_cd_parts(raw))

    def cd(self, raw: str | None) -> Path | None:
        """Change logical place and sync active yaml."""
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
        path = self._site_yaml_if_present()
        if path is not None:
            self.active_yaml = path
            return path
        raise ValueError(
            f"No .yaml/.yml at site root. "
            f"Create {HOUSEWIRE_YAML} (or any site *.yaml) "
            f"or use add location under an existing site."
        )

    def use_yaml(self, name: str) -> Path:
        path = self.resolve_under_root(name)
        if not path.is_file() or not is_yaml(path):
            raise FileNotFoundError(f"Not a YAML file: {name}")
        if path.parent.resolve() != self.root:
            raise ValueError(
                f"Only a YAML at the site root can be the document. Got: {name}"
            )
        resolved = path.resolve()
        self._site_yaml = resolved
        self.active_yaml = resolved
        return resolved

    def active_path(self) -> Path:
        return self.ensure_active_yaml()
