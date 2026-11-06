"""Phase 4 hosted providers and gateways: documented hosts, honest plan boundaries, key placement.

No network and no account: the wire test talks to a local fake server and checks which header carried the key.
"""

from __future__ import annotations

from urllib.parse import urlsplit

import pytest

from hutch.connections import ConnectionBook, load_templates
from hutch.providers.auth_headers import KEY_PLACEHOLDER, bind_key_headers
from hutch.providers.catalog import bundled_catalog
from hutch.providers.connection import provider_for_connection
from hutch.providers.base import ProviderError

#: template -> (provider identity, base url, key variable). The base url is the vendor-documented default
#: or "https://" where the host belongs to the user (an Azure resource).
NEW_TEMPLATES = {
    "vercel-ai-gateway": ("vercel-ai-gateway", "https://ai-gateway.vercel.sh/v1", "AI_GATEWAY_API_KEY"),
    "litellm": ("litellm", "http://localhost:4000/v1", "LITELLM_API_KEY"),
    "clawrouter": ("clawrouter", "https://clawrouter.openclaw.ai/v1", "CLAWROUTER_API_KEY"),
    "bedrock-runtime": ("bedrock", "https://bedrock-runtime.us-east-1.amazonaws.com/openai/v1",
                        "AWS_BEARER_TOKEN_BEDROCK"),
    "bedrock-mantle": ("bedrock-mantle", "https://bedrock-mantle.us-east-1.api.aws/v1", "AWS_BEARER_TOKEN_BEDROCK"),
    "microsoft-foundry": ("microsoft-foundry", "https://", "AZURE_OPENAI_API_KEY"),
    "qianfan": ("qianfan", "https://qianfan.baidubce.com/v2", "QIANFAN_API_KEY"),
    "stepfun-global": ("stepfun", "https://api.stepfun.ai/v1", "STEPFUN_GLOBAL_API_KEY"),
}

#: Plan endpoints whose terms limit use to interactive or listed tools; no template may point at one.
PLAN_PATHS = (
    ("api.lkeap.cloud.tencent.com", "/plan"),
    ("tokenhub.tencentmaas.com", "/plan"),
    ("tokenhub-intl.tencentmaas.com", "/plan"),
    ("tokenhub.tencentcloudmaas.com", "/plan"),
    ("tokenhub-intl.tencentcloudmaas.com", "/plan"),
    ("ark.cn-beijing.volces.com", "/api/coding"),
    ("ark.ap-southeast.bytepluses.com", "/api/coding"),
)


@pytest.fixture()
def catalog():
    return bundled_catalog()


def test_new_templates_are_catalogued_with_their_documented_host_and_key_variable(catalog):
    templates = load_templates()
    for name, (provider, base_url, env) in NEW_TEMPLATES.items():
        template = templates[name]
        assert template["provider"] == provider, name
        assert template["base_url"] == base_url, name
        assert template["api_key_env"] == env, name
        assert name in catalog.require(provider).connection_templates, name
        assert catalog.provider_for_template(name).id == provider, name


def test_a_template_is_not_a_support_claim(catalog):
    """Nothing here was exercised with a key, so no identity may claim more than implemented-unverified."""
    for _name, (provider, _base, _env) in NEW_TEMPLATES.items():
        assert catalog.require(provider).integration_status == "implemented-unverified", provider


def test_synthetic_uses_the_documented_openai_path_and_records_the_anthropic_base():
    template = load_templates()["synthetic"]
    assert template["base_url"] == "https://api.synthetic.new/openai/v1"
    assert template["anthropic_base_url"] == "https://api.synthetic.new/anthropic"
    assert template["protocol"] == "openai-chat"


def test_tencent_token_plan_is_blocked_with_its_cited_terms(catalog):
    method = catalog.require("tencent-cloud").auth("token-plan")
    assert method is not None and method.status == "blocked"
    assert method.docs and "tencent" in method.docs[0].url
    assert catalog.require("tencent-cloud").auth("api-key").status == "implemented"


def test_no_template_points_at_a_restricted_plan_endpoint():
    for name, template in load_templates().items():
        for key in ("base_url", "anthropic_base_url", "models_base_url"):
            url = template.get(key)
            if not url:
                continue
            parts = urlsplit(url)
            for host, prefix in PLAN_PATHS:
                assert not (parts.hostname == host and parts.path.startswith(prefix)), (name, key, url)


def test_pay_as_you_go_ark_templates_say_they_are_not_a_plan():
    templates = load_templates()
    assert "pay-as-you-go" in templates["volcengine"]["model_protocol_hint"]
    assert "/api/coding" in templates["volcengine"]["model_protocol_hint"]
    assert "per token" in templates["byteplus"]["model_protocol_hint"]


def test_stepfun_regions_are_separate_templates_with_separate_key_variables():
    templates = load_templates()
    assert templates["stepfun"]["api_key_env"] != templates["stepfun-global"]["api_key_env"]
    assert urlsplit(templates["stepfun"]["base_url"]).hostname == "api.stepfun.com"
    assert urlsplit(templates["stepfun-global"]["base_url"]).hostname == "api.stepfun.ai"


def test_bedrock_templates_name_the_region_key_scope_and_inference_profile_pitfalls():
    templates = load_templates()
    runtime, mantle = templates["bedrock-runtime"], templates["bedrock-mantle"]
    assert runtime["models_endpoint"] is False, "bedrock-runtime has no GET /models"
    assert mantle["models_endpoint"] is True
    for template in (runtime, mantle):
        text = template["model_protocol_hint"]
        assert "Region" in text and "inference profile" in text
    assert "12 hours" in runtime["quota_hint"]
    assert "/openai/v1" in mantle["model_protocol_hint"], "Mantle serves some models under another prefix"


def test_vercel_gateway_requires_acknowledging_the_system_credential_fallback():
    template = load_templates()["vercel-ai-gateway"]
    assert template["terms"]["requires_ack"] is True
    assert "system credentials" in template["terms"]["notice"]
    assert template["terms"]["url"].startswith("https://vercel.com/docs/ai-gateway")


def test_litellm_template_says_model_ids_are_aliases():
    hint = load_templates()["litellm"]["model_protocol_hint"]
    assert "alias" in hint and "served" in hint


def test_bind_key_headers_puts_the_key_in_the_named_header_and_drops_the_bearer():
    headers, bearer = bind_key_headers({"User-Agent": "hutch/x", "api-key": KEY_PLACEHOLDER}, "sk-test")
    assert headers == {"User-Agent": "hutch/x", "api-key": "sk-test"}
    assert bearer == ""


def test_bind_key_headers_leaves_ordinary_headers_and_the_bearer_alone():
    headers, bearer = bind_key_headers({"User-Agent": "hutch/x"}, "sk-test")
    assert headers == {"User-Agent": "hutch/x"}
    assert bearer == "sk-test"


def test_a_placeholder_must_be_the_whole_value():
    with pytest.raises(ValueError):
        bind_key_headers({"x-note": f"prefix {KEY_PLACEHOLDER}"}, "sk-test")


def test_a_template_with_a_user_owned_host_is_refused_until_the_host_is_given(tmp_path):
    book = ConnectionBook(tmp_path)
    with pytest.raises(ValueError, match="--base-url") as refused:
        book.add("microsoft-foundry", name="foundry-test")
    assert "Foundry" in str(refused.value)
    connection = book.add("microsoft-foundry", name="foundry-test", base_url="https://res.openai.azure.com/openai/v1/")
    assert connection.base_url == "https://res.openai.azure.com/openai/v1"
    assert connection.headers == {"api-key": KEY_PLACEHOLDER}, "the stored connection never holds the key"


def test_foundry_sends_the_key_in_api_key_and_no_bearer(tmp_path, monkeypatch):
    from tests.fakes import FakeOpenAI
    oai = FakeOpenAI()
    try:
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "azure-test-key")
        book = ConnectionBook(tmp_path)
        book.add("microsoft-foundry", name="foundry-test", base_url=f"{oai.url}/v1")
        provider = provider_for_connection(book, "foundry-test", "my-deployment")
        provider.list_models()
        sent = oai.of("/v1/models")[0]["headers"]
        assert sent["api-key"] == "azure-test-key"
        assert "authorization" not in {k.lower() for k in sent}
        assert KEY_PLACEHOLDER not in sent.values()
    finally:
        oai.close()


def test_key_in_header_is_refused_on_other_protocols(tmp_path, monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "azure-test-key")
    book = ConnectionBook(tmp_path)
    book.add("microsoft-foundry", name="foundry-test", base_url="https://res.openai.azure.com/openai/v1",
             model_protocols={"claude-x": "anthropic"})
    with pytest.raises(ProviderError):
        provider_for_connection(book, "foundry-test", "claude-x")


def test_key_header_templates_declare_no_speech_transcription_or_search_route():
    """Those clients copy ``conn.headers`` verbatim, so they must never be handed a placeholder."""
    checked = 0
    for name, template in load_templates().items():
        if KEY_PLACEHOLDER not in (template.get("headers") or {}).values():
            continue
        checked += 1
        assert not {"speech", "transcription", "search"} & set(template), name
    assert checked >= 1
