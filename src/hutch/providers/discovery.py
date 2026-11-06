"""Local inference discovery over known loopback endpoints only.

Discovery is deliberately narrow: fixed loopback endpoints, plain HTTP, no credential unless the
caller supplies one for exactly that origin, no redirects, a short timeout and a bounded body. It
answers "is a local model server answering, which one is it, and what does it report?" - it never
claims that a model works, and it never sends a provider key on its own.

An answer is fingerprinted, not trusted by port. A decoy on llama.cpp's old port is reported as an
unidentified OpenAI-compatible server; a 401 is `needs_key`, not a dead port.
"""

from __future__ import annotations

import json
import urllib.error
from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable, Optional
from urllib.parse import urlsplit

from .local import DEFAULT_TIMEOUT, ProbeError, get_json, introspect, verified_loopback_url
from .local.base import NEEDS_KEY, READY, UNREACHABLE, UNKNOWN

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
MAX_RESPONSE_BYTES = 256 * 1024
MAX_MODELS = 500


@dataclass(frozen=True)
class LocalEndpoint:
    provider_id: str
    title: str
    url: str
    style: str  # "ollama" | "openai"
    alternates: tuple[str, ...] = ()


#: llama-server's stock port is 9931 (Phase 0); 8080 is kept as a candidate for older setups.
ENDPOINTS: tuple[LocalEndpoint, ...] = (
    LocalEndpoint("ollama", "Ollama", "http://127.0.0.1:11434/api/tags", "ollama"),
    LocalEndpoint("lmstudio", "LM Studio", "http://127.0.0.1:1234/v1/models", "openai"),
    LocalEndpoint("vllm", "vLLM", "http://127.0.0.1:8000/v1/models", "openai"),
    LocalEndpoint("sglang", "SGLang", "http://127.0.0.1:30000/v1/models", "openai"),
    LocalEndpoint("llamacpp", "llama.cpp", "http://127.0.0.1:9931/v1/models", "openai",
                  ("http://127.0.0.1:8080/v1/models",)),
)


def _origin_url(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or "127.0.0.1"
    netloc = f"[{host}]" if ":" in host else host
    if parts.port is not None:
        netloc += f":{parts.port}"
    return f"{parts.scheme}://{netloc}"


def _http_get(url: str, timeout: float, bearer: str = "") -> Any:
    return get_json(url, timeout, bearer)


def parse_models(style: str, payload: Any) -> list[str]:
    """Model ids from an Ollama tags response or an OpenAI-compatible models response."""
    models: list[str] = []
    if not isinstance(payload, dict):
        return models
    if style == "ollama":
        rows = payload.get("models")
        if not isinstance(rows, list):
            return models
        for row in rows:
            name = row.get("name") or row.get("model") if isinstance(row, dict) else None
            if isinstance(name, str) and name.strip():
                models.append(name.strip())
    else:
        rows = payload.get("data")
        if not isinstance(rows, list):
            return models
        for row in rows:
            model_id = row.get("id") if isinstance(row, dict) else None
            if isinstance(model_id, str) and model_id.strip():
                models.append(model_id.strip())
    cleaned = []
    for model in models:
        if len(model) > 200 or any(ord(char) < 32 for char in model):
            continue
        cleaned.append(model)
    return sorted(dict.fromkeys(cleaned))[:MAX_MODELS]


def _needs_key_fix(provider_id: str, url: str) -> str:
    origin = _origin_url(url)
    if provider_id == "lmstudio":
        return (f"create an API token in LM Studio Server Settings and store it for {origin}; "
                "Hutch sends it only to that origin, never in the URL")
    return (f"store this server's API key for {origin}; Hutch sends it only to that origin, "
            "never in the URL")


def _result(endpoint: LocalEndpoint, url: str) -> dict[str, Any]:
    return {"provider": endpoint.provider_id, "title": endpoint.title, "url": url,
            "reachable": False, "models": [], "model_meta": [], "error": "", "state": UNREACHABLE,
            "runtime": "unknown", "version": "", "confidence": "unknown", "evidence": "",
            "applied_context": {}, "parallel": None, "policy": "unknown", "policy_detail": "",
            "fix": ""}


def _merge_state(result: dict[str, Any], state: Any) -> None:
    """Copy one adapter's report into the discovery row without inventing missing values."""
    result["state"] = state.state
    result["version"] = state.version
    result["models"] = [model.name for model in state.models] or result["models"]
    result["model_meta"] = [asdict(model) for model in state.models]
    result["applied_context"] = {name: loaded.applied_context
                                 for name, loaded in state.loaded.items() if loaded.applied_context}
    parallel = next((loaded.parallel for loaded in state.loaded.values() if loaded.parallel), None)
    result["parallel"] = parallel
    result["policy"], result["policy_detail"] = state.policy, state.policy_detail
    if state.identity is not None:
        result["runtime"] = state.identity.runtime
        result["confidence"] = state.identity.confidence
        result["evidence"] = state.identity.evidence
    elif not result["evidence"]:
        result["evidence"] = "the port answered but did not identify the runtime"


def probe_service(endpoint: LocalEndpoint, *, timeout: float = 0.5,
                  get: Callable[..., Any] = _http_get,
                  credential_for: Optional[Callable[[str, str], str]] = None) -> dict[str, Any]:
    """Probe one fixed local endpoint, trying its candidate ports. Never raises for a dead service."""
    candidates = (endpoint.url, *endpoint.alternates)
    result = _result(endpoint, endpoint.url)
    for url in candidates:
        verified_loopback_url(url)
        credential = credential_for(endpoint.provider_id, url) if credential_for else ""
        try:
            response = get(url, timeout, credential)
        except ProbeError as exc:
            result["error"] = str(exc)
            continue
        except urllib.error.URLError as exc:  # a caller-supplied getter may raise the stdlib error
            result["error"] = f"no service answered ({type(exc).__name__})"
            continue
        result["url"] = url
        result["reachable"] = True
        if response.status in (401, 403):
            result["state"] = NEEDS_KEY
            result["error"] = ""
            result["fix"] = _needs_key_fix(endpoint.provider_id, url)
            result["evidence"] = f"/v1/models answered HTTP {response.status}"
            return result
        if response.status != 200:
            result["state"] = UNKNOWN
            result["error"] = f"the service answered HTTP {response.status}"
            continue
        try:
            payload = json.loads(response.body.decode("utf-8", "replace"))
        except (ValueError, UnicodeError):
            result["error"] = "the service answered but not with a model list"
            continue
        result["models"] = parse_models(endpoint.style, payload)
        result["error"] = ""
        if endpoint.style == "ollama":
            result["runtime"], result["state"], result["confidence"] = "ollama", READY, "strong"
            result["evidence"] = "/api/tags returned an Ollama tags response"
            return result
        try:
            state = introspect(endpoint.provider_id, _origin_url(url), credential, timeout=timeout, http=get)
        except ProbeError:
            state = None
        if state is None or not state.reachable:
            result["state"] = UNKNOWN
            result["runtime"] = "unknown"
            result["confidence"] = "weak"
            result["evidence"] = "/v1/models answered but native introspection failed"
            return result
        _merge_state(result, state)
        return result
    return result


def probe_local_services(*, timeout: float = DEFAULT_TIMEOUT, endpoints: Iterable[LocalEndpoint] = ENDPOINTS,
                         get: Callable[..., Any] = _http_get,
                         credential_for: Optional[Callable[[str, str], str]] = None) -> dict[str, dict[str, Any]]:
    """Probe the known loopback endpoints in order; a per-service failure never fails the whole check."""
    out: dict[str, dict[str, Any]] = {}
    for endpoint in endpoints:
        out[endpoint.provider_id] = probe_service(endpoint, timeout=timeout, get=get,
                                                  credential_for=credential_for)
    return out


def services_json(probed: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [probed[key] for key in sorted(probed, key=lambda item: probed[item]["title"].lower())]
