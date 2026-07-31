from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from housewire.commands import request_leave, run_shell_line
from housewire.completion import enable_readline_completion
from housewire.project.session import ProjectSession


def run_repl(
    project_path: Path,
    generate_fn: Callable[..., int],
) -> int:
    session = ProjectSession(project_path)
    print(f"housewire shell — {session.root}")
    print(
        "Escribe help. Tab completa. "
        "add/rm element|cable|conduit|connection → memoria (save); "
        "add location (carpeta) → disco al momento."
    )
    if not enable_readline_completion(session):
        print("(Sin readline: Tab completion no disponible)")
    while True:
        try:
            line = input(f"housewire:{session.prompt_label()}$ ")
        except (EOFError, KeyboardInterrupt):
            print()
            if not request_leave(session):
                continue
            return 0
        code = run_shell_line(session, line, generate_fn=generate_fn)
        if code == -1:
            if not request_leave(session):
                continue
            return 0
        if code is not None and code != 0:
            pass
