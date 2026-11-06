"""Which addresses may a model endpoint resolve to? Decided on addresses, never on spellings.

A model endpoint is a place Hutch sends prompts (and sometimes a key). The URL a person typed names a host; what
matters is the address the connection finally reaches. Five kinds, from the address itself:

* ``loopback``  127.0.0.0/8 and ::1.
* ``private``   RFC 1918, IPv6 ULA, and 100.64.0.0/10 (carrier-grade NAT, which tailnets use).
* ``fake_ip``   198.18.0.0/15, the range proxies such as Clash and Surge hand out for names they intercept.
* ``public``    a global unicast address.
* ``blocked``   link-local (cloud metadata lives at 169.254.169.254), unspecified, multicast, reserved,
                documentation and tunnel ranges. Refused for every scheme, always.

A host that is an IP literal is judged as that address. A name must resolve to ``public`` or ``fake_ip`` unless it
is a local-style name (``localhost``, a single label, ``.lan``, ``.local``, ``.ts.net`` ...), is listed in
``HUTCH_PRIVATE_HOSTS``, or is a vendor host a connection template declares. That is the exact-origin allowlist: the
person's own server is trusted by its exact name, and no other name is. See ADR-0034.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from typing import Callable, Optional

from ..netguard import _literal_ip as literal_ip  # same package: one parser for every legacy IPv4 spelling
from .base import ProviderError

LOOPBACK, PRIVATE, FAKE_IP, PUBLIC, BLOCKED = "loopback", "private", "fake_ip", "public", "blocked"
ALLOW_ENV = "HUTCH_PRIVATE_HOSTS"

_PRIVATE_NETS = tuple(ipaddress.ip_network(n) for n in
                      ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "fc00::/7"))
_FAKE_NETS = (ipaddress.ip_network("198.18.0.0/15"),)
_EMBEDDED_V4 = (("64:ff9b::/96", slice(-4, None)), ("2002::/16", slice(2, 6)))   # NAT64, 6to4
_LOCAL_SUFFIXES = (".local", ".lan", ".home.arpa", ".internal", ".localdomain", ".localhost", ".ts.net")
_METADATA_NAMES = frozenset({"metadata", "metadata.google.internal", "instance-data"})
_Resolver = Callable[..., list]


class EndpointRefused(ProviderError):
    """The destination is not allowed. ``layer`` says which check refused it (policy | dns)."""

    def __init__(self, message: str, layer: str = "policy"):
        super().__init__("bad_request", message)
        self.layer = layer


def _unwrap(addr):
    """The IPv4 address hidden inside a mapped, NAT64 or 6to4 IPv6 address, else the address itself."""
    if not isinstance(addr, ipaddress.IPv6Address):
        return addr
    if addr.ipv4_mapped is not None:
        return addr.ipv4_mapped
    for net, part in _EMBEDDED_V4:
        if addr in ipaddress.ip_network(net):
            return ipaddress.IPv4Address(addr.packed[part])
    return addr


def classify_address(ip) -> str:
    """The kind of one address (``blocked`` for anything unparseable)."""
    try:
        addr = _unwrap(ipaddress.ip_address(str(ip).split("%", 1)[0]) if not hasattr(ip, "packed") else ip)
    except ValueError:
        return BLOCKED
    if addr.is_loopback:
        return LOOPBACK
    if addr.is_unspecified or addr.is_multicast or addr.is_link_local:
        return BLOCKED
    if any(addr in net for net in _FAKE_NETS):
        return FAKE_IP
    if any(addr in net for net in _PRIVATE_NETS):
        return PRIVATE
    return PUBLIC if addr.is_global else BLOCKED


def local_style(host: str) -> bool:
    """A name that, by its shape, belongs to the person's own network rather than the public internet."""
    h = host.lower().rstrip(".")
    return h == "localhost" or "." not in h or h.endswith(_LOCAL_SUFFIXES)


def allowed_hosts(env: Optional[dict] = None) -> frozenset[str]:
    """Exact names the person declared as their own private servers (``HUTCH_PRIVATE_HOSTS``, comma separated)."""
    raw = (os.environ if env is None else env).get(ALLOW_ENV, "")
    return frozenset(item.strip().lower().rstrip(".") for item in raw.split(",") if item.strip())


def _addresses(host: str, port: int, resolver: Optional[_Resolver]) -> list[str]:
    literal = literal_ip(host)
    if literal is not None:
        return [str(literal)]
    try:
        infos = (resolver or socket.getaddrinfo)(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, OSError) as exc:
        raise EndpointRefused(f"'{host}' does not resolve ({exc})", "dns") from exc
    found = list(dict.fromkeys(str(info[4][0]).split("%", 1)[0] for info in infos))
    if not found:
        raise EndpointRefused(f"'{host}' does not resolve", "dns")
    return found


def literal_refusal(host: str) -> Optional[str]:
    """Why a host that needs no lookup (an IP literal in any spelling, or a metadata name) is refused, else None."""
    name = host.lower().rstrip(".")
    if name not in _METADATA_NAMES and literal_ip(name) is None:
        return None
    try:
        vet(name, 0)
    except EndpointRefused as exc:
        return str(exc)
    return None


def vet(host: str, port: int, *, resolver: Optional[_Resolver] = None, vendor: bool = False,
        env: Optional[dict] = None) -> list[tuple[str, str]]:
    """Resolve ``host`` and return ``[(address, kind), ...]`` in resolver order, or raise :class:`EndpointRefused`."""
    name = host.lower().rstrip(".")
    if name in _METADATA_NAMES:
        raise EndpointRefused(f"'{host}' is a cloud metadata name and is never a model endpoint")
    vetted = [(ip, classify_address(ip)) for ip in _addresses(name, port, resolver)]
    for ip, kind in vetted:
        if kind == BLOCKED:
            where = ip if name == ip else f"'{host}' resolves to {ip}, which"
            raise EndpointRefused(f"{where} is a link-local, reserved or otherwise blocked address (this range "
                                  "includes cloud metadata services) and is never a model endpoint")
    if literal_ip(name) is not None or vendor or local_style(name) or name in allowed_hosts(env):
        return vetted
    for ip, kind in vetted:
        if kind not in (PUBLIC, FAKE_IP):
            raise EndpointRefused(
                f"'{host}' looks like a public name but resolves to {ip}, a {kind} address. If this is your own "
                f"server, use its address, a local name such as {name.split('.')[0]}.lan, or list it in "
                f"{ALLOW_ENV} (exact names, comma separated)")
    return vetted
