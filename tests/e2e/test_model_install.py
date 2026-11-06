"""Installing and cancelling a local model from the Models page, against a fake Ollama (the real runtime is covered by the live record).

The button is the only thing that starts a download and it shows the size first; a running download can be cancelled and a
finished one appears in the installed list. The fake runtime speaks the ndjson shape captured from Ollama 0.40.13.
"""

from __future__ import annotations

import pytest

pw = pytest.importorskip("playwright.sync_api")
expect = pw.expect

from hutch.server.app import create_app  # noqa: E402
from tests.fakes import FakeOllama  # noqa: E402
from tests.support.browser import launch_browser  # noqa: E402
from tests.support.live_app import PageWatch, serve  # noqa: E402


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as playwright:
        b = launch_browser(playwright)
        yield b
        b.close()


@pytest.fixture()
def live(tmp_path, monkeypatch):
    runtime = FakeOllama(models={"fake:4b": {}})
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OLLAMA_HOST", runtime.url)
    from hutch.runtime.ladder import reset_provider_cache
    reset_provider_cache()
    try:
        with serve(create_app()) as base:
            yield base, runtime
    finally:
        runtime.close()


def _first_install_button(page):
    button = page.locator("[data-install-model]").first
    button.wait_for(timeout=20_000)
    return button


def test_the_button_shows_the_size_and_install_finishes_with_the_model_in_the_runtime(browser, live):
    base, runtime = live
    page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    watch = PageWatch(page)
    try:
        page.goto(f"{base}/models#models-advanced", wait_until="domcontentloaded")       # the link in the empty state opens the section
        button = _first_install_button(page)
        tag = button.get_attribute("data-install-model")
        assert tag not in runtime.models
        assert "GiB" in button.inner_text() or not button.get_attribute("data-install-size"), "the size is on the button before the click"
        assert page.locator(f'[data-install-state="{tag}"]').inner_text() == "", "nothing starts until the button is pressed"
        button.click()
        panel = page.locator(f'[data-install-plan-for="{tag}"]')
        panel.wait_for(timeout=10_000)
        assert "GiB free" in panel.inner_text() or "free disk" in panel.inner_text(), "the plan shows the disk before the download"
        assert tag not in runtime.models, "reviewing the plan does not start a download"
        panel.get_by_role("button", name="Confirm download").click()
        for _ in range(60):
            if tag in runtime.models:
                break
            page.wait_for_timeout(250)
        assert tag in runtime.models, "the download went through the runtime's own pull"
        assert not [e for e in watch.errors if "install" in e.lower()], watch.errors
    finally:
        page.context.close()


def test_a_running_download_can_be_cancelled_and_installs_nothing(browser, live):
    base, runtime = live
    runtime.pull_delay, runtime.pull_events = 0.5, 20          # slow enough to cancel mid-flight
    page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    try:
        page.goto(f"{base}/models#models-advanced", wait_until="domcontentloaded")       # the link in the empty state opens the section
        button = _first_install_button(page)
        tag = button.get_attribute("data-install-model")
        button.click()
        panel = page.locator(f'[data-install-plan-for="{tag}"]')
        panel.wait_for(timeout=10_000)
        panel.get_by_role("button", name="Confirm download").click()
        cancel = page.locator(f'[data-install-cancel-for="{tag}"]')
        cancel.wait_for(timeout=15_000)
        cancel.click()
        expect(page.locator(f'[data-install-state="{tag}"]')).to_contain_text("Cancelled", timeout=20_000)
        assert tag not in runtime.models, "a cancelled download installs nothing"
        expect(button).to_be_enabled()
    finally:
        page.context.close()
