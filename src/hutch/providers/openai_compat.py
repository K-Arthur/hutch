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
                   Watchdog, abort_response, parse_tool_args_state)

PRESET_URLS = {
    "openai": "https://api.openai.com/v1",
    "lmstudio": "http://localhost:1234/v1",
    "llamacpp": "http://localhost:8080/v1",
    "llama.cpp": "http://localhost:8080/v1",
    "vllm": "http://localhost:8000/v1",
}

_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,159}$")
_MAX_DISCOVERED_MODELS = 10000


def _httpx():
    import httpx
    return httpx


class OpenAICompatProvider(Provider):
    name = "openai-compatible"

    def __init__(self, base_url: str, api_key: str = "", provider_name: str = "openai-compatible",
                 headers: Optional[dict[str, str]] = None, session_header: str = "", auth_hint: str = ""):
        from .registry import is_official_endpoint, reject_endpoint_credentials
        self.base_url = reject_endpoint_credentials(base_url).rstrip("/")
        self._official_openai = is_official_endpoint("openai", self.base_url)
        self._uses_completion_token_field = self._official_openai or provider_name == "openrouter"
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
        try:
            text = resp.read().decode("utf-8", "replace") if hasattr(resp, "read") else resp.text
            j = json.loads(text)
            detail = (j.get("error") or {}).get("message") if isinstance(j.get("error"), dict) else j.get("error", text)
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
        """ONE authenticated GET of the model list: (ok, detail, names). Spends no tokens."""
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
        return True, f"authenticated; {len(names)} model(s) available", names

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
        if self.name != "openrouter":
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
        if req.max_tokens:
            # OpenAI's official host uses max_completion_tokens; compatible endpoints generally use max_tokens.
            # Match the authority exactly so a proxy path or lookalike hostname cannot select the OpenAI dialect.
            body["max_completion_tokens" if self._uses_completion_token_field else "max_tokens"] = int(req.max_tokens)
        if req.temperature is not None:
            body["temperature"] = req.temperature
        if stream:
            body["stream_options"] = {"include_usage": True}
        return body

    def _complete(self, req: ChatRequest, stream: bool) -> ChatResult:
        body = self._body(req, stream)
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
                    raise ProviderError("stream", f"no data for {req.idle_timeout:.0f}s - the stream stalled",
                                        provider=self.name)
                raise self._wrap_exc(exc)
            finally:
                dog.cancel()
                unregister()
        if should_reject_empty_stream(assembler):
            raise ProviderError("stream", "the stream ended without any content", provider=self.name)
        tcs = []
        for slot in assembler.calls():
            args, err, state, double = parse_tool_args_state(slot["arguments"])
            tcs.append(ToolCall(id=slot["id"], name=slot["name"], arguments=args, raw=slot["arguments"],
                                parse_error=err, arguments_state=state, double_decoded=double))
        result = self._result(assembler.content, tcs, assembler.usage, assembler.finish,
                              assembler.model or req.model, req, streamed=True)
        result.notes.extend(assembler.notes)
        return result

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
        reason = "tool_calls" if tcs else ("length" if finish == "length" else "stop")
        res = ChatResult(content=content, tool_calls=tcs, prompt_tokens=int(usage.get("prompt_tokens") or 0),
                         completion_tokens=int(usage.get("completion_tokens") or 0),
                         cached_tokens=int(details.get("cached_tokens") or 0), finish_reason=reason, model=model,
                         streamed=streamed, context_window=int(req.num_ctx or 0))
        if not usage:
            res.notes.append("the server reported no token usage; counts are estimates")
        return res
