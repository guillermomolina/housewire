from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from housewire.commands import request_leave, run_shell_line
from housewire.completion import enable_readline_completion
from housewire.project.session import ProjectSession


def read_logical_line(
    *,
    prompt: str,
    continue_prompt: str = "… ",
    input_fn=input,
) -> str:
    """Read one shell command, joining lines that end with ``\\``.

    Lets paste/multi-line work like a POSIX shell::

        add conduit X \\
          --from A.Op --to B.Op \\
          --contains C1
    """
    chunks: list[str] = []
    first = True
    while True:
        raw = input_fn(prompt if first else continue_prompt)
        first = False
        stripped = raw.rstrip()
        if stripped.endswith("\\"):
            chunks.append(stripped[:-1].rstrip())
            continue
        chunks.append(stripped)
        break
    cleaned: list[str] = []
    for i, chunk in enumerate(chunks):
        piece = chunk.strip() if i > 0 else chunk.rstrip()
        if piece:
            cleaned.append(piece)
    return " ".join(cleaned)


def run_repl(
    project_path: Path,
    generate_fn: Callable[..., int],
) -> int:
    session = ProjectSession(project_path)
    print(f"housewire shell — {session.root}")
    print(
        "Escribe help. Tab completa. Cambios en memoria hasta save. "
        "Varias lineas: termina con \\"
    )
    if not enable_readline_completion(session):
        print("(Sin readline: Tab completion no disponible)")
    while True:
        try:
            line = read_logical_line(
                prompt=f"housewire:{session.prompt_label()}$ ",
                input_fn=session.input_fn,
            )
        except (EOFError, KeyboardInterrupt):
            print()
            if not request_leave(session):
                continue
            return 0
        stripped = line.lstrip()
        if stripped.startswith("--"):
            print(
                "Parece una continuación de comando. "
                "Pon \\ al final de la línea anterior, o pega todo en una sola línea."
            )
            continue
        code = run_shell_line(session, line, generate_fn=generate_fn)
        if code == -1:
            if not request_leave(session):
                continue
            return 0
        if code is not None and code != 0:
            pass
