from __future__ import annotations

from pathlib import Path

from housewire.house import is_house_document
from housewire.project.io import load_yaml
from housewire.project.paths import EXCLUDED_DIR_NAMES, is_excluded_path, is_yaml


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
        base = f"{self.root.name}/{rel}"
        if self.active_yaml is not None:
            try:
                active_rel = self.active_yaml.relative_to(self.root)
            except ValueError:
                active_rel = self.active_yaml
            return f"{base} [{active_rel}]"
        return base

    def cwd_path(self) -> Path:
        return (self.root / self.cwd).resolve()

    def resolve_under_root(self, raw: str) -> Path:
        raw = raw.strip()
        if not raw or raw == ".":
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
        """Cambia de directorio. Si hay un solo YAML house/v1, lo auto-activa.

        Returns the auto-used yaml path, or None.
        """
        if raw is None or raw.strip() == "":
            self.cwd = Path(".")
        else:
            target = self.resolve_under_root(raw)
            if not target.is_dir():
                raise NotADirectoryError(f"No es un directorio: {raw}")
            self.cwd = target.relative_to(self.root)
        self.active_yaml = None
        return self.try_auto_use_yaml()

    def list_dir(self) -> list[tuple[str, str]]:
        directory = self.cwd_path()
        entries: list[tuple[str, str]] = []
        for child in sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if child.name in EXCLUDED_DIR_NAMES:
                continue
            if is_excluded_path(child, self._excluded):
                continue
            if child.is_dir():
                entries.append((child.name + "/", "dir"))
            elif is_yaml(child):
                marker = ""
                if self.active_yaml and child.resolve() == self.active_yaml.resolve():
                    marker = " *"
                entries.append((child.name + marker, "yaml"))
        return entries

    def house_yaml_files_in_cwd(self) -> list[Path]:
        found: list[Path] = []
        for child in sorted(self.cwd_path().iterdir()):
            if not child.is_file() or not is_yaml(child):
                continue
            if is_excluded_path(child, self._excluded):
                continue
            try:
                data = load_yaml(child)
            except ValueError:
                continue
            if is_house_document(data):
                found.append(child)
        return found

    def try_auto_use_yaml(self) -> Path | None:
        """Si no hay YAML activo y hay exactamente uno house/v1 en cwd, lo activa."""
        if self.active_yaml is not None:
            return self.active_yaml
        candidates = self.house_yaml_files_in_cwd()
        if len(candidates) == 1:
            self.active_yaml = candidates[0]
            return self.active_yaml
        return None

    def ensure_active_yaml(self) -> Path:
        if self.active_yaml is not None:
            return self.active_yaml
        auto = self.try_auto_use_yaml()
        if auto is not None:
            return auto
        candidates = self.house_yaml_files_in_cwd()
        if not candidates:
            raise ValueError(
                "No hay YAML activo ni house/v1 en este directorio. Usa: use <archivo.yaml>"
            )
        names = ", ".join(p.name for p in candidates)
        raise ValueError(f"Hay varios YAML; usa: use <archivo.yaml>. Candidatos: {names}")

    def use_yaml(self, name: str) -> Path:
        path = self.resolve_under_root(name)
        if not path.is_file() or not is_yaml(path):
            raise FileNotFoundError(f"No es un archivo YAML: {name}")
        self.active_yaml = path
        return path

    def active_path(self) -> Path:
        return self.ensure_active_yaml()
