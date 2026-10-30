"""Focused browser journey for the incremental live-update path.

The optimisation under test: committed run event batches arrive as a named SSE event, are
applied to the transcript block in place, and the redundant full refresh is suppressed. A
batch carrying approval/choice/terminal state must still fall back to the authoritative full
render. The test asserts behaviour, not timings, so it stays stable on a noisy host.
"""

from __future__ import annotations

import json
import os
import threading
import time

import pytest

pw = pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402

from hutch.models import ApprovalMode, Bot, Event, EventType, Run, RunStatus  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from hutch.store import Store  # noqa: E402
from tests.support.browser import launch_browser  # noqa: E402

RUN_ID = "run_live_update_journey"


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as playwright:
        launched = launch_browser(playwright)
        yield launched
        launched.close()


@pytest.fixture()
def live_run(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setenv("HUTCH_STATE_DIR", str(state))
    monkeypatch.setenv("HUTCH_MAX_CONCURRENT", "2")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver")
    store = Store(__import__("hutch.config", fromlist=["get_config"]).get_config())
    bot = store.create_bot(Bot(name="live-journey", display_name="Live Journey", model="mock/demo",
                               tools=["shell", "files"], approval_mode=ApprovalMode.auto))
    run = store.create_run(Run(bot_id=bot.id, prompt="live update journey", status=RunStatus.waiting_approval))
    store.append_event(Event(run_id=run.id, type=EventType.log, data={"kind": "seed", "note": "seed event"}))
    store.flush_events()
    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    assert server.started, "uvicorn did not start"
    base = f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}"
    try:
        yield base, store, run
    finally:
        store.close()
        server.should_exit = True
        thread.join(timeout=10)


def test_live_batch_applies_incrementally_and_unsafe_batches_fall_back(browser, live_run):
    base, store, run = live_run
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    errors: list[str] = []
    run_requests: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: run_requests.append(request.url)
            if f"/api/runs/{run.id}" in request.url and "/stream" not in request.url else None)
    try:
        page.goto(base + "/bots", wait_until="load", timeout=30000)
        page.evaluate("(id) => { location.hash = '#/run/' + id; }", run.id)
        page.wait_for_selector(f'.thread[data-run-id="{run.id}"]', timeout=20000)
        page.wait_for_function("() => window.HutchLive && window.HutchLive.cacheSize() > 0", timeout=20000)
        page.wait_for_timeout(600)
        base_stats = page.evaluate("() => window.HutchLive.stats()")
        requests_before = len(run_requests)
        for index in range(4):
            store.append_event(Event(run_id=run.id, type=EventType.log,
                                      data={"kind": "live", "note": f"journal marker {index}"}))
        store.flush_events()
        page.wait_for_function(
            "() => document.querySelector('#chat-stream')?.innerText.includes('journal marker 3')",
            timeout=20000)
        applied = page.evaluate("() => window.HutchLive.stats()")
        assert applied["batchesApplied"] > base_stats["batchesApplied"], applied
        assert applied["errors"] == 0, applied
        assert not errors, errors
        assert len(run_requests) - requests_before <= 1, "a safe batch should not force a full refetch"

        # An approval request is not safe for an in-place apply: the authoritative full render
        # must run and show the card.
        requests_before_fallback = len(run_requests)
        store.append_event(Event(run_id=run.id, type=EventType.approval_request,
                                  data={"approval_id": "ap_live_journey", "tool": "shell",
                                        "summary": "approve the journey command"}))
        store.flush_events()
        deadline = time.time() + 20
        after_fallback = applied
        while time.time() < deadline:
            after_fallback = page.evaluate("() => window.HutchLive.stats()")
            if (after_fallback["batchesSeen"] > applied["batchesSeen"]
                    and len(run_requests) > requests_before_fallback):
                break
            page.wait_for_timeout(100)
        assert after_fallback["batchesSeen"] > applied["batchesSeen"], after_fallback
        assert len(run_requests) > requests_before_fallback, (
            "an unsafe batch must fall back to the authoritative full refresh")
        assert not errors, errors
    finally:
        context.close()