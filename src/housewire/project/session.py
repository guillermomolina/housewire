from __future__ import annotations

from pathlib import Path

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

    def cd(self, raw: str | None) -> None:
        if raw is None or raw.strip() == "":
            self.cwd = Path(".")
            return
        target = self.resolve_under_root(raw)
        if not target.is_dir():
            raise NotADirectoryError(f"No es un directorio: {raw}")
        self.cwd = target.relative_to(self.root)
        self.active_yaml = None

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

    def use_yaml(self, name: str) -> Path:
        path = self.resolve_under_root(name)
        if not path.is_file() or not is_yaml(path):
            raise FileNotFoundError(f"No es un archivo YAML: {name}")
        self.active_yaml = path
        return path

    def active_path(self) -> Path:
        if self.active_yaml is None:
            raise ValueError("No hay YAML activo. Usa: use <archivo.yaml>")
        return self.active_yaml
