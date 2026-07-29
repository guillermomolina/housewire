"""WireViz shows the same pin name on left and right ports.

house/v1 collapsed pairs encode asymmetric labels in pinlabels as:
  left\\x1emiddle\\x1eright
This module rewrites Graphviz HTML so each side shows the right text.
"""
from __future__ import annotations

import re

# Unit separator — unlikely in terminal labels
PINLABEL_SIDE_SEP = "\x1e"

_PIN_ROW_RE = re.compile(
    r'<td port="(p\d+)l">([^<]*)</td>'
    r'(\s*)<td>([^<]*)</td>'
    r'(\s*)<td port="(p\d+)r">([^<]*)</td>'
)

_SEP_TRIPLE_RE = re.compile(
    rf"([^{PINLABEL_SIDE_SEP}<>]+){re.escape(PINLABEL_SIDE_SEP)}"
    rf"([^{PINLABEL_SIDE_SEP}<>]+){re.escape(PINLABEL_SIDE_SEP)}"
    rf"([^{PINLABEL_SIDE_SEP}<>]+)"
)


def format_side_pinlabel(left: str, middle: str, right: str) -> str:
    return f"{left}{PINLABEL_SIDE_SEP}{middle}{PINLABEL_SIDE_SEP}{right}"


def _fix_pin_row(match: re.Match[str]) -> str:
    port_l, _old_left, sp1, mid, sp2, port_r, _old_right = match.groups()
    if PINLABEL_SIDE_SEP not in mid:
        return match.group(0)
    parts = mid.split(PINLABEL_SIDE_SEP)
    if len(parts) == 3:
        left, middle, right = parts
        return (
            f'<td port="{port_l}l">{left}</td>'
            f"{sp1}<td>{middle}</td>"
            f'{sp2}<td port="{port_r}r">{right}</td>'
        )
    if len(parts) == 2:
        left, right = parts
        return (
            f'<td port="{port_l}l">{left}</td>'
            f'{sp2}<td port="{port_r}r">{right}</td>'
        )
    return match.group(0)


def _fix_remaining_sep_labels(text: str) -> str:
    """Cable annotations still carry the raw pinlabel; show left→right."""

    def repl(match: re.Match[str]) -> str:
        left, _middle, right = match.groups()
        return f"{left}→{right}"

    return _SEP_TRIPLE_RE.sub(repl, text)


def fix_asymmetric_pinlabels_html(html: str) -> str:
    html = _PIN_ROW_RE.sub(_fix_pin_row, html)
    return _fix_remaining_sep_labels(html)


def apply_wireviz_asymmetric_pinlabel_patch() -> None:
    from wireviz.Harness import Harness

    if getattr(Harness, "_house_asymmetric_pinlabels", False):
        return

    original = Harness.create_graph

    def create_graph(self):  # type: ignore[no-untyped-def]
        graph = original(self)
        graph.body = [fix_asymmetric_pinlabels_html(line) for line in graph.body]
        return graph

    Harness.create_graph = create_graph  # type: ignore[method-assign]
    Harness._house_asymmetric_pinlabels = True
