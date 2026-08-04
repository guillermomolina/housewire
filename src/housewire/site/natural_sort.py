"""Natural sort keys so Interruptor_2 precedes Interruptor_10."""
from __future__ import annotations

import re
from typing import Any

_NAT_CHUNK = re.compile(r"(\d+)")


def natural_sort_key(text: str) -> tuple[Any, ...]:
    """Case-insensitive key with numeric chunks compared as integers."""
    raw = str(text or "")
    parts: list[Any] = []
    for chunk in _NAT_CHUNK.split(raw):
        if not chunk:
            continue
        if chunk.isdigit():
            parts.append((0, int(chunk)))
        else:
            parts.append((1, chunk.casefold()))
    return tuple(parts)
