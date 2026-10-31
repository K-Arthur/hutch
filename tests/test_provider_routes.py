"""Hosted OpenAI-compatible routes: template -> adapter wiring, key scoping and evidence agreement.

These tests establish that Hutch has a real connection path to each endpoint and that the recorded
reachability artifact still describes the endpoint the template uses. They do not establish that any
model, account or capability works; that needs an authenticated call and is recorded separately.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hutch.connections import ConnectionBook, load_templates
from hutch.providers.base import ProviderError
from hutch.providers.catalog import bundled_catalog
from hutch.providers.connection import probe_connection_typed, provider_for_connection
from hutch.providers.openai_compat import OpenAICompatProvider

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (ROOT / "docs/research/2026-10-provider-platform/artifacts/live-verification"
            / "endpoint-reachability-2026-10-31.json")

#: Routes added by the 2026-10-31 slice. Each is a real OpenAI-compatible connection, not a catalogue row.
ROUTES = {
    "mistral": "https://api.mistral.ai/v1",
    "xai": "https://api.x.ai/v1",
    "minimax": "https://api.minimax.io/v1",
    "moonshot": "https://api.moonshot.ai/v1",
    "zai": "https://api.z.ai/api/paas/v4",
    "cohere": "https://api.cohere.ai/compatibility/v1",
    "stepfun": "https://api.stepfun.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "cerebras": "https://api.cerebras.ai/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "together": "https://api.together.xyz/v1",
    "deepinfra": "https://api.deepinfra.com/v1/openai",
    "novita": "https://api.novita.ai/openai/v1",
    "chutes": "https://llm.chutes.ai/v1",
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "huggingface": "https://router.huggingface.co/v1",
    "synthetic": "https://api.synthetic.new/v1",
    "venice": "https://api.venice.ai/api/v1",
    "gmi-cloud": "https://api.gmi-serving.com/v1",
    "arcee": "https://api.arcee.ai/api/v1",
    "ollama-cloud": "https://ollama.com/v1",
    "volcengine": "https://ark.cn-beijing.volces.com/api/v3",
    "tencent-cloud": "https://tokenhub.tencentmaas.com/v1",
    "kilocode": "https://api.kilo.ai/api/gateway/v1",
    "byteplus": "https://ark.ap-southeast.bytepluses.com/api/v3",
}


@pytest.fixture()
def catalogue():
    return bundled_catalog()


def test_each_route_is_a_real_openai_compatible_connection(tmp_path, monkeypatch):
    templates = load_templates()
    for provider, base_url in ROUTES.items():
        template = templates[provider]
        assert template["provider"] == provider
        assert template["protocol"] == "openai-chat"
        assert template["base_url"] == base_url
        assert template["models_endpoint"] is True
        assert template["auth_method"] == "api_key"

        monkeypatch.setenv(template["api_key_env"], "route-test-key")
        book = ConnectionBook(tmp_path / provider, )
        book.add(provider, f"acct-{provider}")
        assert book.key(f"acct-{provider}") == "route-test-key"

        conn = provider_for_connection(book, f"acct-{provider}", "some-model")
        assert isinstance(conn, OpenAICompatProvider)
        assert conn.base_url == base_url


def test_a_route_never_uses_another_providers_ambient_key(tmp_path, monkeypatch):
    """OPENAI_API_KEY must not reach a non-OpenAI host just because the route is OpenAI-shaped."""
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-openai-key")
    templates = load_templates()
    for provider in ROUTES:
        monkeypatch.delenv(templates[provider]["api_key_env"], raising=False)
        book = ConnectionBook(tmp_path / f"state-{provider}")
        book.add(provider, f"owned-{provider}")
        with pytest.raises(ProviderError) as excinfo:
            provider_for_connection(book, f"owned-{provider}", "some-model")
        assert excinfo.value.kind == "auth"


def test_a_keyless_route_is_reported_as_needing_authentication(tmp_path):
    book = ConnectionBook(tmp_path / "state")
    book.add("groq", "groq-personal")
    result = probe_connection_typed(book, "groq-personal")
    assert result.state != "verified"
    assert result.kind == "auth"


def test_catalogue_marks_every_route_implemented_unverified(catalogue):
    for provider in ROUTES:
        row = catalogue.require(provider)
        assert row.integration_status == "implemented-unverified", provider
        assert row.connection_templates == (provider,), provider
        assert row.auth("api-key").status == "implemented", provider


def test_templates_match_the_recorded_reachability_evidence():
    evidence = json.loads(EVIDENCE.read_text())
    assert evidence["checked_on"] == "2026-10-31"
    probed = {row["provider"]: row for row in evidence["probes"]}
    assert set(probed) == set(ROUTES), "evidence and route table must describe the same routes"
    templates = load_templates()
    for provider, base_url in ROUTES.items():
        assert probed[provider]["url"] == base_url + "/models"
        assert templates[provider]["base_url"] == base_url
        # A probe that never reached the host (0) or failed server-side cannot back a template.
        assert probed[provider]["status"] not in (0,), provider
        assert probed[provider]["status"] < 500, provider


def test_every_catalogue_status_has_a_readable_label(catalogue):
    """A person reading the page must not get the stored slug, and the label must say what it claims."""
    from hutch.providers.catalog import INTEGRATION_STATUSES, STATUS_TEXT

    assert set(STATUS_TEXT) == set(INTEGRATION_STATUSES), "every stored status needs a label and a meaning"
    for provider in catalogue.providers:
        label, meaning = provider.status_label, provider.status_meaning
        assert label and meaning, provider.id
        assert label != provider.integration_status, provider.id
        assert "-" not in label, f"{provider.id}: label still reads like a slug ({label!r})"
        # "route only, untested" must never read as a working integration.
        if provider.integration_status == "implemented-unverified":
            assert "no live account" in meaning, provider.id
        if provider.integration_status in ("blocked", "retired"):
            assert "does not" in meaning or "not " in meaning, provider.id
