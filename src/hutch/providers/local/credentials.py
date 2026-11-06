"""Origin-scoped credentials for key-protected local runtimes.

A key belongs to the server that issued it. This lookup returns one only when a configured
connection's base URL has the same scheme and port on the same loopback host, so a key saved for
one local server is never offered to another. The key is passed as a header by the probe; it never
enters a URL, a discovery result, a log or a page.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from ...connections import ConnectionBook
from .probe import origin

_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})


def _same_origin(left: str, right: str) -> bool:
    left_origin, right_origin = origin(left), origin(right)
    if left_origin[0] != right_origin[0] or left_origin[2] != right_origin[2]:
        return False
    if left_origin[1] == right_origin[1]:
        return True
    return left_origin[1] in _LOOPBACK and right_origin[1] in _LOOPBACK


def runtime_credentials(state_dir: Path) -> Callable[[str, str], str]:
    """Return ``(provider_id, url) -> key`` scoped to a configured connection's exact origin."""

    def lookup(provider_id: str, url: str) -> str:
        book = ConnectionBook(Path(state_dir))
        candidates = [(name, conn) for name, conn in book.configured().items()
                      if _same_origin(conn.base_url, url)]
        if not candidates:
            return ""
        candidates.sort(key=lambda row: row[0] != provider_id)
        for name, _conn in candidates:
            key = book.key(name)
            if key:
                return key
        return ""

    return lookup
