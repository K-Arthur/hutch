"""Pinned egress for MCP endpoints (ADR-0017 §8.1).

A connector endpoint is owner-supplied, so it is hostile input until proven otherwise. Hutch's
existing ``netguard`` screens a URL and its addresses; this module adds the part ``netguard``
cannot express: the address that was *screened* must be the address actually dialled.

The mechanism is a per-request context variable. ``handle_async_request`` resolves the hostname,
checks every returned address against the egress policy, selects one, and pins it for the
duration of that request. The network backend refuses any connection that was not pinned, so a
rebinding DNS answer between the check and the connect cannot redirect the request. Each origin
keeps its own connection pool, so two hostnames sharing an address cannot share an HTTP/2
connection.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Optional
from urllib.parse import urlsplit

import httpx2

from ...netguard import blocked_ip_reason, screen_url

_LOCAL_NAMES = {"localhost", "localhost.localdomain"}


class McpEndpointError(ValueError):
    """An MCP endpoint is outside the local egress policy."""


def is_local_host(host: str) -> bool:
    """True for loopback names and addresses, which may be spoken to in plaintext."""
    if host.casefold().rstrip(".") in _LOCAL_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _resolve(host: str, port: int, resolver: Optional[Callable[..., list]] = None) -> list[str]:
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        try:
            infos = (resolver or socket.getaddrinfo)(host, port, type=socket.SOCK_STREAM)
        except (OSError, socket.gaierror) as exc:
            raise McpEndpointError("MCP destination could not be resolved") from exc
        addresses = list(dict.fromkeys(str(info[4][0]).split("%", 1)[0] for info in infos))
    else:
        addresses = [str(literal)]
    if not addresses:
        raise McpEndpointError("MCP destination did not resolve")
    return addresses


class PinnedNetworkBackend:
    """Dial only the address the request screened, while keeping the hostname for TLS and Host."""

    def __init__(self, host: str, port: int, delegate=None):
        if delegate is None:
            from httpcore2._backends.auto import AutoBackend
            delegate = AutoBackend()
        self.host, self.port, self.delegate = host, port, delegate
        self._address: ContextVar[Optional[str]] = ContextVar(f"hutch_mcp_ip_{id(self)}", default=None)

    @contextmanager
    def pin(self, address: str):
        token: Token = self._address.set(address)
        try:
            yield
        finally:
            self._address.reset(token)

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        address = self._address.get()
        if not address or host.casefold().rstrip(".") != self.host or port != self.port:
            raise McpEndpointError("MCP transport attempted an unpinned network connection")
        return await self.delegate.connect_tcp(address, port, timeout=timeout,
                                               local_address=local_address,
                                               socket_options=socket_options)

    async def connect_unix_socket(self, path, socket_options=None):
        raise McpEndpointError("MCP network connections cannot use Unix sockets")

    async def sleep(self, seconds):
        return await self.delegate.sleep(seconds)


class PinnedMcpHTTPTransport(httpx2.AsyncBaseTransport):
    """Screen every MCP request (including redirects) and pin the address it was cleared for."""

    def __init__(self, *, resolver: Optional[Callable[..., list]] = None,
                 transport_factory: Optional[Callable[[], httpx2.AsyncBaseTransport]] = None,
                 allowed_local_origins: tuple[str, ...] = ()):
        self.resolver = resolver
        self.transport_factory = transport_factory or (lambda: httpx2.AsyncHTTPTransport(trust_env=False))
        self.transports: dict[tuple[str, str, int], tuple[httpx2.AsyncBaseTransport, PinnedNetworkBackend]] = {}
        self.allowed_local_origins = frozenset(_origin_tuple(url) for url in allowed_local_origins)

    async def handle_async_request(self, request):
        try:
            parts = urlsplit(str(request.url))
            host = (parts.hostname or "").lower().rstrip(".")
            port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
        except ValueError:
            raise McpEndpointError("MCP request destination is malformed") from None
        scheme = parts.scheme.lower()
        if not host or scheme not in {"http", "https"}:
            raise McpEndpointError("MCP request destination must use HTTP or HTTPS")
        addresses = _resolve(host, port, self.resolver)
        if is_local_host(host):
            if (scheme, host, port) not in self.allowed_local_origins:
                raise McpEndpointError(
                    "local MCP destinations must match the explicitly reviewed endpoint")
            if any(not ipaddress.ip_address(address).is_loopback for address in addresses):
                raise McpEndpointError("Local MCP destinations must resolve only to loopback addresses")
        elif (scheme != "https" or screen_url(str(request.url))
              or any(blocked_ip_reason(address) for address in addresses)):
            raise McpEndpointError("MCP request destination is not an allowed public HTTPS address")
        address = addresses[0]
        origin = (scheme, host, port)
        pair = self.transports.get(origin)
        if pair is None:
            backend = PinnedNetworkBackend(host, port)
            transport = self.transport_factory()
            pool = getattr(transport, "_pool", None)
            if pool is not None and hasattr(pool, "_network_backend"):
                pool._network_backend = backend
            self.transports[origin] = (transport, backend)
        else:
            transport, backend = pair
        default_port = (scheme, port) in {("http", 80), ("https", 443)}
        host_header = f"[{host}]" if ":" in host else host
        request.headers["Host"] = host_header if default_port else f"{host_header}:{port}"
        with backend.pin(address):
            return await transport.handle_async_request(request)

    async def aclose(self):
        transports, self.transports = list(self.transports.values()), {}
        for transport, _backend in transports:
            await transport.aclose()


def _origin_tuple(url: str) -> tuple[str, str, int]:
    try:
        parts = urlsplit(url)
        scheme, host = parts.scheme.lower(), (parts.hostname or "").lower().rstrip(".")
        port = parts.port or (443 if scheme == "https" else 80)
    except (AttributeError, TypeError, ValueError):
        raise McpEndpointError("reviewed endpoint URL is malformed") from None
    return scheme, host, port


def validate_mcp_endpoint(url: str, *, resolver: Optional[Callable[..., list]] = None) -> str:
    """Validate a saved endpoint; plaintext HTTP is limited to explicitly local loopback."""
    if not isinstance(url, str) or not url.strip():
        raise McpEndpointError("Enter an MCP endpoint URL")
    try:
        parts = urlsplit(url.strip())
        host = parts.hostname
        port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
    except ValueError:
        raise McpEndpointError("MCP endpoint URL is malformed") from None
    if (parts.scheme.lower() not in {"http", "https"} or not host or parts.username is not None
            or parts.password is not None or parts.query or parts.fragment):
        raise McpEndpointError("MCP endpoint must be an HTTP(S) URL without credentials, query, or fragment")
    host = host.lower().rstrip(".")
    if not 1 <= port <= 65535:
        raise McpEndpointError("MCP endpoint port is invalid")
    addresses = _resolve(host, port, resolver)
    if is_local_host(host):
        if any(not ipaddress.ip_address(address).is_loopback for address in addresses):
            raise McpEndpointError("Local MCP endpoints must resolve only to loopback addresses")
    else:
        if parts.scheme.lower() != "https":
            raise McpEndpointError("Remote MCP endpoints require HTTPS")
        if screen_url(url.strip()):
            raise McpEndpointError("MCP endpoint URL uses a blocked host or address")
        if any(blocked_ip_reason(address) for address in addresses):
            raise McpEndpointError("MCP endpoint resolves to a private or reserved network address")
    return url.strip()


__all__ = ["McpEndpointError", "PinnedMcpHTTPTransport", "is_local_host", "validate_mcp_endpoint"]
