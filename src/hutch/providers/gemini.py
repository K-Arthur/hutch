"""Google Gemini over the Generative Language REST API (``generateContent``).

Evidence behind the wire shapes (read 2026-10-31, not inferred from an SDK):

* the published discovery document
  ``https://generativelanguage.googleapis.com/$discovery/rest?version=v1beta`` (revision 20261030)
  defines ``GenerateContentRequest`` / ``Part`` / ``UsageMetadata`` and the ``finishReason`` enum that
  ``gemini_wire`` converts;
* ``https://ai.google.dev/gemini-api/docs/text-generation`` documents the ``x-goog-api-key`` header and
  ``:streamGenerateContent?alt=sse`` for server-sent events;
* ``https://ai.google.dev/gemini-api/docs/thinking`` documents that generateContent carries thought
  signatures as part metadata and that they must be replayed with the history.

Deliberate limits, because a wrong default here would break every call:

* thinking is left at the model default. ``effort`` maps to ``thinkingLevel`` only for Gemini 3+ models
  (the schema says the field errors on earlier models); ``think=False`` never sends "no thinking";
* the constrained structured-output strategy stays unavailable: this adapter sends no response schema;
* a remote image URL is refused rather than fetched - a provider adapter is not an HTTP fetcher for
  user-supplied URLs, so only inline ``data:`` images travel;
* ``temperature`` is sent when set, but the schema documents that Gemini 3.6 Flash and newer silently
  ignore it; that is recorded in the compatibility matrix instead of being presented as effective.
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

from .base import (ChatRequest, ChatResult, Health, ModelMeta, Provider, ProviderError, ToolCall,
                   Watchdog, abort_response)
from .gemini_wire import (DEFAULT_BASE_URL, MAX_MODELS, MAX_PAGES, MODEL_RE,
                          MULTIMODAL_MODEL, REFUSAL_REASONS, SIGNATURE_MESSAGE,
                          forget_signatures, model_id, request_body, signature_for, tool_calls_from,
                          usage_counts)

__all__ = ["GeminiProvider", "DEFAULT_BASE_URL", "forget_signatures", "signature_for"]


class GeminiProvider(Provider):
    name = "google"
    #: Gemini's generateContent accepts inline image parts (converted in gemini_wire.to_contents)
    supports_media_input = True

    def __init__(self, api_key: str = "", base_url: Optional[str] = None, provider_name: str = "google",
                 headers: Optional[dict[str, str]] = None, session_header: str = "", auth_hint: str = ""):
        from .registry import is_official_endpoint, reject_endpoint_credentials
        self.base_url = reject_endpoint_credentials(base_url or DEFAULT_BASE_URL).rstrip("/")
        self._official = is_official_endpoint("google", self.base_url)
        self.api_key = api_key
        self.auth_hint = auth_hint
        self.name = provider_name
        self.extra_headers = dict(headers or {})
        self.session_header = session_header
        self._client = None

    # --------------------------------------------------------------- transport

    def _httpx(self):
        import httpx
        return httpx

    def _http(self):
        if self._client is None:
            headers = {"x-goog-api-key": self.api_key} if self.api_key else {}
            headers.update(self.extra_headers)
            from ..offline import httpx_offline_options
            self.base_url, transport, trust_env = httpx_offline_options(self.base_url, self.name)
            options: dict[str, Any] = {"base_url": self.base_url, "headers": headers, "trust_env": trust_env}
            if transport is not None:
                options["transport"] = transport
            self._client = self._httpx().Client(**options)
        return self._client

    def _req_headers(self, req: ChatRequest) -> dict[str, str]:
        return {self.session_header: req.session_id} if self.session_header and req.session_id else {}

    def _timeout(self, req: Optional[ChatRequest] = None, read: Optional[float] = None):
        h = self._httpx()
        return h.Timeout(connect=10.0, read=read or (req.first_token_timeout if req else 30.0),
                         write=30.0, pool=5.0)

    # --------------------------------------------------------------- errors

    @staticmethod
    def _error_payload(raw: Any) -> tuple[str, str]:
        """(status word, message) from a Google error envelope; never echoes the key."""
        try:
            payload = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
        except (ValueError, TypeError):
            payload = None
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            return str(error.get("status") or ""), str(error.get("message") or "the provider reported an error")
        text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw or "")
        return "", text[:400] or "the provider reported an error"

    def _error_from_response(self, resp) -> ProviderError:
        raw = resp.read() if hasattr(resp, "read") else getattr(resp, "text", "")
        status_word, detail = self._error_payload(raw)
        low = f"{status_word} {detail}".lower()
        st = resp.status_code
        if st in (401, 403) or "api key not valid" in low or "unauthenticated" in low:
            hint = f" {self.auth_hint}." if self.auth_hint else ""
            return ProviderError("auth", f"{self.name} rejected the credentials ({detail}). Check the API key.{hint}",
                                 provider=self.name, status=st)
        if st == 404 or "not found" in low or "is not supported for" in low:
            return ProviderError("model_missing", str(detail), provider=self.name, status=st)
        if "thought signature" in low:
            return ProviderError("bad_request", f"{detail} {SIGNATURE_MESSAGE}", provider=self.name, status=st)
        if st == 429:
            if "quota" in low or "billing" in low or "credit" in low:
                return ProviderError("quota", f"{self.name} has no available quota: {detail}", provider=self.name,
                                     status=st)
            ra = resp.headers.get("retry-after")
            return ProviderError("rate_limit", f"{self.name} rate-limited the request: {detail}", provider=self.name,
                                 status=st, retry_after=float(ra) if ra and ra.replace(".", "").isdigit() else None)
        if (("token count" in low and ("exceed" in low or "too long" in low))
                or ("context" in low and "length" in low)):
            return ProviderError("context", str(detail), provider=self.name, status=st)
        if st in (400, 422):
            return ProviderError("bad_request", str(detail), provider=self.name, status=st)
        return ProviderError("server" if st >= 500 else "bad_request",
                             f"{self.name} returned HTTP {st}: {detail}", provider=self.name, status=st)

    def _wrap_exc(self, exc: Exception) -> ProviderError:
        h = self._httpx()
        if isinstance(exc, ProviderError):
            return exc
        if isinstance(exc, h.ConnectError):
            return ProviderError("unreachable", f"cannot connect to {self.base_url}", provider=self.name)
        if isinstance(exc, h.TimeoutException):
            return ProviderError("timeout", f"{self.name} did not respond in time", provider=self.name)
        if isinstance(exc, (h.RemoteProtocolError, h.ReadError, h.StreamError, h.CloseError)):
            return ProviderError("stream", f"the response stream broke: {exc}", provider=self.name)
        return ProviderError("other", f"{type(exc).__name__}: {exc}", provider=self.name)

    # --------------------------------------------------------------- metadata

    def health(self) -> Health:
        if not self.api_key:
            return Health(ok=False, detail=self.auth_hint or "no GEMINI_API_KEY set")
        t = time.perf_counter()
        try:
            r = self._http().get("/models", params={"pageSize": 1}, timeout=self._timeout(read=5.0))
            if r.status_code >= 400:
                # Google answers an invalid key with 400 INVALID_ARGUMENT, not 401, so the body is the
                # only reliable signal; mapping through the same path keeps the message truthful.
                error = self._error_from_response(r)
                detail = "reachable, but the API key was rejected" if error.kind == "auth" else str(error)
                return Health(ok=False, detail=detail)
        except Exception as exc:
            return Health(ok=False, detail=self._wrap_exc(exc).args[0])
        return Health(ok=True, latency_ms=(time.perf_counter() - t) * 1000.0)

    def _model_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        token = ""
        seen_tokens: set[str] = set()
        for _ in range(MAX_PAGES):
            params: dict[str, Any] = {"pageSize": 1000}
            if token:
                params["pageToken"] = token
            response = self._http().get("/models", params=params, timeout=self._timeout(read=10.0))
            if response.status_code >= 400:
                raise self._error_from_response(response)
            payload = response.json()
            page = payload.get("models") if isinstance(payload, dict) else None
            if not isinstance(page, list):
                raise ProviderError("other", f"{self.name} returned an invalid model catalog", provider=self.name)
            rows.extend(row for row in page if isinstance(row, dict))
            if len(rows) > MAX_MODELS:
                raise ProviderError("other", f"{self.name}'s model catalog exceeded Hutch's discovery limit",
                                    provider=self.name)
            token = payload.get("nextPageToken") or ""
            if not token:
                break
            if token in seen_tokens:
                raise ProviderError("other", "Gemini returned a repeated model-list page token", provider=self.name)
            seen_tokens.add(token)
        else:
            raise ProviderError("other", "Gemini's model catalog exceeded Hutch's page limit", provider=self.name)
        return rows

    def list_models(self) -> list[ModelMeta]:
        models: list[ModelMeta] = []
        for row in self._model_rows():
            name = str(row.get("name") or "").removeprefix("models/")
            if not MODEL_RE.fullmatch(name):
                continue
            methods = row.get("supportedGenerationMethods")
            # Discovery returns the methods a model serves; an embedding-only model must not be offered
            # as a chat route. A row that omits the field is not assumed to generate content.
            if not isinstance(methods, list) or "generateContent" not in methods:
                continue
            limit = row.get("inputTokenLimit")
            models.append(ModelMeta(name=name,
                                    max_context=limit if isinstance(limit, int) and not isinstance(limit, bool)
                                    and limit > 0 else None))
        return models

    def probe_models(self) -> tuple[bool, str, list[str]]:
        try:
            names = sorted({row.name for row in self.list_models()})
        except ProviderError as exc:
            return False, str(exc), []
        return True, f"authenticated; {len(names)} model(s) available", names

    def supports_vision(self, model: str) -> bool:
        """Whether this model is documented to accept image parts.

        Narrower than "every gemini model": the 1.0 generation shipped a separate text-only Pro model, so a
        prefix match would claim image input for a checkpoint that rejects it. Gemma and embedding models are
        excluded for the same reason.
        """
        name = str(model or "").lower().removeprefix("models/")
        if not name.startswith("gemini-") or "embedding" in name or name.startswith("gemma"):
            return False
        return bool(MULTIMODAL_MODEL.match(name))

    # --------------------------------------------------------------- request body

    # --------------------------------------------------------------- chat

    def _complete(self, req: ChatRequest, stream: bool) -> ChatResult:
        path = f"/models/{model_id(req.model, self.name)}"
        body = request_body(req, self.base_url, self.name)
        try:
            if stream:
                return self._chat_stream(req, path, body)
            response = self._http().post(f"{path}:generateContent", json=body, timeout=self._timeout(req),
                                         headers=self._req_headers(req))
            if response.status_code >= 400:
                raise self._error_from_response(response)
            return self._from_full(response.json(), req)
        except Exception as exc:
            raise self._wrap_exc(exc)

    def _chat_stream(self, req: ChatRequest, path: str, body: dict[str, Any]) -> ChatResult:
        text: list[str] = []
        thinking: list[str] = []
        calls: list[dict[str, Any]] = []
        usage: dict[str, Any] = {}
        finish = finish_message = served_model = blocked = ""
        finish_seen = False
        with self._http().stream("POST", f"{path}:streamGenerateContent", params={"alt": "sse"}, json=body,
                                 timeout=self._timeout(req), headers=self._req_headers(req)) as response:
            if response.status_code >= 400:
                response.read()
                raise self._error_from_response(response)
            abort = lambda: abort_response(response)
            dog = Watchdog(abort)
            unregister = req.register_cancel(abort)
            try:
                for line in response.iter_lines():
                    dog.arm(req.idle_timeout)
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError as exc:
                        raise ProviderError("stream", f"malformed stream chunk: {exc.msg}", provider=self.name)
                    if not isinstance(chunk, dict):
                        raise ProviderError("stream", "the stream carried a non-object chunk", provider=self.name)
                    if chunk.get("error"):
                        raise ProviderError("server", f"{self.name} error mid-stream: {chunk['error']}",
                                            provider=self.name)
                    usage = chunk.get("usageMetadata") or usage
                    served_model = chunk.get("modelVersion") or served_model
                    blocked = (chunk.get("promptFeedback") or {}).get("blockReason") or blocked
                    candidate = (chunk.get("candidates") or [{}])[0]
                    if candidate.get("finishReason"):
                        finish, finish_seen = str(candidate["finishReason"]), True
                    if candidate.get("finishMessage"):
                        finish_message = str(candidate["finishMessage"])
                    for part in ((candidate.get("content") or {}).get("parts") or []):
                        self._take_part(part, text, thinking, calls)
            except Exception as exc:
                if dog.stalled:
                    raise self._partial("no data for {:.0f}s - the stream stalled".format(req.idle_timeout),
                                        "".join(text), usage, finish)
                wrapped = self._wrap_exc(exc)
                if not wrapped.partial_content and text:
                    wrapped.partial_content = "".join(text)
                    wrapped.partial_usage = usage_counts(usage)
                    wrapped.partial_finish = finish
                raise wrapped
            finally:
                dog.cancel()
                unregister()
        if blocked:
            raise self._refused(blocked, content="".join(text))
        if not text and not calls:
            raise ProviderError("stream", "the stream ended without any content", provider=self.name)
        if not finish_seen and not calls:
            raise self._partial("the stream ended without a completion marker; the reply may be incomplete",
                                "".join(text), usage, finish)
        return self._result("".join(text), "".join(thinking), self._calls(calls, served_model or req.model),
                            usage, finish, served_model or req.model, req, streamed=True,
                            finish_message=finish_message)

    @staticmethod
    def _take_part(part: Any, text: list[str], thinking: list[str], calls: list[dict[str, Any]]) -> None:
        if not isinstance(part, dict):
            return
        if part.get("thought") and isinstance(part.get("text"), str):
            thinking.append(part["text"])
        elif isinstance(part.get("text"), str):
            text.append(part["text"])
        if isinstance(part.get("functionCall"), dict):
            calls.append({"part": part["functionCall"], "signature": part.get("thoughtSignature") or ""})

    def _from_full(self, payload: Any, req: ChatRequest) -> ChatResult:
        if not isinstance(payload, dict):
            raise ProviderError("other", f"{self.name} returned an invalid response", provider=self.name)
        blocked = (payload.get("promptFeedback") or {}).get("blockReason")
        if blocked:
            raise self._refused(str(blocked), content="")
        candidate = (payload.get("candidates") or [{}])[0] if payload.get("candidates") else {}
        if not isinstance(candidate, dict):
            candidate = {}
        texts: list[str] = []
        thinking: list[str] = []
        calls: list[dict[str, Any]] = []
        for part in ((candidate.get("content") or {}).get("parts") or []):
            self._take_part(part, texts, thinking, calls)
        served = str(payload.get("modelVersion") or req.model)
        return self._result("".join(texts), "".join(thinking), self._calls(calls, served),
                            payload.get("usageMetadata") or {}, str(candidate.get("finishReason") or ""),
                            served, req, streamed=False, finish_message=str(candidate.get("finishMessage") or ""))

    # --------------------------------------------------------------- results

    def _calls(self, calls: list[dict[str, Any]], served_model: str) -> list[ToolCall]:
        return [ToolCall(id=row["id"], name=row["name"], arguments=row["arguments"], raw=row["raw"])
                for row in tool_calls_from(calls, served_model, self.base_url, self.name)]

    def _partial(self, message: str, content: str, usage: dict[str, Any], finish: str) -> ProviderError:
        return ProviderError("stream", f"{self.name} {message}", provider=self.name, partial_content=content,
                             partial_usage=usage_counts(usage), partial_finish=finish)

    def _refused(self, reason: str, *, content: str = "") -> ProviderError:
        error = ProviderError("refused", f"{self.name} declined the request ({reason})", provider=self.name,
                              partial_content=content)
        error.category = reason  # type: ignore[attr-defined]
        return error

    def _result(self, content: str, thinking: str, tool_calls: list[ToolCall], usage: dict[str, Any],
                finish: str, model: str, req: ChatRequest, *, streamed: bool,
                finish_message: str = "") -> ChatResult:
        if finish in REFUSAL_REASONS and not tool_calls:
            raise self._refused(finish, content=content)
        if finish == "MISSING_THOUGHT_SIGNATURE":
            raise ProviderError("bad_request", SIGNATURE_MESSAGE, provider=self.name)
        if finish == "MALFORMED_FUNCTION_CALL":
            raise ProviderError("bad_request", "Gemini produced a malformed function call; nothing was executed",
                                provider=self.name)
        if finish in ("UNEXPECTED_TOOL_CALL", "TOO_MANY_TOOL_CALLS"):
            raise ProviderError("bad_request", f"Gemini stopped the turn: {finish}", provider=self.name)
        if finish == "CONTINUATION":
            raise ProviderError("incomplete", f"{model} did not finish this response; it can be continued",
                                provider=self.name, partial_content=content)
        reason = ("length" if finish == "MAX_TOKENS" else
                  "tool_calls" if tool_calls else
                  "refusal" if finish in REFUSAL_REASONS else "stop")
        counts = usage_counts(usage)
        result = ChatResult(content=content, thinking=thinking, tool_calls=tool_calls,
                            prompt_tokens=counts["prompt_tokens"], completion_tokens=counts["completion_tokens"],
                            cached_tokens=counts["cached_tokens"], finish_reason=reason, model=model,
                            streamed=streamed, context_window=int(req.num_ctx or 0))
        thoughts = int(usage.get("thoughtsTokenCount") or 0)
        if thoughts:
            result.notes.append(f"the provider counted {thoughts} thinking token(s) separately")
        if finish_message and finish not in ("STOP", ""):
            result.notes.append(f"the provider's finish message: {finish_message[:300]}")
        if not usage:
            result.notes.append("the server reported no token usage; counts are estimates")
        return result
