"""MCP tools as ordinary Hutch tools (ADR-0017 §3.1, §4.4).

One class owns the whole governed call shape, so a per-tool code path cannot forget the policy
check, the approval gate, the receipt or the schema re-check. The per-tool variation is *data*
the owner reviewed: the operation class recorded on the grant.

Dispatch already refuses a call whose grant was revoked (``runtime.dispatch``), and refuses
arguments that do not match ``parameters``. This class adds the three checks dispatch cannot make
because they need the reviewed catalog:

1. the schema revision the grant was approved against still matches the catalog;
2. a tool that needs approval asks for it, with the exact tool, account and arguments shown;
3. the grant is re-read after the human wait, because a revocation while the approval card is
   open must not be overtaken by an approval the owner has since withdrawn.

Server output is untrusted text. It is bounded, and a result that merely *looks* successful is
not reported as a completed external effect: ``isError`` from the server is honoured, and an
ambiguous transport failure is reported as unknown rather than retried.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ...approvals import DeniedError
from ...safety import Decision, Verdict
from ...toolcalling.validate import validate_call
from ...tools.base import Tool, ToolContext, ToolResult
from .config import McpConfigurationError
from .discovery import MAX_DISCOVERED_TOOLS
from .network import McpEndpointError
from .transport import OPERATION_DEADLINE_SECONDS, open_client

MAX_RESULT_BYTES = 256 * 1024


def _is_transport_failure(error: BaseException) -> bool:
    """True for the SDK/HTTP failure shapes that mean 'the link broke', not 'the server refused'."""
    import httpx2
    if isinstance(error, (httpx2.TransportError, ConnectionError, BrokenPipeError)):
        return True
    if isinstance(error, BaseExceptionGroup):
        return any(_is_transport_failure(item) for item in error.exceptions)
    return False

#: The approval-required classes. ``read`` is the only class that may run without asking.
_SILENT_CLASSES = frozenset({"read"})


def _public_result(result: Any) -> tuple[bool, str]:
    """Retain bounded text/structured output only; binary blocks stay out of the transcript."""
    chunks: list[str] = []
    structured = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
    if structured is not None:
        chunks.append(json.dumps(structured, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":"), allow_nan=False))
    for item in getattr(result, "content", None) or []:
        kind = getattr(item, "type", "")
        if kind == "text" and isinstance(getattr(item, "text", None), str):
            chunks.append(item.text)
        elif kind in {"image", "audio", "resource", "resource_link"}:
            chunks.append(f"[{kind} content omitted]")
    text = "\n".join(chunks) or "The MCP server returned no text content."
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) > MAX_RESULT_BYTES:
        text = encoded[:MAX_RESULT_BYTES].decode("utf-8", errors="ignore")
        text += "\n[server output clipped at Hutch's 256 KiB MCP result limit]"
    return bool(getattr(result, "is_error", False)), text


class McpToolAdapter(Tool):
    """One reviewed MCP tool, bound to the integration identity and the Bot grant that allows it."""

    def __init__(self, *, integration_id: str, server_tool_name: str, canonical_name: str,
                 schema_revision: str, input_schema: dict[str, Any], description: str,
                 operation_class: str, definition: dict[str, Any], title: str = "") -> None:
        self.name = canonical_name
        self.parameters = input_schema or {"type": "object", "properties": {}}
        self._integration_id = integration_id
        self._server_tool_name = server_tool_name
        self._schema_revision = schema_revision
        self._operation_class = operation_class if operation_class in {"read", "write", "destructive", "unknown"} else "unknown"
        self._definition = definition
        self._label = title or server_tool_name
        self.description = self._compose_description(description)

    def _compose_description(self, description: str) -> str:
        """Describe the tool as data from an external server, never as instructions to follow."""
        effect = {"read": "Read-only according to the owner's review.",
                  "write": "Changes data; every call needs approval.",
                  "destructive": "Can delete or overwrite; every call needs approval.",
                  "unknown": "Effect not yet classified; every call needs approval."}[self._operation_class]
        body = (description or "").strip()
        prefix = f"External tool '{self._label}' from the {self._integration_id} connector. {effect}"
        if not body:
            return prefix
        return f"{prefix} The server describes it as: {body}"[:8000]

    # -- governed identity -------------------------------------------------

    def integration_binding(self) -> tuple[str, str]:
        return self._integration_id, self._server_tool_name

    def effect(self, args: dict[str, Any], ctx: ToolContext) -> str:
        """Reads leave no receipt; anything else is bracketed by an intent and a receipt (ADR-0003)."""
        if self._operation_class in _SILENT_CLASSES:
            return ""
        transport = self._definition.get("transport", "")
        return "web" if transport == "mcp_http" else "process"

    def recorded_arguments(self, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        return {**args, "integration_id": self._integration_id, "server_tool": self._server_tool_name}

    # -- execution ---------------------------------------------------------

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        from . import service
        grant = service.grant_for(ctx.store, ctx.bot.id, self._integration_id, self._server_tool_name)
        if not grant:
            return ToolResult(False, "This connector tool is no longer granted to this assistant; nothing was run.")
        if grant.get("schema_revision") and grant["schema_revision"] != self._schema_revision:
            return ToolResult(
                False, "The connector's tool definition changed since it was reviewed; ask the owner to review "
                       "this assistant's access again. Nothing was run.")
        # The effect class the owner set is part of the authority. It can be re-classified without the
        # schema changing, so a tool dict built while the class was 'read' must not execute a class that
        # now needs approval.
        if (grant.get("operation_class") or "unknown") != self._operation_class:
            return ToolResult(
                False, "This connector tool's effect class changed since this run started; "
                       "nothing was run. Start a new run so the new review applies.")

        problems = validate_call(self.parameters, args)
        if problems:
            return ToolResult(False, f"The connector rejected these arguments before sending: {'; '.join(problems)}")

        if ctx.dry_run:
            return ToolResult(True, f"[rehearsal] would call {self._label} on the {self._integration_id} connector. "
                                    "Nothing was sent.", {"simulated": True})

        if self._operation_class not in _SILENT_CLASSES:
            detail = {"connector": self._integration_id, "tool": self._server_tool_name,
                      "account": grant.get("account_label") or self._integration_id,
                      "arguments": args, "effect": self._operation_class}
            # An empty sticky key means no standing "always allow" can ever cover a connector call
            # that was not classified as a read: the owner reviews each one, which is what the page,
            # the readiness report and the documentation all promise.
            decision = Decision(Verdict.ask, f"connector {self._operation_class}", sticky_key="",
                                outward=self._operation_class == "destructive", risk="high")
            try:
                ctx.gate.decide(self.name, f"Use {self._label} on {grant.get('account_label') or self._integration_id}",
                                detail, decision=decision, ask_in_auto=True)
            except DeniedError as exc:
                return ToolResult(False, f"the connector call was not approved; nothing was sent ({exc})")
            current = service.grant_for(ctx.store, ctx.bot.id, self._integration_id, self._server_tool_name)
            if not current or (current.get("schema_revision") or "") != (self._schema_revision or ""):
                return ToolResult(False, "connector access changed while approval was pending; nothing was sent.")
            if (current.get("operation_class") or "unknown") != self._operation_class:
                return ToolResult(False, "this connector tool's effect class changed while approval was "
                                         "pending; nothing was sent.")
            # The intent row is written here, immediately before the call, never around the approval
            # wait: a run killed while a person is deciding has not started anything (ADR-0003).
            refusal = ctx.begin_effect()
            if refusal:
                return ToolResult(False, f"error: {refusal}")

        return self._call(args, ctx)

    def _call(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        import anyio

        async def invoke() -> tuple[bool, str]:
            with anyio.fail_after(OPERATION_DEADLINE_SECONDS):
                async with open_client(self._definition, ctx.workspace) as client:
                    result = await client.call_tool(self._server_tool_name, args)
                    if getattr(result, "result_type", "complete") != "complete":
                        return False, ("The connector asked for follow-up input. Hutch does not grant extra "
                                       "authority to a connector prompt; nothing further was sent.")
                    return _public_result(result)

        try:
            is_error, text = anyio.run(invoke)
        except McpConfigurationError:
            raise
        except (McpEndpointError, TimeoutError, OSError, ValueError):
            # No partially applied result is claimed here: a transport failure is reported as a
            # failure, and a non-idempotent call is never retried automatically (brief §8.5).
            return ToolResult(False, "The connector call did not complete. Nothing is confirmed to have happened; "
                                     "check the service before retrying.")
        except Exception as error:
            if _is_transport_failure(error):
                return ToolResult(False, "The connector call lost its connection. Nothing is confirmed to have "
                                         "happened; check the service before retrying.")
            return ToolResult(False, "The connector could not complete this call; it returned an error Hutch does "
                                     "not interpret as success.")
        if is_error:
            return ToolResult(False, text, {"connector_error": True})
        return ToolResult(True, text, {"integration_id": self._integration_id,
                                       "server_tool": self._server_tool_name})


def construct_mcp_tools(store: Any, bot: Any, run: Any = None) -> dict[str, Tool]:
    """Build the MCP tools this Bot's reviewed grants allow, for ``build_tools``.

    Returns an empty mapping when the Bot's route cannot govern an external call: Strict Offline
    Bots have no host network, and both gates are re-checked at dispatch anyway. A Bot object
    without a usable id (a stripped-down caller or a partial model in a test) yields no tools
    rather than an error, because ``build_tools`` must keep working for every caller.
    """
    if getattr(getattr(bot, "inference_mode", None), "value", "") == "offline":
        return {}
    bot_id = getattr(bot, "id", "")
    if not isinstance(bot_id, str) or not bot_id:
        return {}
    from . import service
    rows = service.tools_for(store, bot_id)
    if not rows or len(rows) > MAX_DISCOVERED_TOOLS:
        return {}
    tools: dict[str, Tool] = {}
    for row in rows:
        definition = row.get("definition")
        if not isinstance(definition, dict):
            continue
        tools[row["canonical_name"]] = McpToolAdapter(
            integration_id=row["integration_id"], server_tool_name=row["server_tool_name"],
            canonical_name=row["canonical_name"], schema_revision=row.get("schema_revision", ""),
            input_schema=row.get("input_schema") or {}, description=row.get("description", ""),
            operation_class=row.get("operation_class", "unknown"), definition=definition,
            title=row.get("title", ""))
    return tools


__all__ = ["MAX_RESULT_BYTES", "McpToolAdapter", "construct_mcp_tools"]
