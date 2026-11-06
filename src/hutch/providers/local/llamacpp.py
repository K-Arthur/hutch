"""llama.cpp server introspection from /props, /health, /slots and /v1/models.

The window is fixed at launch. ``-c`` is the total KV budget, which unified KV lets one slot use
in full; when the cache is divided, each slot gets a fraction. So the only honest per-request
window is what ``/slots[].n_ctx`` reports. Launch flags (``--context-shift``, ``--parallel``) are
not exposed over HTTP and are never inferred from a port.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Optional

from ..base import ModelMeta
from .base import Identity, LOADING, Loaded, NEEDS_KEY, READY, RuntimeState, Slot, UNKNOWN, UNREACHABLE
from .probe import DEFAULT_TIMEOUT, ProbeError, get_json

POLICY_NOTE = ("launch flags are not reported over HTTP; Hutch sizes to the per-slot window and refuses "
               "an over-long prompt before sending, so a shift cannot drop the system prompt unnoticed")


def _root(base_url: str) -> str:
    root = str(base_url or "").rstrip("/")
    for suffix in ("/v1/models", "/v1", "/api/tags"):
        if root.endswith(suffix):
            root = root[: -len(suffix)]
    return root


def _int(value: Any) -> Optional[int]:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else None


def _model_id(raw: str) -> str:
    """A llama-server started with ``-m /path/model.gguf`` lists that path as its id.

    It also accepts the basename without the extension as the request model (verified live), so
    Hutch presents that usable id instead of an absolute path in a route spec.
    """
    if raw.startswith("/") and raw.endswith(".gguf"):
        return os.path.basename(raw)[:-5]
    return raw


def _model_name(props: dict[str, Any], models: list[ModelMeta]) -> str:
    for model in models:
        return model.name
    path = str(props.get("model_path") or "")
    return _model_id(path) if path else ""


def _modalities(row: dict[str, Any], props: dict[str, Any]) -> list[str]:
    caps: list[str] = []
    architecture = row.get("architecture")
    inputs = architecture.get("input_modalities") if isinstance(architecture, dict) else None
    if isinstance(inputs, list):
        if any(item in ("image", "vision") for item in inputs):
            caps.append("vision")
        if "audio" in inputs:
            caps.append("audio")
    modalities = props.get("modalities") if isinstance(props.get("modalities"), dict) else {}
    if modalities.get("vision") and "vision" not in caps:
        caps.append("vision")
    if modalities.get("audio") and "audio" not in caps:
        caps.append("audio")
    template_caps = props.get("chat_template_caps") if isinstance(props.get("chat_template_caps"), dict) else {}
    if template_caps.get("supports_tools"):
        caps.append("tools")
    return caps


def _parse_models(payload: Any) -> list[ModelMeta]:
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    out: list[ModelMeta] = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            continue
        meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
        params = meta.get("n_params")
        out.append(ModelMeta(
            name=_model_id(row["id"])[:200],
            backend="llama.cpp",
            params_b=round(params / 1e9, 2) if isinstance(params, (int, float)) and params > 0 else None,
            quant=str(meta.get("ftype") or ""),
            max_context=_int(meta.get("n_ctx_train")) or _int(meta.get("n_ctx")),
            size_bytes=_int(meta.get("size")),
            capabilities=_modalities(row, {}),
        ))
    return out


def _parse_slots(payload: Any) -> list[Slot]:
    rows = payload.get("slots") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    return [Slot(n_ctx=_int(row.get("n_ctx")), processing=bool(row.get("is_processing")))
            for row in rows if isinstance(row, dict)]


class LlamaCppRuntime:
    provider_id = "llamacpp"

    def __init__(self, base_url: str, credential: str = "", *, timeout: float = DEFAULT_TIMEOUT,
                 http: Callable[..., Any] = get_json):
        self.base_url = _root(base_url)
        self._credential = credential
        self._timeout = timeout
        self._http = http
        self._cached: Optional[RuntimeState] = None
        self.identity = Identity("unknown", "not inspected")

    def _get(self, path: str):
        return self._http(self.base_url + path, self._timeout, self._credential)

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

    def _read(self) -> RuntimeState:
        if self._cached is not None:
            return self._cached
        state = RuntimeState(self.provider_id)
        try:
            health = self._get("/health")
        except ProbeError as exc:
            state.detail = str(exc)
            self._cached = state
            return state
        state.reachable = True
        if health.status in (401, 403):
            state.state, state.detail = NEEDS_KEY, "the server requires an API key (HTTP %d from /health)" % health.status
            self._cached = state
            return state
        loading = health.status == 503
        if loading:
            state.detail = "loading the model (HTTP 503 from /health)"
        elif health.status != 200:
            state.state, state.detail = UNKNOWN, f"/health answered HTTP {health.status}"
            self._cached = state
            return state

        props: dict[str, Any] = {}
        try:
            props_response = self._get("/props")
        except ProbeError:
            props_response = None
        if props_response is not None and props_response.status in (401, 403):
            state.state, state.detail = NEEDS_KEY, "the server requires an API key (HTTP %d from /props)" % props_response.status
            self._cached = state
            return state
        if props_response is not None and props_response.status == 200:
            try:
                payload = props_response.json()
                props = payload if isinstance(payload, dict) else {}
            except ProbeError:
                props = {}

        models: list[ModelMeta] = []
        try:
            models_response = self._get("/v1/models")
        except ProbeError:
            models_response = None
        if models_response is not None and models_response.status in (401, 403):
            state.state, state.detail = NEEDS_KEY, "the server requires an API key (HTTP %d from /v1/models)" % models_response.status
            self._cached = state
            return state
        if models_response is not None and models_response.status == 200:
            try:
                models = _parse_models(models_response.json())
            except ProbeError:
                models = []
        state.models = models
        state.version = str(props.get("build_info") or "")

        build = props.get("default_generation_settings") if isinstance(props.get("default_generation_settings"), dict) else {}
        slots: list[Slot] = []
        try:
            slots_response = self._get("/slots")
            if slots_response.status == 200:
                slots = _parse_slots(slots_response.json())
        except ProbeError:
            slots = []
        name = _model_name(props, models)
        applied = max((slot.n_ctx for slot in slots if slot.n_ctx), default=None)
        parallel = len(slots) or _int(props.get("total_slots"))
        if not applied:
            applied = _int(build.get("n_ctx"))
        if name and (applied or parallel):
            state.loaded[name] = Loaded(model=name, applied_context=applied, parallel=parallel, slots=slots)
        for row in models:
            if row.name == name:
                row.applied_context = applied
                row.backend_version = state.version
                row.capabilities = list(dict.fromkeys([*row.capabilities, *(_modalities({}, props))]))
        state.policy, state.policy_detail = "unknown", POLICY_NOTE
        state.identity = self._identity(props, models, models_response)
        if loading:
            state.state = LOADING
        elif props or models:
            state.state = READY
        else:
            state.state, state.detail = UNKNOWN, "the port answered but neither /props nor /v1/models identified a server"
        self._cached = state
        return state

    @staticmethod
    def _identity(props: dict[str, Any], models: list[ModelMeta], response: Any) -> Identity:
        build = str(props.get("build_info") or "")
        if build:
            return Identity("llamacpp", f"/props build_info {build!r}", build)
        if response is not None and getattr(response, "status", 0) == 200:
            try:
                payload = response.json()
            except ProbeError:
                payload = {}
            rows = payload.get("data") if isinstance(payload, dict) else None
            owners = {row.get("owned_by") for row in rows or [] if isinstance(row, dict)}
            if "llamacpp" in owners:
                return Identity("llamacpp", "/v1/models data[].owned_by is 'llamacpp'", "", "strong")
            if owners:
                return Identity("unknown", f"/v1/models answered but owned_by is {sorted(map(str, owners))!r}", "", "unknown")
        if models:
            return Identity("llamacpp", "/v1/models listed models without a runtime owner", "", "weak")
        return Identity("unknown", "no identifying field was returned")
