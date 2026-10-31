"""Tests for provider-scoped authentication profiles over the real connection store (no network)."""

from __future__ import annotations

import json

import pytest

from hutch.connections import ConnectionBook
from hutch.providers.accounts import (
    account_profile,
    disconnect_local,
    provider_groups,
    rename_account,
)


@pytest.fixture()
def book(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return ConnectionBook(tmp_path / "state")


def _add_common(book):
    book.add("openai-api", "openai-personal", title="OpenAI personal")
    book.add("openai-api", "openai-work", title="OpenAI work")
    book.add("anthropic-api", "claude-work", title="Claude work")
    book.add("openrouter", "openrouter-main", title="OpenRouter main")
    book.add("custom-openai", "internal-gateway", title="Internal gateway",
             base_url="https://models.example.com/v1", api_key_env="EXAMPLE_GATEWAY_KEY")
    return book


def test_templates_declare_provider_and_auth_method(book):
    from hutch.connections import load_templates
    templates = load_templates()
    assert templates["openai-api"]["provider"] == "openai"
    assert templates["openai-api"]["auth_method"] == "api_key"
    assert templates["chatgpt-plan"]["auth_method"] == "pkce"
    assert templates["custom-openai"]["provider"] == "custom-compatible"
    # The UI-facing template list deliberately withholds OAuth-backed templates from generic creation.
    assert "chatgpt-plan" not in book.templates()
    conn = book.add("openai-api", "acct", title="Account")
    assert conn.provider == "openai"
    assert conn.auth_method == "api_key"


def test_multiple_accounts_group_under_one_provider(book):
    _add_common(book)
    groups = {group.provider_id: group for group in provider_groups(book)}
    openai = groups["openai"]
    assert openai.provider is not None and openai.provider.title == "OpenAI"
    assert [profile.name for profile in openai.accounts] == ["openai-personal", "openai-work"]
    assert groups["anthropic"].provider.category == "vendor"
    assert groups["openrouter"].provider.category == "gateway"
    assert groups["custom-compatible"].provider.category == "compatible_endpoint"


def test_account_state_is_explicit_before_and_after_a_local_key(book):
    _add_common(book)
    profile = account_profile(book, "openai-personal")
    assert profile.status == "needs_key"
    assert profile.credential == "missing"
    assert profile.billing_label == "Per-token API billing"
    assert profile.auth_label == "Platform API key"  # catalogue label for the declared auth method
    book.set_key("openai-personal", "sk-unit-test-placeholder")
    profile = account_profile(book, "openai-personal")
    assert profile.status == "ready"
    assert profile.credential == "present"
    assert profile.credential_source == "key file in the state directory"
    other = account_profile(book, "openai-work")
    assert other.status == "needs_key"  # accounts are independent; one key does not authorize the other


def test_environment_key_is_reported_as_the_source(book, monkeypatch):
    _add_common(book)
    monkeypatch.setenv("OPENAI_API_KEY", "env-unit-test-placeholder")
    profile = account_profile(book, "openai-personal")
    assert profile.status == "ready"
    assert profile.credential_source == "environment variable OPENAI_API_KEY"


def test_rename_changes_display_title_only_and_survives_reload(book, tmp_path):
    _add_common(book)
    rename_account(book, "openai-personal", "  Personal   (API)  ")
    reloaded = ConnectionBook(tmp_path / "state")
    profile = account_profile(reloaded, "openai-personal")
    assert profile.title == "Personal (API)"
    assert profile.name == "openai-personal"  # spec name is stable
    for bad in ("", "   ", "x" * 121):
        with pytest.raises(ValueError):
            rename_account(book, "openai-personal", bad)


def test_disconnect_removes_local_key_and_says_what_it_did_not_do(book):
    _add_common(book)
    book.set_key("openai-personal", "sk-unit-test-placeholder")
    result = disconnect_local(book, "openai-personal")
    assert result["local_credentials_removed"] is True
    assert result["provider_revocation_requested"] is False
    assert "local key only" in result["detail"]
    assert account_profile(book, "openai-personal").status == "needs_key"
    assert book.get("openai-personal") is not None  # the connection itself is kept


def test_disconnect_without_a_stored_key_is_honest(book):
    _add_common(book)
    result = disconnect_local(book, "openai-work")
    assert result["local_credentials_removed"] is False
    assert "nothing was removed" in result["detail"]


def test_chatgpt_plan_account_is_not_an_api_key(book):
    book.add("chatgpt-plan", "chatgpt-plan", auth_account_id="acct_" + "a" * 24)
    profile = account_profile(book, "chatgpt-plan")
    assert profile.provider_id == "openai"
    assert profile.auth_method == "pkce"
    assert profile.billing == "subscription"
    assert profile.status == "needs_sign_in"
    result = disconnect_local(book, "chatgpt-plan")
    assert result["local_credentials_removed"] is False
    assert "Sign in with ChatGPT" in result["detail"]


def test_legacy_connection_rows_resolve_provider_through_the_template(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    state = tmp_path / "state"
    state.mkdir()
    (state / "connections.json").write_text(json.dumps({"connections": {
        "legacy-openai": {"template": "openai-api", "title": "Legacy OpenAI"},
        "legacy-custom": {"template": "custom-openai", "base_url": "https://models.example.com/v1"},
    }}))
    book = ConnectionBook(state)
    assert book.errors == []
    assert account_profile(book, "legacy-openai").provider_id == "openai"
    assert account_profile(book, "legacy-custom").provider_id == "custom-compatible"


def test_invalid_explicit_provider_is_reported_not_guessed(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    (state / "connections.json").write_text(json.dumps({"connections": {
        "bad": {"template": "openai-api", "provider": "Not A Slug"},
    }}))
    book = ConnectionBook(state)
    assert book.errors  # refused at load with a reason
    assert "bad" not in book.names()


def test_empty_store_has_no_groups(book):
    assert book.configured() == {}
    assert provider_groups(book) == []
