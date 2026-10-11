"""Provider contract: one normalized request/result shape for every model backend.

Why a layer at all (research, docs/research/offerings-and-failures.md):

* **LM-1** - Ollama's OpenAI-compatible endpoint cannot set the context size, so prompts are silently
  truncated from the front. A provider for a *specific* runtime can set it explicitly every call.
* **SR-9** - a streaming request that fails mid-flight is retried once without streaming.
* **SR-2** - every result carries exact token counts (prompt / completion / cached) for cost accounting.
* **SR-1** - provider failures are typed, so a dead runtime fails fast with a cause instead of hanging.

Internal messages are OpenAI-shaped (``role`` / ``content`` / ``tool_calls`` / ``tool_call_id``); each
provider converts to its wire format. Tool specs are the OpenAI function-tool shape from ``Tool.spec()``.
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# ------------------------------------------------------------------ errors

class ProviderError(Exception):
    """A model call failed. ``kind`` drives retry / fallback / the explanation shown to the user."""

    KINDS = ("unreachable", "timeout", "auth", "rate_limit", "server", "bad_request",
             "context", "refused", "stream", "model_missing", "oom", "other")

    def __init__(self, kind: str, message: str, *, provider: str = "", status: Optional[int] = None,
                 retry_after: Optional[float] = None):
        super().__init__(message)
        self.kind = kind if kind in self.KINDS else "other"
        self.provider = provider
        self.status = status
        self.retry_after = retry_after

    @property
    def retryable(self) -> bool:
        """Whether a later attempt may recover this availability failure."""
        return self.kind in ("unreachable", "timeout", "rate_limit", "server", "stream", "oom")

    @property
    def streaming_related(self) -> bool:
        """Whether this failure specifically implicates streaming and merits one plain retry."""
        if self.kind == "stream":
            return True
        if self.kind != "bad_request" or self.status not in (400, 422):
            return False
        # A generic validation error (for example, an unsupported token-limit field) is not a
        # stream failure. Repeating it without streaming just sends the same invalid request again.
        detail = str(self).casefold()
        return "stream" in detail or "server-sent event" in detail or "sse" in detail


# ------------------------------------------------------------------ request / result

@dataclass
class ChatRequest:
    model: str
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] = field(default_factory=list)
    num_ctx: Optional[int] = None          # context window to REQUEST; Ollama always gets it (LM-1)
    max_tokens: Optional[int] = None       # per-turn generation cap (SR-5)
    temperature: Optional[float] = None
    think: Optional[bool] = False          # SR-5: thinking off by default for small local models
    effort: Optional[str] = None           # hosted models that take an effort level
    keep_alive: str = "10m"                # local runtimes: how long the model stays resident
    first_token_timeout: float = 600.0     # CPU inference of a long prompt can take minutes to first token
    idle_timeout: float = 90.0             # max silence between chunks once streaming has started
    stream: bool = True
    allow_stream_retry: bool = True       # builtin accounting disables hidden attempts and reserves each retry itself
    # called with a close() function so Stop can abort the in-flight request; returns an unregister fn
    register_cancel: Callable[[Callable[[], None]], Callable[[], None]] = lambda fn: (lambda: None)
    #: True once the user pressed Stop. A cancelled call must never be "recovered" by the streaming retry
    is_cancelled: Callable[[], bool] = lambda: False
    session_id: str = ""                   # stable per conversation; standalone runs use their own id
    #: Backend-native schema constraint ({name, schema, attachment}) for the constrained
    #: strategy. Attachments: "response_format" (OpenAI-compatible) or "format_field"
    #: (Ollama native). None means no structured-output control is attached.
    structured_output: Optional[dict[str, Any]] = None
    #: Opt in to a redacted description of the serialized request. Used only by isolated persona previews.
    capture_adapter_receipt: bool = False
    adapter_receipt: Optional[dict[str, Any]] = field(default=None, init=False, repr=False)


def record_adapter_receipt(req: ChatRequest, adapter: str, serialized: dict[str, Any], *, stream: bool) -> None:
    """Capture only safe shape metadata from the exact adapter payload before it is sent.

    This opt-in deliberately omits request contents, headers, destinations and credentials. Do not widen the
    result with arbitrary payload fields; the receipt is made visible in the persona-preview inspector.
    """
    if not req.capture_adapter_receipt:
        return

    raw_messages = serialized.get("messages")
    if not isinstance(raw_messages, list):
        raw_messages = serialized.get("input")
    messages = raw_messages if isinstance(raw_messages, list) else []
    roles: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if isinstance(role, str) and role in {"system", "developer", "user", "assistant", "tool"}:
            roles.append(role)
        elif isinstance(message.get("type"), str) and message["type"] in {"function_call", "function_call_output"}:
            roles.append(message["type"])

    has_separate_system = bool(serialized.get("system") or serialized.get("instructions"))
    has_system = has_separate_system or any(role in {"system", "developer"} for role in roles)
    if has_separate_system and not any(role in {"system", "developer"} for role in roles):
        roles.insert(0, "system")
    message_count = len(messages) + int(has_separate_system and not any(
        isinstance(message, dict) and isinstance(message.get("role"), str)
        and message.get("role") in {"system", "developer"} for message in messages))

    tool_schemas = serialized.get("tools")
    tool_count = len(tool_schemas) if isinstance(tool_schemas, list) else 0
    for message in messages:
        if isinstance(message, dict) and message.get("type") == "additional_tools":
            nested = message.get("tools")
            if isinstance(nested, list):
                tool_count += len(nested)

    cap_field: str | None = None
    cap: int | None = None
    for key in ("max_output_tokens", "max_completion_tokens", "max_tokens"):
        candidate = serialized.get(key)
        if isinstance(candidate, int) and not isinstance(candidate, bool) and candidate > 0:
            cap, cap_field = candidate, key
            break
    if cap is None:
        options = serialized.get("options")
        candidate = options.get("num_predict") if isinstance(options, dict) else None
        if isinstance(candidate, int) and not isinstance(candidate, bool) and candidate > 0:
            cap, cap_field = candidate, "options.num_predict"

    model = serialized.get("model")
    if not isinstance(model, str) or not model or len(model) > 160 or any(ord(char) < 32 for char in model):
        model = "unknown"
    req.adapter_receipt = {
        "adapter": adapter,
        "model": model,
        "stream": bool(stream),
        "output_token_cap": cap,
        "output_cap_field": cap_field,
        "message_count": message_count,
        "message_roles": roles[:12],
        "system_instructions_present": has_system,
        "tool_schema_count": tool_count,
        "structured_output": "response_format" in serialized or "format" in serialized,
    }


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    raw: str = ""                          # the model's raw argument text, kept for repair (LM-13)
    parse_error: str = ""
    #: "json_object" (a decoded body), "empty" (no body was emitted at all), or "invalid".
    #: The loop decides whether an empty body is legal from the tool's own schema, so a
    #: required-argument tool can never execute on an invented `{}`.
    arguments_state: str = "json_object"
    #: The body was a JSON string containing JSON (a documented small-model failure); the
    #: decode is retained but flagged so the transcript shows the repair.
    double_decoded: bool = False


@dataclass
class ChatResult:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0                 # TOTAL prompt tokens, cached or not
    completion_tokens: int = 0
    cached_tokens: int = 0                 # prompt tokens served from the provider's cache (PF-1)
    cache_write_tokens: int = 0            # prompt tokens written to the cache (Anthropic)
    finish_reason: str = "stop"            # stop | tool_calls | length | refusal
    model: str = ""
    thinking: str = ""
    load_ms: float = 0.0                   # cold-load time reported by a local runtime (LM-6)
    total_ms: float = 0.0
    tokens_per_sec: Optional[float] = None
    streamed: bool = True
    prompt_truncated: bool = False         # the runtime evaluated fewer prompt tokens than we sent
    context_window: int = 0                # the window the model actually got, when known
    notes: list[str] = field(default_factory=list)
    refusal_category: Optional[str] = None


@dataclass
class ModelMeta:
    """What a runtime reports about an installed model (LM-5)."""
    name: str
    params_b: Optional[float] = None       # billions of parameters
    quant: str = ""
    family: str = ""
    max_context: Optional[int] = None      # the model's trained window
    size_bytes: Optional[int] = None       # weights on disk / in memory
    n_layers: Optional[int] = None
    n_kv_heads: Optional[int] = None
    head_dim: Optional[int] = None
    capabilities: list[str] = field(default_factory=list)
    template_hash: str = ""                # chat-template fingerprint (LM-11 profile key)
    license: str = ""
    digest: str = ""


@dataclass
class Health:
    ok: bool
    detail: str = ""
    version: str = ""
    loaded: list[dict[str, Any]] = field(default_factory=list)   # models currently resident
    latency_ms: float = 0.0


# ------------------------------------------------------------------ helpers

def parse_tool_args(raw: Any) -> tuple[dict[str, Any], str]:
    """Backwards-compatible wrapper over :func:`parse_tool_args_state` (dict, error)."""
    args, error, _state, _double = parse_tool_args_state(raw)
    return args, error


def parse_tool_args_state(raw: Any) -> tuple[dict[str, Any], str, str, bool]:
    """Models emit arguments as a dict (Ollama/Anthropic), a JSON string (OpenAI), or occasionally garbage.

    Returns ``(arguments, error, state, double_decoded)`` where state is
    ``"json_object"``, ``"empty"`` (nothing was emitted), or ``"invalid"``. JSON is decoded
    strictly (no duplicate keys, no NaN/Infinity, no trailing content) so a corrupted stream
    cannot be silently repaired into a different executable call; the raw text stays available
    for the one bounded repair retry (LM-13).
    """
    from ..toolcalling.strictjson import JSONProblem, loads_strict

    if isinstance(raw, dict):
        return raw, "", "json_object", False
    if raw is None or raw == "":
        return {}, "", "empty", False
    if isinstance(raw, str):
        try:
            val = loads_strict(raw)
        except JSONProblem as exc:
            return {}, str(exc), "invalid", False
        double = False
        if isinstance(val, str):  # double-encoded: a documented small-model failure, retained with a flag
            try:
                val = loads_strict(val)
                double = True
            except JSONProblem:
                return {}, "arguments were a JSON string that is not itself JSON", "invalid", False
        if isinstance(val, dict):
            return val, "", "json_object", double
        return {}, f"arguments must be a JSON object, got {type(val).__name__}", "invalid", False
    return {}, f"unsupported arguments type {type(raw).__name__}", "invalid", False


def abort_response(resp: Any) -> None:
    """Abort an in-flight HTTP response from ANOTHER thread.

    ``response.close()`` alone does not interrupt a read that is already blocked on the socket (found by a
    test: a Stop during a stalled model call waited out the whole timeout). Shutting the socket down does -
    the blocked ``recv`` returns and the reader raises, so Stop and the stall watchdog are prompt.
    """
    try:
        stream = resp.extensions.get("network_stream")
        sock = stream.get_extra_info("socket") if stream is not None else None
        if sock is not None:
            import socket as _socket
            sock.shutdown(_socket.SHUT_RDWR)
    except Exception:
        pass
    try:
        resp.close()
    except Exception:
        pass


class Watchdog:
    """Fires ``on_stall`` if ``arm`` is not re-called within the window. Used to abort a stalled stream."""

    def __init__(self, on_stall: Callable[[], None]):
        self._on_stall = on_stall
        self._timer: Optional[threading.Timer] = None
        self.stalled = False

    def arm(self, seconds: float) -> None:
        self.cancel()
        self._timer = threading.Timer(seconds, self._fire)
        self._timer.daemon = True
        self._timer.start()

    def _fire(self) -> None:
        self.stalled = True
        try:
            self._on_stall()
        except Exception:
            pass

    def cancel(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None


# ------------------------------------------------------------------ provider ABC

class Provider(ABC):
    name = "provider"

    @abstractmethod
    def _complete(self, req: ChatRequest, stream: bool) -> ChatResult:  # pragma: no cover
        """One attempt, streaming or not. Raise ProviderError with a precise ``kind``."""

    def chat(self, req: ChatRequest) -> ChatResult:
        """SR-9: try streaming; if the *stream* failed, retry exactly once without streaming."""
        t0 = time.perf_counter()
        if not req.stream:
            result = self._complete(req, stream=False)
            result.streamed = False
        else:
            try:
                result = self._complete(req, stream=True)
            except ProviderError as exc:
                if not exc.streaming_related or req.is_cancelled() or not req.allow_stream_retry:
                    raise
                result = self._complete(req, stream=False)
                result.streamed = False
                result.notes.append(f"streaming failed ({exc}); retried once without streaming")
        result.total_ms = result.total_ms or (time.perf_counter() - t0) * 1000.0
        return result

    def health(self) -> Health:  # pragma: no cover - overridden
        return Health(ok=True)

    def list_models(self) -> list[ModelMeta]:
        return []

    def show(self, model: str) -> Optional[ModelMeta]:
        return None
