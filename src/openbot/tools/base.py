"""Tool protocol and registry shared by all runtimes."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from ..config import OpenBotConfig
from ..models import Bot, Run
from ..safety import PolicyEngine
from ..approvals import ApprovalGate
from ..store import Store


@dataclass
class ToolResult:
    ok: bool
    output: str = ""          # text fed back to the model
    data: dict[str, Any] = field(default_factory=dict)


class Tool:
    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {}  # JSON Schema for the arguments object

    def run(self, args: dict[str, Any], ctx: "ToolContext") -> ToolResult:  # pragma: no cover
        raise NotImplementedError

    def spec(self) -> dict[str, Any]:
        """OpenAI-style function tool schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolContext:
    bot: Bot
    run: Run
    store: Store
    policy: PolicyEngine
    gate: ApprovalGate
    config: OpenBotConfig
    workspace: Path
    headless: bool = True
    on_finish: list[Callable[[], None]] = field(default_factory=list)
    emit: Optional[Callable[[Any], None]] = None  # sink for run events (used by browser pause-to-human)


MAX_TOOL_OUTPUT = 12_000  # chars — huge tool dumps blowing up context is a documented failure


def clip(text: str, limit: int = MAX_TOOL_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n… [output clipped, {len(text) - limit} chars omitted]"


def _schema(required: list[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required}
