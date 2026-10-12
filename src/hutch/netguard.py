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


# ------------------------------------------------------------------ approved local development origins


class LocalOrigins:
    """Exact loopback origins a person approved for local development of a web app.

    This is an *allowance*, not a bypass of the guard: only ``localhost`` / a literal 127.0.0.0/8 address / ``::1`` with an
    explicit port can ever be listed, so a private LAN address, link-local/metadata address or internal DNS name stays
    refused whatever is configured. Each entry is a full ``scheme://host:port`` origin; ``localhost`` is mapped to the
    loopback literals here and is never resolved through DNS. The browser applies a further page-context rule (see
    ``RequestGuard``): public pages cannot load sub-resources from, or redirect into, an approved local origin.
    """

    MAX_ENTRIES = 8

    def __init__(self, entries: "frozenset[tuple[str, str, int]] | None" = None):
        self._entries: frozenset[tuple[str, str, int]] = entries or frozenset()

    @staticmethod
    def _normalise(value: Any) -> tuple[str, str, int]:
        if not isinstance(value, str) or not value.strip() or len(value) > 64:
            raise ValueError("a local development origin must be a short text value such as http://localhost:3000")
        text = value.strip()
        try:
            parts = urlsplit(text)
            port = parts.port
        except ValueError:
            raise ValueError(f"{text!r} is not a valid origin") from None
        scheme = parts.scheme.lower()
        if scheme != "http":
            # https tunnels cannot be inspected by the egress proxy, so request context could not be enforced for them
            raise ValueError("a local development origin must use http (for example http://localhost:3000)")
        if parts.username is not None or parts.password is not None or "@" in parts.netloc:
            raise ValueError("a local development origin cannot contain credentials")
        if parts.path not in ("", "/") or parts.query or parts.fragment:
            raise ValueError("a local development origin is scheme://host:port only (no path, query or fragment)")
        host = (parts.hostname or "").lower()
        if port is None:
            raise ValueError("a local development origin needs an explicit port, e.g. http://localhost:3000")
        if host == "localhost":
            return scheme, host, port
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            literal = None
        if literal is None or not literal.is_loopback or (
                isinstance(literal, ipaddress.IPv6Address) and literal.ipv4_mapped is not None):
            raise ValueError("only localhost or a loopback address (127.0.0.0/8, ::1) can be a local development origin")
        return scheme, str(literal), port

    @classmethod
    def parse(cls, values: Any) -> "LocalOrigins":
        """Validate configuration. Raises ``ValueError`` naming the first bad entry."""
        if values in (None, ""):
            return cls()
        if isinstance(values, str) or not hasattr(values, "__iter__"):
            raise ValueError("local development origins must be a list")
        entries = {cls._normalise(v) for v in values}
        if len(entries) > cls.MAX_ENTRIES:
            raise ValueError(f"at most {cls.MAX_ENTRIES} local development origins can be approved")
        return cls(frozenset(entries))

    @classmethod
    def lenient(cls, values: Any) -> "LocalOrigins":
        """Runtime form: invalid stored entries are dropped (fail closed) rather than failing the run."""
        kept: set[tuple[str, str, int]] = set()
        for value in values if isinstance(values, (list, tuple, set, frozenset)) else ():
            try:
                kept.add(cls._normalise(value))
            except ValueError:
                continue
        return cls(frozenset(sorted(kept)[: cls.MAX_ENTRIES]))

    def __bool__(self) -> bool:
        return bool(self._entries)

    def __iter__(self):
        for scheme, host, port in sorted(self._entries):
            shown = f"[{host}]" if ":" in host else host
            yield f"{scheme}://{shown}:{port}"

    def allows(self, scheme: str, host: str, port: Optional[int]) -> bool:
        host = host.lower().strip("[]").rstrip(".")
        scheme = scheme.lower()
        if port is None:
            port = 443 if scheme == "https" else 80
        return (scheme, host, port) in self._entries

    def allows_url(self, url: str) -> bool:
        try:
            parts = urlsplit(url.strip())
            if parts.username is not None or parts.password is not None:
                return False
            return bool(parts.hostname) and self.allows(parts.scheme, parts.hostname, parts.port)
        except (ValueError, AttributeError):
            return False

    def allows_hostport(self, host: str, port: int) -> bool:
        """For CONNECT tunnels, where the scheme is not visible to the proxy."""
        return any(self.allows(scheme, host, port) for scheme in ("http", "https"))

    def without_ports(self, ports: "set[int]") -> "LocalOrigins":
        """The same approvals minus any origin on one of ``ports`` (used to exclude Hutch's own dashboard)."""
        return LocalOrigins(frozenset(e for e in self._entries if e[2] not in ports))

    def ports(self) -> set[int]:
        return {e[2] for e in self._entries}

    @staticmethod
    def addresses(host: str) -> list[str]:
        """Numeric addresses to connect to for an approved host (never a DNS lookup)."""
        h = host.lower().strip("[]").rstrip(".")
        return ["127.0.0.1", "::1"] if h == "localhost" else [h]


def dashboard_ports() -> "set[int]":
    """Ports on which Hutch's own dashboard may be listening: the default plus the one ``hutch serve`` exported."""
    import os
    ports = {8787}
    exported = os.environ.get("HUTCH_DASHBOARD_PORT", "").strip()
    if exported.isdigit():
        ports.add(int(exported))
    return ports


class LocalAccess:
    """Runtime enforcement state for approved local development origins (shared by the browser tool and egress proxy).

    The proxy is the only layer that sees every connection, including each redirect hop, but a redirect hop of a
    browser-initiated navigation carries the same fetch metadata (``Sec-Fetch-Site: none``, no Referer) as the tool's own
    deliberate navigation. Request context therefore cannot tell them apart; the *tool* can. It opens a short permit for
    exactly the origin it is navigating to (``permit_navigation``) and closes it when the call returns. A request for an
    approved local origin is allowed when it comes from an approved local page (same-origin/same-site, or a Referer/Origin
    that is an approved local origin) or while a permit for that exact origin is open. Everything else, notably a public
    page's sub-resource, link, script navigation or redirect, is refused.
    """

    PERMIT_SECONDS = 45.0

    def __init__(self, origins: Optional[LocalOrigins] = None, clock: Optional[Callable[[], float]] = None):
        import threading
        import time
        self.origins = origins or LocalOrigins()
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._permit: Optional[tuple[tuple[str, str, int], float]] = None

    def permit_navigation(self, url: str) -> bool:
        """Open a permit for the origin of ``url`` if (and only if) it is an approved local origin."""
        if not self.origins.allows_url(url):
            return False
        parts = urlsplit(url.strip())
        key = (parts.scheme.lower(), (parts.hostname or "").lower().strip("[]"), parts.port or 80)
        with self._lock:
            self._permit = (key, self._clock() + self.PERMIT_SECONDS)
        return True

    def clear_permit(self) -> None:
        with self._lock:
            self._permit = None

    def _permitted(self, url: str) -> bool:
        with self._lock:
            permit = self._permit
        if permit is None or self._clock() > permit[1]:
            return False
        parts = urlsplit(url.strip())
        return (parts.scheme.lower(), (parts.hostname or "").lower().strip("[]"), parts.port or 80) == permit[0]

    def refusal(self, url: str, headers: "list[tuple[str, str]]") -> Optional[str]:
        """None if a request for ``url`` may proceed from this context, else why not. Non-local URLs are not judged here."""
        if not self.origins.allows_url(url):
            return None
        values: dict[str, str] = {}
        for name, value in headers:
            values.setdefault(name.lower(), value.strip())
        if values.get("sec-fetch-site", "").lower() in ("same-origin", "same-site"):
            return None
        for name in ("origin", "referer"):
            value = values.get(name, "")
            if value and value.lower() != "null" and self.origins.allows_url(value):
                return None
        initiated_by_tool = (values.get("sec-fetch-site", "").lower() == "none"
                             and values.get("sec-fetch-mode", "").lower() == "navigate"
                             and values.get("sec-fetch-dest", "").lower() == "document"
                             and not values.get("referer") and not values.get("origin"))
        if initiated_by_tool and self._permitted(url):
            return None
        return ("an approved local development origin is only reachable from the approved local app "
                "or by an explicit navigation to it")


# ------------------------------------------------------------------ syntax screen


def screen_url(url: str, local_origins: Optional[LocalOrigins] = None) -> Optional[str]:
    """Why ``url`` must not be fetched, judged without touching the network. None means "not refused by syntax".

    ``local_origins`` is the person's explicit allowance for local development (see ``LocalOrigins``); anything not exactly
    listed there is judged by the normal rules."""
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
    if local_origins and local_origins.allows(scheme, host, parts.port):
        return None
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
                       redirects=redirects, truncated=truncated, address=ip)
    raise NetGuardError(f"too many redirects (more than {max_redirects})")


# ------------------------------------------------------------------ per-request guard (browser)


class RequestGuard:
    """Judge every request a browser makes (navigations, redirects, sub-resources, XHR) by the same rules.

    This is an early browser URL check, not an egress boundary by itself. The default Hutch browser also uses
    ``PinnedBrowserProxy``, which independently resolves and pins every HTTP(S)/WebSocket connection. Decisions here are cached
    briefly for navigation policy; never remove the proxy and rely on this route check alone.
    """

    def __init__(self, resolver: Optional[Callable[..., list]] = None, ttl: float = 30.0,
                 clock: Callable[[], float] | None = None, local_origins: Optional[LocalOrigins] = None):
        import time
        self._resolver, self._ttl, self._clock = resolver, ttl, clock or time.monotonic
        self._local = local_origins or LocalOrigins()
        self._cache: dict[tuple[str, int], tuple[float, Optional[str]]] = {}

    def check(self, url: str) -> Optional[str]:
        """None if the request may proceed, else the reason it is blocked."""
        if url.startswith(("data:", "blob:", "about:", "chrome-error:")):
            return None                                   # no network involved
        if self._local.allows_url(url):
            return None            # an approved local origin: page context is judged by ``_local_context_refusal``
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

    def _local_context_refusal(self, request) -> Optional[str]:
        """Why a request to an approved local origin must not proceed from *this* page context; None if it may.

        Approving ``http://localhost:3000`` lets the bot work on that app. It must not let any public page the bot happens to
        visit read or poke it, so: sub-resource/frame requests count only when the top-level page is itself an approved local
        origin (or blank). Document navigations are judged at the proxy, which sees redirect hops that route handlers do not.
        Anything that cannot be established fails closed.
        """
        try:
            navigation = request.is_navigation_request()
            try:
                frame = request.frame
            except Exception:
                frame = None              # a popup's first navigation is issued before its frame exists
            if navigation and (frame is None or frame.parent_frame is None):
                # Redirect hops are not routed by Playwright; only the egress proxy sees them (``LocalAccess``).
                return None
            if frame is None:
                return "the page context for a local development origin could not be verified"
            top = frame.page.url or ""
            if top in ("", "about:blank") or self._local.allows_url(top):
                return None
            return "an approved local development origin is only reachable from the approved local app"
        except Exception:
            return "the page context for a local development origin could not be verified"

    def route_handler(self, on_block: Optional[Callable[[str, str], None]] = None):
        """A Playwright ``context.route("**/*", handler)`` callback."""
        def handle(route, request):
            if self._local.allows_url(request.url):
                reason = self._local_context_refusal(request)
            else:
                reason = self.check(request.url)
            if reason is None:
                route.continue_()
                return
            if on_block:
                on_block(request.url, reason)
            route.abort("blockedbyclient")
        return handle
