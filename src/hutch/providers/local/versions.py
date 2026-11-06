"""Which local-runtime features a reported version actually has.

Ollama and LM Studio publish release notes for the features Hutch uses; llama.cpp publishes no
feature matrix, so its build string is recorded and features are gated by field presence. A
gate is only a claim Hutch is willing to make: an unknown version produces no advice, never a
guess (R32).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

Version = tuple[int, ...]


@dataclass(frozen=True)
class Gate:
    feature: str
    minimum: Version
    label: str


OLLAMA_GATES: tuple[Gate, ...] = (
    Gate("tools", (0, 3, 0), "tool calling"),
    Gate("structured_output", (0, 5, 0), "schema-constrained output"),
    Gate("thinking", (0, 9, 0), "thinking control"),
    Gate("measured_window", (0, 10, 0), "the applied context window in /api/ps"),
)

LMSTUDIO_GATES: tuple[Gate, ...] = (
    Gate("tools", (0, 3, 6), "tool calling"),
    Gate("ttl", (0, 3, 9), "idle TTL and auto-evict"),
    Gate("native_api", (0, 4, 0), "the native /api/v1 API and API tokens"),
)

_GATES = {"ollama": OLLAMA_GATES, "lmstudio": LMSTUDIO_GATES}
_ALIASES = {"llama.cpp": "llamacpp"}
_VERSION = re.compile(r"^[vV]?(\d+(?:\.\d+)*)")
_NAMES = {"ollama": "Ollama", "lmstudio": "LM Studio"}


def parse_version(text: object) -> Optional[Version]:
    match = _VERSION.match(str(text or "").strip())
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def compare(left: Version, right: Version) -> int:
    width = max(len(left), len(right))
    a, b = left + (0,) * (width - len(left)), right + (0,) * (width - len(right))
    return (a > b) - (a < b)


def at_least(version: object, minimum: Version) -> Optional[bool]:
    parsed = version if isinstance(version, tuple) else parse_version(version)
    return None if parsed is None else compare(parsed, minimum) >= 0


def format_version(version: Version) -> str:
    return ".".join(str(part) for part in version)


def gates(provider_id: str) -> tuple[Gate, ...]:
    return _GATES.get(_ALIASES.get(provider_id, provider_id), ())


def unmet(provider_id: str, version: object,
          features: Optional[Iterable[str]] = None) -> list[Gate]:
    parsed = parse_version(version)
    if parsed is None:
        return []
    wanted = set(features) if features is not None else None
    return [gate for gate in gates(provider_id)
            if (wanted is None or gate.feature in wanted) and compare(parsed, gate.minimum) < 0]


def upgrade_advice(provider_id: str, version: object) -> str:
    missing = unmet(provider_id, version)
    if not missing:
        return ""
    name = _NAMES.get(_ALIASES.get(provider_id, provider_id), provider_id)
    minimum = max(gate.minimum for gate in missing)
    labels = ", ".join(gate.label for gate in missing)
    return f"upgrade {name} to {format_version(minimum)} or newer for {labels}"
