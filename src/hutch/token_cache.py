"""Bounded identity caches for deterministic transcript token estimates.

``context.prompt_tokens`` and ``runtime.fitloop.count_tokens`` re-estimate the whole
message list on every step. Session messages are append-only dicts: the engine appends new
turns and may add metadata keys (images, computer_observation), but it does not rewrite an
existing message's ``content`` or ``tool_calls`` in place. These caches key an estimate on
the identity of exactly the values the formula reads and keep strong references, so an id
cannot be recycled while an entry is live and a replaced value (for example a new
``content`` object) misses on the next lookup. Entries are bounded; a miss only recomputes
the same deterministic integer.

This is a pure performance mechanism: every public function returns exactly the value the
uncached formula returns, which the focused tests pin against a reference implementation.
"""

from __future__ import annotations

from typing import Any, Callable

MAX_MESSAGE_ENTRIES = 4096
MAX_SEQUENCE_ENTRIES = 256


class MessageTokenCache:
    """Identity cache for one message -> integer estimate (content/tool_calls aware)."""

    def __init__(self, max_entries: int = MAX_MESSAGE_ENTRIES):
        self._max_entries = max(1, max_entries)
        self._entries: dict[int, tuple[Any, Any, Any, int]] = {}
        self._hits = 0
        self._misses = 0

    def get(self, message: Any, content: Any, tool_calls: Any, compute: Callable[[], int]) -> int:
        """Cached value for ``message``, recomputed when ``content``/``tool_calls`` are replaced."""
        entry = self._entries.get(id(message))
        if entry is not None and entry[0] is message and entry[1] is content and entry[2] is tool_calls:
            self._hits += 1
            return entry[3]
        value = compute()
        if len(self._entries) >= self._max_entries:
            self._entries.pop(next(iter(self._entries)))  # bounded FIFO: cheap, order is not a contract
        self._entries[id(message)] = (message, content, tool_calls, value)
        self._misses += 1
        return value

    def clear(self) -> None:
        self._entries.clear()
        self._hits = 0
        self._misses = 0

    def info(self) -> dict[str, int]:
        """Bounded observability for tests and diagnostics (not a public API)."""
        return {"size": len(self._entries), "hits": self._hits, "misses": self._misses,
                "max_entries": self._max_entries}


class SequenceTokenCache:
    """Identity cache for a sequence of immutable items (for example tool schemas)."""

    def __init__(self, max_entries: int = MAX_SEQUENCE_ENTRIES):
        self._max_entries = max(1, max_entries)
        self._entries: dict[tuple[int, ...], tuple[tuple[Any, ...], int]] = {}
        self._hits = 0
        self._misses = 0

    def get(self, items: tuple[Any, ...], compute: Callable[[], int]) -> int:
        key = tuple(id(item) for item in items)
        entry = self._entries.get(key)
        if entry is not None and len(entry[0]) == len(items) and all(a is b for a, b in zip(entry[0], items)):
            self._hits += 1
            return entry[1]
        value = compute()
        if len(self._entries) >= self._max_entries:
            self._entries.pop(next(iter(self._entries)))
        self._entries[key] = (items, value)
        self._misses += 1
        return value

    def clear(self) -> None:
        self._entries.clear()
        self._hits = 0
        self._misses = 0

    def info(self) -> dict[str, int]:
        """Bounded observability for tests and diagnostics (not a public API)."""
        return {"size": len(self._entries), "hits": self._hits, "misses": self._misses,
                "max_entries": self._max_entries}
