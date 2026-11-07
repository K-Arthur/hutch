"""EC-28 in the browser: a route that leaves this machine asks once, and cancel keeps the default.

The picker fixture serves a synthetic catalogue from the real picker; the model-sharing
endpoint is the real one, so the dialog text and the recorded acknowledgement are the
server's own words.
"""

from __future__ import annotations

import json

from tests.e2e.test_design_system import app_server, browser  # noqa: E402,F401
from tests.e2e.test_model_picker import _confirm_sharing, _open_menu, picker  # noqa: E402,F401


def test_a_hosted_route_asks_before_it_is_used_and_cancel_keeps_the_default(picker):
    page, _ = picker
    _open_menu(page)
    page.keyboard.press("/")
    page.locator(".ms-all").wait_for()
    page.locator('input[name="ms-pick"][value="openai/gpt-5.1"]').check()
    page.locator("#modal-confirm").click()
    dialog = page.locator("dialog[role=dialog]").filter(has_text="Share this assistant's work?")
    dialog.wait_for()
    assert "Data leaves this computer" in dialog.inner_text()
    assert "gpt-5.1" in dialog.inner_text()
    page.locator("#modal-cancel").click()
    dialog.wait_for(state="hidden")
    assert page.locator(".ms-btn.is-custom").count() == 0, "cancelling the confirmation keeps the saved default"

    _open_menu(page)
    page.keyboard.press("/")
    page.locator(".ms-all").wait_for()
    page.locator('input[name="ms-pick"][value="openai/gpt-5.1"]').check()
    page.locator("#modal-confirm").click()
    _confirm_sharing(page)
    page.locator(".ms-btn.is-custom").wait_for()
    assert page.locator(".ms-btn .ms-label").inner_text() == "gpt-5.1"


def test_saving_a_cloud_route_as_the_default_asks_again_and_cancel_keeps_the_old_default(picker):
    page, _ = picker
    cloud_spec = "ollama/qwen3-coder:480b-cloud"
    catalog = {"default": "ollama/qwen3:8b", "models": [
        {"spec": "ollama/qwen3:8b", "label": "qwen3:8b", "group": "This bot", "state": "ready", "default": True,
         "hosted": False, "note": "this bot's own model", "worst_case_usd": 0},
        {"spec": cloud_spec, "label": "qwen3-coder:480b-cloud", "group": "Hosted", "state": "ready", "hosted": True,
         "note": "Ollama Cloud model; inference runs on ollama.com", "worst_case_usd": 0},
    ]}
    page.route("**/api/bots/*/models*",
               lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(catalog)))

    _open_menu(page)
    page.keyboard.press("/")
    page.locator(".ms-all").wait_for()
    page.locator(f'input[name="ms-pick"][value="{cloud_spec}"]').check()
    page.locator("#modal-confirm").click()
    _confirm_sharing(page)
    page.locator(".ms-btn.is-custom").wait_for()

    _open_menu(page)
    page.locator('[data-save-default]').click()
    dialog = page.locator("dialog[role=dialog]").filter(has_text="Share this assistant's work?")
    dialog.wait_for()
    page.locator("#modal-cancel").click()
    dialog.wait_for(state="hidden")
    assert "One-message override" in page.locator(".ms-btn").get_attribute("aria-label")
    # The saved default is unchanged until the confirmation is accepted.
    saved = page.evaluate("fetch('/api/bots/design-system-review').then(r => r.json())")
    assert saved["model"] == "ollama/qwen3:8b"

    _open_menu(page)
    page.locator('[data-save-default]').click()
    _confirm_sharing(page)
    page.locator(".ms-btn:not(.is-custom)").wait_for()
    assert "Assistant default" in page.locator(".ms-btn").get_attribute("aria-label")
    saved = page.evaluate("fetch('/api/bots/design-system-review').then(r => r.json())")
    assert saved["model"] == cloud_spec
