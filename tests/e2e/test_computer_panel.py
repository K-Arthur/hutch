"""The computer-session panel in the real run view (real Chromium, real server, real frame files).

Set HUTCH_EVIDENCE_DIR to keep the screenshots (they are how the layout is inspected; assertions alone are not enough).
"""

from __future__ import annotations

import os
import struct
import threading
import time
import zlib
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402

from hutch.computer.frames import FrameStore  # noqa: E402
from hutch.config import get_config  # noqa: E402
from hutch.models import Bot, Event, EventType, Run, RunStatus  # noqa: E402
from hutch.server.app import create_app  # noqa: E402


def _png(width: int, height: int, seed: int) -> bytes:
    """A recognisable synthetic frame: a window-like layout, so scaling and clipping are visible in screenshots."""
    rows = []
    for y in range(height):
        row = bytearray(b"\x00")
        for x in range(width):
            title = y < height // 10
            body = 0xF2 if (x // 40 + y // 40) % 2 == 0 else 0xE4
            row.append(0x33 if title else (0xB0 if x < 6 or y > height - 6 else body))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture()
def live(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "127.0.0.1")
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


def _seed(app, *, owner="agent", status=RunStatus.running, hostile=False, width=1280, height=800,
          captured_at=None, with_frame_file=True):
    store = app.state.store
    bot = Bot(name=f"desk-{owner}", model="ollama/qwen3:4b", tools=["computer"], computer_apps=["kwrite"])
    store.upsert_bot(bot)
    run = store.create_run(Run(bot_id=bot.id, prompt="Edit the note in the editor", status=RunStatus.running))
    ref = None
    if with_frame_file:
        ref = FrameStore(get_config().run_dir(bot.name, run.id)).save(_png(width, height, 1), "image/png")
    store.append_event(Event(run_id=run.id, type=EventType.log, data={
        "kind": "computer_control", "surface": "desktop", "owner": owner, "generation": 3,
        "reason": ('<img src=x onerror="window.__pwned=1">' if hostile else "a person took control"),
        "fresh_observation_required": True}))
    frame = ref.public() if ref else {"frame_id": "f000001", "sha256": "0" * 64, "bytes": 10,
                                      "media_type": "image/png", "width": width, "height": height}
    store.append_event(Event(run_id=run.id, type=EventType.tool_result, data={
        "tool": "computer", "ok": True, "output": "observed the desktop", "frames": [frame],
        "observation": {"schema": 1, "surface": {"kind": "desktop_screen", "id": "screen-0"},
                        "captured_at": captured_at or time.strftime("%Y-%m-%dT%H:%M:%S.000+00:00", time.gmtime()),
                        "environment": {"mode": "isolated", "applications": ["kwrite", "<b>x</b>"]}}}))
    if status is RunStatus.waiting_human:
        store.append_event(Event(run_id=run.id, type=EventType.human_needed, data={
            "reason": "Sign in at the page", "url": "https://example.test/login", "handoff": "Finish the step."}))
    store.flush_events()
    if status is not RunStatus.running:
        store.set_status(run, status)
    return run


def _open(browser, base, run, width, height):
    page = browser.new_page(viewport={"width": width, "height": height})
    page.goto(f"{base}/#/run/{run.id}")
    page.locator("[data-computer-panel]").wait_for(timeout=10_000)
    return page


def _shot(page, name):
    target = os.environ.get("HUTCH_EVIDENCE_DIR")
    if target:
        Path(target).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(target) / f"computer-panel-{name}.png"), full_page=False)


@pytest.mark.parametrize("width,height", [(360, 780), (768, 1024), (1440, 900)])
def test_computer_settings_round_trip_and_readiness_at_each_width(browser, live, width, height):
    base, app = live
    bot = Bot(name="computer-settings", tools=["browser"])
    app.state.store.upsert_bot(bot)
    page = browser.new_page(viewport={"width": width, "height": height}, reduced_motion="reduce")
    errors = []
    page.on("pageerror", lambda err: errors.append(str(err)))
    try:
        page.goto(f"{base}/#/bot/{bot.name}")
        page.locator("#assistant-more-settings > summary").click()
        form = page.locator("#form-computer")
        form.get_by_label("Local web apps").fill("http://localhost:3000\nhttp://127.0.0.1:5000")
        form.get_by_label("Allowed desktop applications").fill("kwrite")
        form.get_by_label("Allow observations to hosted AI").check()
        form.get_by_role("button", name="Save computer access").click()
        page.wait_for_function("() => document.querySelector('#form-computer input[name=observation_to_hosted]')?.checked")
        deadline = time.monotonic() + 5
        while not app.state.store.get_bot(bot.id).observation_to_hosted and time.monotonic() < deadline:
            time.sleep(0.05)
        saved = app.state.store.get_bot(bot.id)
        assert set(saved.local_dev_origins) == {"http://localhost:3000", "http://127.0.0.1:5000"}
        assert saved.computer_apps == ["kwrite"] and saved.observation_to_hosted
        page.reload()
        page.locator("#assistant-more-settings > summary").click()
        form = page.locator("#form-computer")
        assert form.get_by_label("Allow observations to hosted AI").is_checked()
        form.get_by_role("button", name="Check host readiness").click()
        page.wait_for_function("() => {const el=document.querySelector('#computer-readiness'); return el && el.textContent && !el.textContent.includes('Checking');}")
        assert "undefined" not in page.locator("#computer-readiness").inner_text()
        form.scroll_into_view_if_needed()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        assert not errors, errors
        _shot(page, f"settings-{width}")
    finally:
        page.close()


@pytest.mark.parametrize("width,height", [(360, 780), (768, 1024), (1440, 900)])
def test_panel_shows_environment_owner_and_a_never_live_frame_at_each_width(browser, live, width, height):
    base, app = live
    run = _seed(app)
    page = _open(browser, base, run, width, height)
    try:
        panel = page.locator("[data-computer-panel]")
        text = panel.inner_text()
        assert "Isolated desktop" in text and "Hutch is in control" in text
        assert "does not prove a sandbox boundary" in text
        assert "not a live view" in text and "Live" not in text.replace("not a live view", "")
        img = panel.locator("img.computer-img")
        img.wait_for()
        assert page.evaluate("el => el.complete && el.naturalWidth > 0", img.element_handle()), "frame did not load"
        assert panel.locator("[data-stop-run]").is_visible()
        # layout: no horizontal page scroll, panel and image inside the viewport. The shell animates its sidebar on load,
        # so wait for the layout to settle into a fitting state (a layout that never fits still fails here).
        page.wait_for_function(
            """() => { const p = document.querySelector('[data-computer-panel]'); const r = p.getBoundingClientRect();
                      return r.left >= 0 && r.right <= window.innerWidth + 1 &&
                             document.documentElement.scrollWidth <= window.innerWidth + 1; }""", timeout=5000)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        box = panel.bounding_box()
        assert box and box["x"] >= 0 and box["x"] + box["width"] <= width + 1
        img_box = img.bounding_box()
        assert img_box and img_box["width"] <= width and img_box["height"] > 40
        _shot(page, f"{width}")
    finally:
        page.close()


def test_a_person_in_control_is_stated_and_resume_reuses_the_existing_control(browser, live):
    base, app = live
    run = _seed(app, owner="human", status=RunStatus.waiting_human)
    page = _open(browser, base, run, 1440, 900)
    try:
        panel = page.locator("[data-computer-panel]")
        assert "You are in control" in panel.inner_text()
        resume = panel.locator("[data-human-resume]")
        assert resume.is_visible() and int(resume.get_attribute("data-event-seq")) > 0
        assert resume.get_attribute("data-run-id") == run.id
        assert "Remote clicking and typing are not available" in panel.inner_text()
        _shot(page, "human-control")
    finally:
        page.close()


def test_page_and_application_strings_are_untrusted_text_not_markup(browser, live):
    base, app = live
    run = _seed(app, hostile=True)
    page = _open(browser, base, run, 768, 900)
    try:
        page.wait_for_timeout(500)
        assert page.evaluate("window.__pwned === undefined"), "injected markup executed"
        panel = page.locator("[data-computer-panel]")
        assert panel.locator("img[src='x']").count() == 0
        assert '<img src=x onerror="window.__pwned=1">' in panel.inner_text(), "hostile text must be shown as text"
    finally:
        page.close()


def test_an_old_frame_is_labelled_stale_and_a_finished_run_is_labelled_final(browser, live):
    base, app = live
    old = _seed(app, captured_at="2026-10-10T09:00:00.000+00:00")
    page = _open(browser, base, old, 1440, 900)
    try:
        text = page.locator("[data-computer-panel]").inner_text()
        assert "not a live view" in text and "ago" in text
        assert page.locator(".computer-frame.is-stale").count() == 1
        _shot(page, "stale")
    finally:
        page.close()
    done = _seed(app, owner="stopped", status=RunStatus.stopped)
    page = _open(browser, base, done, 1440, 900)
    try:
        text = page.locator("[data-computer-panel]").inner_text()
        assert "Final frame" in text and "Stopped" in text
        assert page.locator("[data-stop-run]").count() == 0
    finally:
        page.close()


def test_an_evicted_frame_says_so_instead_of_showing_a_broken_image(browser, live):
    base, app = live
    run = _seed(app, with_frame_file=False)
    page = _open(browser, base, run, 1440, 900)
    try:
        page.locator(".computer-missing").wait_for(timeout=8000)
        assert "no longer retained" in page.locator(".computer-missing").inner_text()
        _shot(page, "missing-frame")
    finally:
        page.close()
