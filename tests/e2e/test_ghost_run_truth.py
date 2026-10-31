"""A ghost live run never reads as work: no "N working", no Stop all, no "Stopping" (owner report).

A 23-day-old row left in a live status by a pre-lease/never-heartbeated claim used to count as 1 working and
show "Stopping" forever. The supervisor must reconcile it (stopped/interrupted) and the header must only
count runs with current lease evidence.
"""

from __future__ import annotations

import json
import time
import urllib.request
from datetime import timedelta
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")

from hutch.config import get_config  # noqa: E402
from hutch.models import Bot, Run, RunStatus, iso, utcnow  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from hutch.store import Store  # noqa: E402
from tests.support.browser import launch_browser  # noqa: E402
from tests.support.live_app import PageWatch, serve  # noqa: E402


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as playwright:
        b = launch_browser(playwright)
        yield b
        b.close()


@pytest.fixture()
def legacy_state(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    config = get_config()
    store = Store(config)
    try:
        bot = store.create_bot(Bot(name="tidy-downloads", display_name="Tidy Downloads",
                                   model="ollama/llama3.2:3b", tools=[]))
        run = Run(bot_id=bot.id, prompt="sort this week's downloads into folders",
                  status=RunStatus.cancelling, owner="",
                  created_at=iso(utcnow() - timedelta(days=23)))
        run_id = store.create_run(run).id
        with store._lock:                 # the exact stuck shape: fenced claim, no lease expiry at all
            store._db.execute("UPDATE runs SET fence = 3, lease_owner = 'dead-supervisor', "
                              "lease_expires_at = NULL WHERE id = ?", (run_id,))
            store._db.commit()
    finally:
        store.close()
    with serve(create_app()) as url:
        yield url, run_id


def _get(base, path):
    with urllib.request.urlopen(base + path, timeout=30) as response:
        return json.loads(response.read().decode())


def test_the_ghost_is_reconciled_and_the_header_stays_quiet(browser, legacy_state):
    base, run_id = legacy_state
    deadline = time.monotonic() + 40
    status, working = None, None
    while time.monotonic() < deadline:
        runs = _get(base, "/api/runs")
        items = runs.get("items") if isinstance(runs, dict) else runs
        match = next((r for r in items or [] if r.get("id") == run_id), None)
        status = (match or {}).get("status")
        working = _get(base, "/api/stats")["working_runs"]
        if status not in ("cancelling", "recovering", "running") and working == 0:
            break
        time.sleep(0.5)
    assert status in ("stopped", "cancelled", "failed"), status
    assert working == 0

    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    watch = PageWatch(page)
    try:
        page.goto(f"{base}/#/activity", wait_until="domcontentloaded")
        page.locator(".app-top-context h1").wait_for(timeout=20_000)
        page.wait_for_timeout(1500)
        assert page.locator(".app-top-work").count() == 0
        assert page.locator("form[action='/stop-all']").count() == 0
        body = page.locator("body").inner_text()
        assert "Working now" not in body and "1 working" not in body
        assert "Stopping" not in body
        assert not watch.errors, watch.errors
    finally:
        page.context.close()
