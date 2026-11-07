"""Provider detail page and wizard actions through the real app: state on disk, CSRF, ownership, secrets."""

from __future__ import annotations

import re
import stat
from types import SimpleNamespace
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from hutch.connections import ConnectionBook
from hutch.providers.capabilities import CAPABILITIES
from hutch.server.app import create_app


@pytest.fixture()
def env(tmp_path, monkeypatch):
    for name in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "OPENCODE_API_KEY", "FAL_KEY"):
        monkeypatch.delenv(name, raising=False)
    directory = tmp_path / "state"
    monkeypatch.setenv("HUTCH_STATE_DIR", str(directory))
    with TestClient(create_app()) as client:
        yield client, directory


def _token(client) -> str:
    return re.search(r'name="csrf" content="([^"]+)"', client.get("/providers").text).group(1)


def _post(client, path, **data):
    return client.post(path, data={"csrf": _token(client), **data}, follow_redirects=False)


def _flash(response, kind="notice") -> str:
    """The flash text the redirect carries (a short-lived cookie), decoded."""
    return " ".join(unquote(cookie) for cookie in response.headers.get_list("set-cookie"))


def test_an_unknown_provider_is_a_404_for_the_page_and_every_action(env):
    client, _ = env
    assert client.get("/providers/no-such-provider").status_code == 404
    assert _post(client, "/providers/no-such-provider/connect", template="deepseek").status_code == 404
    assert _post(client, "/providers/no-such-provider/accounts/x/key", key="k").status_code == 404


def test_the_wizard_adds_an_account_then_stores_a_key_with_owner_only_permissions(env):
    client, directory = env
    page = client.get("/providers/deepseek").text
    assert 'data-step="add"' in page and 'aria-current="step"' in page
    added = _post(client, "/providers/deepseek/connect", template="deepseek", name="deepseek-work", route="api-key")
    assert added.status_code == 303
    assert added.headers["location"] == "/providers/deepseek?account=deepseek-work#route-api-key"
    assert "deepseek-work" in ConnectionBook(directory).names()
    stored = _post(client, "/providers/deepseek/accounts/deepseek-work/key", key="  sk-wizard-page-secret  ", route="api-key")
    assert stored.status_code == 303
    book = ConnectionBook(directory)
    assert book.key("deepseek-work") == "sk-wizard-page-secret"
    assert stat.S_IMODE(book.key_file("deepseek-work").stat().st_mode) == 0o600
    after = client.get("/providers/deepseek?account=deepseek-work").text
    assert "sk-wizard-page-secret" not in after
    assert re.search(r'data-state="done" data-step="key"', after)


def test_every_wizard_action_refuses_a_missing_csrf_token(env):
    client, _ = env
    for path in ("/providers/deepseek/connect", "/providers/deepseek/accounts/x/key",
                 "/providers/deepseek/accounts/x/ack", "/providers/deepseek/accounts/x/test"):
        assert client.post(path, data={"template": "deepseek"}, follow_redirects=False).status_code == 403, path


def test_an_account_of_another_provider_cannot_be_acted_on_through_this_one(env):
    client, directory = env
    ConnectionBook(directory).add("deepseek", "deepseek-work")
    for action, extra in (("key", {"key": "k"}), ("ack", {"agree": "1"}), ("test", {})):
        response = _post(client, f"/providers/openai/accounts/deepseek-work/{action}", **extra)
        assert response.status_code == 404, action
    assert not ConnectionBook(directory).key_file("deepseek-work").exists()


def test_a_template_of_another_provider_is_refused_and_creates_nothing(env):
    client, directory = env
    response = _post(client, "/providers/deepseek/connect", template="openai-api", name="sneaky", route="api-key")
    assert response.status_code == 303 and "sneaky" not in ConnectionBook(directory).names()
    assert "not an account type for DeepSeek" in _flash(response, "error")


def test_a_vendor_template_cannot_be_pointed_at_another_host_from_the_wizard(env):
    client, directory = env
    _post(client, "/providers/deepseek/connect", template="deepseek", name="deepseek-x",
          base_url="https://evil.example/v1", route="api-key")
    conn = ConnectionBook(directory).get("deepseek-x")
    assert conn is not None and "evil.example" not in conn.base_url and conn.base_url.startswith("https://api.deepseek.com")


def test_a_custom_endpoint_accepts_the_operators_base_url(env):
    client, directory = env
    _post(client, "/providers/custom-compatible/connect", template="custom-openai", name="my-server",
          base_url="https://models.example.org/v1", route="custom-endpoint")
    conn = ConnectionBook(directory).get("my-server")
    assert conn is not None and conn.base_url == "https://models.example.org/v1"


def test_an_empty_key_is_refused_and_a_taken_name_is_reported(env):
    client, directory = env
    _post(client, "/providers/deepseek/connect", template="deepseek", name="deepseek-work", route="api-key")
    empty = _post(client, "/providers/deepseek/accounts/deepseek-work/key", key="   ", route="api-key")
    assert "empty" in _flash(empty, "error") and not ConnectionBook(directory).key_file("deepseek-work").exists()
    again = _post(client, "/providers/deepseek/connect", template="deepseek", name="deepseek-work", route="api-key")
    assert "already exists" in _flash(again, "error")


def test_terms_need_the_checkbox_and_then_move_the_step_to_done(env):
    client, directory = env
    _post(client, "/providers/opencode-go/connect", template="opencode-go", name="go", route="api-key")
    _post(client, "/providers/opencode-go/accounts/go/key", key="sk-go-placeholder", route="api-key")
    page = client.get("/providers/opencode-go?account=go").text
    assert re.search(r'data-state="current" data-step="ack"', page)
    refused = _post(client, "/providers/opencode-go/accounts/go/ack", route="api-key")
    assert "Tick the box" in _flash(refused, "error")
    assert re.search(r'data-state="current" data-step="ack"', client.get("/providers/opencode-go?account=go").text)
    _post(client, "/providers/opencode-go/accounts/go/ack", agree="1", route="api-key")
    done = client.get("/providers/opencode-go?account=go").text
    assert re.search(r'data-state="done" data-step="ack"', done) and re.search(r'data-state="current" data-step="test"', done)


def test_the_test_action_reports_the_connection_checks_own_words(env, monkeypatch):
    client, directory = env
    _post(client, "/providers/deepseek/connect", template="deepseek", name="deepseek-work", route="api-key")
    monkeypatch.setattr("hutch.server.pages_provider_detail.check_connection",
                        lambda book, name: SimpleNamespace(ok=False, detail="the provider answered HTTP 401"))
    failed = _post(client, "/providers/deepseek/accounts/deepseek-work/test", route="api-key")
    assert "the provider answered HTTP 401" in _flash(failed, "error")
    monkeypatch.setattr("hutch.server.pages_provider_detail.check_connection",
                        lambda book, name: SimpleNamespace(ok=True, detail="model list answered"))
    assert "model list answered" in _flash(_post(client, "/providers/deepseek/accounts/deepseek-work/test"))


def test_a_route_hutch_has_not_built_shows_its_status_and_no_form(env):
    client, _ = env
    page = client.get("/providers/alibaba-model-studio").text
    wizard = page[page.index('class="wizard"'):page.index("</ol>")]
    assert "<form" not in wizard and 'data-state="info"' in wizard and "Not built" in wizard
    blocked = client.get("/providers/github-copilot").text
    assert 'data-state="blocked"' in blocked and "<form" not in blocked[blocked.index('class="wizard"'):blocked.index("</ol>")]


def test_the_evidence_table_lists_every_capability_and_never_hides_what_is_unknown(env):
    client, _ = env
    page = client.get("/providers/deepseek").text
    table = page[page.index('class="capability-table"'):page.index("</table>")]
    assert table.count("<tr>") == len(CAPABILITIES) + 1            # header row plus one per capability
    assert "unverified" in table and "live-verified" in table      # DeepSeek text has a dated live run
    unknown = client.get("/providers/qianfan").text
    assert "live-verified" not in unknown[unknown.index('class="capability-table"'):unknown.index("</table>")]


def test_a_media_only_vendor_names_its_environment_variable_and_offers_no_key_form(env, monkeypatch):
    client, _ = env
    page = client.get("/providers/fal").text
    assert "FAL_KEY" in page and "ambient" in page and 'name="key"' not in page
    monkeypatch.setenv("FAL_KEY", "never-render-this-value")
    assert "never-render-this-value" not in client.get("/providers/fal").text


def test_only_a_local_provider_probes_loopback_and_its_page_still_shows_the_server_step(env, monkeypatch):
    client, _ = env
    calls = []

    def fake_probe(**_kwargs):
        calls.append(1)
        return {}

    monkeypatch.setattr("hutch.server.pages_providers.probe_local_services", fake_probe)
    assert client.get("/providers/deepseek").status_code == 200
    assert calls == [], "a hosted provider's page must not probe the loopback services"
    page = client.get("/providers/ollama").text
    assert calls and 'data-step="server"' in page


def test_a_sign_in_template_is_refused_with_a_pointer_to_apps_and_ai_and_never_a_server_error(env):
    """Regression: a crafted POST for the ChatGPT sign-in template raised KeyError and returned a 500."""
    client, directory = env
    response = _post(client, "/providers/openai/connect", template="chatgpt-plan", name="fake-chatgpt", route="chatgpt-sign-in")
    assert response.status_code == 303
    assert "sign-in account" in _flash(response, "error") and "Apps & AI" in _flash(response, "error")
    assert "fake-chatgpt" not in ConnectionBook(directory).names()
