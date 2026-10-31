"""The main assistant's way to suggest a new assistant. It proposes; the person creates."""

from __future__ import annotations

from ..proposals import MAX_PENDING, ProposalError, propose
from .base import Tool, ToolContext, ToolResult, rehearsed


class ProposeAssistantTool(Tool):
    name = "propose_assistant"
    description = (
        "Suggest a new, focused assistant for a job that needs a long-term owner. Nothing is created: the person reviews the "
        "suggestion, can change anything, and creates it themselves, or dismisses it. Keep the roster small: suggest one at a "
        f"time and ask before suggesting several (at most {MAX_PENDING} can wait). Give it a short name and say what it should "
        "own and hand back."
    )
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "minLength": 2, "maxLength": 60, "description": "A short, human name, e.g. Research Briefing"},
            "job": {"type": "string", "minLength": 10, "maxLength": 800, "description": "The one job it should own and what it hands back"},
            "why": {"type": "string", "maxLength": 300, "description": "Why this job deserves its own assistant"},
        },
        "required": ["name", "job"],
        "additionalProperties": False,
    }

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        if ctx.dry_run:
            return rehearsed(f"suggest the assistant {str(args.get('name', ''))[:60]} to the person")
        if ctx.store.workspace_coordinator_id() != ctx.bot.id:
            return ToolResult(ok=False, output="error: only the main assistant can suggest new assistants")
        try:
            item = propose(ctx.store, name=args.get("name", ""), job=args.get("job", ""), why=args.get("why", ""),
                           from_bot_id=ctx.bot.id, conversation_id=ctx.run.conversation_id or "")
        except ProposalError as exc:
            return ToolResult(ok=False, output=f"not suggested: {exc}")
        return ToolResult(ok=True, output=(f"Suggested {item['name']}. Nothing was created: the person sees it in their sidebar "
                                           "and decides. Tell them in one sentence what you suggested and why, then continue."),
                          data={"proposal_id": item["id"]})
