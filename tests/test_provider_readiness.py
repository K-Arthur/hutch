"""Tests for readiness states (local facts only, no network)."""

from __future__ import annotations

import pytest

from hutch.connections import ConnectionBook
from hutch.providers.readiness import (
    STATES,
    account_readiness,
    provider_readiness,
    readiness_json,
    route_readiness,
)


@pytest.fixture()
def book(tmp_path, monkeypatch):
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    return ConnectionBook(tmp_path / "state")


def test_account_without_a_key_needs_authentication(book):
    book.add("openai-api", "openai-personal", title="Personal")
    state = account_readiness(book, "openai-personal")
    assert state.state == "needs_authentication"
    assert "OPENAI_API_KEY" in (state.next_action + state.detail)
    assert state.state in STATES


def test_account_with_a_key_is_available_but_not_capability_verified(book):
    book.add("openai-api", "openai-personal", title="Personal")
    book.set_key("openai-personal", "sk-unit-test-placeholder")
    state = account_readiness(book, "openai-personal")
    assert state.state == "available"
    assert state.ready
    route = route_readiness(book, "openai-personal/gpt-4o")
    assert route.state == "capability_unverified"
    assert route.scope == "model"


def test_empty_or_unknown_specs_need_configuration(book):
    assert route_readiness(book, "").state == "needs_configuration"
    assert route_readiness(book, "not-a-provider/model").state == "needs_configuration"


def test_ambient_key_route_is_never_called_available(book, monkeypatch):
    assert route_readiness(book, "openai/gpt-4o").state == "needs_authentication"
    monkeypatch.setenv("OPENAI_API_KEY", "env-unit-test-placeholder")
    route = route_readiness(book, "openai/gpt-4o")
    assert route.state == "capability_unverified"


def test_blocked_and_deferred_providers_are_explained(book):
    assert route_readiness(book, "github-copilot/some-model").state == "blocked_by_policy"
    assert route_readiness(book, "fal/some-model").state == "needs_configuration"


def test_local_route_states_depend_on_probe_result(book):
    assert route_readiness(book, "ollama/llama3").state == "capability_unverified"
    unreachable = {"ollama": {"reachable": False}}
    assert route_readiness(book, "ollama/llama3", local_services=unreachable).state == "endpoint_unavailable"
    reachable = {"ollama": {"reachable": True, "models": ["llama3"]}}
    assert route_readiness(book, "ollama/llama3", local_services=reachable).state == "capability_unverified"


def test_provider_readiness_groups_accounts(book):
    book.add("openai-api", "openai-personal")
    book.add("openai-api", "openai-work")
    summary = provider_readiness(book, "openai")
    assert summary["provider"] == "openai"
    assert len(summary["accounts"]) == 2
    assert all(account["state"] == "needs_authentication" for account in summary["accounts"])
    body = readiness_json(account_readiness(book, "openai-personal"))
    assert set(body) == {"state", "subject", "scope", "detail", "next_action", "ready"}


# An OpenCode route is resolved by the OpenCode tool on this computer, not by a Hutch connection. The Models page used to say
# "needs configuration: no account or ambient credential resolves this route" about a free OpenCode model right above a routing
# table that called the same route "Runnable".

OPENCODE_ROUTE = "opencode/opencode/deepseek-v4.1-flash-free"


def test_an_opencode_route_is_not_called_unconfigured_when_the_tool_is_installed(book, monkeypatch):
    monkeypatch.setattr("hutch.providers.readiness.shutil.which", lambda name: "/usr/bin/opencode")
    result = route_readiness(book, OPENCODE_ROUTE)
    assert result.state == "capability_unverified", "never 'available' from a listing alone, never 'needs configuration' either"
    assert "OpenCode" in result.detail and "credential" not in result.detail
    assert "Add a connection" not in result.next_action


def test_an_opencode_route_without_the_tool_says_what_to_install(book, monkeypatch):
    monkeypatch.setattr("hutch.providers.readiness.shutil.which", lambda name: None)
    result = route_readiness(book, OPENCODE_ROUTE)
    assert result.state == "needs_configuration"
    assert "not found" in result.detail and "OpenCode" in result.next_action


def test_a_saved_connection_named_opencode_is_judged_as_a_connection(book, monkeypatch):
    monkeypatch.setattr("hutch.providers.readiness.shutil.which", lambda name: None)
    book.add("openai-api", "opencode", title="My own")
    book.set_key("opencode", "sk-unit-test-placeholder")
    result = route_readiness(book, OPENCODE_ROUTE)
    assert result.state == "capability_unverified" and "not found" not in result.detail


# A provider spec names the provider, not the account. When an account (or an account plus an ambient key)
# exists, saying "no named connection provides this provider" is false, and saying "available" would
# silently decide which account pays.

def test_a_provider_spec_with_a_configured_account_names_the_account_instead_of_denying_it(book):
    book.add("google-gemini")
    book.set_key("google-gemini", "placeholder-key")
    result = route_readiness(book, "google/gemini-3.8-flash", env={})
    assert result.state == "needs_configuration"
    assert "google-gemini" in result.detail and "no named connection" not in result.detail
    assert "google-gemini/gemini-3.8-flash" in result.next_action
    assert route_readiness(book, "google-gemini/gemini-3.8-flash", env={}).state == "capability_unverified"


def test_a_provider_spec_does_not_choose_between_an_account_and_an_ambient_key(book):
    book.add("anthropic-api")
    book.set_key("anthropic-api", "placeholder-key")
    result = route_readiness(book, "anthropic/claude-opus-5-5", env={"ANTHROPIC_API_KEY": "placeholder-key"})
    assert result.state == "needs_configuration" and "ANTHROPIC_API_KEY" in result.detail
