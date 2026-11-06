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


#: Templates moved to a vendor-documented path after the 2026-10-31 reachability evidence was recorded. The
#: recorded probe still describes the legacy URL (both answer HTTP 200); the new path was probed 2026-11-06.
MOVED = {"synthetic": "https://api.synthetic.new/openai/v1"}


@pytest.fixture()
def catalogue():
    return bundled_catalog()


def test_each_route_is_a_real_openai_compatible_connection(tmp_path, monkeypatch):
    templates = load_templates()
    for provider, base_url in ROUTES.items():
        template = templates[provider]
        assert template["provider"] == provider
        assert template["protocol"] == "openai-chat"
        assert template["base_url"] == MOVED.get(provider, base_url)
        assert template["models_endpoint"] is True
        assert template["auth_method"] == "api_key"

        monkeypatch.setenv(template["api_key_env"], "route-test-key")
        book = ConnectionBook(tmp_path / provider, )
        book.add(provider, f"acct-{provider}")
        assert book.key(f"acct-{provider}") == "route-test-key"

        conn = provider_for_connection(book, f"acct-{provider}", "some-model")
        assert isinstance(conn, OpenAICompatProvider)
        assert conn.base_url == MOVED.get(provider, base_url)


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
        assert provider in row.connection_templates, provider
        assert row.auth("api-key").status == "implemented", provider


def test_templates_match_the_recorded_reachability_evidence():
    evidence = json.loads(EVIDENCE.read_text())
    assert evidence["checked_on"] == "2026-10-31"
    probed = {row["provider"]: row for row in evidence["probes"]}
    assert set(probed) == set(ROUTES), "evidence and route table must describe the same routes"
    templates = load_templates()
    for provider, base_url in ROUTES.items():
        assert probed[provider]["url"] == base_url + "/models"
        assert templates[provider]["base_url"] == MOVED.get(provider, base_url)
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


def test_a_connection_can_declare_a_separate_catalogue_url(tmp_path):
    """OpenCode Go serves chat at /go/openai/v1 but documents its model list at /go/v1."""
    book = ConnectionBook(tmp_path / "state")
    book.add("opencode-go", "go")
    book.set_key("go", "test-key")
    conn = book.get("go")
    assert conn.models_base_url == "https://opencode.ai/inference/go/v1"
    provider = provider_for_connection(book, "go", "glm-5.3")
    assert provider.base_url == "https://opencode.ai/inference/go/openai/v1"
    assert provider.catalog_url == "https://opencode.ai/inference/go/v1"
    assert provider._catalog() == "https://opencode.ai/inference/go/v1/models"


def test_an_overridden_base_url_takes_the_catalogue_with_it(tmp_path):
    """Chat and discovery must never point at different hosts."""
    book = ConnectionBook(tmp_path / "state")
    book.add("opencode-go", "local-go", base_url="https://gateway.example.test/v1")
    conn = book.get("local-go")
    assert conn.models_base_url == "", "a template catalogue URL must not survive a different base host"
    book.set_key("local-go", "test-key")
    provider = provider_for_connection(book, "local-go", "glm-5.3")
    assert provider._catalog() == "/models"


def test_the_catalogue_url_cannot_embed_credentials(tmp_path):
    with pytest.raises(ValueError):
        ConnectionBook(tmp_path / "state").add(
            "opencode-go", "bad", models_base_url="https://user:pass@opencode.ai/inference/go/v1")


def test_a_redirect_is_refused_and_the_key_never_leaves_the_host():
    """A 3xx would move the bearer key to whatever host Location names, so it is reported, not followed."""
    import http.server
    import socketserver
    import threading

    hits = []

    class Target(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append({"path": self.path, "auth": self.headers.get("Authorization")})
            body = b'{"object": "list", "data": [{"id": "leaked-model"}]}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    target = socketserver.TCPServer(("127.0.0.1", 0), Target)
    threading.Thread(target=target.serve_forever, daemon=True).start()

    class Origin(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{target.server_address[1]}/v1/models")
            self.end_headers()

        def log_message(self, *args):
            pass

    origin = socketserver.TCPServer(("127.0.0.1", 0), Origin)
    threading.Thread(target=origin.serve_forever, daemon=True).start()
    try:
        provider = OpenAICompatProvider(f"http://127.0.0.1:{origin.server_address[1]}/v1",
                                        "secret-connection-key", provider_name="redirect-test")
        ok, detail, models = provider.probe_models()
        assert not ok and models == []
        assert "does not follow endpoint redirects" in detail
        assert "set the connection endpoint to the final url" in detail.lower()
        assert hits == [], "the redirect target must never receive the request or the key"
        assert provider.health().ok is False, "health must not call a redirecting endpoint healthy"
    finally:
        origin.shutdown()
        target.shutdown()
