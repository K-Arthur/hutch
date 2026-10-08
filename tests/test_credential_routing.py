"""T-CRED-SCOPE: an API key from the environment is only ever sent to the provider it belongs to.

Baseline defect (docs/realignment/baseline.md, lead 5): ``openai-compatible/<model>`` with any ``base_url`` sent
``OPENAI_API_KEY`` as the bearer token, and the ``openai`` preset did the same once ``base_url`` was overridden, so a bot
pointed at a custom or local URL handed the OpenAI key to it.
"""

from __future__ import annotations

import httpx
import pytest

from hutch.providers import ChatRequest, make_provider
from hutch.providers.base import ProviderError
from hutch.providers.claude import ClaudeProvider

SECRET = "sk-test-secret-0123456789"


def _bearer_seen(provider) -> str | None:
    """Make one request through the provider's real HTTP client and report the Authorization header it carried."""
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"data": []})

    client = provider._http()
    provider._client = httpx.Client(base_url=provider.base_url, headers=dict(client.headers),
                                    transport=httpx.MockTransport(handler))
    provider.probe_models()
    return seen.get("auth")


@pytest.mark.parametrize("provider,base_url", [
    ("openai-compatible", "http://evil.example/v1"),
    ("openai-compatible", "http://localhost:9999/v1"),
    ("openai", "http://evil.example/v1"),                    # preset with an overridden URL
    ("openai", "http://api.openai.com/v1"),                  # plain http to the right host would expose the key on the wire
    ("openai", "https://api.openai.com.evil.example/v1"),    # look-alike host
    ("openai", "https://evil.example/https://api.openai.com/v1"),
])
def test_ambient_openai_key_is_not_sent_to_other_endpoints(provider, base_url):
    p = make_provider(provider, base_url, env={"OPENAI_API_KEY": SECRET})
    assert _bearer_seen(p) is None


def test_openai_preset_still_gets_its_own_key():
    p = make_provider("openai", None, env={"OPENAI_API_KEY": SECRET})
    assert p.base_url == "https://api.openai.com/v1"
    assert _bearer_seen(p) == f"Bearer {SECRET}"


def test_openai_preset_with_the_official_url_spelled_out_keeps_its_key():
    p = make_provider("openai", "https://api.openai.com/v1", env={"OPENAI_API_KEY": SECRET})
    assert _bearer_seen(p) == f"Bearer {SECRET}"


def test_custom_endpoint_uses_only_the_explicit_hutch_variable():
    env = {"OPENAI_API_KEY": SECRET, "HUTCH_API_KEY": "custom-endpoint-key"}
    p = make_provider("openai-compatible", "http://my-vllm.lan:8000/v1", env=env)
    assert _bearer_seen(p) == "Bearer custom-endpoint-key"


def test_a_withheld_key_is_explained_when_the_endpoint_rejects_the_request():
    p = make_provider("openai-compatible", "http://evil.example/v1", env={"OPENAI_API_KEY": SECRET})
    resp = httpx.Response(401, json={"error": {"message": "no key"}})
    err = p._error_from_response(resp)
    assert err.kind == "auth"
    assert "HUTCH_API_KEY" in str(err) and SECRET not in str(err)


def test_legacy_routing_is_an_explicit_unsafe_opt_in():
    env = {"OPENAI_API_KEY": SECRET, "HUTCH_LEGACY_KEY_ROUTING": "1"}
    p = make_provider("openai-compatible", "http://evil.example/v1", env=env)
    assert _bearer_seen(p) == f"Bearer {SECRET}"


def test_anthropic_key_is_not_sent_to_a_custom_base_url(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    p = make_provider("anthropic", "http://evil.example")
    assert isinstance(p, ClaudeProvider) and p.api_key == ""
    with pytest.raises(ProviderError) as exc:
        p._c()
    assert exc.value.kind == "auth" and "api.anthropic.com" in str(exc.value) and SECRET not in str(exc.value)


def test_anthropic_key_is_used_for_the_official_host(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    assert make_provider("anthropic", None).api_key == SECRET
    assert make_provider("anthropic", "https://api.anthropic.com").api_key == SECRET


def test_anthropic_base_url_from_the_environment_cannot_redirect_the_ambient_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://evil.example")
    assert make_provider("anthropic", None).api_key == ""


def test_explicit_key_passed_by_a_connection_is_never_filtered():
    """A connection names its own key and endpoint on purpose; that path is unchanged."""
    p = ClaudeProvider(api_key="conn-key", base_url="https://plan.example/anthropic", provider_name="plan")
    assert p.api_key == "conn-key"
    assert ChatRequest  # the explicit-key path does not go through the ambient filter
