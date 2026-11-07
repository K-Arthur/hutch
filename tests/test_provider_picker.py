"""The route picker and the resolved tuple on provider and Models pages, through the real app."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from hutch.connections import ConnectionBook
from hutch.models import ApprovalMode, Bot
from hutch.server.app import create_app


@pytest.fixture()
def env(tmp_path, monkeypatch):
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    directory = tmp_path / "state"
    monkeypatch.setenv("HUTCH_STATE_DIR", str(directory))
    with TestClient(create_app()) as client:
        yield client, directory


def _result(html: str) -> str:
    start = html.index('id="route-picker-result"')
    return html[start:html.index("</section>", start)]


def _field(result: str, label: str) -> str:
    match = re.search(rf"<dt>{label}</dt><dd[^>]*>(.*?)</dd>", result, re.S)
    assert match, label
    return re.sub(r"<[^>]+>", " ", match.group(1)).split()


def test_without_a_model_the_picker_asks_for_one_and_resolves_nothing(env):
    client, _ = env
    result = _result(client.get("/providers/deepseek").text)
    assert "Enter a model id to see its route." in result and 'class="resolution"' not in result


def test_a_provider_with_no_account_says_so_and_is_not_green(env):
    client, _ = env
    result = _result(client.get("/providers/deepseek", params={"pick_model": "some-model"}).text)
    assert " ".join(_field(result, "Account")) == "no account chosen no configured account"
    assert "chip st-succeeded" not in result and "Hutch never substitutes" in result


def test_a_named_account_resolves_with_its_billing_and_endpoint(env):
    client, directory = env
    book = ConnectionBook(directory)
    book.add("deepseek", "deepseek-work")
    book.set_key("deepseek-work", "sk-picker-placeholder")
    page = client.get("/providers/deepseek", params={"pick_account": "deepseek-work", "pick_model": "m1"}).text
    result = _result(page)
    assert _field(result, "Account")[0] == "deepseek-work" and "named connection" in " ".join(_field(result, "Account"))
    assert "Per-token API billing" in " ".join(_field(result, "Billing"))
    assert "api.deepseek.com" in " ".join(_field(result, "Endpoint"))
    assert "sk-picker-placeholder" not in page
    assert 'value="deepseek-work" selected' in page


def test_two_accounts_and_no_choice_is_reported_never_picked(env):
    client, directory = env
    book = ConnectionBook(directory)
    book.add("deepseek", "deepseek-a")
    book.add("deepseek", "deepseek-b")
    result = _result(client.get("/providers/deepseek", params={"pick_account": "deepseek", "pick_model": "m1"}).text)
    assert "not chosen: 2 named account(s)" in " ".join(_field(result, "Account"))
    assert "no account chosen" in " ".join(_field(result, "Account"))


def test_an_unknown_account_or_runtime_in_the_url_is_not_trusted(env):
    client, _ = env
    page = client.get("/providers/deepseek", params={"pick_account": "not-mine", "pick_model": "m1",
                                                      "pick_runtime": "no-such-runtime"}).text
    result = _result(page)
    assert "deepseek/m1" in " ".join(_field(result, "Route"))
    assert " ".join(_field(result, "Runtime")).startswith("builtin")


def test_every_query_parameter_is_bound_to_its_own_name(env):
    """Regression: one shared Query object bound all three picker parameters to the first name."""
    client, directory = env
    ConnectionBook(directory).add("deepseek", "deepseek-work")
    page = client.get("/providers/deepseek", params={"pick_account": "deepseek-work", "pick_model": "model-x",
                                                      "pick_runtime": "opencode"}).text
    assert 'value="model-x"' in page and 'value="deepseek-work" selected' in page
    assert 'value="opencode" selected' in page


def test_the_models_page_shows_the_resolved_route_for_each_saved_route(env):
    client, directory = env
    ConnectionBook(directory).add("deepseek", "deepseek-work")
    client.app.state.store.create_bot(Bot(name="resolver-bot", model="deepseek-work/deepseek-chat",
                                          tools=[], approval_mode=ApprovalMode.ask))
    page = client.get("/models").text
    assert "Resolved route: who pays, runtime and endpoint" in page
    assert 'aria-label="Resolved route for deepseek-work/deepseek-chat"' in page
    section = page[page.index('aria-label="Resolved route for deepseek-work/deepseek-chat"'):]
    assert "named connection" in section[:900] and "Per-token API billing" in section[:900]


def test_strict_offline_refuses_a_hosted_route_in_the_policys_own_words(env):
    client, _ = env
    result = _result(client.get("/providers/deepseek", params={"pick_model": "m1", "pick_mode": "offline"}).text)
    mode = " ".join(_field(result, "Inference mode"))
    assert mode.startswith("refused") and "not an allowed local model route" in mode
    assert "chip st-failed" in result
    assert " ".join(_field(result, "Next step")) == "Choose a local model route, or switch the inference mode to Hybrid."
    assert "Exercise the route" not in result


def test_strict_offline_allows_a_loopback_route_without_calling_it_working(env):
    client, _ = env
    result = _result(client.get("/providers/ollama", params={"pick_model": "tiny", "pick_mode": "offline"}).text)
    mode = " ".join(_field(result, "Inference mode"))
    assert mode.startswith("allowed") and "Strict Offline allows this route" in mode
    assert "chip st-succeeded" not in result.split("Inference mode")[1].split("</dd>")[0]


def test_hybrid_and_an_unknown_mode_add_no_mode_row_and_the_choice_is_kept(env):
    client, _ = env
    for mode in ("hybrid", "not-a-mode", ""):
        page = client.get("/providers/deepseek", params={"pick_model": "m1", "pick_mode": mode}).text
        assert "Inference mode</dt>" not in _result(page), mode
    page = client.get("/providers/deepseek", params={"pick_model": "m1", "pick_mode": "local"}).text
    assert 'value="local" selected' in page and "Inference mode</dt>" in _result(page)
