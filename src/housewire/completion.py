"""Tab completion for the housewire interactive shell (readline)."""
from __future__ import annotations

import shlex
from pathlib import Path
from typing import TYPE_CHECKING

from housewire.project.paths import EXCLUDED_DIR_NAMES, is_excluded_path, is_yaml

if TYPE_CHECKING:
    from housewire.project.session import ProjectSession

SHELL_COMMANDS = (
    "pwd",
    "cd",
    "ls",
    "use",
    "show",
    "pend",
    "add",
    "rm",
    "save",
    "reload",
    "generate",
    "version",
    "help",
    "exit",
    "quit",
)

ADD_SUBCOMMANDS = ("location", "element", "cable", "conduit", "pend", "connection", "dir")
RM_SUBCOMMANDS = ("element", "cable", "connection", "file", "dir")


def _quote_if_needed(value: str) -> str:
    if any(ch in value for ch in (" ", "\t", '"', "'")):
        return shlex.quote(value)
    return value


def _tokens_before_cursor(line: str, begidx: int) -> tuple[list[str], bool]:
    """Tokens completely before the token being completed, and whether a new token started."""
    before = line[:begidx]
    starting_new = (begidx == 0) or (begidx > 0 and line[begidx - 1].isspace())
    if not before.strip():
        return [], True
    try:
        tokens = shlex.split(before)
    except ValueError:
        tokens = before.split()
    return tokens, starting_new


def complete_candidates(
    session: ProjectSession,
    line: str,
    text: str,
    *,
    begidx: int | None = None,
) -> list[str]:
    """Return strings that replace ``text`` for Tab completion."""
    if begidx is None:
        begidx = len(line) - len(text) if text and line.endswith(text) else len(line)

    tokens, starting_new = _tokens_before_cursor(line, begidx)

    # Completing command name
    if not tokens:
        return [cmd + " " for cmd in SHELL_COMMANDS if cmd.startswith(text)]

    cmd = tokens[0]

    # add / rm subcommands
    if cmd == "add" and len(tokens) == 1 and starting_new:
        return [s + " " for s in ADD_SUBCOMMANDS if s.startswith(text)]
    if cmd == "add" and len(tokens) == 2 and not starting_new:
        return [s + " " for s in ADD_SUBCOMMANDS if s.startswith(text)]
    if cmd == "rm" and len(tokens) == 1 and starting_new:
        return [s + " " for s in RM_SUBCOMMANDS if s.startswith(text)]
    if cmd == "rm" and len(tokens) == 2 and not starting_new:
        return [s + " " for s in RM_SUBCOMMANDS if s.startswith(text)]

    # Path args
    dirs_only = False
    yaml_only = False
    want_path = False

    if cmd == "cd" and (
        (len(tokens) == 1 and starting_new) or (len(tokens) == 2 and not starting_new)
    ):
        return complete_location_path(session, text)
    if cmd == "use" and (
        (len(tokens) == 1 and starting_new) or (len(tokens) == 2 and not starting_new)
    ):
        want_path, yaml_only = True, True
    elif (
        len(tokens) >= 2
        and tokens[0] in {"add", "rm"}
        and tokens[1] in {"dir", "file"}
        and (
            (len(tokens) == 2 and starting_new)
            or (len(tokens) == 3 and not starting_new)
        )
    ):
        want_path = True
        dirs_only = tokens[1] == "dir"
        yaml_only = tokens[0] == "rm" and tokens[1] == "file"

    # Path args (filesystem) for use / add dir / rm dir|file
    if want_path:
        return complete_path(session, text, dirs_only=dirs_only, yaml_only=yaml_only)

    return []


def complete_location_path(session: ProjectSession, partial: str) -> list[str]:
    """Tab-complete logical location paths (outline + inline)."""
    partial = partial or ""
    unquoted = partial
    if unquoted.startswith(("'", '"')):
        quote = unquoted[0]
        if unquoted.endswith(quote) and len(unquoted) >= 2:
            unquoted = unquoted[1:-1]
        else:
            unquoted = unquoted[1:]

    if unquoted.endswith("/") or unquoted == "":
        rel_dir = unquoted.rstrip("/")
        name_prefix = ""
        prefix = f"{rel_dir}/" if rel_dir else ""
    else:
        path = Path(unquoted)
        parent = path.parent
        rel_dir = "" if str(parent) == "." else str(parent).replace("\\", "/")
        name_prefix = path.name
        prefix = (rel_dir.rstrip("/") + "/") if rel_dir else ""

    if rel_dir:
        parent_parts = [p for p in Path(rel_dir).parts if p not in ("", ".")]
    else:
        parent_parts = list(session.logical_parts)

    try:
        cursor = session._resolve_logical(parent_parts)
        children = session._list_children(cursor.yaml_path, cursor.inline_parts)
    except (ValueError, FileNotFoundError, OSError):
        return []

    matches: list[str] = []
    for child in children:
        if not child.name.startswith(name_prefix):
            continue
        matches.append(_quote_if_needed(prefix + child.name + "/"))
    matches.sort(key=lambda m: m.lower())
    return matches


def complete_path(
    session: ProjectSession,
    partial: str,
    *,
    dirs_only: bool = False,
    yaml_only: bool = False,
) -> list[str]:
    partial = partial or ""
    unquoted = partial
    if unquoted.startswith(("'", '"')):
        quote = unquoted[0]
        if unquoted.endswith(quote) and len(unquoted) >= 2:
            unquoted = unquoted[1:-1]
        else:
            unquoted = unquoted[1:]

    if unquoted.endswith("/") or unquoted == "":
        rel_dir = unquoted
        name_prefix = ""
        prefix = unquoted
    else:
        path = Path(unquoted)
        parent = path.parent
        rel_dir = "" if str(parent) == "." else str(parent).replace("\\", "/")
        name_prefix = path.name
        prefix = (rel_dir.rstrip("/") + "/") if rel_dir else ""

    try:
        base = session.resolve_under_root(rel_dir or ".")
    except (ValueError, OSError):
        return []
    if not base.is_dir():
        return []

    matches: list[str] = []
    try:
        children = sorted(base.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError:
        return []

    for child in children:
        if child.name in EXCLUDED_DIR_NAMES:
            continue
        if is_excluded_path(child, session._excluded):
            continue
        if not child.name.startswith(name_prefix):
            continue
        if child.is_dir():
            if yaml_only:
                continue
            candidate = prefix + child.name + "/"
            matches.append(_quote_if_needed(candidate))
        elif child.is_file() and is_yaml(child):
            if dirs_only:
                continue
            from housewire.project.paths import is_housewire_yaml

            if not is_housewire_yaml(child):
                continue
            if not child.name.startswith(name_prefix):
                continue
            candidate = prefix + child.name
            matches.append(_quote_if_needed(candidate))
    matches.sort(key=lambda m: m.lower())
    return matches


class ShellCompleter:
    def __init__(self, session: ProjectSession) -> None:
        self.session = session
        self._matches: list[str] = []

    def __call__(self, text: str, state: int) -> str | None:
        if state == 0:
            try:
                import readline

                line = readline.get_line_buffer()
                begidx = readline.get_begidx()
            except Exception:
                line = text
                begidx = 0
            self._matches = complete_candidates(
                self.session, line, text, begidx=begidx
            )
        try:
            return self._matches[state]
        except IndexError:
            return None


def enable_readline_completion(session: ProjectSession) -> bool:
    """Install Tab completion. Returns False if readline is unavailable."""
    try:
        import readline
    except ImportError:
        return False

    readline.set_completer(ShellCompleter(session))
    # Include '/' inside the token so nested paths complete as one argument.
    readline.set_completer_delims(" \t\n;")

    # GNU readline: "tab: complete". libedit (macOS): "bind ^I rl_complete".
    # Applying the libedit line on GNU readline can bind the key ``b`` and
    # make that letter unusable in the shell — only use one, matching the library.
    doc = getattr(readline, "__doc__", "") or ""
    if "libedit" in doc:
        bindings = ("bind ^I rl_complete",)
    else:
        bindings = ("tab: complete",)

    bound = False
    for binding in bindings:
        try:
            readline.parse_and_bind(binding)
            bound = True
        except Exception:
            continue
    return bound
