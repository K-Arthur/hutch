"""Per-route setup guides: steps follow real account state, and unbuilt routes never get a form."""

from __future__ import annotations

import pytest

from hutch.connections import ConnectionBook
from hutch.providers.catalog import bundled_catalog
from hutch.providers.wizard import Context, route_guides


@pytest.fixture()
def book(config, monkeypatch):
    for name in ("DEEPSEEK_API_KEY", "OPENCODE_API_KEY", "XIAOMI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    return ConnectionBook(config.state_dir)


def _ctx(provider_id, book, store, *, focus="", local=(), runtimes=(), media_env=""):
    return Context(provider=bundled_catalog().require(provider_id), book=book, store=store,
                   templates=book.templates(), local_services=tuple(local), runtimes=tuple(runtimes),
                   media_env=media_env, focus=focus)


def _guide(provider_id, route_id, book, store, **kw):
    guides = route_guides(_ctx(provider_id, book, store, **kw))
    return next(g for g in guides if g.method.id == route_id)


def _states(guide):
    return {step.key: step.state for step in guide.steps}


def test_every_unbuilt_blocked_or_retired_route_is_one_honest_step_without_a_form(book, store):
    seen = 0
    for provider in bundled_catalog().providers:
        for guide in route_guides(_ctx(provider.id, book, store)):
            if guide.method.status in ("implemented", "experimental"):
                continue
            seen += 1
            assert len(guide.steps) == 1 and not guide.steps[0].form, (provider.id, guide.method.id)
            assert guide.steps[0].state in ("blocked", "info")
            assert guide.steps[0].state == ("blocked" if guide.method.status in ("blocked", "retired") else "info")
    assert seen >= 15


def test_an_api_key_route_walks_add_then_key_then_test_as_state_changes(book, store):
    assert _states(_guide("deepseek", "api-key", book, store)) == {
        "add": "current", "key": "blocked", "test": "blocked", "model": "blocked"}
    book.add("deepseek", "deepseek-work")
    assert _states(_guide("deepseek", "api-key", book, store)) == {
        "add": "done", "key": "current", "test": "blocked", "model": "blocked"}
    book.set_key("deepseek-work", "sk-wizard-placeholder")
    guide = _guide("deepseek", "api-key", book, store)
    assert _states(guide) == {"add": "done", "key": "done", "test": "current", "model": "info"}
    assert [step.form for step in guide.steps if step.form] == ["connect", "key", "test"]
    assert guide.focus == "deepseek-work" and guide.accounts == ("deepseek-work",)


def test_no_step_ever_contains_the_stored_key(book, store):
    book.add("deepseek", "deepseek-work")
    book.set_key("deepseek-work", "sk-wizard-secret-value")
    guide = _guide("deepseek", "api-key", book, store)
    assert all("sk-wizard-secret-value" not in repr(step) for step in guide.steps)
    assert "key file in the state directory" in next(s for s in guide.steps if s.key == "key").body


def test_terms_step_appears_only_when_required_and_clears_after_acknowledgement(book, store):
    book.add("opencode-go", "go")
    book.set_key("go", "sk-go-placeholder")
    guide = _guide("opencode", "cli-sign-in", book, store)   # a different route of another provider: no templates
    assert "ack" not in _states(guide)
    go = _guide("opencode-go", "api-key", book, store)
    assert _states(go)["ack"] == "current" and _states(go)["test"] == "blocked"
    assert next(s for s in go.steps if s.key == "ack").body        # the notice itself is shown
    book.acknowledge(store, "go")
    go = _guide("opencode-go", "api-key", book, store)
    assert _states(go)["ack"] == "done" and _states(go)["test"] == "current"


def test_multi_template_providers_offer_every_template_and_custom_ones_ask_for_a_base_url(book, store):
    xiaomi = _guide("xiaomi", "api-key", book, store)
    choices = {c["id"]: c for c in next(s for s in xiaomi.steps if s.key == "add").data["choices"]}
    assert {"xiaomi", "xiaomi-token-plan-sgp", "xiaomi-token-plan-cn", "xiaomi-token-plan-ams"} <= set(choices)
    custom = _guide("custom-compatible", "custom-endpoint", book, store)
    wants = {c["id"]: c for c in next(s for s in custom.steps if s.key == "add").data["choices"]}
    assert wants["custom-openai"]["needs_base_url"] is True and wants["custom-openai"]["asks_base_url"] is True
    assert choices["xiaomi"]["needs_base_url"] is False and choices["xiaomi"]["asks_base_url"] is False
    litellm = _guide("litellm", "custom-endpoint", book, store)
    ours = next(c for c in next(s for s in litellm.steps if s.key == "add").data["choices"] if c["id"] == "litellm")
    assert ours["needs_base_url"] is False and ours["asks_base_url"] is True      # a default exists, still editable


def test_the_focus_account_is_the_requested_one_when_it_belongs_to_the_route(book, store):
    book.add("deepseek", "deepseek-a")
    book.add("deepseek", "deepseek-b")
    book.set_key("deepseek-b", "sk-b-placeholder")
    assert _guide("deepseek", "api-key", book, store).focus == "deepseek-a"
    focused = _guide("deepseek", "api-key", book, store, focus="deepseek-b")
    assert focused.focus == "deepseek-b" and _states(focused)["key"] == "done"
    assert _guide("deepseek", "api-key", book, store, focus="not-an-account").focus == "deepseek-a"


def test_a_media_only_vendor_has_no_form_and_says_the_variable_is_ambient(book, store, monkeypatch):
    monkeypatch.delenv("FAL_KEY", raising=False)
    missing = _guide("fal", "api-key", book, store, media_env="FAL_KEY")
    assert [s.form for s in missing.steps] == [""] and missing.steps[0].state == "current"
    assert "ambient" in missing.steps[0].body and "not set" in missing.steps[0].body
    monkeypatch.setenv("FAL_KEY", "placeholder-never-shown")
    present = _guide("fal", "api-key", book, store, media_env="FAL_KEY")
    assert present.steps[0].state == "done" and "placeholder-never-shown" not in present.steps[0].body


def test_a_sign_in_route_points_at_apps_and_ai_and_creates_no_account(book, store):
    guide = _guide("openai", "chatgpt-sign-in", book, store)
    step = guide.steps[0]
    assert step.link == ("Open Apps & AI", "/#/connections") and not step.form and step.state == "current"


def test_a_local_route_reports_what_the_probe_found(book, store):
    down = _guide("ollama", "local-service", book, store, local=[{"provider": "ollama", "reachable": False,
                  "url": "http://127.0.0.1:11434/api/tags"}])
    assert down.steps[0].state == "current" and "No answer" in down.steps[0].body
    up = _guide("ollama", "local-service", book, store, local=[{"provider": "ollama", "reachable": True,
                "url": "http://127.0.0.1:11434/api/tags", "models": ["a", "b"]}])
    assert up.steps[0].state == "done" and "2 model(s)" in up.steps[0].body and "not proof" in up.steps[0].body


def test_a_cli_route_reports_whether_the_tool_is_installed(book, store):
    absent = _guide("opencode", "managed-session", book, store, runtimes=[{"id": "opencode", "cli": None}])
    assert absent.steps[0].state == "current" and absent.steps[0].key == "cli"
    present = _guide("opencode", "managed-session", book, store,
                     runtimes=[{"id": "opencode", "cli": {"installed": True, "version": "v2.2.5"}}])
    assert present.steps[0].state == "done" and "v2.2.5" in present.steps[0].body
    assert present.steps[1].state == "current"
