"""Approved local development origins: validation and request-context rules (no network, no browser)."""

from __future__ import annotations

import pytest

from hutch.netguard import LocalAccess, LocalOrigins, screen_url


@pytest.mark.parametrize("value, normalised", [
    ("http://localhost:3000", "http://localhost:3000"),
    ("HTTP://LocalHost:3000/", "http://localhost:3000"),
    ("http://127.0.0.1:8080", "http://127.0.0.1:8080"),
    ("http://127.1.2.3:80", "http://127.1.2.3:80"),
    ("http://[::1]:5173", "http://[::1]:5173"),
])
def test_valid_origins_are_normalised(value, normalised):
    assert list(LocalOrigins.parse([value])) == [normalised]


@pytest.mark.parametrize("value", [
    "http://localhost",                      # port is required: "localhost" alone would approve every local service
    "https://localhost:3000",                # tunnels cannot be inspected by the egress proxy
    "http://192.168.1.20:3000",              # LAN
    "http://10.0.0.5:8080",
    "http://169.254.169.254:80",             # metadata service
    "http://0.0.0.0:3000",
    "http://app.localhost:3000",             # names other than plain localhost are never approvable
    "http://example.com:3000",
    "http://localhost:3000/admin",           # an origin, not a path
    "http://localhost:3000?x=1",
    "http://user:pw@localhost:3000",
    "http://[::ffff:127.0.0.1]:3000",        # IPv4-mapped spelling
    "http://2130706433:3000",                # legacy decimal spelling of 127.0.0.1
    "file:///etc/passwd",
    "",
    42,
])
def test_unsafe_origins_are_rejected(value):
    with pytest.raises(ValueError):
        LocalOrigins.parse([value])


def test_the_list_is_bounded():
    many = [f"http://localhost:{3000 + i}" for i in range(LocalOrigins.MAX_ENTRIES + 1)]
    with pytest.raises(ValueError, match="at most"):
        LocalOrigins.parse(many)


def test_lenient_runtime_parse_drops_bad_entries_instead_of_widening():
    kept = LocalOrigins.lenient(["http://localhost:3000", "http://192.168.1.2:80", "nonsense", 7])
    assert list(kept) == ["http://localhost:3000"]


def test_screen_url_allows_only_the_exact_origin():
    local = LocalOrigins.parse(["http://localhost:3000"])
    assert screen_url("http://localhost:3000/app?x=1", local) is None
    assert screen_url("http://localhost:3001/", local) is not None          # other port
    assert screen_url("https://localhost:3000/", local) is not None         # other scheme
    assert screen_url("http://127.0.0.1:3000/", local) is not None          # another spelling is not approved
    assert screen_url("http://localhost:3000/", None) is not None           # default: still blocked
    assert screen_url("http://169.254.169.254/latest", local) is not None   # metadata stays blocked


def _access(clock=None):
    now = {"t": 1000.0}
    access = LocalAccess(LocalOrigins.parse(["http://localhost:3000"]), clock=clock or (lambda: now["t"]))
    return access, now


APP = "http://localhost:3000/dashboard"
NAV = [("sec-fetch-site", "none"), ("sec-fetch-mode", "navigate"), ("sec-fetch-dest", "document"),
       ("sec-fetch-user", "?1")]


def test_non_local_urls_are_not_judged_here():
    access, _ = _access()
    assert access.refusal("http://public.example/", []) is None


def test_a_public_page_subresource_or_script_navigation_is_refused():
    access, _ = _access()
    assert access.refusal(APP, [("sec-fetch-site", "cross-site"), ("referer", "http://public.example/")])
    assert access.refusal(APP, [("sec-fetch-site", "cross-site")])
    assert access.refusal(APP, [("origin", "http://public.example")])
    assert access.refusal(APP, [("origin", "null")])


def test_requests_from_the_approved_local_page_are_allowed():
    access, _ = _access()
    assert access.refusal(APP, [("sec-fetch-site", "same-origin")]) is None
    assert access.refusal(APP, [("sec-fetch-site", "same-site")]) is None
    assert access.refusal(APP, [("sec-fetch-site", "cross-site"), ("referer", "http://localhost:3000/")]) is None
    assert access.refusal(APP, [("origin", "http://localhost:3000")]) is None


def test_a_browser_initiated_navigation_needs_the_tools_permit():
    access, now = _access()
    assert access.refusal(APP, NAV), "without a permit a referrer-less navigation cannot be told from a redirect hop"
    assert access.permit_navigation(APP) is True
    assert access.refusal(APP, NAV) is None
    # a different approved origin or path-less variants are not covered by this origin's permit
    other = LocalAccess(LocalOrigins.parse(["http://localhost:3000", "http://127.0.0.1:4000"]), clock=lambda: now["t"])
    other.permit_navigation(APP)
    assert other.refusal("http://127.0.0.1:4000/x", NAV)
    access.clear_permit()
    assert access.refusal(APP, NAV)


def test_a_permit_expires():
    access, now = _access()
    access.permit_navigation(APP)
    now["t"] += LocalAccess.PERMIT_SECONDS + 1
    assert access.refusal(APP, NAV)


def test_a_permit_cannot_be_opened_for_a_public_url_and_does_not_unblock_other_hosts():
    access, _ = _access()
    assert access.permit_navigation("http://public.example/") is False
    assert access.permit_navigation("http://localhost:9999/") is False
    assert access.refusal("http://localhost:9999/", NAV) is None  # not an approved origin: not judged here (screen_url refuses)


def test_the_permit_does_not_cover_a_navigation_with_a_foreign_referrer():
    access, _ = _access()
    access.permit_navigation(APP)
    with_referrer = NAV + [("referer", "http://public.example/")]
    assert access.refusal(APP, with_referrer)


def test_the_dashboards_own_port_can_be_excluded_from_approved_origins(monkeypatch):
    from hutch.netguard import dashboard_ports
    monkeypatch.setenv("HUTCH_DASHBOARD_PORT", "9911")
    assert dashboard_ports() == {8787, 9911}
    approved = LocalOrigins.parse(["http://localhost:3000", "http://localhost:9911", "http://127.0.0.1:8787"])
    kept = approved.without_ports(dashboard_ports())
    assert list(kept) == ["http://localhost:3000"]
    access = LocalAccess(kept)
    assert access.refusal("http://localhost:9911/approvals", [("sec-fetch-site", "same-origin")]) is None  # not judged here
    assert not kept.allows_url("http://localhost:9911/approvals")
