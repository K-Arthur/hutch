"""The Catalog destination: reviewed entries, a search, provenance and inert install.

The page lists the bundled manifests with publisher, version and content hash, shows what an entry asks
for before anything exists, opens the normal setup review for "Create a copy", runs the sharing checklist
on export, and accepts a catalog template in setup without saving anything until Create.
"""

from __future__ import annotations

import json
import os
import pathlib

import pytest

pw = pytest.importorskip("playwright.sync_api")

from hutch.models import Bot  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from tests.support.browser import launch_browser  # noqa: E402
from tests.support.live_app import PageWatch, horizontal_overflow, serve  # noqa: E402


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as playwright:
        b = launch_browser(playwright)
        yield b
        b.close()


@pytest.fixture()
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    app = create_app()
    app.state.store.create_bot(Bot(name="catalog-source-bot", display_name="Catalog Source Bot",
                                   instructions="Review release notes and summarize the changes.",
                                   tools=["files"], model="ollama/llama3.2:3b"))
    with serve(app) as url:
        yield url, app


def test_catalog_is_reachable_with_search_and_provenance(browser, base):
    url, app = base
    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    watch = PageWatch(page)
    try:
        page.goto(f"{url}/#/catalog", wait_until="domcontentloaded")
        page.locator("[data-catalog-entry]").first.wait_for(timeout=20_000)
        assert page.title() == "Catalog — Hutch"
        assert page.locator('[data-nav="catalog"][aria-current="page"]').count() == 1
        assert page.locator("[data-catalog-entry]").count() == 8
        assert "Hutch" in page.locator("[data-catalog-entry]").first.inner_text()

        search = page.locator("#catalog-search")
        search.fill("planner")
        pw.expect(page.locator("[data-catalog-entry]:not([hidden])")).to_have_count(1)
        search.fill("")

        page.locator('[data-catalog-entry="day-planner"] a', has_text="Review").click()
        page.wait_for_url("**/#/catalog/day-planner")
        detail = page.locator(".catalog-detail")
        detail.wait_for(timeout=20_000)
        text = detail.inner_text()
        assert "Day Planner" in text and "publisher" in text.lower() and "content hash" in text.lower()
        assert "What it asks for" in text and "files" in text
        assert detail.locator("details pre").text_content().startswith("You build a realistic plan")
        page.screenshot(path=str(pathlib.Path(os.environ.get("TMPDIR", "/tmp")) / "catalog-detail-1440.png"),
                        animations="disabled")

        bots_before = len(app.state.store.list_bots())
        page.get_by_role("button", name="Create a copy").click()
        page.wait_for_url("**/#/assistant/new")
        page.get_by_role("heading", name="Set up your assistant").wait_for(timeout=20_000)
        assert len(app.state.store.list_bots()) == bots_before      # inert until Create
        assert not watch.errors, watch.errors
    finally:
        page.context.close()


@pytest.mark.parametrize("width,height", [(900, 900), (360, 800)])
def test_catalog_holds_at_narrow_widths(browser, base, width, height):
    url, _ = base
    page = browser.new_context(viewport={"width": width, "height": height}).new_page()
    watch = PageWatch(page)
    try:
        page.goto(f"{url}/#/catalog", wait_until="domcontentloaded")
        page.locator("[data-catalog-entry]").first.wait_for(timeout=20_000)
        assert horizontal_overflow(page) == 0
        assert page.locator("[data-catalog-entry]").count() == 8
        assert not watch.errors, watch.errors
    finally:
        page.context.close()


def test_export_runs_the_sharing_checklist_and_downloads_a_template(browser, base):
    url, app = base
    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    watch = PageWatch(page)
    try:
        page.goto(f"{url}/#/catalog", wait_until="domcontentloaded")
        select = page.locator("#catalog-export-bot")
        select.wait_for(timeout=20_000)
        select.select_option("catalog-source-bot")
        page.get_by_role("button", name="Review template").click()
        dialog = page.get_by_role("dialog")
        dialog.wait_for()
        body = dialog.inner_text()
        assert "Review before sharing" in body and "No API keys" in body
        assert "Never included" in body
        with page.expect_download() as download:
            dialog.get_by_role("button", name="Download template").click()
        assert download.value.suggested_filename == "catalog-source-bot-template.json"
        assert len(app.state.store.list_bots()) == 1     # export never creates or edits an assistant
        assert not watch.errors, watch.errors
    finally:
        page.context.close()


def test_setup_imports_a_catalog_template_as_an_unsaved_draft(browser, base):
    url, app = base
    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    watch = PageWatch(page)
    try:
        manifest = json.loads((pathlib.Path(__file__).resolve().parents[2]
                               / "src" / "hutch" / "data" / "catalog" / "day-planner.json").read_text(encoding="utf-8"))
        page.goto(f"{url}/#/assistant/new", wait_until="domcontentloaded")
        page.get_by_role("heading", name="Set up your assistant").wait_for(timeout=20_000)
        page.locator("#setup-customize").click()
        page.get_by_role("heading", name="Choose what powers it").wait_for(timeout=20_000)
        page.locator("#setup-back").click()
        page.locator("#setup-yaml-import-details > summary").click()
        page.locator("#setup-yaml-file").set_input_files({"name": "day-planner.json", "mimeType": "application/json",
                                                          "buffer": json.dumps(manifest).encode("utf-8")})
        page.get_by_role("status").filter(has_text="Catalog template validated and copied into this unsaved draft").wait_for()
        assert page.get_by_label("Assistant name").input_value() == "Day Planner"
        assert page.get_by_label("What would you like this assistant to handle?").input_value().startswith("You build a realistic plan")
        assert len(app.state.store.list_bots()) == 1      # nothing saved by import
        assert not watch.errors, watch.errors
    finally:
        page.context.close()
