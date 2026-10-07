"""Claude via the official Anthropic SDK (LM-15: hosted access is by API key).

The SDK is imported lazily - ``import anthropic`` costs ~1.1 s, and a local-only install should never pay it
(PF-6). It lives in the ``hutch[anthropic]`` extra.

Decisions, each from the Claude API guidance:
* streaming + ``get_final_message()`` (no request timeouts on long outputs); SDK retries are OFF
  (``max_retries=0``) because Hutch owns retries and the fallback chain (SR-8), so a 429 is not retried twice
  underneath us and then again above.
* top-level ``cache_control`` so the stable prefix (tools -> system -> early messages) is cached; the system
  prompt and tool list are byte-identical across a run, which is what makes it hit (PF-1). Cache reads and
  writes are reported separately so the dashboard shows the real cached-token share.
* thinking is left at the model default (adaptive / always on for current models); Hutch never sends
  ``budget_tokens`` (removed on current models) and never disables thinking.
* ``stop_reason == "refusal"`` is a normal HTTP 200: it is turned into a typed ``refused`` error carrying the
  category, so the chain can fall back (SR-8). Anthropic's own beta server-side ``fallbacks`` parameter is NOT
  enabled by default: it could not be validated without a live key, and a wrong default would break every call.
* credentials: an explicit API key only. Hutch never reads or proxies OAuth profile tokens.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from .base import ChatRequest, ChatResult, Health, ModelMeta, Provider, ProviderError, ToolCall, abort_response

#: models that accept an ``effort`` level (others error if it is sent)
EFFORT_PREFIXES = ("claude-opus-5", "claude-sonnet-5", "claude-fable", "claude-mythos", "claude-opus-4-8",
                   "claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-4-6")


def _sdk():
    try:
        import anthropic
    except ImportError as exc:
        raise ProviderError("other", "the Anthropic SDK is not installed: pip install 'hutch[anthropic]'",
                            provider="anthropic") from exc
    return anthropic


def to_claude_messages(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Internal (OpenAI-shaped) messages -> (system text, Anthropic messages).

    Consecutive tool results are merged into ONE user message: splitting them across messages teaches the model
    to stop making parallel calls.
    """
    import json
    system_parts: list[str] = []
    out: list[dict[str, Any]] = []
    for m in messages:
        role = m["role"]
        if role == "system":
            system_parts.append(m.get("content") or "")
        elif role == "user":
            out.append({"role": "user", "content": m.get("content") or ""})
        elif role == "assistant":
            blocks: list[dict[str, Any]] = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for tc in m.get("tool_calls") or []:
                raw = tc["function"].get("arguments")
                try:
                    args = json.loads(raw) if isinstance(raw, str) and raw else (raw or {})
                except json.JSONDecodeError:
                    args = {}
                blocks.append({"type": "tool_use", "id": tc["id"], "name": tc["function"]["name"], "input": args})
            out.append({"role": "assistant", "content": blocks or [{"type": "text", "text": ""}]})
        elif role == "tool":
            block = {"type": "tool_result", "tool_use_id": m.get("tool_call_id", ""),
                     "content": m.get("content") or "(empty)"}
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list) \
                    and out[-1]["content"] and out[-1]["content"][0].get("type") == "tool_result":
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
    return "\n\n".join(p for p in system_parts if p), out


def to_claude_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"name": t["function"]["name"], "description": t["function"].get("description", ""),
             "input_schema": t["function"].get("parameters") or {"type": "object", "properties": {}}}
            for t in tools]


class ClaudeProvider(Provider):
    name = "anthropic"

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY", "")
        self.base_url = base_url or os.environ.get("ANTHROPIC_BASE_URL") or None
        self._client = None

    def _c(self):
        if not self.api_key:
            raise ProviderError("auth", "no Anthropic API key: set ANTHROPIC_API_KEY (Hutch uses API keys only and "
                                        "never reads login tokens)", provider=self.name)
        if self._client is None:
            sdk = _sdk()
            kw: dict[str, Any] = {"api_key": self.api_key, "max_retries": 0}
            if self.base_url:
                kw["base_url"] = self.base_url
            self._client = sdk.Anthropic(**kw)
        return self._client

    def health(self) -> Health:
        if not self.api_key:
            return Health(ok=False, detail="no ANTHROPIC_API_KEY set")
        try:
            _sdk()
        except ProviderError as exc:
            return Health(ok=False, detail=str(exc))
        return Health(ok=True, detail="API key present (not verified: Hutch does not spend tokens to check)")

    def list_models(self) -> list[ModelMeta]:
        return []

    # --------------------------------------------------------------- errors

    def _map(self, exc: Exception) -> ProviderError:
        sdk = _sdk()
        if isinstance(exc, ProviderError):
            return exc
        if isinstance(exc, sdk.AuthenticationError):
            return ProviderError("auth", "Anthropic rejected the API key", provider=self.name, status=401)
        if isinstance(exc, sdk.PermissionDeniedError):
            return ProviderError("auth", f"the API key lacks permission: {exc}", provider=self.name, status=403)
        if isinstance(exc, sdk.RateLimitError):
            ra = None
            try:
                ra = float(exc.response.headers.get("retry-after", ""))
            except (ValueError, AttributeError):
                pass
            return ProviderError("rate_limit", f"Anthropic rate limit: {exc.message}", provider=self.name,
                                 status=429, retry_after=ra)
        if isinstance(exc, sdk.NotFoundError):
            return ProviderError("model_missing", f"unknown model or endpoint: {exc.message}", provider=self.name,
                                 status=404)
        if isinstance(exc, sdk.BadRequestError):
            low = str(exc.message).lower()
            kind = "context" if ("too long" in low or "context" in low and "exceed" in low) else "bad_request"
            return ProviderError(kind, exc.message, provider=self.name, status=400)
        if isinstance(exc, sdk.APITimeoutError):
            return ProviderError("timeout", "Anthropic did not respond in time", provider=self.name)
        if isinstance(exc, sdk.APIConnectionError):
            return ProviderError("unreachable", f"cannot reach Anthropic: {exc}", provider=self.name)
        if isinstance(exc, sdk.APIStatusError):
            return ProviderError("server" if exc.status_code >= 500 else "bad_request",
                                 f"Anthropic returned HTTP {exc.status_code}: {exc.message}",
                                 provider=self.name, status=exc.status_code)
        return ProviderError("other", f"{type(exc).__name__}: {exc}", provider=self.name)

    # ----------------------------------------------------------------- chat

    def _complete(self, req: ChatRequest, stream: bool) -> ChatResult:
        client = self._c()
        sdk = _sdk()
        system, messages = to_claude_messages(req.messages)
        kwargs: dict[str, Any] = {
            "model": req.model, "max_tokens": int(req.max_tokens or 16000), "messages": messages,
            "cache_control": {"type": "ephemeral"},     # PF-1: cache the stable prefix automatically
            "timeout": sdk.Timeout(max(req.first_token_timeout, 60.0), connect=10.0),
        }
        if system:
            kwargs["system"] = system
        if req.tools:
            kwargs["tools"] = to_claude_tools(req.tools)
        if req.effort and req.model.startswith(EFFORT_PREFIXES):
            kwargs["output_config"] = {"effort": req.effort}
        try:
            if stream:
                with client.messages.stream(**kwargs) as s:
                    unregister = req.register_cancel(lambda: abort_response(s.response))
                    try:
                        msg = s.get_final_message()
                    finally:
                        unregister()
            else:
                msg = client.messages.create(**kwargs)
        except Exception as exc:
            raise self._map(exc)
        return self._fold(msg, req, stream)

    def _fold(self, msg: Any, req: ChatRequest, streamed: bool) -> ChatResult:
        text, thinking, calls = [], [], []
        for b in msg.content:
            if b.type == "text":
                text.append(b.text)
            elif b.type == "thinking":
                thinking.append(getattr(b, "thinking", "") or "")
            elif b.type == "tool_use":
                calls.append(ToolCall(id=b.id, name=b.name, arguments=dict(b.input or {})))
        u = msg.usage
        cache_read = int(getattr(u, "cache_read_input_tokens", 0) or 0)
        cache_write = int(getattr(u, "cache_creation_input_tokens", 0) or 0)
        uncached = int(getattr(u, "input_tokens", 0) or 0)
        reason = {"end_turn": "stop", "stop_sequence": "stop", "tool_use": "tool_calls", "max_tokens": "length",
                  "refusal": "refusal", "pause_turn": "stop"}.get(msg.stop_reason or "end_turn", "stop")
        if msg.stop_reason == "refusal":
            details = getattr(msg, "stop_details", None)
            cat = getattr(details, "category", None) if details else None
            err = ProviderError("refused", f"{msg.model} declined the request (category: {cat or 'unspecified'})",
                                provider=self.name)
            err.category = cat  # type: ignore[attr-defined]
            raise err
        return ChatResult(content="".join(text), thinking="".join(thinking), tool_calls=calls,
                          prompt_tokens=uncached + cache_read + cache_write,
                          completion_tokens=int(getattr(u, "output_tokens", 0) or 0), cached_tokens=cache_read,
                          cache_write_tokens=cache_write, finish_reason=reason, model=msg.model,
                          streamed=streamed, context_window=0)
