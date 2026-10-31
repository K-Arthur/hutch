"""Pre-dispatch checks shared by every runtime that can run a tool (ADR-0017 S3).

Both rules below used to be convention rather than mechanism:

* JSON-Schema validation ran in the built-in model loop
  (``runtime.builtin``), so workflow nodes and the OpenCode bridge dispatched unvalidated
  arguments into whatever tool they named;
* approval and authority were whatever the tool itself chose to consult.

That is defensible for a first-party tool whose schema is a repository constant. It is not
defensible for a third-party tool whose schema arrives from a server and whose grant can be
revoked while a run is in flight. Enforcement therefore lives at the dispatch boundary that
``runtime.steps.call_tool`` owns, so no caller can be the one that forgot.

This module is deliberately outside ``runtime/steps.py``; that file is frozen over its size
cap and shrinks only.
"""

from __future__ import annotations

from typing import Any, Optional

from ..tools import Tool, ToolContext


def dispatch_refusal(tool: Tool, name: str, args: dict[str, Any], ctx: ToolContext) -> Optional[str]:
    """The reason this call must not run, or ``None`` when it may.

    Order matters. Authority is checked before the schema so a revoked grant never leaks
    whether the arguments would have matched, and a stale ``tools`` dict (built before the
    revocation) cannot revive authority the store no longer records.
    """
    binding_of = getattr(tool, "integration_binding", None)
    binding = binding_of() if callable(binding_of) else None
    if binding is not None:
        integration_id, server_tool_name = binding
        reader = getattr(ctx.store, "integration_tool_granted", None)
        if not callable(reader) or not reader(ctx.bot.id, integration_id, server_tool_name):
            return (f"`{name}` is no longer granted to this assistant for that connection; "
                    "nothing was run. Re-approve the tool in Apps & AI if it should be available.")
    try:
        from .toolrepair import validate_args
        problems = validate_args(tool.parameters or {}, args)
    except Exception:
        # A schema this install cannot analyse is a refusal, never a pass
        # (toolcalling.validate's own fail-closed rule).
        return f"`{name}` could not be checked against its registered schema; nothing was run."
    if problems:
        return f"`{name}` was rejected: {'; '.join(problems)}. Nothing was run."
    return None


__all__ = ["dispatch_refusal"]
