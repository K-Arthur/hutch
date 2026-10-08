"""T-SSRF: no URL form, redirect or DNS answer may reach a private, loopback, link-local or metadata address.

Baseline defect (docs/realignment/baseline.md, "Additional defects"): the old guard matched a host *string* against a regex,
so seven forms of loopback/metadata addresses were allowed and redirects were followed without a second look.
"""

from __future__ import annotations

import httpx
import pytest

from hutch.models import RiskTier
from hutch.netguard import NetGuardError, blocked_ip_reason, display_url_origin, resolve_public, safe_get, screen_url
from hutch.safety import PolicyEngine

# every one of these was ALLOWED by the baseline guard and must now be refused without any network access
HOSTILE = [
    "http://[::1]/",
    "http://user@127.0.0.1/",
    "http://user:pw@example.com/",              # credentials in a URL are a parsing-confusion vector
    "http://2130706433/",                        # decimal
    "http://0x7f.0.0.1/",                        # hex
    "http://0177.0.0.1/",                        # octal
    "http://127.1/",
    "http://[::ffff:127.0.0.1]/",                # IPv4-mapped
    "http://[::ffff:7f00:1]/",
    "http://[64:ff9b::7f00:1]/",                 # NAT64 embedding loopback
    "http://[2002:7f00:1::]/",                   # 6to4 embedding loopback
    "http://metadata.google.internal/",
    "http://localhost./",                        # trailing dot
    "http://LOCALHOST/",
    "http://foo.localhost/",
    "http://printer.local/",
    "http://169.254.169.254/latest/meta-data",
    "http://[fd00:ec2::254]/",                   # AWS IPv6 metadata (unique-local)
    "http://100.100.100.200/",                   # Alibaba metadata (CGNAT range)
    "http://10.0.0.5:8080/",
    "http://192.168.1.1/",
    "http://172.16.0.1/",
    "http://0.0.0.0/",
    "http://[::]/",
    "http://224.0.0.1/",
    "file:///etc/passwd",
    "ftp://example.com/",
    "gopher://example.com/",
    "javascript:alert(1)",
    "http:///nohost",
    "",
]


def test_denial_log_origin_redacts_userinfo_path_query_and_fragment():
    assert display_url_origin("https://user:secret@example.com/private?token=abc#frag") == "https://example.com"
    assert display_url_origin("http://[2001:4860:4860::8888]:8080/private") == "http://[2001:4860:4860::8888]:8080"
    assert display_url_origin("not a URL") == "<invalid URL>"

PUBLIC = ["https://example.com/page", "http://example.com", "https://sub.example.co.uk:8443/x?y=1", "http://93.184.216.34/"]


@pytest.mark.parametrize("url", HOSTILE)
def test_hostile_urls_are_refused_before_any_lookup(url):
    assert screen_url(url), f"{url!r} should have been refused"


@pytest.mark.parametrize("url", PUBLIC)
def test_ordinary_public_urls_pass_the_syntax_screen(url):
    assert screen_url(url) is None


@pytest.mark.parametrize("url", HOSTILE)
def test_policy_engine_check_url_agrees(url):
    assert PolicyEngine(RiskTier.supervised, []).check_url(url).verdict.value == "deny"


def test_policy_engine_allows_public_urls():
    p = PolicyEngine(RiskTier.supervised, [])
    for url in PUBLIC:
        assert p.check_url(url).verdict.value == "allow"


@pytest.mark.parametrize("ip", ["8.8.8.8", "93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"])
def test_global_addresses_are_allowed(ip):
    assert blocked_ip_reason(ip) is None


@pytest.mark.parametrize("ip", ["127.0.0.1", "::1", "10.1.2.3", "172.31.255.255", "192.168.0.1", "169.254.169.254",
                                "100.64.0.1", "192.0.0.1", "198.18.0.1", "240.0.0.1", "255.255.255.255", "0.0.0.0",
                                "fe80::1", "fc00::1", "fec0::1", "::ffff:10.0.0.1", "ff02::1", "2001::1"])
def test_non_public_addresses_are_refused(ip):
    assert blocked_ip_reason(ip)


def _resolver(mapping):
    def resolve(host, port, *a, **kw):
        ips = mapping[host] if isinstance(mapping, dict) else mapping(host)
        return [(2 if ":" not in ip else 10, 1, 6, "", (ip, port)) for ip in ips]
    return resolve


def test_a_public_name_that_resolves_to_loopback_is_refused():
    r = _resolver({"localtest.me": ["127.0.0.1"]})
    with pytest.raises(NetGuardError, match="resolves to"):
        resolve_public("localtest.me", 80, r)


def test_every_dns_answer_must_be_public_not_just_the_first():
    r = _resolver({"mixed.example": ["93.184.216.34", "10.0.0.7"]})
    with pytest.raises(NetGuardError):
        resolve_public("mixed.example", 80, r)


def test_unresolvable_names_are_refused():
    def boom(*a, **k):
        import socket
        raise socket.gaierror("no such host")
    with pytest.raises(NetGuardError, match="does not resolve"):
        resolve_public("nope.example", 80, boom)


def _mock(handler):
    return httpx.MockTransport(handler)


def test_redirect_to_a_private_address_is_not_followed():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data"})

    r = _resolver({"example.com": ["93.184.216.34"]})
    with pytest.raises(NetGuardError):
        safe_get("http://example.com/", resolver=r, transport=_mock(handler))
    assert len(seen) == 1 and "169.254" not in seen[0]       # the second hop never left the machine


def test_redirect_to_a_name_that_resolves_privately_is_not_followed():
    hits = []

    def handler(request):
        hits.append(request.headers["host"])
        return httpx.Response(302, headers={"location": "http://rebind.example/x"})

    r = _resolver({"example.com": ["93.184.216.34"], "rebind.example": ["127.0.0.1"]})
    with pytest.raises(NetGuardError, match="resolves to"):
        safe_get("http://example.com/", resolver=r, transport=_mock(handler))
    assert hits == ["example.com"]


def test_the_connection_is_pinned_to_the_validated_ip_and_the_name_is_looked_up_once():
    """DNS rebinding: a second lookup would be free to answer differently, so there must not be one."""
    lookups, requests = [], []

    def resolver(host, port, *a, **kw):
        lookups.append(host)
        ip = "93.184.216.34" if len(lookups) == 1 else "127.0.0.1"     # the attacker flips the answer after validation
        return [(2, 1, 6, "", (ip, port))]

    def handler(request):
        requests.append((request.url.host, request.headers["host"], request.extensions.get("sni_hostname")))
        return httpx.Response(200, text="ok", headers={"content-type": "text/plain"})

    res = safe_get("https://example.com/p", resolver=resolver, transport=_mock(handler))
    assert res.status == 200 and res.text == "ok"
    assert lookups == ["example.com"]
    assert requests == [("93.184.216.34", "example.com", "example.com")]


def test_redirects_are_followed_when_every_hop_is_public_and_are_bounded():
    r = _resolver({"a.example": ["93.184.216.34"], "b.example": ["93.184.216.35"]})

    def ok(request):
        if request.headers["host"] == "a.example":
            return httpx.Response(301, headers={"location": "https://b.example/final"})
        return httpx.Response(200, text="done")

    res = safe_get("https://a.example/", resolver=r, transport=_mock(ok))
    assert res.text == "done" and res.url == "https://b.example/final" and res.redirects == ["https://b.example/final"]

    def loop(request):
        return httpx.Response(302, headers={"location": "https://a.example/again"})

    with pytest.raises(NetGuardError, match="redirects"):
        safe_get("https://a.example/", resolver=r, transport=_mock(loop), max_redirects=3)


def test_response_bodies_are_bounded():
    r = _resolver({"big.example": ["93.184.216.34"]})
    res = safe_get("https://big.example/", resolver=r, max_bytes=1000,
                   transport=_mock(lambda req: httpx.Response(200, content=b"x" * 50_000)))
    assert len(res.text) <= 1000 and res.truncated


def test_a_redirect_that_downgrades_to_a_forbidden_scheme_is_refused():
    r = _resolver({"a.example": ["93.184.216.34"]})
    with pytest.raises(NetGuardError):
        safe_get("https://a.example/", resolver=r,
                 transport=_mock(lambda req: httpx.Response(302, headers={"location": "file:///etc/passwd"})))


class _Route:
    def __init__(self): self.did = None
    def continue_(self): self.did = "continue"
    def abort(self, why): self.did = f"abort:{why}"


class _Req:
    def __init__(self, url): self.url = url


def test_browser_request_guard_blocks_private_navigation_redirects_and_subresources():
    from hutch.netguard import RequestGuard
    r = _resolver({"example.com": ["93.184.216.34"], "rebind.example": ["10.1.1.1"]})
    blocked = []
    handler = RequestGuard(resolver=r).route_handler(lambda url, why: blocked.append(url))
    results = {}
    for url in ["https://example.com/", "https://rebind.example/x.js", "http://169.254.169.254/", "file:///etc/passwd",
                "data:text/plain,hi", "http://[::1]:8080/"]:
        route = _Route(); handler(route, _Req(url)); results[url] = route.did
    assert results["https://example.com/"] == "continue" and results["data:text/plain,hi"] == "continue"
    assert all(v == "abort:blockedbyclient" for k, v in results.items() if k not in ("https://example.com/", "data:text/plain,hi"))
    assert "https://rebind.example/x.js" in blocked


def test_request_guard_caches_a_decision_briefly_not_forever():
    from hutch.netguard import RequestGuard
    calls, now = [], [0.0]

    def r(host, port, *a, **k):
        calls.append(host)
        return [(2, 1, 6, "", ("93.184.216.34", port))]

    g = RequestGuard(resolver=r, ttl=30, clock=lambda: now[0])
    assert g.check("https://example.com/a") is None and g.check("https://example.com/b") is None
    assert calls == ["example.com"]
    now[0] = 31.0
    assert g.check("https://example.com/c") is None and calls == ["example.com", "example.com"]
