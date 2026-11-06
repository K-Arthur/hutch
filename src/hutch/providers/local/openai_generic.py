"""OpenAI-compatible local servers: vLLM, SGLang, and any other /v1/models answer.

``/v1/models`` is the OpenAI model object. vLLM and SGLang add ``max_model_len`` to every entry (vLLM's and
SGLang's ``ModelCard``; checked 2026-11-06), and it is the largest prompt-plus-output the server accepts per request.
It is reported as the applied window only when ``owned_by`` identifies the server as one of those two. Any other
OpenAI-compatible server keeps an unknown window even if it sends a similar field. Identity comes from the response,
never the port: an unrecognised server stays unlabelled rather than being called llama.cpp or vLLM.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from ..base import ModelMeta
from .base import Identity, Loaded, NEEDS_KEY, READY, RuntimeState, UNKNOWN
from .probe import DEFAULT_TIMEOUT, ProbeError, get_json

OWNERS = {"vllm": "vllm", "sglang": "sglang", "llamacpp": "llamacpp", "lmstudio": "lmstudio"}
POLICY_NOTE = ("the server does not report the window it serves over /v1/models; Hutch states the window as "
               "unknown and makes no truncation claim")
WINDOW_SERVERS = frozenset({"vllm", "sglang"})


def _root(base_url: str) -> str:
    root = str(base_url or "").rstrip("/")
    if root.endswith("/v1/models"):
        root = root[: -len("/v1/models")]
    elif root.endswith("/v1"):
        root = root[: -len("/v1")]
    elif root.endswith("/models"):
        root = root[: -len("/models")]
    return root


def _int(value: Any) -> Optional[int]:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else None


def _parse(payload: Any) -> list[ModelMeta]:
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    out: list[ModelMeta] = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            continue
        out.append(ModelMeta(
            name=row["id"][:200],
            max_context=_int(row.get("max_model_len")) or _int(row.get("context_length")),
        ))
    return out


class OpenAIGenericRuntime:
    def __init__(self, provider_id: str, base_url: str, credential: str = "", *,
                 timeout: float = DEFAULT_TIMEOUT, http: Callable[..., Any] = get_json):
        self.provider_id = provider_id
        self.base_url = _root(base_url)
        self._credential = credential
        self._timeout = timeout
        self._http = http
        self._cached: Optional[RuntimeState] = None
        self.identity = Identity("unknown", "not inspected")

    def identify(self) -> Identity:
        return self._read().identity or Identity("unknown", "not inspected")

    def models(self) -> list[ModelMeta]:
        return self._read().models

    def loaded(self) -> dict[str, Loaded]:
        return self._read().loaded

    def capabilities(self, model: str) -> list[str]:
        return []

    def state(self) -> RuntimeState:
        return self._read()

    def _read(self) -> RuntimeState:
        if self._cached is not None:
            return self._cached
        state = RuntimeState(self.provider_id)
        url = self.base_url + "/v1/models"
        try:
            response = self._http(url, self._timeout, self._credential)
        except ProbeError as exc:
            state.detail = str(exc)
            self._cached = state
            return state
        state.reachable = True
        if response.status in (401, 403):
            state.state = NEEDS_KEY
            state.detail = f"the server requires an API key (HTTP {response.status} from /v1/models)"
            self._cached = state
            return state
        if response.status != 200:
            state.state, state.detail = UNKNOWN, f"/v1/models answered HTTP {response.status}"
            self._cached = state
            return state
        try:
            payload = response.json()
        except ProbeError:
            state.state, state.detail = UNKNOWN, "/v1/models answered but not with JSON"
            self._cached = state
            return state
        state.models = _parse(payload)
        owners = {row.get("owned_by") for row in (payload.get("data") or [])
                  if isinstance(row, dict) and isinstance(row.get("owned_by"), str)}
        expected = OWNERS.get(self.provider_id)
        if expected and expected in owners:
            state.identity = Identity(expected, f"/v1/models data[].owned_by is {expected!r}", "", "strong")
        elif owners:
            state.identity = Identity("unknown", f"/v1/models answered but owned_by is {sorted(owners)!r}", "", "weak")
        elif state.models:
            state.identity = Identity("unknown", "/v1/models listed models without an owner", "", "weak")
        else:
            state.identity = Identity("unknown", "/v1/models returned no models", "", "unknown")
        state.state = READY if state.models else UNKNOWN
        state.policy, state.policy_detail = "unknown", POLICY_NOTE
        if state.identity.runtime in WINDOW_SERVERS and state.identity.confidence == "strong":
            state.loaded = {m.name: Loaded(m.name, applied_context=m.max_context) for m in state.models if m.max_context}
            if state.loaded:
                state.policy, state.policy_detail = "refuse", f"{state.identity.runtime} rejects a request above max_model_len"
        self._cached = state
        return state
