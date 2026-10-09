"""Conversational clarification tools, separate from action permissions."""

from __future__ import annotations

from .base import Tool, ToolContext, ToolResult


class AskUserChoiceTool(Tool):
    name = "ask_user_choice"
    description = ("Ask the user a bounded single- or multiple-choice question in this conversation. "
                   "The answer is a conversational preference only; it does not approve or authorize an action. "
                   "Use only when a decision is genuinely needed to continue.")
    parameters = {
        "type": "object",
        "properties": {
            "question": {"type": "string", "minLength": 1, "maxLength": 1000},
            "selection_mode": {"type": "string", "enum": ["single", "multiple"]},
            "options": {"type": "array", "minItems": 2, "maxItems": 12,
                         "items": {"type": "string", "minLength": 1, "maxLength": 160}},
        },
        "required": ["question", "selection_mode", "options"],
        "additionalProperties": False,
    }

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        if ctx.dry_run:
            return ToolResult(ok=False, output="structured questions are unavailable in rehearsal; ask the user directly in chat")
        if not ctx.run.conversation_id:
            return ToolResult(ok=False, output="structured questions are available only inside a conversation")
        try:
            saved = ctx.store.create_conversation_question(
                ctx.run.id, args.get("question", ""), args.get("selection_mode", ""),
                args.get("options", []), fence=ctx.run.fence)
        except (ValueError, RuntimeError) as exc:
            return ToolResult(ok=False, output=f"question was not saved: {exc}")
        return ToolResult(ok=True, output="The question is saved. Stop this run and wait for the user's selection.",
                          data={"question_pending": True, "question_id": saved["id"]})
