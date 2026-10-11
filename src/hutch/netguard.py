"""Network egress guard: may this URL be fetched, and if so, to which address?

The old check matched a host *string* against a regex. That misses every address spelling the operating system accepts
(``[::1]``, ``0x7f.0.0.1``, ``2130706433``, IPv4-mapped IPv6, 6to4/NAT64 embeddings), every public name that resolves to a
private address, and every redirect. This module decides on **addresses**, not spellings:

* ``screen_url``   syntax only, no network: scheme, credentials, blocked names, and every IP-literal spelling.
* ``resolve_public`` resolves the name and requires **every** answer to be a public address.
* ``safe_get``     fetches with the connection pinned to the validated address (no second lookup, so DNS rebinding has nothing to
                   flip), follows redirects itself and re-checks every hop, and bounds the body.

Browser requests need more than ``RequestGuard``: that route check refuses unsafe URLs early, while ``PinnedBrowserProxy``
independently resolves and connects to a validated numeric address for HTTP(S) and WebSocket traffic. The proxy must remain
enabled; route interception alone cannot prevent DNS rebinding. A locally configured model endpoint is an explicit exception
made by a *connection*, never by URL pattern.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from urllib.parse import urljoin, urlsplit

MAX_REDIRECTS = 5
DEFAULT_MAX_BYTES = 2_000_000

#: names that are never public, whatever the resolver says (also stops a hostile local resolver config from helping)
_BLOCKED_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback", "metadata", "metadata.google.internal",
                  "instance-data", "kubernetes.default", "kubernetes.default.svc"}
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".localdomain", ".home.arpa", ".lan", ".intranet", ".corp", ".svc",
                     ".cluster.local")
_NUMERIC_HOST = re.compile(r"^[0-9a-fA-FxX.]+$")


class NetGuardError(Exception):
    """The destination is not allowed (or could not be established safely)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


# ------------------------------------------------------------------ addresses


def blocked_ip_reason(ip: "ipaddress.IPv4Address | ipaddress.IPv6Address | str") -> Optional[str]:
    """None if ``ip`` is a public unicast address; otherwise why it is refused. Embedded IPv4 is unwrapped."""
    try:
        addr = ipaddress.ip_address(ip) if isinstance(ip, str) else ip
    except ValueError:
        return f"{ip!r} is not an IP address"
    if isinstance(addr, ipaddress.IPv6Address):
        if addr.ipv4_mapped is not None:
            return blocked_ip_reason(addr.ipv4_mapped)
        raw = addr.packed
        if addr in ipaddress.ip_network("64:ff9b::/96"):                       # NAT64: IPv4 in the low 32 bits
            return blocked_ip_reason(ipaddress.IPv4Address(raw[-4:]))
        if addr in ipaddress.ip_network("2002::/16"):                          # 6to4: IPv4 in bits 16..48
            return blocked_ip_reason(ipaddress.IPv4Address(raw[2:6]))
        if addr in ipaddress.ip_network("2001::/32"):                          # Teredo: tunnelled, unverifiable
            return f"{addr} is a Teredo tunnel address"
        if addr in ipaddress.ip_network("fec0::/10"):                          # deprecated site-local
            return f"{addr} is a site-local address"
    if addr.is_multicast:
        return f"{addr} is a multicast address"
    if not addr.is_global:
        return f"{addr} is not a public address (private, loopback, link-local, shared or reserved range)"
    return None


def _literal_ip(host: str) -> Optional["ipaddress.IPv4Address | ipaddress.IPv6Address"]:
    """The address a host *spelling* means, including the legacy IPv4 forms libc accepts (decimal, hex, octal, short)."""
    h = host.strip("[]")
    try:
        return ipaddress.ip_address(h)
    except ValueError:
        pass
    if ":" in h:
        return None
    if _NUMERIC_HOST.match(h) and re.search(r"[0-9]", h):
        try:
            return ipaddress.IPv4Address(socket.inet_aton(h))
        except (OSError, ValueError):
            return None
    return None


# ------------------------------------------------------------------ syntax screen


def screen_url(url: str) -> Optional[str]:
    """Why ``url`` must not be fetched, judged without touching the network. None means "not refused by syntax"."""
    if not isinstance(url, str) or not url.strip():
        return "empty URL"
    try:
        parts = urlsplit(url.strip())
        host = parts.hostname
        _ = parts.port                                       # raises ValueError on a bad port
    except ValueError:
        return "malformed URL"
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        return f"scheme '{scheme or '(none)'}' is not allowed (http/https only)"
    if not host:
        return "URL has no host"
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        return "credentials in a URL are not allowed"
    host = host.lower().rstrip(".")
    if not host:
        return "URL has no host"
    literal = _literal_ip(host)
    if literal is not None:
        reason = blocked_ip_reason(literal)
        return f"targeting a non-public address: {reason}" if reason else None
    if host in _BLOCKED_NAMES or host.endswith(_BLOCKED_SUFFIXES):
        return f"'{host}' is an internal name"
    try:
        host.encode("idna")
    except UnicodeError:
        return "host is not a valid name"
    return None


def display_url_origin(url: str) -> str:
    """Return a log-safe origin label without paths, query strings, fragments or user information."""
    try:
        parts = urlsplit(url.strip())
        host = parts.hostname
        port = parts.port
    except (AttributeError, TypeError, ValueError):
        return "<invalid URL>"
    if not host:
        return "<invalid URL>"
    host = host.lower().rstrip(".")
    if ":" in host:
        host = f"[{host}]"
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https", "ws", "wss"}:
        scheme = "request"
    return f"{scheme}://{host}" + (f":{port}" if port is not None else "")


# ------------------------------------------------------------------ resolution


def resolve_public(host: str, port: int, resolver: Optional[Callable[..., list]] = None) -> list[str]:
    """Resolve ``host`` and require EVERY answer to be public. Returns the validated addresses in resolver order."""
    resolver = resolver or socket.getaddrinfo
    host = host.rstrip(".")
    literal = _literal_ip(host)
    if literal is not None:
        reason = blocked_ip_reason(literal)
        if reason:
            raise NetGuardError(f"targeting a non-public address: {reason}")
        return [str(literal)]
    try:
        infos = resolver(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, OSError) as exc:
        raise NetGuardError(f"'{host}' does not resolve: {exc}") from exc
    ips: list[str] = []
    for info in infos:
        addr = str(info[4][0]).split("%", 1)[0]
        reason = blocked_ip_reason(addr)
        if reason:
            raise NetGuardError(f"'{host}' resolves to a non-public address ({reason})")
        if addr not in ips:
            ips.append(addr)
    if not ips:
        raise NetGuardError(f"'{host}' does not resolve")
    return ips


# ------------------------------------------------------------------ fetch


@dataclass
class Fetched:
    status: int
    reason: str
    headers: dict[str, str]
    text: str
    url: str
    redirects: list[str] = field(default_factory=list)
    truncated: bool = False
    address: str = ""
    #: the raw, already size-bounded response body (b"\0" default keeps test fixtures that
    #: construct Fetched by hand working); media acquisition needs bytes, not decoded text
    body: bytes = b""

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


def _httpx():
    import httpx
    return httpx


def _decode(body: bytes, content_type: str) -> str:
    m = re.search(r"charset=([\w-]+)", content_type or "", re.IGNORECASE)
    for enc in ([m.group(1)] if m else []) + ["utf-8"]:
        try:
            return body.decode(enc, "replace")
        except LookupError:
            continue
    return body.decode("utf-8", "replace")


def safe_get(url: str, *, timeout: float = 20.0, max_redirects: int = MAX_REDIRECTS, max_bytes: int = DEFAULT_MAX_BYTES,
             headers: Optional[dict[str, str]] = None, resolver: Optional[Callable[..., list]] = None,
             transport: Any = None) -> Fetched:
    """GET ``url`` with every hop validated and the connection pinned to the validated address.

    ``resolver`` and ``transport`` exist so tests can supply a fake DNS and an in-memory server.
    """
    httpx = _httpx()
    current, redirects = url.strip(), []
    for _hop in range(max_redirects + 1):
        reason = screen_url(current)
        if reason:
            raise NetGuardError(reason)
        parts = urlsplit(current)
        https = parts.scheme.lower() == "https"
        host = (parts.hostname or "").rstrip(".")
        port = parts.port or (443 if https else 80)
        ip = resolve_public(host, port, resolver)[0]
        netloc = f"[{ip}]:{port}" if ":" in ip else f"{ip}:{port}"
        pinned = parts._replace(netloc=netloc).geturl()
        default_port = (port == (443 if https else 80))
        hdrs = {"Host": host if default_port else f"{host}:{port}", **(headers or {})}
        ext = {"sni_hostname": host} if https and not _literal_ip(host) else {}
        body, truncated = b"", False
        with httpx.Client(transport=transport or httpx.HTTPTransport(), timeout=timeout, follow_redirects=False) as client:
            with client.stream("GET", pinned, headers=hdrs, extensions=ext) as resp:
                status, reason_phrase, rheaders = resp.status_code, resp.reason_phrase, dict(resp.headers)
                if status in (301, 302, 303, 307, 308) and rheaders.get("location"):
                    nxt = urljoin(current, rheaders["location"])
                else:
                    nxt = ""
                    for chunk in resp.iter_bytes():
                        body += chunk
                        if len(body) >= max_bytes:
                            body, truncated = body[:max_bytes], True
                            break
        if nxt:
            redirects.append(nxt)
            current = nxt
            continue
        return Fetched(status=status, reason=reason_phrase, headers=rheaders,
                       text=_decode(body, rheaders.get("content-type", "")), url=current,
                       redirects=redirects, truncated=truncated, address=ip, body=body)
    raise NetGuardError(f"too many redirects (more than {max_redirects})")


# ------------------------------------------------------------------ per-request guard (browser)


class RequestGuard:
    """Judge every request a browser makes (navigations, redirects, sub-resources, XHR) by the same rules.

    This is an early browser URL check, not an egress boundary by itself. The default Hutch browser also uses
    ``PinnedBrowserProxy``, which independently resolves and pins every HTTP(S)/WebSocket connection. Decisions here are cached
    briefly for navigation policy; never remove the proxy and rely on this route check alone.
    """

    def __init__(self, resolver: Optional[Callable[..., list]] = None, ttl: float = 30.0,
                 clock: Callable[[], float] | None = None):
        import time
        self._resolver, self._ttl, self._clock = resolver, ttl, clock or time.monotonic
        self._cache: dict[tuple[str, int], tuple[float, Optional[str]]] = {}

    def check(self, url: str) -> Optional[str]:
        """None if the request may proceed, else the reason it is blocked."""
        if url.startswith(("data:", "blob:", "about:", "chrome-error:")):
            return None                                   # no network involved
        reason = screen_url(url)
        if reason:
            return reason
        parts = urlsplit(url)
        host = (parts.hostname or "").rstrip(".")
        port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
        now = self._clock()
        hit = self._cache.get((host, port))
        if hit and now - hit[0] < self._ttl:
            return hit[1]
        try:
            resolve_public(host, port, self._resolver)
            verdict: Optional[str] = None
        except NetGuardError as exc:
            verdict = exc.reason
        if len(self._cache) > 512:
            self._cache.clear()
        self._cache[(host, port)] = (now, verdict)
        return verdict

    def route_handler(self, on_block: Optional[Callable[[str, str], None]] = None):
        """A Playwright ``context.route("**/*", handler)`` callback."""
        def handle(route, request):
            reason = self.check(request.url)
            if reason is None:
                route.continue_()
                return
            if on_block:
                on_block(request.url, reason)
            route.abort("blockedbyclient")
        return handle
