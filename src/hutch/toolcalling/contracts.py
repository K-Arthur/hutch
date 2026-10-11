"""Typed contracts for the unified tool-calling boundary.

The authoritative object is :class:`ToolDefinition` - Hutch's own view of a tool.
Wire shapes (OpenAI function specs, Anthropic tool blocks, prompt text) are
*serializations* produced by :mod:`hutch.toolcalling.compiler`; a provider adapter
never reaches back into the registry or mutates a canonical schema.

Identity is deliberately multi-part and must not be collapsed:

* ``name``            canonical registered identity (stable, used by policy and receipts)
* ``alias``           provider-visible name, when the protocol constrains names;
                      only generated deterministically and always reversible
* ``schema_revision`` hash of the canonical argument schema at registration time
* ``owner``/``scope`` catalog owner and connection/account scope (later used to
                      refuse a call that belongs to a different account)

An invocation id (per generated call) and a provider call id live on the decoded
action, not here: they are per-turn facts, not tool identity.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Optional

#: Stamped into every plan; bump when compiled artifacts change shape.
COMPILER_VERSION = "toolcalling-1"

STRATEGIES = ("native", "constrained", "prompt", "disabled")

#: How a schema transformation relates canonical semantics to the wire schema.
CLASSIFICATIONS = ("equivalent", "reversibly_encoded", "locally_enforced", "narrowed", "unsupported")

#: Protocol ids; one adapter owns each.
PROTOCOLS = ("openai-chat", "anthropic-messages", "ollama-native", "openai-responses", "prompt-text")

#: Provider-visible tool-name constraints, per protocol. Conservative defaults.
_NAME_PATTERNS = {
    "openai-chat": re.compile(r"^[A-Za-z0-9_-]{1,64}$"),
    "anthropic-messages": re.compile(r"^[A-Za-z0-9_-]{1,64}$"),
    "openai-responses": re.compile(r"^[A-Za-z0-9_-]{1,64}$"),
    "ollama-native": re.compile(r"^[A-Za-z0-9_.-]{1,64}$"),
    "prompt-text": re.compile(r"^[A-Za-z0-9_.-]{1,96}$"),
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def schema_revision(schema: Any) -> str:
    return hashlib.sha256(canonical_json(schema).encode()).hexdigest()[:16]


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True)
class ToolDefinition:
    """One authorized tool, snapshotted for a single compilation."""

    name: str
    description: str
    parameters: Mapping[str, Any]
    dialect: str = "2020-12"
    owner: str = "builtin"
    scope: str = ""                       # connection/account binding this tool belongs to
    effect: str = ""                      # declared effect class when the tool states one
    capabilities: frozenset[str] = frozenset()
    policy: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    alias: str = ""                       # provider-visible name (defaults to ``name``)
    revision_hash: str = ""               # computed once at snapshot time

    @property
    def visible_name(self) -> str:
        return self.alias or self.name

    @property
    def revision(self) -> str:
        return self.revision_hash or schema_revision(self.canonical_schema())

    def canonical_schema(self) -> dict[str, Any]:
        return _thaw(self.parameters)

    @classmethod
    def from_tool(cls, tool: Any, *, owner: str = "builtin", scope: str = "",
                  protocol: str = "openai-chat") -> "ToolDefinition":
        schema = tool.parameters if isinstance(getattr(tool, "parameters", None), dict) else {}
        alias = ""
        pattern = _NAME_PATTERNS.get(protocol, _NAME_PATTERNS["openai-chat"])
        if not pattern.fullmatch(tool.name or ""):
            digest = hashlib.sha256(tool.name.encode()).hexdigest()[:10]
            alias = f"tool_{digest}"
            if not pattern.fullmatch(alias):  # pragma: no cover - pattern is permissive enough
                raise ValueError(f"cannot build a provider-visible alias for {tool.name!r}")
        return cls(name=tool.name, description=getattr(tool, "description", "") or "",
                   parameters=_deep_freeze(schema), owner=owner, scope=scope,
                   effect="", alias=alias, revision_hash=schema_revision(schema))


@dataclass(frozen=True)
class Diagnostic:
    """One field-level finding from schema analysis or lowering."""

    code: str
    severity: str                  # info | warning | error
    tool: str
    field: str                     # JSON-pointer-ish path inside the tool arguments
    classification: str
    detail: str

    def as_event(self) -> dict[str, Any]:
        return {"code": self.code, "severity": self.severity, "tool": self.tool,
                "field": self.field, "classification": self.classification, "detail": self.detail}


@dataclass(frozen=True)
class ActionCandidate:
    """A decoded but *unvalidated* model action. Nothing here has authority yet."""

    kind: str                      # call | final | clarify | invalid
    source: str                    # native | constrained | prompt
    tool: str = ""                 # provider-visible name as emitted
    arguments: Mapping[str, Any] = field(default_factory=dict)
    raw_arguments: str = ""        # exact argument text, kept for repair and re-encoding
    content: str = ""
    error: str = ""
    call_id: str = ""

    @property
    def is_call(self) -> bool:
        return self.kind == "call"


@dataclass(frozen=True)
class CompilationPlan:
    """Immutable per-model-turn snapshot of how the catalog will be represented."""

    strategy: str
    protocol: str
    profile_fingerprint: str
    profile_key: str
    tools: tuple[ToolDefinition, ...]
    wire_tools: tuple[dict[str, Any], ...]
    prompt_contract: str
    envelope_schema: Optional[Mapping[str, Any]] = None
    payload_field: str = "content"          # where the decoded action is expected
    aliases: Mapping[str, str] = field(default_factory=dict)   # visible -> canonical
    diagnostics: tuple[Diagnostic, ...] = ()
    catalog_hash: str = ""
    plan_hash: str = ""
    compiler_version: str = COMPILER_VERSION
    validator: str = ""
    compiled_ms: float = 0.0
    cache_hit: bool = False

    def resolve_name(self, visible: str) -> Optional[ToolDefinition]:
        """Reversible lookup: exact visible name -> canonical definition, or None."""
        canonical = self.aliases.get(visible, visible)
        for tool in self.tools:
            if tool.name == canonical:
                return tool
        return None

    def canonical_wire_payload(self) -> dict[str, Any]:
        """A serializable summary for diagnostics/events (never contains credentials)."""
        return {
            "strategy": self.strategy,
            "protocol": self.protocol,
            "profile": self.profile_key,
            "catalog_hash": self.catalog_hash,
            "plan_hash": self.plan_hash,
            "compiler_version": self.compiler_version,
            "validator": self.validator,
            "tools": [tool.name for tool in self.tools],
            "aliases": dict(self.aliases),
            "diagnostics": [d.as_event() for d in self.diagnostics],
        }
