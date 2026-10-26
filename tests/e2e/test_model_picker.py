"""The model picker's quick selection and vendor marks.

The catalog is a fixed, synthetic list served from a route intercept, so nothing contacts a provider. Roles, ids and
`data-spec` values are unchanged from the picker that existed before (tests/e2e/test_browser.py covers its authority:
validation, one-message override, saving a default); this file covers what quick selection added.
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit

import pytest

pw = pytest.importorskip("playwright.sync_api")
expect = pw.expect

from tests.e2e.test_design_system import app_server, browser  # noqa: E402,F401

CATALOG = {"default": "ollama/qwen3:8b", "models": [
    {"spec": "ollama/qwen3:8b", "label": "qwen3:8b", "group": "This bot", "state": "ready", "default": True, "hosted": False,
     "note": "this bot's own model", "worst_case_usd": 0},
    {"spec": "ollama/llama3.1:8b", "label": "llama3.1:8b", "group": "On this machine", "state": "ready", "hosted": False,
     "note": "Fast general model", "worst_case_usd": 0},
    {"spec": "ollama/gemma3:27b", "label": "gemma3:27b", "group": "On this machine", "state": "wont_fit", "hosted": False,
     "fix": "Needs about 24 GB of memory; this computer has 16 GB."},
    {"spec": "openai/gpt-5.1", "label": "gpt-5.1", "group": "Hosted", "state": "ready", "hosted": True,
     "note": "Best for long documents", "worst_case_usd": 0.42},
    {"spec": "openai/gpt-5.1-mini", "label": "gpt-5.1-mini", "group": "Hosted", "state": "ready", "hosted": True,
     "note": "Low cost for everyday work", "worst_case_usd": 0.03},
    {"spec": "anthropic/claude-sonnet-5-5", "label": "claude-sonnet-5-5", "group": "Hosted", "state": "setup", "hosted": True,
     "fix": "Connect Anthropic in Apps & AI to use this model."},
    {"spec": "openrouter/deepseek/deepseek-v3.2", "label": "deepseek-v3.2", "group": "Hosted", "state": "ready", "hosted": True,
     "note": "Search OpenRouter for more", "worst_case_usd": 0.01},
]}


@pytest.fixture()
def picker(browser, app_server):
    base, _app = app_server
    context = browser.new_context(viewport={"width": 1280, "height": 900}, reduced_motion="reduce")
    page = context.new_page()
    errors: list[str] = []
    external: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external.append(request.url) if urlsplit(request.url).hostname not in {"127.0.0.1", "localhost"} else None)
    page.route("**/api/bots/*/models*", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(CATALOG)))
    page.goto(f"{base}/#/chat/design-system-review", wait_until="domcontentloaded")
    page.locator(".ms-btn").wait_for()
    yield page, base
    assert not errors, errors
    assert not external, external          # marks are bundled artwork and monograms: nothing is fetched
    context.close()


def _open_menu(page):
    page.locator(".ms-btn").click()
    page.locator(".ms-menu .ms-item").first.wait_for()


def test_every_model_wears_a_vendor_mark_with_a_where_it_runs_badge(picker):
    page, _ = picker
    _open_menu(page)
    row = lambda spec: page.locator(f'.ms-menu .ms-item[data-spec="{spec}"]')
    # bundled artwork where we have it, a family monogram otherwise
    assert row("openai/gpt-5.1").locator(".ms-mark.has-brand img").get_attribute("src") == "/static/brands/openai-white-monoblossom.svg"
    assert row("ollama/qwen3:8b").locator(".ms-mark-letter").get_attribute("data-letter") == "Q"
    assert row("ollama/llama3.1:8b").locator(".ms-mark-letter").get_attribute("data-letter") == "L"
    assert row("openrouter/deepseek/deepseek-v3.2").locator(".ms-mark-letter").get_attribute("data-letter") == "D"
    # the badge keeps what the old cloud/chip icon said: runs here, or leaves this machine
    assert row("ollama/qwen3:8b").locator(".ms-mark-where.is-local").count() == 1
    assert row("openai/gpt-5.1").locator(".ms-mark-where.is-hosted").count() == 1
    # decorative: the letter is generated content, so the pill's text is just the model's name
    assert page.locator(".ms-btn").inner_text().strip() == page.locator(".ms-btn .ms-label").inner_text().strip()
    # the name and where it runs are still in text
    assert page.locator(".ms-menu .ms-mark").first.evaluate("el => el.closest('[aria-hidden=true]') !== null")
    assert "leaves this machine" in row("openai/gpt-5.1").inner_text() + row("openai/gpt-5.1").locator(".visually-hidden").inner_text()
    # the pill beside the composer carries the mark of the route in use
    assert page.locator(".ms-btn .ms-route-icon .ms-mark").count() == 1


def test_quick_picks_lead_with_the_default_what_is_in_use_and_what_was_chosen_lately(picker):
    page, base = picker
    _open_menu(page)
    assert page.locator(".ms-menu .ms-section").all_inner_texts()[0] != "Quick picks", "no recents yet, so no separate group"
    page.keyboard.press("2")                                  # llama3.1:8b is the second row
    page.locator(".ms-btn.is-custom").wait_for()
    _open_menu(page)
    page.keyboard.press("4")                                  # then a hosted route
    chosen = page.locator(".ms-btn .ms-label").inner_text()
    _open_menu(page)
    assert page.locator(".ms-menu .ms-section").all_inner_texts()[0] == "Quick picks"
    quick = page.locator('.ms-menu .ms-section:has-text("Quick picks") ~ .ms-item[role=menuitemradio]')
    names = quick.locator(".ms-item-name").all_inner_texts()[:3]
    assert names[0] == "qwen3:8b", names                        # the default is always first
    assert names[1] == chosen, names                            # then what is in use
    assert "llama3.1:8b" in names, names                        # then what was chosen lately
    # recents belong to the assistant and survive a reload
    page.reload()
    page.locator(".ms-btn").wait_for()
    _open_menu(page)
    assert page.locator(".ms-menu .ms-section").all_inner_texts()[0] == "Quick picks"


def test_number_keys_choose_a_row_and_slash_opens_the_searchable_list(picker):
    page, _ = picker
    _open_menu(page)
    keys = page.locator('.ms-menu .ms-item[role=menuitemradio]').evaluate_all("els => els.map(el => [el.dataset.key, el.dataset.spec])")
    assert [key for key, _spec in keys] == [str(n) for n in range(1, len(keys) + 1)], keys
    assert page.locator(".ms-menu .ms-key").first.inner_text() == "1"
    assert page.locator('.ms-menu .ms-item[data-key="2"]').get_attribute("aria-keyshortcuts") == "2"
    page.keyboard.press("2")
    page.locator(".ms-btn.is-custom").wait_for()
    assert page.locator(".ms-btn .ms-label").inner_text() == dict(keys)["2"].split("/", 1)[1]
    assert page.locator(".ms-menu").is_hidden(), "choosing closes the menu"
    _open_menu(page)
    page.keyboard.press("/")
    page.locator(".ms-all").wait_for()
    expect(page.locator(".ms-search")).to_be_focused()


def test_the_full_list_filters_and_chooses_from_the_keyboard_without_duplicate_choices(picker):
    page, _ = picker
    _open_menu(page)
    page.keyboard.press("/")
    page.locator(".ms-all").wait_for()
    search = page.locator(".ms-search")
    # one radio per route, always (a Recent group moves a row, it never copies it)
    values = page.locator('input[name="ms-pick"]').evaluate_all("els => els.map(el => el.value)")
    assert len(values) == len(set(values)), values
    # filter chips narrow the same list
    page.get_by_role("button", name="Hosted", exact=True).click()
    assert page.get_by_role("button", name="Hosted", exact=True).get_attribute("aria-pressed") == "true"
    assert page.locator(".ms-row:visible").count() == 4          # gpt-5.1, gpt-5.1-mini, claude (needs setup), deepseek
    page.get_by_role("button", name="On this machine", exact=True).click()
    assert page.locator(".ms-row:visible").count() == 3 and page.locator('.ms-row:visible[data-kind="hosted"]').count() == 0
    page.get_by_role("button", name="Ready now", exact=True).click()
    assert page.locator('.ms-row:visible[data-ready="false"]').count() == 0
    page.get_by_role("button", name="All", exact=True).click()
    # arrows move the choice from the search field, Enter uses it
    search.fill("gpt")
    assert page.locator(".ms-row:visible").count() == 2
    search.press("ArrowDown")
    first = page.locator('input[name="ms-pick"]:checked').get_attribute("value")
    search.press("ArrowDown")
    second = page.locator('input[name="ms-pick"]:checked').get_attribute("value")
    assert first != second and {first, second} == {"openai/gpt-5.1", "openai/gpt-5.1-mini"}
    expect(search).to_be_focused()
    search.press("Enter")
    page.locator(".ms-btn.is-custom").wait_for()
    assert page.locator(".ms-btn .ms-label").inner_text() == second.split("/", 1)[1]


def test_the_palette_opens_the_picker_on_a_chat_page_and_only_there(picker):
    page, base = picker
    page.keyboard.press("Control+k")
    page.get_by_role("combobox", name="Search assistants, conversations and pages").fill("model")
    option = page.locator("dialog.palette").get_by_role("option", name="Choose a model")
    expect(option).to_be_visible()
    page.keyboard.press("Enter")
    page.locator(".ms-menu .ms-item").first.wait_for()
    assert page.locator(".ms-btn").get_attribute("aria-expanded") == "true"
    page.keyboard.press("Escape")
    page.goto(f"{base}/#/overview", wait_until="domcontentloaded")
    page.locator("#view").wait_for()
    page.keyboard.press("Control+k")
    page.get_by_role("combobox", name="Search assistants, conversations and pages").fill("choose a model")
    assert page.locator("dialog.palette").get_by_role("option", name="Choose a model").count() == 0
