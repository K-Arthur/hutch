"""OpenAI Responses API adapter for the Sign in with ChatGPT public-client route.

This deliberately accepts only api.openai.com, streams every request with
storage disabled, and omits the fields excluded by the current SIWC preview.
"""

from __future__ import annotations

import json
from typing import Any

from .base import (ChatRequest, ChatResult, ModelMeta, Provider, ProviderError, ToolCall,
                   Watchdog, abort_response, parse_tool_args)

API_URL = "https://api.openai.com/v1"


class OpenAIResponsesProvider(Provider):
    name = "chatgpt"

    def __init__(self, access_token: str, *, base_url: str = API_URL, transport=None):
        from .registry import is_official_endpoint, reject_endpoint_credentials
        self.base_url = reject_endpoint_credentials(base_url).rstrip("/")
        if not is_official_endpoint("openai", self.base_url):
            raise ProviderError("bad_request", "Sign in with ChatGPT tokens may only be sent to https://api.openai.com/v1",
                                provider=self.name)
        if not access_token:
            raise ProviderError("auth", "Sign in with ChatGPT on the Connections page before using this route",
                                provider=self.name)
        self.api_key = access_token
        self._client = None
        self._transport = transport

    def _http(self):
        if self._client is None:
            from ..offline import httpx_offline_options
            import httpx
            base_url, transport, trust_env = httpx_offline_options(self.base_url, self.name)
            options = {"base_url": base_url, "headers": {"Authorization": f"Bearer {self.api_key}"},
                       "trust_env": trust_env}
            if self._transport is not None:
                options["transport"] = self._transport
            elif transport is not None:
                options["transport"] = transport
            self._client = httpx.Client(**options)
        return self._client

    @staticmethod
    def _timeout(req: ChatRequest | None = None, read: float | None = None):
        import httpx
        return httpx.Timeout(connect=5.0, read=read or (req.first_token_timeout if req else 15.0),
                              write=30.0, pool=5.0)

    @staticmethod
    def _body(req: ChatRequest) -> dict[str, Any]:
        instructions: list[str] = []
        items: list[dict[str, Any]] = []
        for message in req.messages:
            role = message.get("role")
            content = message.get("content")
            if role in ("system", "developer"):
                if content:
                    instructions.append(str(content))
                continue
            if role == "tool":
                call_id = message.get("tool_call_id")
                if not isinstance(call_id, str) or not call_id:
                    raise ProviderError("bad_request", "a prior tool result has no Responses API call id", provider="chatgpt")
                items.append({"type": "function_call_output", "call_id": call_id,
                              "output": content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)})
                continue
            if role not in ("user", "assistant"):
                raise ProviderError("bad_request", f"message role '{role}' is not supported on Sign in with ChatGPT",
                                    provider="chatgpt")
            if content:
                if not isinstance(content, (str, list)):
                    raise ProviderError("bad_request", "message content is not supported by the Responses route",
                                        provider="chatgpt")
                items.append({"role": role, "content": content})
            if role == "assistant":
                for call in message.get("tool_calls") or []:
                    call_id = call.get("id")
                    function = call.get("function") or {}
                    name = function.get("name")
                    if not isinstance(call_id, str) or not call_id or not isinstance(name, str) or not name:
                        raise ProviderError("bad_request", "a prior tool call has no call id or function name",
                                            provider="chatgpt")
                    args = function.get("arguments", "{}")
                    if not isinstance(args, str):
                        args = json.dumps(args, ensure_ascii=False)
                    items.append({"type": "function_call", "call_id": call_id,
                                  "name": name, "arguments": args})
        body: dict[str, Any] = {"model": req.model, "input": items, "store": False, "stream": True}
        if instructions:
            body["instructions"] = "\n\n".join(instructions)
        if req.tools:
            tools = []
            for item in req.tools:
                function = item.get("function") or {}
                name = function.get("name")
                parameters = function.get("parameters")
                if item.get("type") != "function" or not isinstance(name, str) or not isinstance(parameters, dict):
                    raise ProviderError("bad_request", "Hutch sent a tool shape that Responses cannot represent",
                                        provider="chatgpt")
                tool = {"type": "function", "name": name, "parameters": parameters,
                        "strict": bool(function.get("strict", False))}
                if function.get("description"):
                    tool["description"] = function["description"]
                tools.append(tool)
            body["tools"] = tools
        return body

    @staticmethod
    def _map_error(status: int, detail: str) -> ProviderError:
        low = detail.casefold()
        if status in (401, 403):
            return ProviderError("auth", "ChatGPT rejected this sign-in; reconnect the account on Connections",
                                 provider="chatgpt", status=status)
        if status == 429 or any(word in low for word in ("usage_limit", "quota", "rate_limit")):
            return ProviderError("rate_limit", f"ChatGPT plan usage is unavailable or limited: {detail}",
                                 provider="chatgpt", status=status)
        if status in (400, 422):
            return ProviderError("bad_request", detail[:800], provider="chatgpt", status=status)
        return ProviderError("server", f"ChatGPT Responses returned HTTP {status}: {detail[:500]}",
                             provider="chatgpt", status=status)

    @classmethod
    def _response_error(cls, response) -> ProviderError:
        try:
            payload = response.json()
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
            detail = error.get("message") or error.get("code") or "request failed"
        except Exception:
            detail = "request failed"
        return cls._map_error(response.status_code, str(detail))

    @classmethod
    def _stream_error(cls, kind: str, error: Any) -> ProviderError:
        if not isinstance(error, dict):
            error = {}
        code = str(error.get("code") or error.get("type") or kind)
        detail = str(error.get("message") or code)[:800]
        low = f"{kind} {code} {detail}".casefold()
        if any(word in low for word in ("usage_limit", "quota", "rate_limit", "rate limit")):
            return cls._map_error(429, detail)
        if any(word in low for word in ("refusal", "content_filter", "safety")):
            return ProviderError("refused", f"ChatGPT refused this response: {detail}", provider="chatgpt")
        # A terminal stream event is a definite provider result, but it does not
        # prove that the request incurred no plan usage. Do not classify every
        # failure as a quota error or retry it invisibly.
        return ProviderError("server", f"ChatGPT ended the response as {kind}: {detail}; usage may be uncertain",
                             provider="chatgpt")

    def probe_models(self) -> tuple[bool, str, list[str]]:
        try:
            response = self._http().get("/models", timeout=self._timeout(read=10.0))
            if response.status_code >= 400:
                err = self._response_error(response)
                return False, str(err), []
            rows = response.json().get("models", [])
            models = [row["slug"] for row in rows if isinstance(row, dict) and row.get("visibility") == "list"
                      and isinstance(row.get("slug"), str)]
            return True, f"authorized; {len(models)} model(s) available for this ChatGPT account", models
        except Exception as exc:
            return False, f"could not verify ChatGPT model access ({type(exc).__name__})", []

    def list_models(self) -> list[ModelMeta]:
        ok, detail, names = self.probe_models()
        if not ok:
            raise ProviderError("auth", detail, provider="chatgpt")
        return [ModelMeta(name=name) for name in names]

    def _complete(self, req: ChatRequest, stream: bool) -> ChatResult:
        # This preview only accepts a streamed request. Retrying a broken stream
        # as a non-stream request is both invalid and could obscure uncertainty.
        req.allow_stream_retry = False
        if not stream:
            raise ProviderError("bad_request", "Sign in with ChatGPT requires streaming; Hutch will not retry it as a non-stream request",
                                provider="chatgpt")
        body = self._body(req)
        content: list[str] = []
        completed: dict[str, Any] | None = None
        saw_terminal_failure: tuple[str, Any] | None = None
        done = False
        try:
            with self._http().stream("POST", "/responses", json=body, timeout=self._timeout(req)) as response:
                if response.status_code >= 400:
                    response.read()
                    raise self._response_error(response)
                abort = lambda: abort_response(response)
                dog = Watchdog(abort)
                unregister = req.register_cancel(abort)
                try:
                    for line in response.iter_lines():
                        dog.arm(req.idle_timeout)
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            continue  # SIWC requires the explicit response.completed event.
                        try:
                            event = json.loads(data)
                        except json.JSONDecodeError as exc:
                            raise ProviderError("stream", f"malformed Responses event: {exc.msg}", provider="chatgpt") from exc
                        kind = event.get("type")
                        if kind == "response.output_text.delta" and isinstance(event.get("delta"), str):
                            content.append(event["delta"])
                        elif kind == "response.completed":
                            completed = event.get("response")
                            done = True
                        elif kind in ("response.failed", "response.incomplete"):
                            response_data = event.get("response") or {}
                            err = response_data.get("error") or event.get("error") or {}
                            saw_terminal_failure = (kind, err)
                            break
                        if done:
                            break
                except Exception as exc:
                    if isinstance(exc, ProviderError):
                        raise
                    if dog.stalled:
                        raise ProviderError("stream", f"no data for {req.idle_timeout:.0f}s - the ChatGPT stream stalled",
                                            provider="chatgpt") from exc
                    import httpx
                    if isinstance(exc, (httpx.TimeoutException, httpx.RemoteProtocolError, httpx.ReadError,
                                        httpx.StreamError, httpx.CloseError)):
                        raise ProviderError("stream", f"the ChatGPT response stream broke ({type(exc).__name__})",
                                            provider="chatgpt") from exc
                    raise ProviderError("other", f"ChatGPT response failed ({type(exc).__name__})", provider="chatgpt") from exc
                finally:
                    dog.cancel()
                    unregister()
        except ProviderError:
            raise
        except Exception as exc:
            import httpx
            if isinstance(exc, httpx.TimeoutException):
                raise ProviderError("timeout", "ChatGPT did not respond in time", provider="chatgpt") from exc
            if isinstance(exc, httpx.ConnectError):
                raise ProviderError("unreachable", "could not connect to the ChatGPT Responses API",
                                    provider="chatgpt") from exc
            raise ProviderError("other", f"ChatGPT request failed ({type(exc).__name__})", provider="chatgpt") from exc
        if saw_terminal_failure:
            raise self._stream_error(*saw_terminal_failure)
        if not done or not isinstance(completed, dict) or completed.get("status") != "completed":
            raise ProviderError("stream", "ChatGPT ended without a completed response; usage remains uncertain",
                                provider="chatgpt")
        output = completed.get("output") or []
        tool_calls: list[ToolCall] = []
        final_text: list[str] = []
        refused = False
        for item in output:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "function_call":
                raw = item.get("arguments") if isinstance(item.get("arguments"), str) else "{}"
                args, error = parse_tool_args(raw)
                call_id = item.get("call_id") or item.get("id")
                name = item.get("name")
                if not isinstance(call_id, str) or not call_id or not isinstance(name, str) or not name:
                    raise ProviderError("stream", "ChatGPT completed with an invalid function call; usage may be uncertain",
                                        provider="chatgpt")
                tool_calls.append(ToolCall(id=call_id, name=name, arguments=args, raw=raw,
                                           parse_error=error))
            elif item.get("type") == "message":
                for part in item.get("content") or []:
                    if isinstance(part, dict) and part.get("type") == "output_text" and isinstance(part.get("text"), str):
                        final_text.append(part["text"])
                    elif isinstance(part, dict) and part.get("type") == "refusal":
                        final_text.append(str(part.get("refusal") or ""))
                        refused = True
        text = "".join(final_text) or "".join(content)
        usage = completed.get("usage") or {}
        details = usage.get("input_tokens_details") or {}
        result = ChatResult(content=text, tool_calls=tool_calls,
                            prompt_tokens=int(usage.get("input_tokens") or 0),
                            completion_tokens=int(usage.get("output_tokens") or 0),
                            cached_tokens=int(details.get("cached_tokens") or 0),
                            finish_reason="tool_calls" if tool_calls else "refusal" if refused else "stop",
                            model=str(completed.get("model") or req.model), streamed=True)
        if refused:
            result.refusal_category = "provider_refusal"
        result.notes.append("ChatGPT Responses preview has no provider-enforced output-token ceiling; Hutch limits are estimates")
        if not usage:
            result.notes.append("ChatGPT did not report token usage; Hutch recorded an estimate")
        return result
