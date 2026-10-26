"""OpenAI-compatible provider: OpenAI, LM Studio, llama.cpp server, vLLM, any ``/v1/chat/completions``.

Plain HTTP (no vendor SDK): the protocol is small, and avoiding the ``openai`` package removes a ~600 ms import
from every CLI start (PF-6) and a dependency from the install.

Limits worth knowing, and surfaced rather than hidden:
* the context window cannot be requested through this API. A server started with a small ``-c`` will reject or
  truncate long prompts; Hutch checks the *model's* reported window where it can, and warns (LM-3).
* if the URL turns out to be an Ollama server, the registry routes to the native provider instead, because
  Ollama's ``/v1`` silently truncates to its default window (see ollama.py).
"""

from __future__ import annotations

import json
import math
import re
import time
from typing import Any, Optional

from .base import (ChatRequest, ChatResult, Health, ModelMeta, Provider, ProviderError, ToolCall,
                   Watchdog, abort_response, parse_tool_args_state, record_adapter_receipt)
from .openrouter_policy import validate_policy

PRESET_URLS = {
    "openai": "https://api.openai.com/v1",
    "lmstudio": "http://localhost:1234/v1",
    "llamacpp": "http://localhost:8080/v1",
    "llama.cpp": "http://localhost:8080/v1",
    "vllm": "http://localhost:8000/v1",
}

_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,159}$")
_MAX_DISCOVERED_MODELS = 10000

# Official image-input model table, checked 2026-10-11. Unknown/custom endpoints remain semantic-only.
_VISION_MODELS = {"gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "gpt-5.1", "gpt-5.2",
                  "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano", "gpt-5.5", "gpt-5.6-sol", "gpt-5.6-terra",
                  "gpt-5.6-luna", "gpt-6-astra", "o4-mini"}


def _httpx():
    import httpx
    return httpx


class OpenAICompatProvider(Provider):
    name = "openai-compatible"
    #: OpenAI-shaped messages already carry content parts; image input passes through
    supports_media_input = True

    def supports_vision(self, model: str) -> bool:
        return self._official_openai and (model in _VISION_MODELS or any(
            re.fullmatch(re.escape(name) + r"-\d{4}-\d{2}-\d{2}", model) for name in _VISION_MODELS))

    def __init__(self, base_url: str, api_key: str = "", provider_name: str = "openai-compatible",
                 headers: Optional[dict[str, str]] = None, session_header: str = "", auth_hint: str = "",
                 openrouter: Optional[bool] = None, routing_policy: Optional[dict] = None):
        from .registry import is_official_endpoint, reject_endpoint_credentials
        self.base_url = reject_endpoint_credentials(base_url).rstrip("/")
        self._official_openai = is_official_endpoint("openai", self.base_url)
        self._openrouter = provider_name == "openrouter" if openrouter is None else openrouter
        self._uses_completion_token_field = self._official_openai or self._openrouter
        self.routing_policy = validate_policy(routing_policy)
        if self.routing_policy and not self._openrouter:
            raise ValueError("OpenRouter routing controls cannot be sent to another provider")
        self.api_key = api_key
        self.auth_hint = auth_hint        # why an ambient key was withheld, appended to auth failures
        self.name = provider_name
        self.extra_headers = dict(headers or {})
        self.session_header = session_header
        self._client = None

    def _http(self):
        if self._client is None:
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            headers.update(self.extra_headers)
            from ..offline import httpx_offline_options
            self.base_url, transport, trust_env = httpx_offline_options(self.base_url, self.name)
            options = {"base_url": self.base_url, "headers": headers, "trust_env": trust_env}
            if transport is not None:
                options["transport"] = transport
            self._client = _httpx().Client(**options)
        return self._client

    def _req_headers(self, req: ChatRequest) -> dict[str, str]:
        """Per-request headers: use the conversation id, or the standalone run id, as session id."""
        return {self.session_header: req.session_id} if self.session_header and req.session_id else {}

    def _timeout(self, req: Optional[ChatRequest] = None, read: Optional[float] = None):
        return _httpx().Timeout(connect=5.0, read=read or (req.first_token_timeout if req else 30.0),
                                write=30.0, pool=5.0)

    # --------------------------------------------------------------- errors

    def _error_from_response(self, resp) -> ProviderError:
        code = ""
        try:
            text = resp.read().decode("utf-8", "replace") if hasattr(resp, "read") else resp.text
            j = json.loads(text)
            detail = (j.get("error") or {}).get("message") if isinstance(j.get("error"), dict) else j.get("error", text)
            if isinstance(j.get("error"), dict):
                code = str(j["error"].get("code") or j["error"].get("type") or "").lower()
        except Exception:
            detail = f"HTTP {resp.status_code}"
        low = str(detail).lower()
        st = resp.status_code
        if st in (401, 403):
            hint = f" {self.auth_hint}." if self.auth_hint else ""
            return ProviderError("auth", f"{self.name} rejected the credentials ({detail}). Check the API key.{hint}",
                                 provider=self.name, status=st)
        if st == 404 and "model" in low:
            return ProviderError("model_missing", str(detail), provider=self.name, status=st)
        if st == 402 or (st == 429 and (code in {"insufficient_quota", "billing_hard_limit_reached",
                                                                "insufficient_credits", "quota_exhausted"}
                or any(phrase in low for phrase in ("insufficient credits", "insufficient balance",
                                                    "quota exhausted", "credits exhausted")))):
            return ProviderError("quota", f"{self.name} has no available credit or quota: {detail}",
                                 provider=self.name, status=st)
        if st == 429:
            ra = resp.headers.get("retry-after")
            return ProviderError("rate_limit", f"{self.name} rate-limited the request: {detail}", provider=self.name,
                                 status=st, retry_after=float(ra) if ra and ra.replace(".", "").isdigit() else None)
        if "context" in low and ("length" in low or "exceed" in low or "too long" in low or "maximum" in low):
            return ProviderError("context", str(detail), provider=self.name, status=st)
        if st in (400, 422):
            return ProviderError("bad_request", str(detail), provider=self.name, status=st)
        return ProviderError("server", f"{self.name} returned HTTP {st}: {detail}", provider=self.name, status=st)

    def _wrap_exc(self, exc: Exception) -> ProviderError:
        h = _httpx()
        if isinstance(exc, ProviderError):
            return exc
        if isinstance(exc, h.ConnectError):
            return ProviderError("unreachable", f"cannot connect to {self.base_url} - is the server running?",
                                 provider=self.name)
        if isinstance(exc, h.TimeoutException):
            return ProviderError("timeout", f"{self.name} did not respond in time", provider=self.name)
        if isinstance(exc, (h.RemoteProtocolError, h.ReadError, h.StreamError, h.CloseError)):
            return ProviderError("stream", f"the response stream broke: {exc}", provider=self.name)
        return ProviderError("other", f"{type(exc).__name__}: {exc}", provider=self.name)

    # ------------------------------------------------------------- metadata

    def health(self) -> Health:
        t = time.perf_counter()
        try:
            r = self._http().get("/models", timeout=self._timeout(read=5.0))
            if r.status_code in (401, 403):
                return Health(ok=False, detail="reachable, but the API key was rejected")
            r.raise_for_status()
        except Exception as exc:
            return Health(ok=False, detail=self._wrap_exc(exc).args[0])
        return Health(ok=True, latency_ms=(time.perf_counter() - t) * 1000.0)

    def probe_models(self) -> tuple[bool, str, list[str]]:
        """Authenticated discovery: (ok, detail, names). Spends no inference tokens.

        OpenRouter's ``/models`` catalog is public, so a 200 there proves nothing
        about the key. Verify the key first with its authenticated ``/key``
        endpoint, which also reports the credit/budget state a person needs
        before choosing a paid model.
        """
        account = ""
        if self._openrouter:
            try:
                key_response = self._http().get("/key", timeout=self._timeout(read=8.0))
            except Exception as exc:
                return False, self._wrap_exc(exc).args[0], []
            if key_response.status_code in (401, 403):
                return False, "OpenRouter rejected the API key", []
            if key_response.status_code >= 400:
                return False, self._error_from_response(key_response).args[0], []
            try:
                data = (key_response.json() or {}).get("data") or {}
            except (ValueError, TypeError, AttributeError):
                data = {}
            if not isinstance(data, dict):
                data = {}
            if data.get("is_management_key") is True or data.get("is_provisioning_key") is True:
                return False, (
                    "OpenRouter accepted this management/provisioning key, but management keys cannot make "
                    "chat completion requests. Create a normal inference API key at "
                    "https://openrouter.ai/settings/keys and use that here."), []
            parts = []
            remaining = data.get("limit_remaining")
            if isinstance(remaining, (int, float)) and not isinstance(remaining, bool):
                parts.append(f"${float(remaining):.2f} key credit remaining")
            effective = data.get("effective_budget")
            if isinstance(effective, dict):
                left = effective.get("remaining_usd")
                if isinstance(left, (int, float)) and not isinstance(left, bool):
                    parts.append(f"${float(left):.2f} before the next budget limit")
                resets = effective.get("resets_at")
                if isinstance(resets, str) and resets:
                    parts.append(f"budget resets {resets}")
            if data.get("is_free_tier") is True:
                parts.append("free tier")
            account = "; ".join(parts)
        try:
            r = self._http().get("/models", timeout=self._timeout(read=8.0))
        except Exception as exc:
            return False, self._wrap_exc(exc).args[0], []
        if r.status_code in (401, 403):
            return False, "reachable, but the API key was rejected", []
        if r.status_code >= 400:
            return False, self._error_from_response(r).args[0], []
        try:
            names = self._catalog_ids(r.json())
        except (ValueError, TypeError, ProviderError) as exc:
            return False, str(exc) or "the endpoint returned an invalid model list", []
        detail = f"authenticated; {len(names)} model(s) available"
        if account:
            detail += f"; {account}"
        return True, detail, names

    def list_models(self) -> list[ModelMeta]:
        try:
            r = self._http().get("/models", timeout=self._timeout(read=10.0))
            if r.status_code >= 400:
                raise self._error_from_response(r)
            return [ModelMeta(name=name) for name in self._catalog_ids(r.json())]
        except ProviderError:
            raise
        except Exception as exc:
            raise self._wrap_exc(exc)

    def _catalog_ids(self, payload: Any) -> list[str]:
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ProviderError("other", f"{self.name} returned an invalid model catalog", provider=self.name)
        if len(payload["data"]) > _MAX_DISCOVERED_MODELS:
            raise ProviderError("other", f"{self.name}'s model catalog exceeded Hutch's discovery limit",
                                provider=self.name)
        ids = {row.get("id") for row in payload["data"] if isinstance(row, dict)
               and isinstance(row.get("id"), str) and _MODEL_ID.fullmatch(row["id"])}
        return sorted(ids)

    def list_openrouter_catalog(self, query: str = "", limit: int = 40) -> list[dict[str, Any]]:
        """Read OpenRouter's text-model catalog for the model picker; never makes an inference request."""
        if not self._openrouter:
            raise ProviderError("bad_request", "the OpenRouter catalog is available only on its named connection",
                                provider=self.name)
        params: dict[str, str] = {"sort": "most-popular", "output_modalities": "text"}
        query = (query or "").strip()[:80]
        if len(query) >= 2:
            params["q"] = query
        try:
            response = self._http().get("/models", params=params, timeout=self._timeout(read=10.0))
            if response.status_code >= 400:
                raise self._error_from_response(response)
            payload = response.json()
        except Exception as exc:
            raise self._wrap_exc(exc)
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise ProviderError("other", "OpenRouter returned an invalid model catalog", provider=self.name)
        found: list[dict[str, Any]] = []
        model_id_pattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,159}$")
        for row in rows:
            if not isinstance(row, dict):
                continue
            model_id = row.get("id")
            if not isinstance(model_id, str) or not model_id_pattern.fullmatch(model_id):
                continue
            name = row.get("name")
            if not isinstance(name, str) or not name.strip() or len(name) > 160 or any(ord(ch) < 32 for ch in name):
                name = model_id
            pricing: dict[str, float] = {}
            raw_pricing = row.get("pricing")
            if isinstance(raw_pricing, dict):
                for field in ("prompt", "completion"):
                    try:
                        rate = float(raw_pricing[field]) * 1_000_000
                    except (KeyError, TypeError, ValueError, OverflowError):
                        continue
                    if math.isfinite(rate) and 0 <= rate <= 100_000:
                        pricing[field] = rate
            parameters = row.get("supported_parameters")
            context_length = row.get("context_length")
            if not isinstance(context_length, int) or isinstance(context_length, bool) or context_length <= 0:
                context_length = 0
            found.append({"id": model_id, "name": name.strip(), "pricing": pricing,
                          "supports_tools": isinstance(parameters, list) and "tools" in parameters,
                          "context_length": context_length})
            if len(found) >= max(1, min(int(limit), 80)):
                break
        return found

    # ----------------------------------------------------------------- chat

    def _body(self, req: ChatRequest, stream: bool) -> dict[str, Any]:
        body: dict[str, Any] = {"model": req.model, "messages": req.messages, "stream": stream}
        if req.tools:
            body["tools"] = req.tools
        structured = req.structured_output or {}
        if structured and structured.get("attachment") == "response_format" and structured.get("schema"):
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": str(structured.get("name") or "hutch_action")[:64],
                    "schema": structured["schema"],
                    "strict": False,
                },
            }
        if req.max_tokens:
            # OpenAI's official host uses max_completion_tokens; compatible endpoints generally use max_tokens.
            # Match the authority exactly so a proxy path or lookalike hostname cannot select the OpenAI dialect.
            body["max_completion_tokens" if self._uses_completion_token_field else "max_tokens"] = int(req.max_tokens)
        if req.temperature is not None:
            body["temperature"] = req.temperature
        if self._openrouter:
            # OpenRouter only adds its billed `usage.cost` field when this is requested.
            # Without it, presets/dynamic model routes can have tokens but no dependable settlement.
            body["usage"] = {"include": True}
            if self.routing_policy:
                body["provider"] = validate_policy(self.routing_policy)
        if stream:
            body["stream_options"] = {"include_usage": True}
        return body

    def _complete(self, req: ChatRequest, stream: bool) -> ChatResult:
        body = self._body(req, stream)
        record_adapter_receipt(req, "openai-chat-completions", body, stream=stream)
        try:
            if stream:
                return self._chat_stream(req, body)
            r = self._http().post("/chat/completions", json=body, timeout=self._timeout(req),
                                  headers=self._req_headers(req))
            if r.status_code >= 400:
                raise self._error_from_response(r)
            return self._from_full(r.json(), req)
        except Exception as exc:
            raise self._wrap_exc(exc)

    def _chat_stream(self, req: ChatRequest, body: dict[str, Any]) -> ChatResult:
        from ..toolcalling.streamassembly import OpenAIChatStreamAssembler, StreamAssemblyError, should_reject_empty_stream
        assembler = OpenAIChatStreamAssembler()
        with self._http().stream("POST", "/chat/completions", json=body, timeout=self._timeout(req),
                                 headers=self._req_headers(req)) as resp:
            if resp.status_code >= 400:
                resp.read()
                raise self._error_from_response(resp)
            abort = lambda: abort_response(resp)
            dog = Watchdog(abort)
            unregister = req.register_cancel(abort)
            try:
                for line in resp.iter_lines():
                    dog.arm(req.idle_timeout)
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        assembler.mark_done()
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError as exc:
                        raise ProviderError("stream", f"malformed stream chunk: {exc.msg}", provider=self.name)
                    if "error" in chunk:
                        raise ProviderError("server", f"{self.name} error mid-stream: {chunk['error']}",
                                            provider=self.name)
                    try:
                        assembler.feed(chunk)
                    except StreamAssemblyError as exc:
                        raise ProviderError("stream", f"unassemblable stream: {exc}", provider=self.name)
            except Exception as exc:
                if dog.stalled:
                    raise self._partial_stream_error(
                        assembler, f"no data for {req.idle_timeout:.0f}s - the stream stalled")
                wrapped = self._wrap_exc(exc)
                if wrapped.partial_content == "" and assembler.content:
                    wrapped.partial_content = assembler.content
                    wrapped.partial_usage = self._usage_summary(assembler.usage)
                    wrapped.partial_finish = assembler.finish
                raise wrapped
            finally:
                dog.cancel()
                unregister()
        if should_reject_empty_stream(assembler):
            raise ProviderError("stream", "the stream ended without any content", provider=self.name)
        if not assembler.done and not assembler.finish_seen:
            raise self._partial_stream_error(
                assembler, "the stream ended without a completion marker; the reply may be incomplete")
        tcs = []
        for slot in assembler.calls():
            args, err, state, double = parse_tool_args_state(slot["arguments"])
            tcs.append(ToolCall(id=slot["id"], name=slot["name"], arguments=args, raw=slot["arguments"],
                                parse_error=err, arguments_state=state, double_decoded=double))
        result = self._result(assembler.content, tcs, assembler.usage, assembler.finish,
                              assembler.model or req.model, req, streamed=True)
        result.notes.extend(assembler.notes)
        return result

    @staticmethod
    def _usage_summary(usage: dict[str, Any]) -> dict[str, int]:
        details = usage.get("prompt_tokens_details") or {}
        return {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "cached_tokens": int(details.get("cached_tokens") or 0),
        }

    def _partial_stream_error(self, assembler, message: str) -> ProviderError:
        return ProviderError(
            "stream", f"{self.name} {message}", provider=self.name,
            partial_content=assembler.content,
            partial_usage=self._usage_summary(assembler.usage),
            partial_finish=assembler.finish,
        )

    def _from_full(self, j: dict[str, Any], req: ChatRequest) -> ChatResult:
        choice = (j.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        tcs = []
        for tc in msg.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function", {})
            raw_value = fn.get("arguments") if isinstance(fn, dict) and "arguments" in fn else tc.get("arguments")
            raw = raw_value if isinstance(raw_value, str) else (
                json.dumps(raw_value, ensure_ascii=False) if raw_value is not None else "")
            name = (fn.get("name") if isinstance(fn, dict) else None) or tc.get("name") or ""
            args, err, state, double = parse_tool_args_state(raw_value)
            tcs.append(ToolCall(id=tc.get("id") or "", name=name if isinstance(name, str) else "",
                                arguments=args, raw=raw or "", parse_error=err,
                                arguments_state=state, double_decoded=double))
        finish = choice.get("finish_reason") or "stop"
        refusal = msg.get("refusal")
        if isinstance(refusal, str) and refusal.strip() and not tcs:
            err = ProviderError("refused", f"{self.name} declined the request: {refusal.strip()[:300]}",
                                provider=self.name)
            err.category = "provider_refusal"  # type: ignore[attr-defined]
            raise err
        if finish == "content_filter" and not tcs:
            err = ProviderError("refused", f"{self.name} filtered the response (content_filter)", provider=self.name)
            err.category = "content_filter"  # type: ignore[attr-defined]
            raise err
        return self._result(msg.get("content") or "", tcs, j.get("usage") or {}, finish,
                            j.get("model", req.model), req, streamed=False)

    def _result(self, content: str, tcs: list[ToolCall], usage: dict[str, Any], finish: str, model: str,
                req: ChatRequest, streamed: bool) -> ChatResult:
        details = usage.get("prompt_tokens_details") or {}
        # Truncation is the stronger fact: a partially streamed tool call must
        # never be reported as a complete tool request.
        reason = "length" if finish == "length" else ("tool_calls" if tcs else "stop")
        reported = None
        raw_cost = usage.get("cost")
        if raw_cost is not None:
            try:
                candidate = float(raw_cost)
                if math.isfinite(candidate) and candidate >= 0:
                    reported = candidate
            except (TypeError, ValueError, OverflowError):
                reported = None
        res = ChatResult(content=content, tool_calls=tcs, prompt_tokens=int(usage.get("prompt_tokens") or 0),
                         completion_tokens=int(usage.get("completion_tokens") or 0),
                         cached_tokens=int(details.get("cached_tokens") or 0), finish_reason=reason, model=model,
                         streamed=streamed, context_window=int(req.num_ctx or 0),
                         reported_cost_usd=reported)
        if reported is not None:
            res.notes.append("the provider reported this call's charge (usage.cost)")
        if not usage:
            res.notes.append("the server reported no token usage; counts are estimates")
        return res
