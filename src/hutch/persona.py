"""Versioned response-style contracts.

One small typed vocabulary — depth, tone, banter — is stored sparsely per scope and resolved by precedence:
current turn → conversation → the owner's saved style for this agent → the agent's preset → the application
default. ``None`` means "not set at this scope"; explicit ``False``/values are preserved, and a reset is an
explicit ``None`` applied to a scope. The resolved plan is the write-once behavior snapshot for one run.
"""

from __future__ import annotations

import json
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

PERSONA_VERSION = 1

Depth = Literal["brief", "standard", "thorough"]
Tone = Literal["neutral", "warm", "direct"]

PERSONA_FIELDS = ("depth", "tone", "banter")

#: Resolution order, lowest precedence first.
LAYERS = ("application", "agent_preset", "agent_override", "conversation", "turn")

LAYER_LABELS = {
    "application": "Hutch default",
    "agent_preset": "Assistant preset",
    "agent_override": "Your saved style",
    "conversation": "This conversation",
    "turn": "This reply",
}


class PersonaStyle(BaseModel):
    """A sparse set of response-style values for one scope; unset fields inherit."""

    model_config = ConfigDict(extra="forbid")

    depth: Optional[Depth] = None
    tone: Optional[Tone] = None
    banter: Optional[bool] = None

    def changes(self) -> dict[str, Any]:
        """Only the fields present in the payload (an explicit null clears a field)."""
        return {name: getattr(self, name) for name in self.model_fields_set}


class PersonaPlan(BaseModel):
    """The resolved behavior snapshot for one run, with per-field provenance."""

    version: int = PERSONA_VERSION
    depth: Depth
    tone: Tone
    banter: bool
    sources: dict[str, str] = Field(default_factory=dict)
    revisions: dict[str, int] = Field(default_factory=dict)


#: The built-in application default: proportional depth, neutral voice, and playful replies
#: available only when the turn itself is clearly playful (evaluated per turn, never persisted).
APPLICATION_DEFAULT = PersonaStyle(depth="standard", tone="neutral", banter=True)


def apply_persona_changes(current: Optional[PersonaStyle], changes: dict[str, Any]) -> PersonaStyle:
    """Apply explicit changes to a scope's stored style (``None`` clears a field)."""
    unknown = set(changes) - set(PERSONA_FIELDS)
    if unknown:
        raise ValueError(f"unknown response-style fields: {sorted(unknown)}")
    values = (current or PersonaStyle()).model_dump()
    values.update(changes)
    return PersonaStyle.model_validate(values)


def encode_persona_state(style: Optional[PersonaStyle], revision: int) -> str:
    """One scope's durable payload: version, revision counter, sparse values."""
    return json.dumps({"version": PERSONA_VERSION, "revision": int(revision),
                       "values": (style or PersonaStyle()).model_dump(exclude_none=True)},
                      ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def decode_persona_state(raw: str | None) -> tuple[Optional[PersonaStyle], int]:
    """Read a scope payload; empty means "never set". A newer stored version is refused, not downgraded."""
    if not raw:
        return None, 0
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("response-style state must be a JSON object")
    version = int(data.get("version", PERSONA_VERSION))
    if version > PERSONA_VERSION:
        raise ValueError(f"response-style state was written by a newer Hutch (version {version})")
    revision = int(data.get("revision", 0))
    if revision < 0:
        raise ValueError("response-style revision must be non-negative")
    try:
        style = PersonaStyle.model_validate(data.get("values") or {})
    except ValueError as exc:
        raise ValueError(f"response-style values are invalid: {exc}") from None
    if not style.changes():
        return None, revision
    return style, revision


def resolve_persona(*, application: Optional[PersonaStyle] = None, agent_preset: Optional[PersonaStyle] = None,
                    agent_override: Optional[PersonaStyle] = None, conversation: Optional[PersonaStyle] = None,
                    turn: Optional[PersonaStyle] = None,
                    revisions: Optional[dict[str, int]] = None) -> PersonaPlan:
    """Resolve every field from the highest layer that set it, recording which layer won."""
    app = APPLICATION_DEFAULT if application is None else apply_persona_changes(
        APPLICATION_DEFAULT, application.model_dump(exclude_none=True))
    layer_styles = {"application": app, "agent_preset": agent_preset, "agent_override": agent_override,
                    "conversation": conversation, "turn": turn}
    values: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for name in LAYERS:
        style = layer_styles[name]
        if style is None:
            continue
        for field in PERSONA_FIELDS:
            value = getattr(style, field)
            if value is not None:
                values[field] = value
                sources[field] = name
    missing = [field for field in PERSONA_FIELDS if values.get(field) is None]
    if missing:
        raise ValueError(f"unresolved response-style fields: {missing}")
    return PersonaPlan(depth=values["depth"], tone=values["tone"], banter=values["banter"],
                       sources=sources, revisions=dict(revisions or {}))


_DEPTH_GUIDANCE = {
    "brief": "Lead with the result and keep routine answers short; expand only when the task asks for it.",
    "standard": "Match the answer's length to the task: short for simple questions, fuller when the work needs it.",
    "thorough": "Give complete, well-organized answers with the reasoning and details that matter, even when the task looks simple.",
}
_TONE_GUIDANCE = {
    "neutral": "Keep a calm, plain, professional voice.",
    "warm": "Keep a warm, personable voice without flattery or filler.",
    "direct": "Be direct and economical; skip pleasantries that add nothing.",
}
_BANTER_ON = ("Playful asides are allowed only when the operator is clearly joking or playing; judge every turn fresh and "
              "never carry playfulness into serious, urgent, safety, approval, or bad-news moments.")
_BANTER_OFF = "Do not use playful or joking language, even when the operator jokes."


def guidance(plan: PersonaPlan) -> str:
    """Render the resolved plan as subordinate prompt guidance. Pure and local: style never costs a model pass."""
    banter = _BANTER_ON if plan.banter else _BANTER_OFF
    return ("Response style chosen for this run. It shapes wording only and never overrides safety, permissions, tool "
            "rules, the task, the operator's explicit request, or detail needed to act correctly (errors, warnings, "
            "denials, approval facts):\n"
            f"- Depth: {_DEPTH_GUIDANCE[plan.depth]}\n"
            f"- Voice: {_TONE_GUIDANCE[plan.tone]}\n"
            f"- Playfulness: {banter}\n"
            "- Sensitive topics: set the style aside; be plain and steady, give the safe and useful part, state limits "
            "without moralizing, and never make light of a serious situation.\n"
            "Do not mention these settings; respond in them.")


__all__ = ["APPLICATION_DEFAULT", "LAYER_LABELS", "LAYERS", "PERSONA_FIELDS", "PERSONA_VERSION", "Depth", "Tone",
           "PersonaPlan", "PersonaStyle", "apply_persona_changes", "decode_persona_state", "encode_persona_state",
           "guidance", "resolve_persona"]
