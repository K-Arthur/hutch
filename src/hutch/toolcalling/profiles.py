"""Capability resolution: exact route + model evidence, never model-family guessing.

The assignment sections 5 and 7 are explicit: a friendly model name or a reachable
HTTP endpoint is not evidence that a checkpoint's template/parser emits native tool
calls; a server accepting a parameter is not evidence that it enforced the parameter.
So this module resolves a :class:`ModelCapabilityProfile` from the exact provider,
endpoint class, protocol adapter, model id, and - where the runtime reports one -
build revision (Ollama digest / chat-template hash). Model family only contributes
notes, never the mode decision.

Evidence states:

* ``documented``  - the vendored/upstream documentation states the behavior
* ``advertised``  - the vendor or model card claims it; not verified here
* ``probed``      - a bounded, harmless probe observed it (requires explicit opt-in)
* ``observed``    - a real governed run observed it (store observations; per route revision)
* ``stale``       - was observed, but the route/model/config changed since
* ``unsupported`` - documented as absent
* ``unknown``     - nothing recorded; Hutch attempts the protocol's safe default

Operator override precedence: an explicit per-Bot choice (``native`` / ``constrained``
/ ``prompt`` / ``disabled``) is validated against the profile and recorded; it can
select a mode but cannot turn an unsupported mode into a supported one silently.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional
from urllib.parse import urlsplit

from .contracts import canonical_json

_EVIDENCE_STATES = ("documented", "advertised", "probed", "observed", "stale", "unsupported", "unknown")

#: Dated evidence markers used by the known profiles below; kept short on purpose.
_CHECKED = "2026-10-10"


@dataclass(frozen=True)
class Evidence:
    state: str = "unknown"
    detail: str = ""
    source: str = ""
    observed_on: str = ""

    def __post_init__(self) -> None:
        if self.state not in _EVIDENCE_STATES:
            raise ValueError(f"unknown evidence state {self.state!r}")

    @property
    def supports(self) -> bool:
        return self.state in ("documented", "probed", "observed")


@dataclass(frozen=True)
class ModelCapabilityProfile:
    key: str
    provider: str
    protocol: str
    endpoint_class: str                    # local | official | custom | unknown
    model: str
    revision: str = ""                     # digest/template hash when the runtime reports one
    native_tools: Evidence = Evidence()
    tool_choice: Evidence = Evidence()
    parallel_calls: Evidence = Evidence()
    streaming_calls: Evidence = Evidence()
    constrained_schema: Evidence = Evidence()
    constrained_attachment: str = ""       # "" | response_format | format_field
    strict_tool_schema: Evidence = Evidence()
    multimodal: Evidence = Evidence()
    notes: tuple[str, ...] = ()
    source: str = "fallback-defaults"      # known-profile | operator-override | observation | fallback-defaults
    observations: tuple[dict[str, Any], ...] = ()
    backend: str = ""
    backend_version: str = ""
    checkpoint_digest: str = ""
    quantization: str = ""
    template_hash: str = ""
    tokenizer_hash: str = ""
    parser_id: str = ""
    effective_context: Optional[int] = None
    decoding: dict[str, Any] = field(default_factory=dict)
    modalities: tuple[str, ...] = ()
    modalities_known: bool = False

    def fingerprint(self) -> str:
        return hashlib.sha256(canonical_json({
            "key": self.key, "provider": self.provider, "protocol": self.protocol,
            "endpoint_class": self.endpoint_class, "model": self.model, "revision": self.revision,
            "native": self.native_tools.state, "constrained": self.constrained_schema.state,
            "attachment": self.constrained_attachment, "source": self.source,
            "execution": self.execution_view()["fingerprint"],
        }).encode()).hexdigest()[:16]

    def capabilities_view(self) -> dict[str, Any]:
        """Compact, redacted view for diagnostics and the settings UI."""
        def ev(item: Evidence) -> dict[str, str]:
            return {"state": item.state, "detail": item.detail, "source": item.source,
                    "observed_on": item.observed_on}
        return {
            "profile": self.key,
            "provider": self.provider,
            "protocol": self.protocol,
            "endpoint_class": self.endpoint_class,
            "model": self.model,
            "revision": self.revision,
            "source": self.source,
            "native_tools": ev(self.native_tools),
            "tool_choice": ev(self.tool_choice),
            "parallel_calls": ev(self.parallel_calls),
            "streaming_calls": ev(self.streaming_calls),
            "constrained_schema": ev(self.constrained_schema),
            "constrained_attachment": self.constrained_attachment,
            "strict_tool_schema": ev(self.strict_tool_schema),
            "multimodal": ev(self.multimodal),
            "execution_profile": self.execution_view(),
            "notes": list(self.notes),
        }

    def execution_view(self) -> dict[str, Any]:
        """Credential-free identity of the model build and settings used for execution."""
        values = {
            "backend": self.backend or self.provider,
            "backend_version": self.backend_version,
            "checkpoint_digest": self.checkpoint_digest,
            "quantization": self.quantization,
            "template_hash": self.template_hash,
            "tokenizer_hash": self.tokenizer_hash,
            "protocol": self.protocol,
            "parser_id": self.parser_id,
            "effective_context": self.effective_context,
            "decoding": dict(self.decoding),
            "modalities": list(self.modalities),
            "modalities_known": self.modalities_known,
        }
        missing = [key for key in ("backend", "backend_version", "checkpoint_digest", "quantization",
                                   "template_hash", "tokenizer_hash", "protocol", "parser_id",
                                   "effective_context", "decoding") if values[key] in (None, "", {})]
        if not values["modalities_known"] or not values["modalities"]:
            missing.append("modalities")
        values["complete"] = not missing
        values["missing"] = missing
        values["fingerprint"] = hashlib.sha256(canonical_json(values).encode()).hexdigest()
        return values


# ------------------------------------------------------------------ route mapping

def protocol_for_provider(provider: str) -> str:
    provider = (provider or "").strip().lower()
    if provider == "anthropic":
        return "anthropic-messages"
    if provider == "ollama":
        return "ollama-native"
    if provider == "chatgpt":
        return "openai-responses"
    return "openai-chat"


def classify_endpoint(endpoint: Optional[str]) -> str:
    """local | official | custom | unknown - by exact authority, not a lookalike name."""
    if not endpoint:
        return "unknown"
    try:
        parts = urlsplit(endpoint.strip())
    except ValueError:
        return "unknown"
    host = (parts.hostname or "").lower()
    if not host:
        return "unknown"
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return "local"
    if host in ("api.openai.com", "api.anthropic.com"):
        return "official"
    return "custom"


def _p(state: str, detail: str, source: str = "") -> Evidence:
    return Evidence(state=state, detail=detail, source=source, observed_on=_CHECKED)


#: Versioned known profiles. Keys are ``provider/endpoint_class`` (or just provider
#: when the endpoint class does not change the answer). Everything here is
#: documentation-derived unless the state says probed/observed.
_KNOWN: dict[tuple[str, str], dict[str, Any]] = {
    ("anthropic", "*"): dict(
        native_tools=_p("documented", "Messages API tool_use blocks with input_schema", "Anthropic tool use docs"),
        tool_choice=_p("documented", "auto/any/none/tool via tool_choice", "Anthropic tool use docs"),
        parallel_calls=_p("documented", "multiple tool_use blocks per message", "Anthropic tool use docs"),
        streaming_calls=_p("documented", "standard buffered streaming; fine-grained is opt-in per tool",
                           "Anthropic fine-grained tool streaming docs"),
        constrained_schema=_p("unsupported", "Hutch's Anthropic adapter does not send structured-output controls",
                              "hutch adapter review"),
        strict_tool_schema=_p("unsupported", "tool input schemas are validated server-side but not grammar-enforced",
                              "Anthropic docs"),
        multimodal=_p("documented", "images accompany chat messages on Claude models; checked at send time",
                      "Anthropic vision docs"),
        notes=("Idle-turn and refusal stop reasons are typed and mapped to provider errors.",),
    ),
    ("openai", "official"): dict(
        native_tools=_p("documented", "Chat Completions function tools; best-effort by default", "OpenAI function calling guide"),
        tool_choice=_p("documented", "auto/none/required/named", "OpenAI function calling guide"),
        parallel_calls=_p("documented", "parallel_tool_calls supported; may return several calls", "OpenAI function calling guide"),
        streaming_calls=_p("documented", "streamed tool_calls deltas assembled by index", "OpenAI function calling guide"),
        constrained_schema=_p("documented", "response_format json_schema available", "OpenAI structured outputs guide"),
        constrained_attachment="response_format",
        strict_tool_schema=_p("documented", "strict requires additionalProperties:false and all fields required; not sent by Hutch",
                              "OpenAI function calling guide"),
        multimodal=_p("documented", "image input passes through on the documented image-model table; "
                              "checked at send time", "OpenAI vision docs"),
        notes=("Hutch sends best-effort native tools; strict mode is reported, never silently imposed.",),
    ),
    ("openai", "*"): dict(  # named OpenAI-compatible connections are less certain
        native_tools=_p("advertised", "common Chat Completions tool framing; each server implements it differently",
                        "Hutch compatibility matrix"),
        tool_choice=_p("unknown", "endpoint-defined"),
        parallel_calls=_p("unknown", "endpoint-defined"),
        streaming_calls=_p("advertised", "fixture-tested framing; endpoint behavior varies", "tests/test_providers.py"),
        constrained_schema=_p("unknown", "only attempted with an explicit operator choice"),
        multimodal=_p("unknown", ""),
    ),
    ("ollama", "local"): dict(
        native_tools=_p("documented", "native /api/chat tools; requires a tool-capable template", "Ollama tool calling docs"),
        tool_choice=_p("unsupported", "Ollama's native API does not take tool_choice", "Ollama tool calling docs"),
        parallel_calls=_p("documented", "multiple tool_calls per reply are supported", "Ollama tool calling docs"),
        streaming_calls=_p("documented", "per-chunk tool_calls are accumulated by the client", "Ollama tool calling docs"),
        constrained_schema=_p("documented", "format accepts a JSON Schema; the schema is also worth grounding in the prompt",
                              "Ollama structured outputs docs"),
        constrained_attachment="format_field",
        strict_tool_schema=_p("unsupported", "the chat template/parser owns extraction; no strict flag", "Ollama tool calling docs"),
        multimodal=_p("documented", "images accompany chat messages on models that report the vision "
                              "capability; checked at send time", "Ollama vision docs"),
        notes=("Ollama Cloud models do not support structured outputs; constrained mode is unavailable for cloud-tagged names.",),
    ),
    ("ollama", "*"): dict(
        native_tools=_p("unknown", "recognized cloud-tagged names are treated as hosted"),
        tool_choice=_p("unsupported", ""),
        parallel_calls=_p("unknown", ""),
        streaming_calls=_p("unknown", ""),
        constrained_schema=_p("unsupported", "Ollama Cloud does not support structured outputs", "Ollama structured outputs docs"),
        multimodal=_p("unknown", ""),
    ),
    ("llamacpp", "*"): dict(
        native_tools=_p("documented", "server-side function calling requires --jinja; generic handler covers unrecognized templates",
                        "llama.cpp function calling docs"),
        tool_choice=_p("unknown", "depends on the template and server version"),
        parallel_calls=_p("documented", "parallel_tool_calls must be requested explicitly", "llama.cpp function calling docs"),
        streaming_calls=_p("unknown", "server emits assembled tool_calls; ids may be omitted"),
        constrained_schema=_p("documented", "response_format json_schema converts to GBNF; unsupported keywords are skipped silently",
                              "llama.cpp GBNF guide"),
        constrained_attachment="response_format",
        strict_tool_schema=_p("unsupported", "no per-tool strict flag; schema-to-GBNF conversion has documented gaps",
                              "llama.cpp GBNF guide"),
        multimodal=_p("unknown", ""),
        notes=("GBNF conversion defaults additionalProperties to false and skips unsupported keywords; the compiler "
               "re-encodes that explicitly and reports every gap.",),
    ),
    ("llama.cpp", "*"): None,  # alias filled below
    ("vllm", "*"): dict(
        native_tools=_p("documented", "server tool calling requires --enable-auto-tool-choice plus a parser; named/required use structured outputs",
                        "vLLM tool calling docs"),
        tool_choice=_p("documented", "auto/none/required/named; required and named enforce schemas via structured outputs",
                       "vLLM tool calling docs"),
        parallel_calls=_p("documented", "parser-dependent; Mistral 7B is documented as weak at parallel calls", "vLLM tool calling docs"),
        streaming_calls=_p("documented", "streamed deltas; a 2026 call-id bug for Mistral required calls was fixed in PR #48947",
                           "vLLM issue #47734"),
        constrained_schema=_p("documented", "response_format json_schema; guided_* fields were removed in v0.12", "vLLM structured outputs docs"),
        constrained_attachment="response_format",
        strict_tool_schema=_p("documented", "per-tool strict / --tool-strict-level; not sent by Hutch", "vLLM tool calling docs"),
        multimodal=_p("unsupported", "image input is refused: a custom OpenAI-compatible endpoint is "
                              "not assumed to accept images"),
        notes=("Hutch does not enable vLLM strict tool mode: it would change the wire contract. Reported, not imposed.",),
    ),
    ("lmstudio", "*"): dict(
        native_tools=_p("advertised", "OpenAI-compatible tool use documented by LM Studio", "LM Studio tool use docs"),
        tool_choice=_p("unknown", ""),
        parallel_calls=_p("unknown", ""),
        streaming_calls=_p("advertised", ""),
        constrained_schema=_p("unknown", "not documented for the chat endpoint; explicit opt-in only"),
        multimodal=_p("unknown", ""),
    ),
    ("chatgpt", "*"): dict(
        native_tools=_p("documented", "preview additional_tools function items only", "Sign in with ChatGPT preview limitations"),
        tool_choice=_p("unsupported", "preview does not expose tool_choice"),
        parallel_calls=_p("unknown", ""),
        streaming_calls=_p("documented", "Responses event stream; completed item carries the full call",
                           "Sign in with ChatGPT preview docs"),
        constrained_schema=_p("unsupported", "structured outputs are not part of the preview surface", ""),
        multimodal=_p("unsupported", "not available through Hutch"),
        notes=("Store=false and the preview field omissions are enforced by the adapter.",),
    ),
    ("openai-compatible", "*"): dict(
        native_tools=_p("advertised", "common framing; each endpoint must be verified for its own model",
                        "Hutch compatibility matrix"),
        tool_choice=_p("unknown", ""),
        parallel_calls=_p("unknown", ""),
        streaming_calls=_p("advertised", "fixture-tested framing", "tests/test_providers.py"),
        constrained_schema=_p("unknown", "explicit operator opt-in only"),
        multimodal=_p("unknown", ""),
    ),
}

_KNOWN[("llama.cpp", "*")] = _KNOWN[("llamacpp", "*")]

_PROTOCOL_DEFAULT_CONSTRAINED = {
    "openai-chat": ("unknown", "response_format"),
    "anthropic-messages": ("unsupported", ""),
    "ollama-native": ("unknown", "format_field"),
    "openai-responses": ("unsupported", ""),
    "prompt-text": ("unsupported", ""),
}


def _lookup(provider: str, endpoint_class: str) -> Optional[dict[str, Any]]:
    for key in ((provider, endpoint_class), (provider, "*")):
        entry = _KNOWN.get(key)
        if entry is not None:
            return entry
    return None


def resolve_profile(*, provider: str, endpoint: str = "", model: str = "", revision: str = "",
                    observations: Iterable[Mapping[str, Any]] = (),
                    override: Optional[str] = None, metadata: Any = None,
                    backend_version: str = "", effective_context: Optional[int] = None,
                    decoding: Optional[Mapping[str, Any]] = None) -> ModelCapabilityProfile:
    """Resolve the profile for one exact route + model.

    ``observations`` are prior governed-run capability records (the store's passive
    observations); they upgrade ``native_tools`` to ``observed`` only when they match
    this exact provider/model/route revision. Nothing here makes a network request.
    """
    provider = (provider or "unknown").strip().lower()
    endpoint_class = classify_endpoint(endpoint)
    if provider == "ollama":
        if re.search(r"(?:^|[:_-])cloud(?:$|[-_.])", model, re.IGNORECASE):
            endpoint_class = "cloud"
        elif endpoint_class in ("unknown", "custom"):
            # The native adapter defaults to localhost; a remote Ollama server is the same
            # product surface. The cloud distinction is the model tag, not the host.
            endpoint_class = "local"
    protocol = protocol_for_provider(provider)
    entry = _lookup(provider, endpoint_class)
    defaults = _PROTOCOL_DEFAULT_CONSTRAINED.get(protocol, ("unknown", ""))

    def value(name: str, fallback: Evidence) -> Evidence:
        if entry and isinstance(entry.get(name), Evidence):
            return entry[name]
        return fallback

    revision = revision or ""
    matched_observations: list[dict[str, Any]] = []
    for row in observations:
        try:
            if str(row.get("provider", "")) != provider or str(row.get("model", "")) != model:
                continue
            if revision and row.get("route_revision") and str(row["route_revision"]) != revision:
                continue
            matched_observations.append(dict(row))
        except Exception:
            continue
        if len(matched_observations) >= 20:
            break

    native = value("native_tools", Evidence(state="unknown", detail="no known profile for this route"))
    if matched_observations and native.state not in ("documented", "probed"):
        native = Evidence(state="observed",
                          detail=f"{len(matched_observations)} governed run(s) on this route produced a declaration-valid call",
                          source="hutch capability observations", observed_on=str(matched_observations[-1].get("observed_at", "")))

    constrained_evidence = value("constrained_schema", Evidence(state=defaults[0], detail=""))
    constrained_state = constrained_evidence.state
    attachment = str((entry or {}).get("constrained_attachment", "")) or defaults[1]
    if constrained_state not in ("documented", "probed", "observed"):
        attachment = ""

    key = f"{provider}/{endpoint_class}"
    parser_id = {"ollama-native": "hutch.ollama-tool-args.strictjson-v1",
                 "openai-chat": "hutch.openai-tool-args.strictjson-v1",
                 "openai-responses": "hutch.responses-tool-args.strictjson-v1",
                 "anthropic-messages": "hutch.anthropic-tool-args.strictjson-v1"}.get(
                     protocol, f"hutch.{protocol}.strictjson-v1")
    raw_modalities = getattr(metadata, "capabilities", None) if metadata is not None else None
    modality_aliases = {"completion": "text", "vision": "image", "audio": "audio",
                        "video": "video", "embedding": "embedding", "text": "text", "image": "image"}
    modalities = tuple(sorted({modality_aliases[str(item).lower()] for item in (raw_modalities or [])
                               if str(item).lower() in modality_aliases}))
    profile = ModelCapabilityProfile(
        key=key, provider=provider, protocol=protocol, endpoint_class=endpoint_class, model=model, revision=revision,
        native_tools=native,
        tool_choice=value("tool_choice", Evidence()),
        parallel_calls=value("parallel_calls", Evidence()),
        streaming_calls=value("streaming_calls", Evidence()),
        constrained_schema=constrained_evidence,
        constrained_attachment=attachment,
        strict_tool_schema=value("strict_tool_schema", Evidence()),
        multimodal=value("multimodal", Evidence()),
        notes=tuple((entry or {}).get("notes", ())),
        source="known-profile" if entry else "fallback-defaults",
        observations=tuple(matched_observations),
        backend=str(getattr(metadata, "backend", "") or provider),
        backend_version=str(getattr(metadata, "backend_version", "") or backend_version or ""),
        checkpoint_digest=str(getattr(metadata, "digest", "") or ""),
        quantization=str(getattr(metadata, "quant", "") or ""),
        template_hash=str(getattr(metadata, "template_hash", "") or ""),
        tokenizer_hash=str(getattr(metadata, "tokenizer_hash", "") or ""),
        parser_id=parser_id,
        effective_context=int(effective_context) if effective_context else None,
        decoding=dict(decoding or {}),
        modalities=modalities,
        modalities_known=raw_modalities is not None,
    )
    if override:
        if override not in ("auto", "native", "constrained", "prompt", "disabled"):
            raise ValueError(f"unknown tool protocol choice {override!r}")
        profile = ModelCapabilityProfile(**{**profile.__dict__, "source": "operator-override"})
    return profile


def strategy_eligibility(profile: ModelCapabilityProfile) -> dict[str, tuple[bool, str]]:
    """Which strategies are available for this profile, with the honest reason.

    ``native`` stays the default attempt for every protocol Hutch actually speaks
    (that is today's behavior; changing it silently would be a regression). An
    unavailable strategy explains the prerequisite instead of saving a no-op.
    """
    constrained_ok = profile.constrained_schema.supports and bool(profile.constrained_attachment)
    constrained_why = "the backend exposes a documented schema-constrained generation control" if constrained_ok else \
        (profile.constrained_schema.detail or "no verified schema-constrained generation control on this route")
    return {
        "native": (True, "Hutch sends the provider's own tool protocol"
                          + (f" ({profile.native_tools.state})" if profile.native_tools.state != "documented" else "")),
        "constrained": (constrained_ok, constrained_why),
        "prompt": (True, "best-effort: a versioned prompt contract with strict local parsing and validation; "
                         "requires the per-Bot opt-in"),
        "disabled": (True, "tools are not offered to the model this run"),
    }
