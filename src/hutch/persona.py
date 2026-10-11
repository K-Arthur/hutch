"""Versioned response-style contracts.

Sparse preferences are resolved by precedence: current turn → conversation → the owner's saved style for this
agent → the agent's preset → application defaults. ``None`` means "not set at this scope"; explicit false,
zero, empty lists, and reset-to-inherit are preserved. A run receives one write-once behavior snapshot.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

PERSONA_VERSION = 3
PERSONA_PROFILE_VERSION = 2

Depth = Literal["auto", "brief", "standard", "detailed", "thorough"]
Preset = Literal["direct", "warm", "dry_wit"]
Humor = Literal["off", "subtle", "playful"]
Tone = Literal["neutral", "warm", "direct"]
Profanity = Literal["avoid", "mirror"]
FormatStyle = Literal["automatic", "conversational", "structured", "bullets"]
AvoidHabit = Literal["filler", "overpraise", "emojis", "repeated_summary", "unasked_offer"]
Intent = Literal["general", "banter", "analysis", "current_facts", "high_stakes", "coding",
                 "recipient_draft", "external_action", "correction"]
Audience = Literal["operator", "recipient"]
GroundingNeed = Literal["conversation", "current_facts", "external_sources", "workspace", "tool_execution"]
OutputContract = Literal["freeform", "json", "code", "citations", "recipient_draft"]
ResolvedDepth = Literal["brief", "standard", "detailed"]
DiagnosticReason = Literal["clear_humor_request", "analytical_work", "current_information",
                           "external_sources", "high_stakes_cue", "code_or_workspace_work", "recipient_draft",
                           "external_action", "answer_correction", "structured_output"]

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
    """The resolved wording and contextual response plan snapshot for one run."""

    version: int = PERSONA_VERSION
    preset: Optional[Preset] = None
    depth: Depth
    resolved_depth: ResolvedDepth = "standard"
    tone: Tone
    humor: Humor = "subtle"
    humor_eligible: bool = False
    banter: bool = True                 # compatibility projection for v1 clients and stored plans
    warmth: int = Field(default=50, ge=0, le=100)
    directness: int = Field(default=50, ge=0, le=100)
    formality: int = Field(default=40, ge=0, le=100)
    profanity: Profanity = "avoid"
    format_style: FormatStyle = "automatic"
    avoid_habits: list[AvoidHabit] = Field(default_factory=list, max_length=5)
    intent: Intent = "general"
    audience: Audience = "operator"
    grounding_needs: list[GroundingNeed] = Field(default_factory=list, max_length=4)
    output_contract: OutputContract = "freeform"
    diagnostic_reasons: list[DiagnosticReason] = Field(default_factory=list, max_length=4)
    sources: dict[str, str] = Field(default_factory=dict)
    revisions: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _decode_prior_plan_shape(cls, raw: Any) -> Any:
        """Older write-once plans had only saved style; preserve their explicit depth when loading."""
        if not isinstance(raw, dict):
            return raw
        value = dict(raw)
        version = value.get("version", PERSONA_VERSION)
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ValueError("response-plan version must be a positive integer")
        if "resolved_depth" not in value:
            selected = value.get("depth", "standard")
            value["resolved_depth"] = selected if selected in {"brief", "standard", "detailed"} else (
                "detailed" if selected == "thorough" else "standard")
        # Historical write-once plans were applied without contextual humor gating. Keep a retry stable.
        if isinstance(version, int) and not isinstance(version, bool) and version < 3 and "humor_eligible" not in value:
            value["humor_eligible"] = True
        return value

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
    # An explicit v2 preset replaces the old voice alias at this scope. A v2 humor choice replaces the old
    # joking alias. This lets newer controls reset old values without losing them during an unrelated edit.
    if "preset" in changes:
        if "tone" not in changes:
            values["tone"] = None
        if "banter" not in changes and "humor" not in changes:
            values["banter"] = None
    if "humor" in changes and "banter" not in changes:
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
    selected_depth = values["depth"]
    resolved_depth = selected_depth if selected_depth in {"brief", "standard", "detailed"} else (
        "detailed" if selected_depth == "thorough" else "standard")
    return PersonaPlan(**values, resolved_depth=resolved_depth, sources=sources, revisions=dict(revisions or {}))


_HIGH_STAKES_RE = re.compile(
    r"\b(?:medical|health|medicine|medication|diagnos\w*|legal|lawyer|attorney|court|lawsuit|tax|"
    r"debt|loan|mortgage|credit|investment|financial|finance|bankrupt\w*|suicid\w*|self[- ]harm|"
    r"weapon|violence|pregnan\w*|emergency)\b",
    re.IGNORECASE,
)
_CURRENT_FACT_RE = re.compile(
    r"\b(?:latest|current|right now|today|this week|as of|up[- ]to[- ]date|price|weather|news|score|"
    r"recent|currently)\b",
    re.IGNORECASE,
)
_SOURCE_RE = re.compile(r"\b(?:search|look up|research|verify|check whether|cite sources|with citations)\b",
                        re.IGNORECASE)
_CODING_RE = re.compile(
    r"\b(?:code|coding|programming|script|function|class|repository|repo|debug|refactor|compile|terminal|shell|"
    r"pull request|commit)\b|```",
    re.IGNORECASE,
)
_ANALYSIS_RE = re.compile(
    r"\b(?:analy[sz]e|analysis|compare|evaluate|investigate|research|audit|pros and cons|step by step|"
    r"in detail|reasoning)\b",
    re.IGNORECASE,
)
_RECIPIENT_DRAFT_RE = re.compile(
    r"\b(?:draft|write|compose|rewrite)\s+(?:an?\s+)?(?:email|letter|message|reply|note|text)\s+to\b|"
    r"\b(?:email|letter|message|reply|note)\s+to\s+(?:my|the|our|[A-Z][\w'-]*)",
    re.IGNORECASE,
)
_ACTION_RE = re.compile(
    r"\b(?:send|delete|book|buy|purchase|pay|transfer|schedule|post|publish|submit|cancel|invite)\s+"
    r"(?:the|this|that|my|our|a|an|to|for|on)\b",
    re.IGNORECASE,
)
_HUMOR_RE = re.compile(r"\b(?:joke|pun|make it funny|keep it playful|be playful|haha+|lol+|lmao|hilarious)\b",
                       re.IGNORECASE)
_SHORTER_RE = re.compile(
    r"^\s*(?:please\s+)?(?:shorter|more concise|less detail|just the answer)(?:\s*,?\s*please)?[.!?]?\s*$|"
    r"\b(?:make|keep|rewrite|revise)\s+(?:that|it|this|the answer|the reply)\s+"
    r"(?:shorter|more concise|with less detail)\b",
    re.IGNORECASE,
)
_DEEPER_RE = re.compile(r"\b(?:go deeper|more detail|expand on that)\b", re.IGNORECASE)
_LESS_HUMOR_RE = re.compile(r"\b(?:less banter|less joking|no jokes|stop joking)\b",
                            re.IGNORECASE)
_CONVERSATION_REF_RE = re.compile(
    r"\b(?:above|earlier|previous(?: answer| reply)?|last answer|what you said|that answer|"
    r"what we discussed|what you told me|what i told you|from last time|last time)\b",
    re.IGNORECASE,
)
_PERSONAL_CONTEXT_RE = re.compile(
    r"\b(?:my\s+(?:favorite|usual|calendar|schedule|emails?|files?|notes?)|"
    r"(?:this|that|the|attached|uploaded)\s+(?:email|message|calendar event)|"
    r"(?:last|previous)\s+(?:email|message|calendar event)|"
    r"what\s+(?:i|you)\s+(?:said|told you)|what we discussed)\b",
    re.IGNORECASE,
)
_WORKSPACE_REFERENCE_RE = re.compile(
    r"\b(?:(?:this|that|the|attached|uploaded)\s+(?:file|document|spreadsheet|pdf)|"
    r"(?:image|photo|screenshot)\s+(?:above|attached|here))\b",
    re.IGNORECASE,
)


def contextualize_persona(plan: PersonaPlan, prompt: str, *,
                          conversation_context: Optional[list[dict[str, str]]] = None) -> PersonaPlan:
    """Add a bounded, local response plan from the current request without persisting preference inference."""
    raw = prompt if isinstance(prompt, str) else ""
    # Bound local inspection cost for very long prompts while retaining their beginning and end.
    text = raw if len(raw) <= 8_000 else raw[:3_999] + "\n" + raw[-4_000:]
    current = text.strip()
    context_available = any(
        isinstance(item, dict) and item.get("role") == "assistant" and bool(item.get("content"))
        for item in (conversation_context or [])
    )
    shorter = bool(_SHORTER_RE.search(current)) and context_available
    deeper = bool(_DEEPER_RE.search(current)) and context_available
    less_humor_request = bool(_LESS_HUMOR_RE.search(current))
    less_humor = less_humor_request and context_available
    explicit_correction = shorter or deeper or less_humor

    high_stakes = bool(_HIGH_STAKES_RE.search(text))
    current_facts = bool(_CURRENT_FACT_RE.search(text))
    external_sources = bool(_SOURCE_RE.search(text))
    coding = bool(_CODING_RE.search(text))
    analysis = bool(_ANALYSIS_RE.search(text))
    recipient_draft = bool(_RECIPIENT_DRAFT_RE.search(text))
    external_action = bool(_ACTION_RE.search(text)) and not recipient_draft
    explicit_humor = bool(_HUMOR_RE.search(text))
    humor_eligible = not (high_stakes or current_facts or external_sources or coding or analysis
                          or recipient_draft or external_action or explicit_correction or less_humor_request)
    references_context = bool(_CONVERSATION_REF_RE.search(text))
    references_personal_context = bool(_PERSONAL_CONTEXT_RE.search(text))
    workspace_reference = bool(_WORKSPACE_REFERENCE_RE.search(text))

    if high_stakes:
        intent: Intent = "high_stakes"
    elif external_action:
        intent = "external_action"
    elif current_facts:
        intent = "current_facts"
    elif coding:
        intent = "coding"
    elif recipient_draft:
        intent = "recipient_draft"
    elif explicit_correction:
        intent = "correction"
    elif analysis:
        intent = "analysis"
    elif explicit_humor and humor_eligible:
        intent = "banter"
    else:
        intent = "general"

    audience: Audience = "recipient" if recipient_draft else "operator"
    grounding: list[GroundingNeed] = []
    if references_context or references_personal_context or explicit_correction:
        grounding.append("conversation")
    if current_facts:
        grounding.append("current_facts")
    elif external_sources:
        grounding.append("external_sources")
    if coding or workspace_reference:
        grounding.append("workspace")
    if external_action:
        grounding.append("tool_execution")

    output_contract: OutputContract = "freeform"
    if recipient_draft:
        output_contract = "recipient_draft"
    elif re.search(r"\b(?:valid\s+)?json\b", text, re.IGNORECASE):
        output_contract = "json"
    elif re.search(r"\b(?:write|return|provide|show|generate)\s+(?:(?:a|an|the)\s+)?"
                   r"(?:python|javascript|typescript|rust|go|sql)?\s*(?:code|script|function|class)\b|```",
                   text, re.IGNORECASE):
        output_contract = "code"
    elif re.search(r"\b(?:cite sources|with citations|include citations|source citations)\b", text, re.IGNORECASE):
        output_contract = "citations"

    if shorter:
        resolved_depth: ResolvedDepth = "brief"
    elif deeper:
        resolved_depth = "detailed"
    elif plan.depth == "brief":
        resolved_depth = "brief"
    elif plan.depth in {"detailed", "thorough"}:
        resolved_depth = "detailed"
    elif plan.depth == "standard":
        resolved_depth = "standard"
    elif intent in {"analysis", "current_facts", "high_stakes", "coding", "external_action"}:
        resolved_depth = "detailed"
    elif intent == "banter":
        resolved_depth = "brief"
    else:
        resolved_depth = "standard"

    reasons: list[DiagnosticReason] = []
    if high_stakes:
        reasons.append("high_stakes_cue")
    if external_action:
        reasons.append("external_action")
    if current_facts:
        reasons.append("current_information")
    if external_sources:
        reasons.append("external_sources")
    if coding or workspace_reference:
        reasons.append("code_or_workspace_work")
    if recipient_draft:
        reasons.append("recipient_draft")
    if explicit_correction:
        reasons.append("answer_correction")
    if output_contract != "freeform":
        reasons.append("structured_output")
    if explicit_humor:
        reasons.append("clear_humor_request")
    if analysis:
        reasons.append("analytical_work")

    sources = dict(plan.sources)
    if shorter or deeper:
        sources["resolved_depth"] = "current_turn"
    elif plan.depth == "auto":
        sources["resolved_depth"] = "context"
    else:
        sources["resolved_depth"] = sources.get("depth", "application")
    if less_humor_request or high_stakes or current_facts or coding or external_action or recipient_draft:
        sources["humor_eligible"] = "current_turn"
    else:
        sources["humor_eligible"] = "context"
    return plan.model_copy(update={
        "intent": intent,
        "resolved_depth": resolved_depth,
        "audience": audience,
        "grounding_needs": grounding,
        "humor_eligible": humor_eligible,
        "output_contract": output_contract,
        "diagnostic_reasons": reasons[:4],
        "sources": sources,
    })


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
    "off": "Do not add unrequested jokes or playful asides. A direct request for safe, low-stakes humor is part of the task and may be followed.",
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
    if not plan.humor_eligible:
        humor_guidance = "- Humor: keep this turn plain; the current request is not unmistakably playful and low-stakes.\n"
    else:
        humor_guidance = f"- Humor: {_HUMOR_GUIDANCE[humor]}\n"
    grounding_guidance = ""
    if "current_facts" in plan.grounding_needs:
        grounding_guidance += "- Grounding: current information is requested; use available current sources or say what you could not verify.\n"
    if "external_sources" in plan.grounding_needs:
        grounding_guidance += "- Grounding: use available sources for requested research or citations; say when sourcing is unavailable.\n"
    if "workspace" in plan.grounding_needs:
        grounding_guidance += "- Grounding: code or workspace work may require inspecting the actual workspace; do not claim unperformed changes.\n"
    if "conversation" in plan.grounding_needs:
        grounding_guidance += "- Grounding: preserve the referenced conversation facts and apply the current correction to the referenced answer only.\n"
    if "tool_execution" in plan.grounding_needs:
        grounding_guidance += "- Grounding: external actions require the available governed tools and their normal approvals; never imply they happened without a result.\n"
    audience_guidance = ("- Audience: prepare wording for the intended recipient as a draft; do not send it unless the operator explicitly asks and normal governance permits.\n"
                         if plan.audience == "recipient" else "")
    contract_guidance = (f"- Output contract: preserve the requested {plan.output_contract} form; this does not change permissions or evidence requirements.\n"
                         if plan.output_contract != "freeform" else "")
    return ("Response style chosen for this run. It shapes wording only and never overrides safety, permissions, tool "
            "rules, the task, the operator's explicit request, or detail needed to act correctly (errors, warnings, "
            "denials, approval facts):\n"
            f"- Depth: {_DEPTH_GUIDANCE[plan.resolved_depth]}\n"
            f"{preset}"
            f"- Voice: {_TONE_GUIDANCE[plan.tone]}\n"
            f"{humor_guidance}"
            f"{grounding_guidance}"
            f"{audience_guidance}"
            f"{contract_guidance}"
            f"- Warmth: {plan.warmth}/100; directness: {plan.directness}/100; formality: {plan.formality}/100.\n"
            f"- Profanity: {'mirror it only if the operator used it first and the context is suitable.' if plan.profanity == 'mirror' else 'avoid it.'}\n"
            f"- Format: {_FORMAT_GUIDANCE[plan.format_style]}\n"
            + habits
            + "- Sensitive topics: set the style aside; be plain and steady, give the safe and useful part, state limits "
            "without moralizing, and never make light of a serious situation. Never make the operator the target of a joke.\n"
            "Do not mention these settings; respond in them.")


__all__ = ["APPLICATION_DEFAULT", "AvoidHabit", "Depth", "FormatStyle", "Humor", "LAYER_LABELS", "LAYERS",
           "PERSONA_FIELDS", "PERSONA_PROFILE_VERSION", "PERSONA_V1_FIELDS", "PERSONA_VERSION", "Preset", "Profanity",
           "Tone", "PersonaPlan", "PersonaStyle", "apply_persona_changes", "contextualize_persona", "decode_persona_state",
           "encode_persona_state", "guidance", "resolve_persona"]
