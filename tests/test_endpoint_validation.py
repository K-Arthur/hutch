"""Save-time endpoint rules: blocked addresses in any spelling and scheme, and the pasted-path clean-up (ADR-0034)."""

from __future__ import annotations

import pytest

from hutch.connection_endpoints import normalize_base
from hutch.connections import ConnectionBook, load_templates


@pytest.fixture()
def book(tmp_path):
    return ConnectionBook(tmp_path)


@pytest.mark.parametrize("url", [
    "https://169.254.169.254/v1", "https://2852039166/v1", "https://0xa9.0xfe.0xa9.0xfe/v1",
    "https://[fe80::1]/v1", "https://metadata.google.internal/v1", "http://0.0.0.0:1234/v1",
])
def test_a_blocked_address_is_refused_over_https_too(book, url):
    with pytest.raises(ValueError, match="never a model endpoint|blocked"):
        book.add("custom-openai", name="blocked-one", base_url=url)
    assert book.get("blocked-one") is None


def test_loopback_and_https_public_endpoints_still_save(book):
    assert book.add("custom-openai", name="local-one", base_url="http://127.0.0.1:1234/v1").base_url \
        == "http://127.0.0.1:1234/v1"
    assert book.add("custom-openai", name="remote-one", base_url="https://models.example.test/v1").base_url \
        == "https://models.example.test/v1"


@pytest.mark.parametrize("pasted,root", [
    ("http://127.0.0.1:8000/v1/chat/completions", "http://127.0.0.1:8000/v1"),
    ("http://127.0.0.1:8000/v1/models", "http://127.0.0.1:8000/v1"),
    ("http://127.0.0.1:8000/v1/", "http://127.0.0.1:8000/v1"),
    ("http://127.0.0.1:8000/v1//", "http://127.0.0.1:8000/v1"),
    ("http://127.0.0.1:8000", "http://127.0.0.1:8000"),                     # nothing is ever added
    ("https://gateway.example.test/v1/messages", "https://gateway.example.test"),
])
def test_a_pasted_api_path_is_reduced_to_the_root(pasted, root):
    assert normalize_base(pasted) == root


def test_the_clean_up_is_applied_when_a_connection_is_saved(book):
    saved = book.add("custom-openai", name="pasted", base_url="http://127.0.0.1:8000/v1/chat/completions")
    assert saved.base_url == "http://127.0.0.1:8000/v1"
    anth = book.add("custom-anthropic", name="pasted-anth", base_url="https://gateway.example.test/v1/messages")
    assert anth.base_url == "https://gateway.example.test"


def test_no_shipped_template_is_changed_by_the_clean_up():
    for name, row in load_templates().items():
        for field in ("base_url", "anthropic_base_url", "models_base_url"):
            url = (row.get(field) or "").rstrip("/")
            assert normalize_base(url) == url, (name, field)
