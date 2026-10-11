"""Versioned response-style contracts.

Sparse preferences are resolved by precedence: current turn → conversation → the owner's saved style for this
agent → the agent's preset → application defaults. ``None`` means "not set at this scope"; explicit false,
zero, empty lists, and reset-to-inherit are preserved. A run receives one write-once behavior snapshot.
"""

from __future__ import annotations

import json
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

PERSONA_VERSION = 2
PERSONA_PROFILE_VERSION = 2

Depth = Literal["auto", "brief", "standard", "detailed", "thorough"]
Preset = Literal["direct", "warm", "dry_wit"]
Humor = Literal["off", "subtle", "playful"]
Tone = Literal["neutral", "warm", "direct"]
Profanity = Literal["avoid", "mirror"]
FormatStyle = Literal["automatic", "conversational", "structured", "bullets"]
AvoidHabit = Literal["filler", "overpraise", "emojis", "repeated_summary", "unasked_offer"]

PERSONA_FIELDS = ("preset", "depth", "tone", "humor", "banter", "warmth", "directness", "formality",
                  "profanity", "format_style", "avoid_habits")
PERSONA_V1_FIELDS = frozenset({"depth", "tone", "banter"})
_CUSTOM_FIELDS = ("warmth", "directness", "formality", "profanity", "format_style", "avoid_habits")

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

    preset: Optional[Preset] = None
    depth: Optional[Depth] = None
    tone: Optional[Tone] = None
    humor: Optional[Humor] = None
    banter: Optional[bool] = None
    warmth: Optional[int] = Field(default=None, ge=0, le=100)
    directness: Optional[int] = Field(default=None, ge=0, le=100)
    formality: Optional[int] = Field(default=None, ge=0, le=100)
    profanity: Optional[Profanity] = None
    format_style: Optional[FormatStyle] = None
    avoid_habits: Optional[list[AvoidHabit]] = Field(default=None, max_length=5)

    def changes(self) -> dict[str, Any]:
        """Only the fields present in the payload (an explicit null clears a field)."""
        return {name: getattr(self, name) for name in self.model_fields_set}


class PersonaPlan(BaseModel):
    """The resolved behavior snapshot for one run, with per-field provenance."""

    version: int = PERSONA_VERSION
    preset: Optional[Preset] = None
    depth: Depth
    tone: Tone
    humor: Humor = "subtle"
    banter: bool = True                 # compatibility projection for v1 clients and stored plans
    warmth: int = Field(default=50, ge=0, le=100)
    directness: int = Field(default=50, ge=0, le=100)
    formality: int = Field(default=40, ge=0, le=100)
    profanity: Profanity = "avoid"
    format_style: FormatStyle = "automatic"
    avoid_habits: list[AvoidHabit] = Field(default_factory=list, max_length=5)
    sources: dict[str, str] = Field(default_factory=dict)
    revisions: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _legacy_banter_projection(self) -> "PersonaPlan":
        fields = self.model_fields_set
        if "humor" in fields:
            self.banter = self.humor != "off"
        elif "banter" in fields:
            self.humor = "subtle" if self.banter else "off"
        return self


#: The built-in application default preserves the old neutral voice and light, clearly invited playfulness.
#: Humor eligibility is still re-evaluated each turn and is never stored as a durable preference by inference.
APPLICATION_DEFAULT = PersonaStyle(depth="auto", tone="neutral", banter=True)


def apply_persona_changes(current: Optional[PersonaStyle], changes: dict[str, Any]) -> PersonaStyle:
    """Apply explicit changes to a scope's stored style (``None`` clears a field)."""
    unknown = set(changes) - set(PERSONA_FIELDS)
    if unknown:
        raise ValueError(f"unknown response-style fields: {sorted(unknown)}")
    values = (current or PersonaStyle()).model_dump()
    values.update(changes)
    # A newly selected named preset replaces legacy tone/joking values that older forms may have saved.
    # New explicit tone/humor values in the same request remain independent overrides.
    if changes.get("preset") is not None and "preset" in changes:
        if "tone" not in changes:
            values["tone"] = None
        if "banter" not in changes and "humor" not in changes:
            values["banter"] = None
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
    version = data.get("version", 1)
    if not isinstance(version, int) or isinstance(version, bool):
        raise ValueError("response-style version must be an integer")
    if version < 1:
        raise ValueError("response-style version must be positive")
    if version > PERSONA_VERSION:
        raise ValueError(f"response-style state was written by a newer Hutch (version {version})")
    revision = data.get("revision", 0)
    if not isinstance(revision, int) or isinstance(revision, bool):
        raise ValueError("response-style revision must be an integer")
    if revision < 0:
        raise ValueError("response-style revision must be non-negative")
    raw_values = data.get("values") or {}
    if version == 1 and isinstance(raw_values, dict) and (set(raw_values) - PERSONA_V1_FIELDS):
        raise ValueError("response-style version 1 contains fields this build cannot interpret")
    try:
        style = PersonaStyle.model_validate(raw_values)
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
    values: dict[str, Any] = {
        "preset": None, "depth": "auto", "tone": "neutral", "humor": "subtle", "banter": True,
        "warmth": 50, "directness": 50, "formality": 40, "profanity": "avoid",
        "format_style": "automatic", "avoid_habits": [],
    }
    sources: dict[str, str] = {field: "application" for field in PERSONA_FIELDS}
    preset_defaults: dict[str, tuple[Tone, Humor]] = {
        "direct": ("direct", "off"),
        "warm": ("warm", "off"),
        "dry_wit": ("direct", "playful"),
    }
    for name in LAYERS:
        style = layer_styles[name]
        if style is None:
            continue
        # Selecting a named preset establishes its voice and humor defaults at this scope. Explicit fields in
        # the same or any later scope remain independent overrides; a later preset replaces only preset-driven
        # voice and humor while leaving depth and bounded customization alone.
        if style.preset is not None:
            values["preset"] = style.preset
            values["tone"], values["humor"] = preset_defaults[style.preset]
            values["banter"] = values["humor"] != "off"
            sources.update({"preset": name, "tone": name, "humor": name, "banter": name})
        if style.depth is not None:
            values["depth"] = "detailed" if style.depth == "thorough" else style.depth
            sources["depth"] = name
        if style.tone is not None:
            values["tone"] = style.tone
            sources["tone"] = name
        if style.humor is not None:
            values["humor"] = style.humor
            values["banter"] = style.humor != "off"
            sources.update({"humor": name, "banter": name})
        elif style.banter is not None:
            # v1 compatibility: true keeps the existing subtle, clearly-invited behavior; false means off.
            values["humor"] = "subtle" if style.banter else "off"
            values["banter"] = style.banter
            sources.update({"humor": name, "banter": name})
        for field in _CUSTOM_FIELDS:
            value = getattr(style, field)
            if value is not None:
                values[field] = value
                sources[field] = name
    return PersonaPlan(**values, sources=sources, revisions=dict(revisions or {}))


_DEPTH_GUIDANCE = {
    "auto": "Choose length from the task: concise for simple requests, fuller for complex or high-stakes work; never omit necessary work.",
    "brief": "Lead with the result and keep routine answers short; retain every step, caveat, and fact needed to act correctly.",
    "standard": "Match the answer's length to the task: short for simple questions, fuller when the work needs it.",
    "detailed": "Give complete, well-organized answers with relevant evidence and explanation; do not add unrelated detail.",
    "thorough": "Give complete, well-organized answers with relevant evidence and explanation; do not add unrelated detail.",
}
_TONE_GUIDANCE = {
    "neutral": "Keep a calm, plain, professional voice.",
    "warm": "Keep a warm, personable voice without flattery or filler.",
    "direct": "Be direct and economical; skip pleasantries that add nothing.",
}
_PRESET_GUIDANCE = {
    "direct": "Prefer a clear answer first, precise language, and useful next steps; preserve uncertainty when it matters.",
    "warm": "Be approachable and considerate without excessive reassurance, praise, or filler.",
    "dry_wit": "Use restrained dry wit only when it fits the operator's low-stakes playful tone; never target the operator or trivialize harm.",
}
_HUMOR_GUIDANCE = {
    "off": "Do not use jokes or playful asides, even when the operator jokes.",
    "subtle": "A brief light aside is allowed only when this turn is clearly playful and low-stakes; judge each turn fresh.",
    "playful": "Playful wording is allowed when this turn is clearly playful and low-stakes; do not force a joke into every answer.",
}
_FORMAT_GUIDANCE = {
    "automatic": "Choose prose or structure to fit the task.",
    "conversational": "Prefer natural prose unless the task benefits from a list or table.",
    "structured": "Use descriptive headings and grouped sections when they make the answer easier to scan.",
    "bullets": "Prefer concise bullet lists where they preserve meaning and readability.",
}
_HABIT_GUIDANCE = {
    "filler": "Avoid filler openings and closings.",
    "overpraise": "Avoid unearned praise and flattering agreement.",
    "emojis": "Avoid emojis.",
    "repeated_summary": "Avoid repeating the same conclusion at the beginning and end.",
    "unasked_offer": "Do not add an unasked offer of further help at the end.",
}


def guidance(plan: PersonaPlan) -> str:
    """Render the resolved plan as subordinate prompt guidance. Pure and local: style never costs a model pass."""
    humor = plan.humor if plan.version >= 2 else ("subtle" if plan.banter else "off")
    preset = f"- Preset: {_PRESET_GUIDANCE[plan.preset]}\n" if plan.preset else ""
    habit_guidance = " ".join(_HABIT_GUIDANCE[habit] for habit in plan.avoid_habits)
    habits = f"- Habits to avoid: {habit_guidance}\n" if habit_guidance else ""
    return ("Response style chosen for this run. It shapes wording only and never overrides safety, permissions, tool "
            "rules, the task, the operator's explicit request, or detail needed to act correctly (errors, warnings, "
            "denials, approval facts):\n"
            f"- Depth: {_DEPTH_GUIDANCE[plan.depth]}\n"
            f"{preset}"
            f"- Voice: {_TONE_GUIDANCE[plan.tone]}\n"
            f"- Humor: {_HUMOR_GUIDANCE[humor]}\n"
            f"- Warmth: {plan.warmth}/100; directness: {plan.directness}/100; formality: {plan.formality}/100.\n"
            f"- Profanity: {'mirror it only if the operator used it first and the context is suitable.' if plan.profanity == 'mirror' else 'avoid it.'}\n"
            f"- Format: {_FORMAT_GUIDANCE[plan.format_style]}\n"
            + habits
            + "- Sensitive topics: set the style aside; be plain and steady, give the safe and useful part, state limits "
            "without moralizing, and never make light of a serious situation. Never make the operator the target of a joke.\n"
            "Do not mention these settings; respond in them.")


__all__ = ["APPLICATION_DEFAULT", "AvoidHabit", "Depth", "FormatStyle", "Humor", "LAYER_LABELS", "LAYERS",
           "PERSONA_FIELDS", "PERSONA_PROFILE_VERSION", "PERSONA_V1_FIELDS", "PERSONA_VERSION", "Preset", "Profanity",
           "Tone", "PersonaPlan", "PersonaStyle", "apply_persona_changes", "decode_persona_state",
           "encode_persona_state", "guidance", "resolve_persona"]
