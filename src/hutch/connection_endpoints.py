"""Validation of the URLs a connection declares.

Kept out of ``connections.py`` so that module stays a store rather than a URL validator, and so the
rules below can be read and tested on their own. Two rules matter for safety:

* a connection endpoint may never embed credentials (a key is a reference, never part of a URL);
* plain HTTP is allowed only for a loopback service, because a hosted endpoint over plain HTTP would
  put the bearer key on the wire.
"""

from __future__ import annotations

import ipaddress
from typing import Any
from urllib.parse import urlsplit

#: Fields a connection may declare a URL in. ``models_base_url`` is separate from the chat base because
#: some plans publish their model catalogue on a different path (OpenCode Go: chat under
#: ``/inference/go/openai/v1``, catalogue under ``/inference/go/v1``).
ENDPOINT_FIELDS = ("base_url", "anthropic_base_url", "models_base_url")


def _parts(endpoint: str):
    try:
        parts = urlsplit(endpoint)
        if parts.username is not None or parts.password is not None:
            raise ValueError("connection endpoints cannot embed credentials; use a key reference")
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError:
        raise ValueError("connection endpoint is malformed or contains embedded credentials") from None
    return parts, host, port


def validate_endpoints(merged: dict[str, Any]) -> None:
    """Refuse a malformed, credential-bearing or non-loopback plain-HTTP endpoint."""
    for field_name in ENDPOINT_FIELDS:
        endpoint = merged.get(field_name)
        if not endpoint:
            continue
        if endpoint.strip().rstrip("/") in ("http:", "https:"):      # a template whose host belongs to the user
            raise ValueError(f"{merged.get('title', 'this template')} has no default host: give your own endpoint "
                             "(--base-url, or the endpoint field in the form)")
        parts, host, port = _parts(endpoint)
        if (parts.scheme not in {"http", "https"} or not host or parts.query or parts.fragment or
                (port is not None and not 1 <= port <= 65535) or "%" in host):
            raise ValueError("connection endpoint must be an absolute HTTP(S) URL without query or fragment")
        from .providers.endpoint_policy import literal_refusal
        refusal = literal_refusal(host)
        if refusal:
            raise ValueError(refusal)
        if parts.scheme == "http":
            try:
                loopback = ipaddress.ip_address(host).is_loopback
            except ValueError:
                loopback = host == "localhost"
            if not loopback:
                raise ValueError("connection endpoints must use HTTPS except for a loopback HTTP service")


#: API paths a person pastes from a curl example; the root is what a connection stores. Anthropic's SDK appends
#: ``/v1/messages`` itself, so its pasted path is removed whole.
_PASTED_API_PATHS = ("/v1/messages", "/chat/completions", "/completions", "/models", "/responses")


def normalize_base(url: str) -> str:
    """The endpoint root: no trailing slash (``/v1/`` made some servers answer ``GET /v1//models`` 404) and no pasted
    API path. Nothing is added: whether a server wants ``/v1`` is something the connectivity test can tell."""
    cleaned = str(url or "").strip().rstrip("/")
    for path in _PASTED_API_PATHS:
        if cleaned.lower().endswith(path):
            return cleaned[: -len(path)].rstrip("/")
    return cleaned


def origin(url: str) -> tuple[str, str, int | None]:
    """(scheme, host, port) for a validated endpoint."""
    parts, host, port = _parts(url)
    return parts.scheme, host, port


def models_base(merged: dict[str, Any]) -> str:
    """The catalogue base URL, only when it belongs to the same service as ``base_url``.

    A template ships ``models_base_url`` for its own host. If a caller points ``base_url`` somewhere else,
    keeping the template's catalogue URL would send discovery to a different service than chat - and, in a
    test, to the vendor's real host instead of the local fake. In that case the catalogue falls back to the
    chat base, which is the ordinary layout.
    """
    declared = str(merged.get("models_base_url") or "").rstrip("/")
    if not declared:
        return ""
    base = str(merged.get("base_url") or "")
    if not base or origin(declared) != origin(base):
        return ""
    return declared


def redirect_refusal(provider_name: str, location: str | None) -> Exception:
    """The error for a 3xx answer: the configured URL is not the endpoint that serves the requests.

    Nothing here follows a redirect, deliberately - the bearer key would travel to whatever host the
    ``Location`` names, which is exactly the credential move the endpoint rules exist to prevent.
    """
    from .providers.base import ProviderError

    return ProviderError(
        "bad_request",
        f"{provider_name} answered with a redirect to {location or 'another URL'}. Hutch does not follow "
        "endpoint redirects, because that would send this connection's key to a different host. Set the "
        "connection endpoint to the final URL instead.",
        provider=provider_name, status=302)
