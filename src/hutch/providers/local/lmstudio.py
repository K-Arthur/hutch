"""LM Studio introspection from the native /api/v1/models surface.

The window in effect is ``loaded_instances[].config.context_length``. ``max_context_length`` is the
model's trained maximum and is never presented as the window in use. When the model is cold, the
native load endpoint accepts an explicit ``context_length`` and echoes the applied value, so Hutch
can make the window known instead of assuming LM Studio's default.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Optional

from ..base import ModelMeta
from .base import Identity, Loaded, NEEDS_KEY, READY, RuntimeState, UNKNOWN
from .probe import DEFAULT_TIMEOUT, ProbeError, get_json, post_json

POLICY_NOTE = ("LM Studio's overflow policy (stopAtLimit or truncateMiddle) is a server setting not exposed on "
               "/api/v1/models; Hutch sizes to the applied window and refuses an over-long prompt before sending")
_PARAMS = re.compile(r"(\d+(?:\.\d+)?)\s*B", re.IGNORECASE)


def _root(base_url: str) -> str:
    root = str(base_url or "").rstrip("/")
    if root.endswith("/v1/models"):
        root = root[: -len("/v1/models")]
    elif root.endswith("/v1"):
        root = root[: -len("/v1")]
    return root


def _int(value: Any) -> Optional[int]:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else None


def _params_b(raw: Any) -> Optional[float]:
    match = _PARAMS.search(str(raw or ""))
    return float(match.group(1)) if match else None


def _capabilities(row: dict[str, Any]) -> list[str]:
    caps: list[str] = []
    if row.get("type") == "embedding":
        caps.append("embedding")
    reported = row.get("capabilities") if isinstance(row.get("capabilities"), dict) else {}
    if reported.get("vision"):
        caps.append("vision")
    if reported.get("trained_for_tool_use"):
        caps.append("tools")
    if isinstance(reported.get("reasoning"), dict):
        caps.append("reasoning")
    return caps


def _parse_models(payload: Any) -> list[ModelMeta]:
    rows = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    out: list[ModelMeta] = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("key"), str):
            continue
        quantization = row.get("quantization") if isinstance(row.get("quantization"), dict) else {}
        loaded = row.get("loaded_instances") if isinstance(row.get("loaded_instances"), list) else []
        applied = None
        if loaded and isinstance(loaded[0], dict):
            config = loaded[0].get("config") if isinstance(loaded[0].get("config"), dict) else {}
            applied = _int(config.get("context_length"))
        out.append(ModelMeta(
            name=row["key"][:200],
            backend="lmstudio",
            params_b=_params_b(row.get("params_string")),
            quant=str(quantization.get("name") or ""),
            family=str(row.get("architecture") or ""),
            max_context=_int(row.get("max_context_length")),
            size_bytes=_int(row.get("size_bytes")),
            capabilities=_capabilities(row),
            applied_context=applied,
        ))
    return out


def _parse_loaded(payload: Any) -> dict[str, Loaded]:
    rows = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return {}
    out: dict[str, Loaded] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("key"), str):
            continue
        for instance in row.get("loaded_instances") or []:
            if not isinstance(instance, dict):
                continue
            config = instance.get("config") if isinstance(instance.get("config"), dict) else {}
            out[row["key"]] = Loaded(
                model=row["key"],
                applied_context=_int(config.get("context_length")),
                parallel=_int(config.get("parallel")),
            )
            break
    return out


class LMStudioRuntime:
    provider_id = "lmstudio"

    def __init__(self, base_url: str, credential: str = "", *, timeout: float = DEFAULT_TIMEOUT,
                 http: Callable[..., Any] = get_json, post: Callable[..., Any] = post_json):
        self.base_url = _root(base_url)
        self._credential = credential
        self._timeout = timeout
        self._http = http
        self._post = post
        self._cached: Optional[RuntimeState] = None
        self.identity = Identity("unknown", "not inspected")

    def identify(self) -> Identity:
        return self._read().identity or Identity("unknown", "not inspected")

    def models(self) -> list[ModelMeta]:
        return self._read().models

    def loaded(self) -> dict[str, Loaded]:
        return self._read().loaded

    def capabilities(self, model: str) -> list[str]:
        found = next((row for row in self.models() if row.name == model), None)
        return list(found.capabilities) if found else []

    def state(self) -> RuntimeState:
        return self._read()

    def load(self, model: str, context_length: int) -> Optional[int]:
        """Load with an explicit window and return the applied value the server echoes, if any."""
        response = self._post(self.base_url + "/api/v1/models/load",
                              {"model": model, "context_length": int(context_length), "echo_load_config": True},
                              timeout=600.0, bearer=self._credential)
        self._cached = None
        if response.status in (401, 403):
            raise ProbeError("needs_key", "LM Studio requires an API token to load a model")
        if response.status != 200:
            raise ProbeError("server", f"LM Studio refused to load {model!r} (HTTP {response.status})")
        payload = response.json()
        config = payload.get("load_config") if isinstance(payload, dict) else None
        return _int(config.get("context_length")) if isinstance(config, dict) else None

    def _read(self) -> RuntimeState:
        if self._cached is not None:
            return self._cached
        state = RuntimeState(self.provider_id)
        try:
            response = self._http(self.base_url + "/api/v1/models", self._timeout, self._credential)
        except ProbeError as exc:
            state.detail = str(exc)
            self._cached = state
            return state
        state.reachable = True
        if response.status in (401, 403):
            state.state = NEEDS_KEY
            state.detail = f"LM Studio requires an API token (HTTP {response.status} from /api/v1/models)"
            self._cached = state
            return state
        if response.status != 200:
            state.state, state.detail = UNKNOWN, f"/api/v1/models answered HTTP {response.status}"
            self._cached = state
            return state
        try:
            payload = response.json()
        except ProbeError:
            state.state, state.detail = UNKNOWN, "/api/v1/models answered but not with JSON"
            self._cached = state
            return state
        if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
            state.state, state.detail = UNKNOWN, "/api/v1/models answered without a models list"
            self._cached = state
            return state
        state.models = _parse_models(payload)
        state.loaded = _parse_loaded(payload)
        state.identity = Identity("lmstudio", "/api/v1/models returned models[].loaded_instances",
                                  "", "strong")
        state.state = READY
        state.policy, state.policy_detail = "unknown", POLICY_NOTE
        self._cached = state
        return state
