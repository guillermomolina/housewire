"""Native OS file/folder dialogs for the local UI server.

Browser pickers cannot expose real filesystem paths to the server. When
housewire serve runs on the user's machine, these helpers open a system
dialog (zenity, kdialog, or tkinter) and return a path the API can open.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


class DialogUnavailableError(RuntimeError):
    """No usable native dialog backend on this host."""


def dialogs_available() -> bool:
    return _backend_name() is not None


def _backend_name() -> str | None:
    if shutil.which("zenity"):
        return "zenity"
    if shutil.which("kdialog"):
        return "kdialog"
    try:
        import _tkinter  # noqa: F401
    except ImportError:
        return None
    # Tk needs a display on Unix; avoid claiming availability headless.
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        return None
    return "tkinter"


def pick_open_yaml(
    *,
    title: str = "Open site YAML",
    start_dir: Path | None = None,
) -> Path | None:
    """Show an open-file dialog filtered to ``.yaml`` / ``.yml``.

    Returns the selected path, or ``None`` if the user cancelled.
    Raises ``DialogUnavailableError`` when no backend works.
    """
    initial = _initial_dir(start_dir)
    backend = _backend_name()
    if backend == "zenity":
        return _zenity_open_file(title=title, initial=initial)
    if backend == "kdialog":
        return _kdialog_open_file(title=title, initial=initial)
    if backend == "tkinter":
        return _tkinter_open_file(title=title, initial=initial)
    raise DialogUnavailableError(
        "No native file dialog (install zenity or kdialog, or Python tkinter)"
    )


def pick_save_site_path(
    *,
    title: str = "Save site as",
    start_dir: Path | None = None,
    default_name: str = "site_copy",
) -> Path | None:
    """Show a save dialog; the chosen path is the new site directory."""
    initial = _initial_dir(start_dir)
    suggested = initial / default_name
    backend = _backend_name()
    if backend == "zenity":
        return _zenity_save_path(title=title, suggested=suggested)
    if backend == "kdialog":
        return _kdialog_save_path(title=title, suggested=suggested)
    if backend == "tkinter":
        return _tkinter_save_path(title=title, suggested=suggested)
    raise DialogUnavailableError(
        "No native save dialog (install zenity or kdialog, or Python tkinter)"
    )


def pick_save_directory(
    *,
    title: str = "Save site as",
    start_dir: Path | None = None,
) -> Path | None:
    """Show a directory picker (legacy; prefer :func:`pick_save_site_path`)."""
    initial = _initial_dir(start_dir)
    backend = _backend_name()
    if backend == "zenity":
        return _zenity_pick_directory(title=title, initial=initial)
    if backend == "kdialog":
        return _kdialog_pick_directory(title=title, initial=initial)
    if backend == "tkinter":
        return _tkinter_pick_directory(title=title, initial=initial)
    raise DialogUnavailableError(
        "No native folder dialog (install zenity or kdialog, or Python tkinter)"
    )


def _initial_dir(start_dir: Path | None) -> Path:
    if start_dir is not None:
        path = start_dir.expanduser().resolve()
        if path.is_file():
            path = path.parent
        if path.is_dir():
            return path
    home = Path.home()
    if home.is_dir():
        return home
    return Path.cwd()


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )


def _zenity_open_file(*, title: str, initial: Path) -> Path | None:
    result = _run(
        [
            "zenity",
            "--file-selection",
            f"--title={title}",
            f"--filename={initial}/",
            "--file-filter=YAML | *.yaml *.yml",
            "--file-filter=All | *",
        ]
    )
    if result.returncode != 0:
        return None
    text = (result.stdout or "").strip()
    return Path(text) if text else None


def _zenity_save_path(*, title: str, suggested: Path) -> Path | None:
    result = _run(
        [
            "zenity",
            "--file-selection",
            "--save",
            "--confirm-overwrite",
            f"--title={title}",
            f"--filename={suggested}",
        ]
    )
    if result.returncode != 0:
        return None
    text = (result.stdout or "").strip()
    return Path(text) if text else None


def _zenity_pick_directory(*, title: str, initial: Path) -> Path | None:
    result = _run(
        [
            "zenity",
            "--file-selection",
            "--directory",
            f"--title={title}",
            f"--filename={initial}/",
        ]
    )
    if result.returncode != 0:
        return None
    text = (result.stdout or "").strip()
    return Path(text) if text else None


def _kdialog_open_file(*, title: str, initial: Path) -> Path | None:
    result = _run(
        [
            "kdialog",
            "--getopenfilename",
            str(initial),
            "YAML (*.yaml *.yml)|All files (*)",
            "--title",
            title,
        ]
    )
    if result.returncode != 0:
        return None
    text = (result.stdout or "").strip()
    return Path(text) if text else None


def _kdialog_save_path(*, title: str, suggested: Path) -> Path | None:
    result = _run(
        [
            "kdialog",
            "--getsavefilename",
            str(suggested),
            "--title",
            title,
        ]
    )
    if result.returncode != 0:
        return None
    text = (result.stdout or "").strip()
    return Path(text) if text else None


def _kdialog_pick_directory(*, title: str, initial: Path) -> Path | None:
    result = _run(
        [
            "kdialog",
            "--getexistingdirectory",
            str(initial),
            "--title",
            title,
        ]
    )
    if result.returncode != 0:
        return None
    text = (result.stdout or "").strip()
    return Path(text) if text else None


def _tkinter_open_file(*, title: str, initial: Path) -> Path | None:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass
    try:
        chosen = filedialog.askopenfilename(
            parent=root,
            title=title,
            initialdir=str(initial),
            filetypes=[
                ("YAML", "*.yaml *.yml"),
                ("All files", "*.*"),
            ],
        )
    finally:
        root.destroy()
    return Path(chosen) if chosen else None


def _tkinter_save_path(*, title: str, suggested: Path) -> Path | None:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass
    try:
        chosen = filedialog.asksaveasfilename(
            parent=root,
            title=title,
            initialdir=str(suggested.parent),
            initialfile=suggested.name,
        )
    finally:
        root.destroy()
    return Path(chosen) if chosen else None


def _tkinter_pick_directory(*, title: str, initial: Path) -> Path | None:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass
    try:
        chosen = filedialog.askdirectory(
            parent=root,
            title=title,
            initialdir=str(initial),
            mustexist=False,
        )
    finally:
        root.destroy()
    return Path(chosen) if chosen else None
