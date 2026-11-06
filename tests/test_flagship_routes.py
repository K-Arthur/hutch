"""Phase 3 flagship identities: separate billing relationships stay separate (no network, no account)."""

from __future__ import annotations

from urllib.parse import urlsplit

import pytest

from hutch.connections import ConnectionBook, load_templates
from hutch.providers.catalog import bundled_catalog
from hutch.runtime.builtin import reset_connection_cache
from hutch.runtime.ladder import reset_provider_cache
from tests.fakes import FakeAnthropic
from tests.test_runtime_builtin import build, run_it, runtime

#: Hosts and path prefixes that serve a subscription plan whose terms limit use to the vendor's own
#: supported tools or to interactive use. Hutch bots run unattended and Hutch is not a listed tool.
POLICY_BLOCKED_ENDPOINTS = (
    ("coding.dashscope.aliyuncs.com", ""),
    ("coding-intl.dashscope.aliyuncs.com", ""),
    ("api.z.ai", "/api/coding"),
    ("open.bigmodel.cn", "/api/coding"),
)


@pytest.fixture()
def catalog():
    return bundled_catalog()


def test_no_template_points_at_a_policy_blocked_plan_endpoint():
    for name, template in load_templates().items():
        for key in ("base_url", "anthropic_base_url", "models_base_url"):
            url = template.get(key)
            if not url:
                continue
            parts = urlsplit(url)
            for host, prefix in POLICY_BLOCKED_ENDPOINTS:
                assert not (parts.hostname == host and parts.path.startswith(prefix)), (name, key, url)


def test_blocked_plan_keys_carry_their_reason_and_source(catalog):
    for provider_id, auth_id in (("qwen", "coding-plan"), ("zai", "coding-plan")):
        method = catalog.require(provider_id).auth(auth_id)
        assert method is not None and method.status == "blocked"
        assert method.docs, f"{provider_id}/{auth_id} blocked without a cited source"


def test_kimi_coding_is_its_own_identity_not_a_moonshot_auth_method(catalog):
    moonshot = catalog.require("moonshot")
    kimi = catalog.require("kimi-coding")
    assert [a.id for a in moonshot.auth_methods] == ["api-key"]
    assert kimi.category == "subscription_service"
    assert kimi.protocols == ("anthropic",)
    assert kimi.integration_status == "implemented-unverified"
    assert catalog.provider_for_template("kimi-coding").id == "kimi-coding"
    assert catalog.provider_for_template("moonshot-cn").id == "moonshot"


def test_kimi_coding_template_is_a_subscription_with_an_acknowledged_notice():
    template = load_templates()["kimi-coding"]
    assert template["protocol"] == "anthropic"
    assert template["billing"] == "subscription"
    assert template["api_key_env"] == "KIMI_API_KEY"
    assert template["terms"]["requires_ack"] is True
    assert "User-Agent" in template["terms"]["notice"]
    assert load_templates()["moonshot"]["api_key_env"] != template["api_key_env"]


def test_regional_keys_use_distinct_environment_variables():
    templates = load_templates()
    pairs = (("moonshot", "moonshot-cn"), ("qwen-standard-intl", "qwen-standard-cn"), ("zai", "zai-cn"))
    for first, second in pairs:
        assert templates[first]["base_url"] != templates[second]["base_url"]
        assert templates[first]["api_key_env"] != templates[second]["api_key_env"], (first, second)


def test_opencode_zen_is_separate_from_go_and_from_the_managed_runtime(catalog):
    zen, go = catalog.require("opencode-zen"), catalog.require("opencode-go")
    assert zen.connection_templates == ("opencode-zen",)
    assert zen.auth("api-key").billing == "per_token"
    assert go.auth("api-key").billing == "subscription"
    templates = load_templates()
    assert templates["opencode-zen"]["base_url"] == "https://opencode.ai/inference/v1"
    assert "/go/" not in templates["opencode-zen"]["base_url"]
    assert catalog.require("opencode").connection_templates == ()


def test_google_no_longer_claims_a_coding_cli(catalog):
    google = catalog.require("google")
    assert "coding_cli" not in google.services
    assert google.auth("oauth-consumer").status == "blocked"
    assert "Antigravity" in google.notes


def test_every_new_template_builds_into_a_connection(tmp_path):
    book = ConnectionBook(tmp_path)
    for name in ("moonshot-cn", "kimi-coding", "zai-cn", "qwen-standard-intl", "qwen-standard-cn", "opencode-zen"):
        connection = book.add(name, name=f"{name}-test")
        assert connection.base_url.startswith("https://") and not connection.base_url.endswith("/")
        assert connection.terms.requires_ack == (name == "kimi-coding")


def test_kimi_coding_sends_the_membership_key_and_hutch_identity_to_messages(store, config, tmp_path, monkeypatch):
    """The wire contract Kimi's terms rely on: its own key, Hutch's own User-Agent, never another client's."""
    reset_provider_cache()
    reset_connection_cache()
    anth = FakeAnthropic()
    try:
        monkeypatch.setenv("KIMI_API_KEY", "kimi-test-key")
        book = ConnectionBook(config.state_dir)
        book.add("kimi-coding", name="kimi", base_url=anth.url)
        book.acknowledge(store, "kimi")
        anth.script = lambda body: {"content": "kimi ok", "input_tokens": 11, "output_tokens": 3}
        ctx, run, _emitted, tools = build(store, config, tmp_path, model="kimi/kimi-for-coding", tools=("remember",))
        assert run_it(runtime(), run, ctx, tools) == "kimi ok"
        sent = anth.of("/v1/messages")[0]
        assert sent["headers"]["x-api-key"] == "kimi-test-key"
        assert sent["headers"]["user-agent"].startswith("hutch/")
        assert "claude" not in sent["headers"]["user-agent"].lower()
    finally:
        anth.close()
