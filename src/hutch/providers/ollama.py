"""Ollama provider - the NATIVE chat API, never the OpenAI-compatible shim (LM-1).

Ollama's defaults silently hurt agents: the context window is 4k below 24 GiB of VRAM (its own docs
recommend >= 64k for agents), and through ``/v1`` the size cannot be set at all, so long prompts are
truncated from the front with no error - system prompt and tool definitions simply vanish (openclaw #4028).

So this provider:
* always sends ``options.num_ctx`` - the caller computes it; we never rely on the runtime default;
* detects truncation after the fact (the evaluated prompt token count pinned at the window) so the
  runtime can escalate or warn instead of carrying on with a lobotomised prompt;
* sends ``think: false`` only to models that report the ``thinking`` capability (SR-5), because thinking
  costs latency and tokens on short routing/extraction turns and sending it to others is an error;
* reports ``load_duration`` so a cold load is visible (LM-6) rather than looking like a hang.

Wire format verified against Ollama's API reference (docs/api.md): /api/chat, /api/show, /api/ps,
/api/tags, and the empty-prompt /api/generate trick for preloading.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Optional

from .base import (ChatRequest, ChatResult, Health, ModelMeta, Provider, ProviderError, ToolCall,
                   Watchdog, abort_response, parse_tool_args)

DEFAULT_BASE_URL = "http://localhost:11434"
TRUNCATION_RATIO = 0.98


def _httpx():
    import httpx  # lazy: ~50 ms, only when a model is actually called (PF-6)
    return httpx


def to_ollama_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        role = m["role"]
        if role == "assistant" and m.get("tool_calls"):
            calls = []
            for tc in m["tool_calls"]:
                args, _ = parse_tool_args(tc["function"].get("arguments"))
                calls.append({"function": {"name": tc["function"]["name"], "arguments": args}})
            out.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": calls})
        elif role == "tool":
            out.append({"role": "tool", "content": m.get("content") or "", "tool_name": m.get("name", "")})
        else:
            out.append({"role": role, "content": m.get("content") or ""})
    return out


class OllamaProvider(Provider):
    name = "ollama"

    def __init__(self, base_url: str = DEFAULT_BASE_URL):
        from .registry import reject_endpoint_credentials
        self.base_url = reject_endpoint_credentials(base_url or DEFAULT_BASE_URL).rstrip("/")
        if self.base_url.endswith("/v1"):  # people paste the OpenAI-style URL; we speak the native API
            self.base_url = self.base_url[:-3]
        self._client = None
        self._caps: dict[str, list[str]] = {}

    # ----------------------------------------------------------------- http

    def _http(self):
        if self._client is None:
            from ..offline import httpx_offline_options
            self.base_url, transport, trust_env = httpx_offline_options(self.base_url, self.name)
            options = {"base_url": self.base_url, "trust_env": trust_env}
            if transport is not None:
                options["transport"] = transport
            self._client = _httpx().Client(**options)
        return self._client

    def _timeout(self, req: Optional[ChatRequest] = None, read: Optional[float] = None):
        h = _httpx()
        return h.Timeout(connect=5.0, read=read or (req.first_token_timeout if req else 30.0),
                         write=30.0, pool=5.0)

    def _error_from_response(self, resp, model: str = "") -> ProviderError:
        text = ""
        try:
            text = resp.read().decode("utf-8", "replace") if hasattr(resp, "read") else resp.text
            detail = json.loads(text).get("error", text)
        except Exception:
            detail = text or f"HTTP {resp.status_code}"
        low = str(detail).lower()
        st = resp.status_code
        if st == 404 or "not found" in low and "model" in low:
            return ProviderError("model_missing", f"{detail} - install it with `ollama pull {model}`" if model
                                 else str(detail), provider=self.name, status=st)
        if "memory" in low or "unable to allocate" in low or "out of memory" in low:
            return ProviderError("oom", f"{detail} - the model plus its context does not fit in memory; pick a "
                                        "smaller model or a smaller context", provider=self.name, status=st)
        if "context" in low and ("exceed" in low or "too long" in low):
            return ProviderError("context", str(detail), provider=self.name, status=st)
        if st in (400, 422):
            return ProviderError("bad_request", str(detail), provider=self.name, status=st)
        if st == 429:
            return ProviderError("rate_limit", str(detail), provider=self.name, status=st)
        return ProviderError("server", f"Ollama returned HTTP {st}: {detail}", provider=self.name, status=st)

    def _wrap_exc(self, exc: Exception) -> ProviderError:
        h = _httpx()
        if isinstance(exc, ProviderError):
            return exc
        if isinstance(exc, h.ConnectError):
            return ProviderError("unreachable", f"cannot connect to Ollama at {self.base_url} - is it running? "
                                                "(`ollama serve`)", provider=self.name)
        if isinstance(exc, h.TimeoutException):
            return ProviderError("timeout", f"Ollama did not respond in time ({type(exc).__name__})",
                                 provider=self.name)
        if isinstance(exc, (h.RemoteProtocolError, h.ReadError, h.StreamError, h.CloseError)):
            return ProviderError("stream", f"the response stream broke: {exc}", provider=self.name)
        return ProviderError("other", f"{type(exc).__name__}: {exc}", provider=self.name)

    # ------------------------------------------------------------- metadata

    def health(self) -> Health:
        t = time.perf_counter()
        try:
            r = self._http().get("/api/version", timeout=self._timeout(read=3.0))
            r.raise_for_status()
            version = r.json().get("version", "")
        except Exception as exc:
            return Health(ok=False, detail=self._wrap_exc(exc).args[0])
        return Health(ok=True, version=version, loaded=self.ps(),
                      latency_ms=(time.perf_counter() - t) * 1000.0)

    def ps(self, timeout: float = 5.0) -> list[dict[str, Any]]:
        try:
            r = self._http().get("/api/ps", timeout=_httpx().Timeout(timeout))
            r.raise_for_status()
            return r.json().get("models", [])
        except Exception:
            return []

    def list_models(self) -> list[ModelMeta]:
        r = self._http().get("/api/tags", timeout=self._timeout(read=10.0))
        r.raise_for_status()
        out = []
        for m in r.json().get("models", []):
            d = m.get("details", {}) or {}
            out.append(ModelMeta(name=m.get("name") or m.get("model", ""), params_b=_params_b(d.get("parameter_size")),
                                 quant=d.get("quantization_level", ""), family=d.get("family", ""),
                                 size_bytes=m.get("size"), digest=m.get("digest", "")))
        return out

    def show(self, model: str) -> Optional[ModelMeta]:
        try:
            r = self._http().post("/api/show", json={"model": model}, timeout=self._timeout(read=15.0))
            if r.status_code == 404:
                return None
            r.raise_for_status()
        except Exception:
            return None
        j = r.json()
        d = j.get("details", {}) or {}
        info = j.get("model_info", {}) or {}
        arch = info.get("general.architecture") or d.get("family") or ""

        def pick(suffix: str) -> Optional[int]:
            for k, v in info.items():
                if k.endswith(suffix) and isinstance(v, (int, float)):
                    return int(v)
            return None

        heads, kv_heads = pick(".attention.head_count"), pick(".attention.head_count_kv")
        emb = pick(".embedding_length")
        head_dim = pick(".attention.key_length") or (emb // heads if emb and heads else None)
        lic = (j.get("license") or "").strip().splitlines()
        meta = ModelMeta(
            name=model, params_b=_params_b(d.get("parameter_size")), quant=d.get("quantization_level", ""),
            family=arch, max_context=pick(".context_length"), n_layers=pick(".block_count"),
            n_kv_heads=kv_heads or heads, head_dim=head_dim, capabilities=list(j.get("capabilities") or []),
            template_hash=hashlib.sha256((j.get("template") or "").encode()).hexdigest()[:12],
            license=lic[0].strip() if lic else "", size_bytes=_size_from_ps_or_none(self, model))
        self._caps[model] = meta.capabilities
        return meta

    def capabilities(self, model: str) -> list[str]:
        if model not in self._caps:
            self.show(model)
            self._caps.setdefault(model, [])
        return self._caps[model]

    # ------------------------------------------------- residency (LM-6)

    def preload(self, model: str, keep_alive: str = "10m") -> float:
        """Load a model without generating (empty-prompt /api/generate). Returns load milliseconds."""
        t = time.perf_counter()
        try:
            r = self._http().post("/api/generate", json={"model": model, "keep_alive": keep_alive},
                                  timeout=self._timeout(read=900.0))
        except Exception as exc:
            raise self._wrap_exc(exc)
        if r.status_code >= 400:
            raise self._error_from_response(r, model)
        ns = r.json().get("load_duration")
        return ns / 1e6 if isinstance(ns, (int, float)) else (time.perf_counter() - t) * 1000.0

    def unload(self, model: str) -> None:
        try:
            self._http().post("/api/generate", json={"model": model, "keep_alive": 0}, timeout=self._timeout(read=30.0))
        except Exception:
            pass

    def is_loaded(self, model: str) -> bool:
        return any(m.get("name") == model or m.get("model") == model for m in self.ps())

    # ----------------------------------------------------------------- chat

    def _body(self, req: ChatRequest, stream: bool) -> dict[str, Any]:
        if not req.num_ctx:
            # LM-1: never fall back to the runtime default (4k below 24 GiB VRAM). A caller that forgot to size
            # the context has a bug, and a silent default is exactly the failure this layer exists to prevent.
            raise ProviderError("bad_request", "Ollama requests must set num_ctx explicitly (LM-1)",
                                provider=self.name)
        options: dict[str, Any] = {"num_ctx": int(req.num_ctx)}
        if req.max_tokens:
            options["num_predict"] = int(req.max_tokens)  # per-turn cap (SR-5)
        if req.temperature is not None:
            options["temperature"] = req.temperature
        body: dict[str, Any] = {"model": req.model, "messages": to_ollama_messages(req.messages),
                                "stream": stream, "options": options, "keep_alive": req.keep_alive}
        if req.tools:
            body["tools"] = req.tools
        if req.think is not None and "thinking" in self.capabilities(req.model):
            body["think"] = bool(req.think)
        return body

    def _complete(self, req: ChatRequest, stream: bool) -> ChatResult:
        body = self._body(req, stream)
        try:
            if stream:
                return self._chat_stream(req, body)
            r = self._http().post("/api/chat", json=body, timeout=self._timeout(req))
            if r.status_code >= 400:
                raise self._error_from_response(r, req.model)
            return self._fold([r.json()], req, streamed=False)
        except Exception as exc:
            raise self._wrap_exc(exc)

    def _chat_stream(self, req: ChatRequest, body: dict[str, Any]) -> ChatResult:
        chunks: list[dict[str, Any]] = []
        with self._http().stream("POST", "/api/chat", json=body, timeout=self._timeout(req)) as resp:
            if resp.status_code >= 400:
                resp.read()
                raise self._error_from_response(resp, req.model)
            abort = lambda: abort_response(resp)
            dog = Watchdog(abort)
            unregister = req.register_cancel(abort)
            try:
                for line in resp.iter_lines():
                    dog.arm(req.idle_timeout)  # after the first chunk, silence means a stall
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise ProviderError("stream", f"malformed stream chunk: {exc.msg}", provider=self.name)
                    if "error" in chunk:
                        raise ProviderError("server", f"Ollama error mid-stream: {chunk['error']}", provider=self.name)
                    chunks.append(chunk)
                    if chunk.get("done"):
                        break
            except Exception as exc:
                if dog.stalled:
                    raise ProviderError("stream", f"no data for {req.idle_timeout:.0f}s - the stream stalled",
                                        provider=self.name)
                raise self._wrap_exc(exc)
            finally:
                dog.cancel()
                unregister()
        if not chunks or not chunks[-1].get("done"):
            raise ProviderError("stream", "the stream ended before Ollama said it was done", provider=self.name)
        return self._fold(chunks, req, streamed=True)

    def _fold(self, chunks: list[dict[str, Any]], req: ChatRequest, streamed: bool) -> ChatResult:
        content, thinking, calls = [], [], []
        for c in chunks:
            msg = c.get("message") or {}
            if msg.get("content"):
                content.append(msg["content"])
            if msg.get("thinking"):
                thinking.append(msg["thinking"])
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function", {})
                args, err = parse_tool_args(fn.get("arguments"))
                raw = fn.get("arguments") if isinstance(fn.get("arguments"), str) else json.dumps(fn.get("arguments"))
                calls.append(ToolCall(id=tc.get("id") or f"call_{len(calls) + 1}", name=fn.get("name", ""),
                                      arguments=args, raw=raw or "", parse_error=err))
        last = chunks[-1]
        p, e = int(last.get("prompt_eval_count") or 0), int(last.get("eval_count") or 0)
        ev_ns = last.get("eval_duration") or 0
        res = ChatResult(
            content="".join(content), thinking="".join(thinking), tool_calls=calls, prompt_tokens=p,
            completion_tokens=e, model=last.get("model", req.model), streamed=streamed,
            load_ms=(last.get("load_duration") or 0) / 1e6, total_ms=(last.get("total_duration") or 0) / 1e6,
            tokens_per_sec=(e / (ev_ns / 1e9)) if ev_ns and e else None,
            context_window=int(req.num_ctx or 0),
            finish_reason="tool_calls" if calls else ("length" if last.get("done_reason") == "length" else "stop"))
        if req.num_ctx and p >= int(req.num_ctx * TRUNCATION_RATIO):
            res.prompt_truncated = True
            res.notes.append(f"prompt evaluated {p} tokens against a {req.num_ctx}-token window: it was almost "
                             "certainly truncated from the front")
        return res


def _params_b(text: Any) -> Optional[float]:
    """'8.0B' -> 8.0, '566.7M' -> 0.5667"""
    if not text:
        return None
    s = str(text).strip().upper()
    try:
        if s.endswith("B"):
            return float(s[:-1])
        if s.endswith("M"):
            return float(s[:-1]) / 1000.0
        if s.endswith("T"):
            return float(s[:-1]) * 1000.0
        return float(s)
    except ValueError:
        return None


def _size_from_ps_or_none(provider: OllamaProvider, model: str) -> Optional[int]:
    for m in provider.ps():
        if m.get("name") == model or m.get("model") == model:
            return m.get("size")
    try:
        for m in provider.list_models():
            if m.name == model:
                return m.size_bytes
    except Exception:
        pass
    return None
