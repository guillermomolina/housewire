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
    session = ProjectSession.open(project_path)
    print(f"housewire shell — {session.site_yaml()}")
    print(
        "Type help. Tab completes. Changes stay in memory until save. "
        "Multi-line: end with \\"
    )
    if not enable_readline_completion(session):
        print("(No readline: Tab completion unavailable)")
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
                "Looks like a command continuation. "
                "Put \\ at the end of the previous line, or paste everything on one line."
            )
            continue
        code = run_shell_line(session, line, generate_fn=generate_fn)
        if code == -1:
            if not request_leave(session):
                continue
            return 0
        if code is not None and code != 0:
            pass
