"""Memory tool — per-bot persistent facts in SQLite.

No embeddings in the MVP: the agent saves short key/value facts and recalls
them by listing (capped). Research and the reference products agree most bot
memory is small; a vector DB can come later (docs/roadmap.md).
"""

from __future__ import annotations

from typing import Any

from .base import Tool, ToolContext, ToolResult, _schema, clip, rehearsed

MAX_MEMORY_CHARS = 6_000


class MemorySaveTool(Tool):
    name = "remember"
    description = "Save a durable fact about your work as key/value. Persists across runs for this bot only."
    parameters = _schema(
        ["key", "value"],
        {
            "key": {"type": "string", "description": "Short stable name, e.g. 'preferred-format'"},
            "value": {"type": "string", "description": "The fact to remember (one or two sentences)"},
        },
    )

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        key, value = (args.get("key") or "").strip(), (args.get("value") or "").strip()
        if not key or not value:
            return ToolResult(ok=False, output="error: 'key' and 'value' are required")
        if ctx.dry_run:
            return rehearsed(f"remember '{key}'")
        ctx.store.remember(ctx.bot.id, key, clip(value, 2000), run_id=ctx.run.id)
        return ToolResult(ok=True, output=f"remembered '{key}'")


class MemoryRecallTool(Tool):
    name = "recall"
    description = "List this bot's remembered facts (optionally filtered by a search substring)."
    parameters = _schema([], {"query": {"type": "string", "description": "Substring filter for keys/values"}})

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        query = (args.get("query") or "").lower()
        items = [
            f"- {m.key}: {m.value}"
            for m in ctx.store.recall_all(ctx.bot.id)
            if not query or query in m.key.lower() or query in m.value.lower()
        ]
        text = "\n".join(items) if items else "(no memories yet)"
        return ToolResult(ok=True, output=clip(text, MAX_MEMORY_CHARS), data={"count": len(items)})
