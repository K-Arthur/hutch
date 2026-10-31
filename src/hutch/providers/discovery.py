"""Local inference discovery over known loopback endpoints only.

Discovery is deliberately narrow: fixed loopback endpoints, plain HTTP, no credential header, no
redirects, a short timeout and a bounded body. It answers "is a local model server answering, and which
models does it list?" - it never claims that a model works, and it never sends a provider key.

URLs supplied by callers are re-validated as loopback; an arbitrary URL is refused before any request.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
MAX_RESPONSE_BYTES = 256 * 1024
MAX_MODELS = 500


@dataclass(frozen=True)
class LocalEndpoint:
    provider_id: str
    title: str
    url: str
    style: str  # "ollama" | "openai"


ENDPOINTS: tuple[LocalEndpoint, ...] = (
    LocalEndpoint("ollama", "Ollama", "http://127.0.0.1:11434/api/tags", "ollama"),
    LocalEndpoint("lmstudio", "LM Studio", "http://127.0.0.1:1234/v1/models", "openai"),
    LocalEndpoint("vllm", "vLLM", "http://127.0.0.1:8000/v1/models", "openai"),
    LocalEndpoint("sglang", "SGLang", "http://127.0.0.1:30000/v1/models", "openai"),
    LocalEndpoint("llamacpp", "llama.cpp", "http://127.0.0.1:8080/v1/models", "openai"),
)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect from a loopback service could leave the machine; refuse it instead."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401 - stdlib signature
        return None


def verified_loopback_url(url: str) -> str:
    """Return the URL only when it is plain HTTP to an exact loopback host without embedded credentials."""
    try:
        parts = urlsplit(str(url))
    except ValueError:
        raise ValueError("local endpoint is not a valid URL") from None
    if parts.scheme != "http":
        raise ValueError("local discovery endpoints must use plain HTTP")
    if not parts.hostname or parts.hostname.lower() not in LOOPBACK_HOSTS:
        raise ValueError("local discovery endpoints must use an exact loopback host")
    if parts.username is not None or parts.password is not None:
        raise ValueError("local discovery endpoints must not embed credentials")
    if parts.fragment:
        raise ValueError("local discovery endpoints must not carry a fragment")
    return url


def _http_get(url: str, timeout: float) -> bytes:
    opener = urllib.request.build_opener(_NoRedirect)
    request = urllib.request.Request(url, headers={"Accept": "application/json",
                                                  "User-Agent": "hutch/local-discovery"})
    with opener.open(request, timeout=timeout) as response:  # no credential header is ever added
        body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError("local discovery response exceeds the size limit")
    return body


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


def probe_service(endpoint: LocalEndpoint, *, timeout: float = 0.5,
                  get: Callable[[str, float], bytes] = _http_get) -> dict[str, Any]:
    """Probe one fixed local endpoint. Returns reachable/models/error; never raises for a dead service."""
    verified_loopback_url(endpoint.url)
    result: dict[str, Any] = {"provider": endpoint.provider_id, "title": endpoint.title,
                              "url": endpoint.url, "reachable": False, "models": [], "error": ""}
    try:
        body = get(endpoint.url, timeout)
        payload = json.loads(body.decode("utf-8", "replace"))
        result["models"] = parse_models(endpoint.style, payload)
        result["reachable"] = True
    except urllib.error.URLError:
        result["error"] = "no service answered"
    except (TimeoutError, OSError):
        result["error"] = "no service answered"
    except (ValueError, UnicodeError):
        result["error"] = "the service answered but not with a model list"
    return result


def probe_local_services(*, timeout: float = 0.5, endpoints: Iterable[LocalEndpoint] = ENDPOINTS,
                         get: Callable[[str, float], bytes] = _http_get) -> dict[str, dict[str, Any]]:
    """Probe the known loopback endpoints in order; a per-service failure never fails the whole check."""
    out: dict[str, dict[str, Any]] = {}
    for endpoint in endpoints:
        out[endpoint.provider_id] = probe_service(endpoint, timeout=timeout, get=get)
    return out


def services_json(probed: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [probed[key] for key in sorted(probed, key=lambda item: probed[item]["title"].lower())]
