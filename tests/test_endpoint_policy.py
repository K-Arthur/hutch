"""Address policy for model endpoints (ADR-0034): decided on addresses, never on spellings."""

from __future__ import annotations

import socket

import pytest

from hutch.providers.endpoint_policy import (BLOCKED, FAKE_IP, LOOPBACK, PRIVATE, PUBLIC, EndpointRefused,
                                             classify_address, local_style, vet)


def _answers(*ips):
    """A resolver that answers with exactly these addresses (a real resolver cannot be told to rebind)."""
    def resolve(host, port, type=None):
        return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))
                for ip in ips]
    return resolve


@pytest.mark.parametrize("ip,kind", [
    ("127.0.0.1", LOOPBACK), ("::1", LOOPBACK), ("127.8.8.8", LOOPBACK),
    ("10.0.0.5", PRIVATE), ("172.16.9.1", PRIVATE), ("192.168.1.20", PRIVATE), ("fd12:3456::1", PRIVATE),
    ("100.101.102.103", PRIVATE),                       # tailnet / carrier-grade NAT
    ("198.18.0.7", FAKE_IP), ("198.19.255.1", FAKE_IP),
    ("8.8.8.8", PUBLIC), ("2606:4700:4700::1111", PUBLIC),
    ("169.254.169.254", BLOCKED), ("fe80::1", BLOCKED), ("0.0.0.0", BLOCKED), ("::", BLOCKED),
    ("224.0.0.1", BLOCKED), ("240.0.0.1", BLOCKED), ("192.0.2.10", BLOCKED), ("2001:db8::1", BLOCKED),
    ("::ffff:169.254.169.254", BLOCKED), ("::ffff:127.0.0.1", LOOPBACK), ("64:ff9b::a9fe:a9fe", BLOCKED),
    ("2002:a9fe:a9fe::1", BLOCKED), ("not-an-ip", BLOCKED),
])
def test_an_address_has_one_kind(ip, kind):
    assert classify_address(ip) == kind


@pytest.mark.parametrize("host", ["169.254.169.254", "2852039166", "0xa9.0xfe.0xa9.0xfe", "[fe80::1]", "0.0.0.0"])
def test_a_blocked_literal_is_refused_in_every_spelling(host):
    with pytest.raises(EndpointRefused, match="never a model endpoint"):
        vet(host.strip("[]"), 443)


def test_a_metadata_name_is_refused_before_any_lookup():
    def boom(*_a, **_k):
        raise AssertionError("must not resolve a metadata name")
    with pytest.raises(EndpointRefused, match="metadata"):
        vet("metadata.google.internal", 80, resolver=boom)


def test_a_name_with_one_blocked_answer_is_refused_even_among_public_ones():
    with pytest.raises(EndpointRefused, match="169.254.169.254"):
        vet("models.example.test", 443, resolver=_answers("8.8.8.8", "169.254.169.254"))


def test_a_public_looking_name_that_resolves_private_is_a_rebind_and_is_refused():
    with pytest.raises(EndpointRefused) as raised:
        vet("models.example.test", 443, resolver=_answers("10.0.0.5"))
    assert "HUTCH_PRIVATE_HOSTS" in str(raised.value) and "private address" in str(raised.value)
    with pytest.raises(EndpointRefused, match="loopback address"):
        vet("models.example.test", 443, resolver=_answers("127.0.0.1"))


def test_a_public_name_resolving_public_or_fake_ip_passes():
    assert vet("api.example.test", 443, resolver=_answers("8.8.8.8")) == [("8.8.8.8", PUBLIC)]
    assert vet("api.example.test", 443, resolver=_answers("198.18.0.9")) == [("198.18.0.9", FAKE_IP)]


@pytest.mark.parametrize("host", ["localhost", "nas", "gpu-box.lan", "mini.local", "llm.home.arpa",
                                  "box.tailnet-name.ts.net", "svc.internal"])
def test_a_local_style_name_may_resolve_private(host):
    assert local_style(host)
    assert vet(host, 8000, resolver=_answers("192.168.1.9")) == [("192.168.1.9", PRIVATE)]


def test_an_exact_listed_name_is_trusted_and_a_sibling_is_not():
    env = {"HUTCH_PRIVATE_HOSTS": " LLM.corp.example.test. , other.example.test"}
    assert vet("llm.corp.example.test", 443, resolver=_answers("10.1.1.1"), env=env) == [("10.1.1.1", PRIVATE)]
    with pytest.raises(EndpointRefused):
        vet("llm2.corp.example.test", 443, resolver=_answers("10.1.1.1"), env=env)


def test_a_listed_name_still_cannot_reach_a_blocked_address():
    env = {"HUTCH_PRIVATE_HOSTS": "llm.corp.example.test"}
    with pytest.raises(EndpointRefused, match="blocked address"):
        vet("llm.corp.example.test", 443, resolver=_answers("169.254.169.254"), env=env)


def test_a_vendor_host_is_exempt_from_the_name_rule_but_not_from_blocked():
    assert vet("api.vendor.test", 443, resolver=_answers("10.9.9.9"), vendor=True) == [("10.9.9.9", PRIVATE)]
    with pytest.raises(EndpointRefused):
        vet("api.vendor.test", 443, resolver=_answers("169.254.169.254"), vendor=True)


def test_resolution_failure_is_a_dns_layer_refusal():
    def fail(*_a, **_k):
        raise socket.gaierror(-2, "Name or service not known")
    with pytest.raises(EndpointRefused) as raised:
        vet("nowhere.example.test", 443, resolver=fail)
    assert raised.value.layer == "dns"
