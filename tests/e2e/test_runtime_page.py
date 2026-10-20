"""Browser regression for the Runtime & background work page (route #/runtime).

Uses the shared e2e fixtures' pattern: a real uvicorn server on an isolated
state directory and a real browser. The service controls are only opened to the
confirm dialog and cancelled — a test must never install a unit on the host.
"""
from __future__ import annotations

import threading
import time

import pytest

pw = pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402

from hutch.models import Bot  # noqa: E402
from hutch.server.app import create_app  # noqa: E402


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        b = None
        errors = []
        for engine in (p.chromium, p.firefox):
            try:
                b = engine.launch()
                break
            except Exception as exc:  # noqa: BLE001 - report which engines were unavailable
                errors.append(f"{engine.name}: {exc}")
        if b is None:
            pytest.skip("no Playwright browser is installed: " + "; ".join(errors))
        yield b
        b.close()


@pytest.fixture()
def live(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_MAX_CONCURRENT", "2")
    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}", app
    server.should_exit = True
    thread.join(timeout=10)


def test_runtime_page_shows_truth_and_controls_bounded_work(live, browser, tmp_path, monkeypatch):
    base, app = live
    store = app.state.store
    bot = store.create_bot(Bot(name="runtime-bot", model="mock/demo"))
    watched = tmp_path / "watched"
    watched.mkdir()
    (watched / "a.txt").write_bytes(b"one")
    source = store.create_event_source(bot_id=bot.id, kind="folder", name="Inbox",
                                       config={"path": str(watched), "settle_seconds": 0})
    pause_entered, release_pause = threading.Event(), threading.Event()
    update_event_source = store.update_event_source

    def delay_source_pause(source_id, **changes):
        if source_id == source["id"] and changes.get("enabled") is False:
            pause_entered.set()
            if not release_pause.wait(5):
                raise TimeoutError("test did not release the held source pause")
        return update_event_source(source_id, **changes)

    monkeypatch.setattr(store, "update_event_source", delay_source_pause)

    page = browser.new_page(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    console_errors: list[str] = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda err: console_errors.append(str(err)))
    page.goto(f"{base}/#/runtime", wait_until="networkidle")
    page.wait_for_selector("h1:has-text('Runtime')")

    assert page.locator(".runtime-card h2").all_inner_texts() == [
        "This machine", "Background service", "Watched sources", "Multi-step jobs", "Queue & automation"]
    assert page.locator('a[data-nav="runtime"]').get_attribute("aria-current") == "page"
    assert page.locator(".runtime-source").count() == 1
    assert "Inbox" in page.locator(".runtime-source").first.inner_text()

    # The background supervisor performs the due check without any model call;
    # the page reports freshness rather than a heartbeat.
    deadline = time.time() + 10
    while time.time() < deadline and not store.get_event_source(source["id"])["last_check_at"]:
        time.sleep(0.1)
    page.click('[data-runtime-action="refresh"]')
    page.wait_for_timeout(500)
    row_text = page.locator(".runtime-source").first.inner_text()
    assert "last checked" in row_text
    assert store.source_events(source["id"], status="recorded") or store.source_events(source["id"])

    # The disclosure loads recorded changes lazily and labels their status.
    page.click(".runtime-source-events summary")
    page.wait_for_selector(".runtime-event-list li", timeout=5000)
    assert "created: a.txt" in page.locator(".runtime-source-events").first.inner_text()

    # Pause automation is the same fence the Scheduled work page uses.
    page.click('[data-runtime-action="automation-pause"]')
    deadline = time.time() + 5
    while time.time() < deadline and not store.workspace_schedule_control()["paused"]:
        time.sleep(0.05)
    assert store.workspace_schedule_control()["paused"] is True
    page.wait_for_selector('text=Automation paused', timeout=5000)
    page.click('[data-runtime-action="automation-resume"]')
    deadline = time.time() + 5
    while time.time() < deadline and store.workspace_schedule_control()["paused"]:
        time.sleep(0.05)
    assert store.workspace_schedule_control()["paused"] is False

    # Pausing one source retires pending events; resuming re-arms checks.
    try:
        page.click('[data-runtime-action="source-pause"]')
        assert pause_entered.wait(5), "source pause request did not reach the store"
        assert page.locator('[data-runtime-action="source-pause"]').is_disabled()
        assert all(button.is_disabled() for button in page.locator("[data-runtime-action]").all())
    finally:
        release_pause.set()
    deadline = time.time() + 5
    while time.time() < deadline and store.get_event_source(source["id"])["enabled"]:
        time.sleep(0.05)
    assert store.get_event_source(source["id"])["enabled"] is False
    page.locator('[data-runtime-action="source-resume"]').wait_for()
    page.click('[data-runtime-action="source-resume"]')
    deadline = time.time() + 5
    while time.time() < deadline and not store.get_event_source(source["id"])["enabled"]:
        time.sleep(0.05)
    assert store.get_event_source(source["id"])["enabled"] is True

    # Opening the install confirmation is inert; cancel must not touch the host.
    page.click('[data-runtime-action="install"]')
    page.wait_for_selector(".modal-card", timeout=5000)
    assert "user service" in page.locator(".modal-card").inner_text()
    page.click("#modal-cancel")
    page.wait_for_timeout(200)
    assert page.locator(".modal-card").count() == 0

    assert console_errors == [], f"console/page errors: {console_errors}"
    page.close()


def test_runtime_page_is_usable_at_phone_width(live, browser):
    base, _app = live
    page = browser.new_page(viewport={"width": 320, "height": 740}, reduced_motion="reduce")
    page.goto(f"{base}/#/runtime", wait_until="networkidle")
    page.wait_for_selector("h1:has-text('Runtime')")
    overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert overflow <= 1, f"phone layout overflows by {overflow}px"
    assert page.locator(".runtime-card").count() == 5
    # The empty state's one primary action is reachable and labelled.
    button = page.locator('[data-runtime-action="add-source"]').first
    assert button.is_visible()
    page.close()
