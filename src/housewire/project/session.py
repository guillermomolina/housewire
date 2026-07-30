from __future__ import annotations

from pathlib import Path

from housewire.house import is_house_document
from housewire.project.io import HOUSEWIRE_YAML, load_yaml
from housewire.project.paths import (
    EXCLUDED_DIR_NAMES,
    is_excluded_path,
    is_housewire_yaml,
    is_yaml,
)


class ProjectSession:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        if not self.root.is_dir():
            raise NotADirectoryError(f"No es un directorio de proyecto: {self.root}")
        self.cwd = Path(".")
        self.active_yaml: Path | None = None
        self._excluded = {(self.root / "out").resolve()}

    def prompt_label(self) -> str:
        rel = "." if str(self.cwd) == "." else str(self.cwd)
        return f"{self.root.name}/{rel}"

    def cwd_path(self) -> Path:
        return (self.root / self.cwd).resolve()

    def resolve_under_root(self, raw: str) -> Path:
        raw = raw.strip()
        if raw == "" or raw == ".":
            return self.cwd_path()
        candidate = (self.cwd_path() / raw).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(f"Ruta fuera del proyecto: {raw}") from exc
        if is_excluded_path(candidate, self._excluded):
            raise ValueError(f"Ruta excluida: {raw}")
        return candidate

    def cd(self, raw: str | None) -> Path | None:
        """Change directory and auto-activate housewire.yaml when present."""
        if raw is None or raw.strip() == "":
            self.cwd = Path(".")
        else:
            target = self.resolve_under_root(raw)
            if not target.is_dir():
                raise NotADirectoryError(f"No es un directorio: {raw}")
            self.cwd = target.relative_to(self.root)
        self.active_yaml = None
        return self.try_auto_use_yaml()

    def list_locations(self) -> list[tuple[str, str | None]]:
        """Child locations (dirs with housewire.yaml): ``(name, place_type_or_None)``."""
        directory = self.cwd_path()
        entries: list[tuple[str, str | None]] = []
        for child in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
            if not child.is_dir():
                continue
            if child.name in EXCLUDED_DIR_NAMES:
                continue
            if is_excluded_path(child, self._excluded):
                continue
            place_type: str | None = None
            has_housewire = False
            for yaml_name in (HOUSEWIRE_YAML, "housewire.yml"):
                meta_path = child / yaml_name
                if not meta_path.is_file():
                    continue
                try:
                    data = load_yaml(meta_path)
                except ValueError:
                    continue
                if not is_house_document(data):
                    continue
                has_housewire = True
                loc = data.get("location")
                if isinstance(loc, dict) and loc.get("type"):
                    place_type = str(loc["type"])
                break
            if not has_housewire:
                continue
            entries.append((child.name, place_type))
        return entries

    def list_elements(self) -> list[tuple[str, str]]:
        """Elements in the current location's housewire.yaml: ``(name, type_id)``."""
        yaml_path = self.housewire_yaml_in_cwd()
        if yaml_path is None:
            return []
        try:
            data = load_yaml(yaml_path)
        except ValueError:
            return []
        if not is_house_document(data):
            return []
        elements = data.get("elements") or {}
        if not isinstance(elements, dict):
            return []
        rows: list[tuple[str, str]] = []
        for name in sorted(elements, key=lambda n: str(n).lower()):
            defn = elements[name]
            type_id = "?"
            if isinstance(defn, dict) and defn.get("type"):
                type_id = str(defn["type"])
            rows.append((str(name), type_id))
        return rows

    def housewire_yaml_in_cwd(self) -> Path | None:
        for name in (HOUSEWIRE_YAML, "housewire.yml"):
            candidate = self.cwd_path() / name
            if not candidate.is_file():
                continue
            try:
                data = load_yaml(candidate)
            except ValueError:
                continue
            if is_house_document(data):
                return candidate
        return None

    def try_auto_use_yaml(self) -> Path | None:
        if self.active_yaml is not None:
            return self.active_yaml
        found = self.housewire_yaml_in_cwd()
        if found is not None:
            self.active_yaml = found
            return self.active_yaml
        return None

    def ensure_active_yaml(self) -> Path:
        if self.active_yaml is not None:
            return self.active_yaml
        auto = self.try_auto_use_yaml()
        if auto is not None:
            return auto
        raise ValueError(
            f"No hay {HOUSEWIRE_YAML} en este directorio. "
            f"Usa: add location <nombre>  o crea {HOUSEWIRE_YAML}"
        )

    def use_yaml(self, name: str) -> Path:
        path = self.resolve_under_root(name)
        if not path.is_file() or not is_yaml(path):
            raise FileNotFoundError(f"No es un archivo YAML: {name}")
        if not is_housewire_yaml(path):
            raise ValueError(
                f"Solo se edita {HOUSEWIRE_YAML} (un fichero por Location). "
                f"Recibido: {path.name}"
            )
        self.active_yaml = path
        return path

    def active_path(self) -> Path:
        return self.ensure_active_yaml()
