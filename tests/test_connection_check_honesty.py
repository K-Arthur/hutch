"""A public model list proves reachability, not that the key works: the check must not claim otherwise.

Measured 2026-11-06 with a placeholder bearer value (no account): these hosts answer HTTP 200 on their model list
whether or not the key is valid.
"""

from __future__ import annotations

import pytest

from hutch.connections import ConnectionBook, load_templates
from hutch.providers.connection import check_connection

LIST_IGNORES_KEY = ("huggingface", "kilocode", "novita", "nvidia", "ollama-cloud", "synthetic", "venice")


def test_templates_whose_list_ignores_the_key_are_flagged_with_a_model_list():
    templates = load_templates()
    flagged = {name for name, row in templates.items() if row.get("models_list_ignores_key")}
    assert flagged == set(LIST_IGNORES_KEY)
    for name in flagged:
        assert templates[name]["models_endpoint"] is True, name


def test_a_flagged_template_lists_models_but_does_not_claim_the_key_was_checked(tmp_path, monkeypatch):
    from tests.fakes import FakeOpenAI
    oai = FakeOpenAI()
    try:
        monkeypatch.setenv("SYNTHETIC_API_KEY", "any-value-at-all")
        book = ConnectionBook(tmp_path)
        book.add("synthetic", name="synth-test", base_url=f"{oai.url}/v1")
        result = check_connection(book, "synth-test")
        assert result.ok is True and result.verified is False
        assert result.models, "the listing itself is still useful"
        assert "not verified" in result.detail.lower()
        assert "authenticated" not in result.detail.lower()
    finally:
        oai.close()


def test_an_unflagged_template_still_reports_a_verified_key(tmp_path, monkeypatch):
    from tests.fakes import FakeOpenAI
    oai = FakeOpenAI()
    try:
        monkeypatch.setenv("GROQ_API_KEY", "good-key")
        oai.require_key = "good-key"
        book = ConnectionBook(tmp_path)
        book.add("groq", name="groq-test", base_url=f"{oai.url}/v1")
        result = check_connection(book, "groq-test")
        assert result.ok is True and result.verified is True
    finally:
        oai.close()


@pytest.mark.parametrize("key,expected", [("good-key", True), ("wrong-key", False)])
def test_an_unflagged_template_rejects_a_wrong_key(tmp_path, monkeypatch, key, expected):
    from tests.fakes import FakeOpenAI
    oai = FakeOpenAI()
    try:
        monkeypatch.setenv("GROQ_API_KEY", key)
        oai.require_key = "good-key"
        book = ConnectionBook(tmp_path)
        book.add("groq", name="groq-test", base_url=f"{oai.url}/v1")
        assert check_connection(book, "groq-test").ok is expected
    finally:
        oai.close()


def test_the_models_page_does_not_call_an_unverified_check_verified(config, monkeypatch):
    import re
    from fastapi.testclient import TestClient
    from hutch.server.app import create_app
    from tests.fakes import FakeOpenAI
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "testserver")
    monkeypatch.setenv("SYNTHETIC_API_KEY", "any-value-at-all")
    oai = FakeOpenAI()
    try:
        ConnectionBook(config.state_dir).add("synthetic", name="synth-test", base_url=f"{oai.url}/v1")
        with TestClient(create_app()) as client:
            token = re.search(r'<meta name="csrf" content="([^"]+)"', client.get("/legacy/connections").text).group(1)
            page = client.post("/models/test", data={"csrf": token, "provider": "synth-test"},
                               follow_redirects=True).text
        assert "checked, not verified" in page
        assert "connection verified" not in page
    finally:
        oai.close()
