from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import pytest

pw = pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402

from hutch.models import Bot  # noqa: E402
from hutch.server.app import create_app  # noqa: E402


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as playwright:
        browser = None
        errors = []
        for engine in (playwright.chromium, playwright.firefox):
            try:
                browser = engine.launch()
                break
            except Exception as exc:
                errors.append(f"{engine.name}: {exc}")
        if browser is None:
            pytest.skip("no Playwright browser is installed: " + "; ".join(errors))
        yield browser
        browser.close()


@pytest.fixture()
def live(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_MAX_CONCURRENT", "2")
    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0,
                                           log_level="error", lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    assert server.started, "local Hutch preview did not start"
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}", app
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive(), "local Hutch preview did not stop"


def _wait_for(predicate, timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    assert predicate(), "condition was not met before timeout"


def test_saved_request_library_is_private_reusable_and_reviewed(browser, live, tmp_path):
    base, app = live
    store = app.state.store
    bot = store.create_bot(Bot(name="saved-request-review", model="mock/demo", tools=[]))
    conversation, _ = store.create_conversation(bot.id, "Launch review", idem_key="saved-request-conversation",
                                                request_hash="saved-request-conversation")
    page = browser.new_page(viewport={"width": 1440, "height": 960})
    errors = []
    external_requests = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda req: external_requests.append(req.url)
            if urlsplit(req.url).netloc not in {urlsplit(base).netloc, ""} else None)
    page.context.tracing.start(screenshots=True, snapshots=True, sources=False)
    trace_saved = False
    try:
        seeded = page.request.post(f"{base}/api/v1/conversations/{conversation['id']}/messages",
                                   data={"prompt": "Help me prepare a launch review."},
                                   headers={"Idempotency-Key": "saved-request-seed"})
        assert seeded.status == 201, seeded.text()
        run_id = seeded.json()["id"]
        _wait_for(lambda: store.get_run(run_id).terminal)

        page.goto(base + "/#/chat/saved-request-review")
        page.locator("#conversation-switcher").select_option(conversation["id"])
        page.locator("#chat-stream").get_by_text("Help me prepare a launch review.", exact=True).wait_for()
        page.locator("#studio-conversation-options").click()
        page.locator("#studio-conversation-more > summary").click()
        page.get_by_role("button", name="Save reusable request").click()
        page.get_by_role("heading", name="Save reusable request").wait_for()
        assert page.locator("#task-template-prompt").input_value() == "Help me prepare a launch review."
        page.locator("#task-template-name").fill("Launch review")
        page.locator("#task-template-prompt").fill("Review the launch plan and list risks.")
        template_viewports = []
        artifacts = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/saved-requests"
        artifacts.mkdir(parents=True, exist_ok=True)
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024),
                                     ("phone", 390, 844), ("compact-phone", 320, 844)):
            page.set_viewport_size({"width": width, "height": height})
            dialog = page.locator("#modal-root .modal-card")
            bounds = dialog.bounding_box()
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow == 0, f"{label} save request dialog has page overflow"
            assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= width
            page.screenshot(path=str(artifacts / f"save-review-{label}.png"))
            template_viewports.append({"label": label, "viewport": [width, height], "bounds": bounds})
        page.locator("#modal-confirm").click()
        _wait_for(lambda: len(store.list_task_templates()) == 1)
        saved = store.list_task_templates()[0]
        assert saved["name"] == "Launch review" and saved["prompt"] == "Review the launch plan and list risks."

        run_ids_before_use = {run.id for run in store.list_runs()}
        page.locator("#composer-menu-btn").click()
        page.get_by_role("button", name="Browse saved requests").click()
        page.get_by_role("heading", name="Saved requests").wait_for()
        page.locator("#saved-task-template-search").fill("launch")
        page.get_by_role("heading", name="Launch review").wait_for()
        library_viewports = []
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024),
                                     ("phone", 390, 844), ("compact-phone", 320, 844)):
            page.set_viewport_size({"width": width, "height": height})
            dialog = page.locator("#modal-root .modal-card")
            bounds = dialog.bounding_box()
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow == 0, f"{label} saved requests dialog has page overflow"
            assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= width
            page.screenshot(path=str(artifacts / f"library-{label}.png"))
            library_viewports.append({"label": label, "viewport": [width, height], "bounds": bounds})

        page.locator("[data-saved-request-use]").click()
        assert page.locator("#chat-prompt").input_value() == "Review the launch plan and list risks."
        assert {run.id for run in store.list_runs()} == run_ids_before_use
        page.wait_for_function("document.querySelector('#live-status')?.textContent.includes('Nothing was sent')")

        page.locator("#composer-menu-btn").click()
        page.get_by_role("button", name="Browse saved requests").click()
        page.locator("[data-saved-request-edit]").click()
        page.get_by_role("heading", name="Edit saved request").wait_for()
        page.locator("#saved-task-template-name").fill("Launch risk review")
        page.locator("#saved-task-template-prompt").fill("Review the launch plan, risks, and owners.")
        page.get_by_role("button", name="Save changes").click()
        page.get_by_role("heading", name="Saved requests").wait_for()
        page.get_by_role("heading", name="Launch risk review").wait_for()
        assert store.list_task_templates()[0]["revision"] == 2

        page.locator("[data-saved-request-delete]").click()
        page.get_by_role("heading", name="Delete saved request?").wait_for()
        page.get_by_role("button", name="Delete request").click()
        _wait_for(lambda: store.list_task_templates() == [])
        page.get_by_role("heading", name="Saved requests").wait_for()
        assert "No saved requests yet" in page.locator("#saved-task-template-list").inner_text()
        assert not errors, errors
        assert not external_requests, external_requests
        page.context.tracing.stop(path=str(artifacts / "trace.zip"))
        trace_saved = True
        (artifacts / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_saved_requests.py::test_saved_request_library_is_private_reusable_and_reviewed",
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_saved_requests.py",
            "browser": browser.browser_type.name, "browser_version": browser.version,
            "viewports": {"save_review": template_viewports, "library": library_viewports},
            "fixture_only": True, "provider_calls": 0, "external_requests": external_requests,
            "page_errors": errors,
            "verified": ["first request is reviewed before saving", "templates persist in the local database",
                         "search filters the library", "Use request fills a draft and starts no run",
                         "edit increments the revision", "delete is confirmed and removes only the template",
                         "dialogs fit desktop, tablet, phone, and compact phone"],
            "trace": "trace.zip",
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        if not trace_saved:
            try:
                page.context.tracing.stop()
            except Exception:
                pass
        page.close()
