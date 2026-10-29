"""Typed integration identity and consent contracts (ADR-0017 §3.1, §4.1, §7).

Identities are stable and separate from display labels: an ``Integration`` is named by a slug
plus the revision hash of its reviewed manifest, and its tools are named
``mcp__<integration>__<tool>`` (the collision map itself is slice S3). The five consent states are
independent gates, install/config, reachability, authentication, capability discovery, and
per-operation authorization, and connection identity or discovery visibility is never
authorization (§7): a higher state never implies the ones below it.

This module is contracts only: no I/O, no transport, no MCP. ``integrations/catalog.py`` derives
the shared tool enumerations from it and from the native tool registry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

#: Integration slugs: lowercase, short, and safe to embed in a canonical tool name.
INTEGRATION_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class IntegrationTransport(str, Enum):
    """How Hutch reaches the integration. Only non-in-process transports engage the MCP client
    manager (S2); the stages of the brief's chain are contracts, not mandatory hops (§3.1)."""

    IN_PROCESS = "in_process"
    MCP_STDIO = "mcp_stdio"
    MCP_HTTP = "mcp_http"


class IntegrationState(str, Enum):
    """The five consent states, in dependency order (§7). Each is an independent gate that is
    earned by an explicit reviewed act; nothing advances automatically past what was checked."""

    INSTALLED = "installed"                              # config saved; never run
    REACHABLE = "reachable"                              # transport answered
    AUTHENTICATED = "authenticated"                      # credentials accepted
    CAPABILITIES_DISCOVERED = "capabilities_discovered"  # tools/list read and reviewed
    OPERATION_AUTHORIZED = "operation_authorized"        # a per-operation grant exists


#: The consent ladder in order; a state is only meaningful if every state before it was earned.
CONSENT_STATES: tuple[IntegrationState, ...] = (
    IntegrationState.INSTALLED,
    IntegrationState.REACHABLE,
    IntegrationState.AUTHENTICATED,
    IntegrationState.CAPABILITIES_DISCOVERED,
    IntegrationState.OPERATION_AUTHORIZED,
)


def validate_integration_id(integration_id: str) -> str:
    """Return the slug unchanged if it is a legal integration identity, else raise ValueError."""
    if not INTEGRATION_ID_PATTERN.fullmatch(integration_id or ""):
        raise ValueError(f"'{integration_id}' is not a valid integration id (lowercase slug, "
                         "starts with a letter, at most 64 characters)")
    return integration_id


def canonical_tool_name(integration_id: str, server_tool_name: str) -> str:
    """The reversible namespaced tool name: ``mcp__<integration>__<tool>`` (§3.1).

    Collisions with existing names are recorded in the store's collision map (S3); derivation here
    stays pure so the same integration always yields the same canonical name.
    """
    validate_integration_id(integration_id)
    if not server_tool_name or len(server_tool_name) > 128 or any(ord(c) < 32 for c in server_tool_name):
        raise ValueError(f"'{server_tool_name}' is not a valid server tool name")
    return f"mcp__{integration_id}__{server_tool_name}"


@dataclass(frozen=True)
class Integration:
    """One reviewed integration: identity, transport, credential reference, consent state (§3.1).

    ``revision`` is the hash of the reviewed manifest the operator consented to; a material change
    produces a new revision, which invalidates prior approvals (§4.4). ``credential_id`` references
    the existing key storage pattern (env var or 0600 file), a secret itself is never stored here.
    """

    integration_id: str
    revision: str
    transport: IntegrationTransport
    title: str = ""                       # display label; never the identity
    credential_id: str = ""               # reference into existing key storage, by name
    state: IntegrationState = IntegrationState.INSTALLED
    enabled: bool = False                 # new authority ships disabled (§8)

    def __post_init__(self) -> None:
        validate_integration_id(self.integration_id)

    def consent_reached(self, state: IntegrationState) -> bool:
        """True if ``state`` and every gate before it were earned (§7's ordered gates)."""
        if self.state not in CONSENT_STATES or state not in CONSENT_STATES:
            return False
        return CONSENT_STATES.index(self.state) >= CONSENT_STATES.index(state)


@dataclass(frozen=True)
class IntegrationToolGrant:
    """One per-bot tool visibility grant (§4.1): ``(integration_id, server_tool_name)`` → canonical
    name, bound to exactly one Bot. Grant rows are reviewed store rows, not allowlist strings,    the pattern the grant-gated calendar tools established. ``schema_revision`` is the sha256 of
    the ``tools/list`` result that produced the spec, re-checked before each protected call (§4.4).
    """

    integration_id: str
    bot_id: str
    server_tool_name: str
    canonical_name: str = ""
    schema_revision: str = ""
    granted_at: Optional[str] = None

    def __post_init__(self) -> None:
        validate_integration_id(self.integration_id)
        if not self.canonical_name:
            object.__setattr__(self, "canonical_name",
                               canonical_tool_name(self.integration_id, self.server_tool_name))
