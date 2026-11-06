"""An explicit route tuple is resolved from local facts and never substitutes a choice."""

from __future__ import annotations

from types import SimpleNamespace

from hutch.connections import ConnectionBook
from hutch.providers.routing import billing_crosses, resolve_chain, resolve_route
from hutch.runtime.ladder import billing_crossing_refusal


def _book(tmp_path) -> ConnectionBook:
    state = tmp_path / "state"
    state.mkdir()
    return ConnectionBook(state)


def test_a_named_account_resolves_without_substitution(tmp_path):
    book = _book(tmp_path)
    book.add("openai-api", "openai-personal", title="Personal")
    resolved = resolve_route(book, "openai-personal/gpt-4o", env={})
    assert resolved.provider == "openai"
    assert resolved.account == "openai-personal"
    assert resolved.account_source == "named connection"
    assert resolved.model == "gpt-4o"
    assert resolved.billing == "per_token"
    assert resolved.protocol == "openai-chat"
    assert resolved.endpoint == "https://api.openai.com/v1"
    assert resolved.status == "needs_authentication"
    assert resolved.substituted is False
    assert resolved.spec == "openai-personal/gpt-4o"


def test_an_ambient_key_is_named_as_the_account_source(tmp_path):
    book = _book(tmp_path)
    resolved = resolve_route(book, "openai/gpt-4o", env={"OPENAI_API_KEY": "placeholder"})
    assert resolved.account == "openai"
    assert "ambient environment (OPENAI_API_KEY)" == resolved.account_source
    assert resolved.status == "capability_unverified"
    assert resolved.substituted is False


def test_an_ambient_key_is_withheld_from_a_custom_endpoint(tmp_path):
    book = _book(tmp_path)
    resolved = resolve_route(book, "openai/gpt-4o", env={"OPENAI_API_KEY": "placeholder"},
                             base_url="https://proxy.example.test/v1")
    assert resolved.account == ""
    assert "withheld" in resolved.account_source
    assert resolved.status == "needs_authentication"
    assert "official host" in resolved.detail


def test_two_accounts_are_not_resolved_by_guessing(tmp_path):
    book = _book(tmp_path)
    book.add("openai-api", "openai-personal")
    book.add("openai-api", "openai-work")
    resolved = resolve_route(book, "openai/gpt-4o", env={"OPENAI_API_KEY": "placeholder"})
    assert resolved.account == ""
    assert resolved.account_source.startswith("not chosen")
    assert resolved.status == "needs_configuration"
    assert resolved.substituted is False


def test_a_blocked_provider_stays_blocked(tmp_path):
    resolved = resolve_route(_book(tmp_path), "github-copilot/gpt-4o", env={})
    assert resolved.status == "blocked_by_policy"
    assert resolved.account == ""
    assert resolved.substituted is False


def test_an_unknown_provider_needs_configuration(tmp_path):
    resolved = resolve_route(_book(tmp_path), "not-a-provider/model", env={})
    assert resolved.status == "needs_configuration"
    assert resolved.provider == "not-a-provider"
    assert resolved.substituted is False


def test_a_local_route_names_the_loopback_service(tmp_path):
    resolved = resolve_route(_book(tmp_path), "ollama/llama3.2", env={}, local_services={})
    assert resolved.account == "local service"
    assert resolved.billing == "free"
    assert resolved.status in ("endpoint_unavailable", "capability_unverified")
    assert resolved.substituted is False


def test_an_unselectable_runtime_is_reported_not_silently_replaced(tmp_path):
    book = _book(tmp_path)
    book.add("openai-api", "openai-personal")
    book.set_key("openai-personal", "placeholder")
    resolved = resolve_route(book, "openai-personal/gpt-4o", runtime="pi", env={})
    assert resolved.runtime == "pi"
    assert resolved.runtime_status == "blocked"
    assert resolved.status == "unsupported_runtime"
    assert resolved.substituted is False


def test_a_fallback_that_crosses_from_subscription_to_metered_requires_consent(tmp_path):
    book = _book(tmp_path)
    book.add("openai-api", "plan", billing="subscription")
    book.add("xai", "metered", billing="per_token")
    bot = SimpleNamespace(model="plan/gpt-4o", fallbacks=["metered/grok-4"], escalation=None,
                          runtime="builtin")
    rows = resolve_chain(book, bot, env={})
    assert [row["role"] for row in rows] == ["primary", "fallback"]
    assert rows[0]["resolution"].billing == "subscription"
    assert rows[0]["requires_consent"] is False
    assert rows[1]["resolution"].billing == "per_token"
    assert rows[1]["requires_consent"] is True
    assert all(not row["resolution"].substituted for row in rows)


def test_a_subscription_primary_refuses_a_metered_fallback(tmp_path):
    book = _book(tmp_path)
    book.add("openai-api", "plan", billing="subscription")
    book.add("xai", "metered", billing="per_token")
    assert billing_crossing_refusal(book, "plan/gpt-4o", "metered/grok-4", local=False)
    assert billing_crossing_refusal(book, "plan/gpt-4o", "plan/gpt-4o-mini", local=False) is None
    assert billing_crossing_refusal(book, "metered/grok-4", "plan/gpt-4o", local=False) is None
    assert billing_crossing_refusal(book, "ollama/llama3.2", "metered/grok-4", local=False) is None
    assert billing_crossing_refusal(book, "plan/gpt-4o", "metered/grok-4", local=True) is None


def test_billing_crossing_is_one_directional():
    assert billing_crosses("subscription", "per_token")
    assert billing_crosses("subscription", "credits")
    assert not billing_crosses("per_token", "subscription")
    assert not billing_crosses("per_token", "per_token")
    assert not billing_crosses("free", "per_token")
