"""An httpx transport that connects to the address the policy approved, and to nothing else.

Checking a name and then letting the HTTP stack look it up again leaves a window in which the answer can change
(DNS rebinding). Here the name is resolved once per request, every answer is judged by ``endpoint_policy.vet``, and
the connection is made to that validated numeric address. The ``Host`` header and the TLS server name stay the
original name, so certificates are still verified against the name the person typed.

Three further rules are enforced at the same point, where a refusal cannot be bypassed by an adapter:

* plain HTTP goes only to a loopback or private address;
* a credential header never travels over plain HTTP to anything but loopback;
* redirects are not followed here (the adapters already refuse a 3xx; see ``connection_endpoints.redirect_refusal``).

When an environment proxy applies to the URL the proxy resolves the name, so the address cannot be pinned; the
literal-address checks still run and the layered connectivity test says so.
"""

from __future__ import annotations

import functools
import urllib.request
from typing import Any, Optional
from urllib.parse import urlsplit

from .endpoint_policy import LOOPBACK, PRIVATE, EndpointRefused, literal_ip, vet

#: request headers that carry a credential
CREDENTIAL_HEADERS = ("authorization", "x-api-key", "api-key", "x-goog-api-key")


@functools.lru_cache(maxsize=1)
def vendor_hosts() -> frozenset[str]:
    """Hosts a connection template or built-in route declares itself: the name rule does not apply to them."""
    from ..connections import load_templates
    from .openai_compat import PRESET_URLS
    urls = [PRESET_URLS.get(name, "") for name in PRESET_URLS]
    for row in load_templates().values():
        urls += [str(row.get(field) or "") for field in ("base_url", "anthropic_base_url", "models_base_url")]
    return frozenset((urlsplit(u).hostname or "").lower() for u in urls if u)


def proxied(url: str) -> bool:
    """Whether an environment proxy would carry this URL (so the destination address is the proxy's business)."""
    parts = urlsplit(url)
    proxy = urllib.request.getproxies().get(parts.scheme)
    return bool(proxy) and not urllib.request.proxy_bypass_environment(parts.hostname or "")


def refuse_unsafe_transport(scheme: str, kind: str, headers: Any) -> None:
    if scheme == "http" and kind not in (LOOPBACK, PRIVATE):
        raise EndpointRefused("plain HTTP is only allowed to a loopback or private address; use https for a "
                              "public host")
    if scheme == "http" and kind != LOOPBACK and any(name in headers for name in CREDENTIAL_HEADERS):
        raise EndpointRefused("this request carries a credential and the endpoint is plain HTTP off this computer; "
                              "a key is never sent in clear text. Use https, or remove the key for a server "
                              "that does not need one")


class PinnedTransport:
    """``httpx.BaseTransport`` wrapper (duck-typed so importing this module does not import httpx)."""

    def __init__(self, *, inner: Any = None, resolver: Any = None, env: Optional[dict] = None,
                 vendor: Optional[frozenset[str]] = None):
        import httpx
        self._inner = inner or httpx.HTTPTransport(trust_env=True)   # honors SSL_CERT_FILE; no env proxies here
        self._resolver, self._env, self._vendor = resolver, env, vendor

    def handle_request(self, request: Any) -> Any:
        import httpx
        url = request.url
        port = url.port or (443 if url.scheme == "https" else 80)
        vendor = self._vendor if self._vendor is not None else vendor_hosts()
        vetted = vet(url.host, port, resolver=self._resolver, vendor=url.host.lower() in vendor, env=self._env)
        extensions = dict(request.extensions)
        if url.scheme == "https" and literal_ip(url.host) is None:
            extensions["sni_hostname"] = url.host
        failure: Optional[Exception] = None
        for ip, kind in vetted:                       # the resolver's order, as a dual-stack client would try it
            refuse_unsafe_transport(url.scheme, kind, request.headers)
            pinned = httpx.Request(request.method, url.copy_with(host=ip), headers=request.headers,
                                   stream=request.stream, extensions=extensions)
            try:
                return self._inner.handle_request(pinned)
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:   # only a failed connect tries the next address
                failure = exc
        raise failure  # type: ignore[misc]  # vet() never returns an empty list

    def close(self) -> None:
        self._inner.close()

    def __enter__(self) -> "PinnedTransport":          # httpx.Client enters and exits its transport
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()


def guarded_options(base_url: str) -> tuple[str, Any, bool]:
    """``(base_url, transport, trust_env)`` for a client talking to a user-supplied model endpoint."""
    parts = urlsplit(base_url)
    if proxied(base_url):
        if parts.hostname and literal_ip(parts.hostname) is not None:
            vet(parts.hostname, parts.port or 80)       # a literal blocked address is refused even via a proxy
        return base_url, None, True
    return base_url, PinnedTransport(), True
