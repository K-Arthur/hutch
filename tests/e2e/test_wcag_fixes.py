"""WCAG 2.2 AA fix verification (docs/realignment/wcag22-audit-2026-10-10.md).

Each test pins one audit finding: F-1 skip link, F-2 route focus/title,
F-3 error-toast target, F-4 prose link underline, F-5 workflow pill target,
M-1 tool-stream summary target, M-2 coarse small-button target,
M-4 unknown-route 404 page shell.
"""
from __future__ import annotations

import threading
import time
from datetime import timedelta

import pytest
import uvicorn

from hutch.models import (ApprovalRequest, Bot, Event, EventType, Run, RunStatus,
                          RuntimeKind, Task, iso, utcnow)
from hutch.server.app import create_app
from hutch.approvals import action_fingerprint


@pytest.fixture(scope="module")
def audit_browser():
    import playwright.sync_api as pw

    with pw.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture()
def audit_live(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_MAX_CONCURRENT", "4")
    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", lifespan="on"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}", app
    server.should_exit = True
    t.join(timeout=10)


def seed_pending_approval(store, name="wcag-fixture-bot"):
    bot = store.create_bot(Bot(name=name, model="mock/demo", runtime=RuntimeKind.mock, tools=["shell"]))
    run = store.create_run(Run(bot_id=bot.id, prompt="wcag fixture", status=RunStatus.waiting_approval))
    detail = {"command": "rm -rf build/tmp"}
    store.create_approval(ApprovalRequest(
        run_id=run.id, bot_id=bot.id, tool="shell", action="rm -rf build/tmp", detail=detail,
        action_hash=action_fingerprint("shell", detail),
        expires_at=iso(utcnow() + timedelta(minutes=10))))
    return bot


def wait_live(page, base):
    page.goto(base + "/#/chat")
    page.locator('#daemon-pill[data-state="live"]').wait_for(state="attached")


def test_skip_link_moves_focus_into_main(audit_browser, audit_live):
    """F-1: activating the skip link delivers focus to the main view."""
    base, _ = audit_live
    page = audit_browser.new_page()
    try:
        wait_live(page, base)
        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement.className") == "skip-link"
        page.keyboard.press("Enter")
        page.wait_for_timeout(250)
        focused = page.evaluate("""() => { const el = document.activeElement;
            return {id: el.id, tag: el.tagName}; }""")
        assert focused == {"id": "view", "tag": "MAIN"}
    finally:
        page.close()


def test_route_change_updates_title_and_rescues_orphaned_focus(audit_browser, audit_live):
    """F-2: hash navigation sets a per-view title and moves focus lost to the re-render."""
    base, _ = audit_live
    page = audit_browser.new_page(viewport={"width": 1200, "height": 800})
    try:
        wait_live(page, base)
        page.evaluate("() => { location.hash = '#/runs'; }")
        page.locator("#run-search").wait_for()
        assert "Work history" in page.title()
        # focus an element inside #view, then navigate away: the swap orphans it,
        # so the router must anchor focus on the new view's heading.
        page.locator("#run-search").focus()
        page.evaluate("() => { location.hash = '#/overview'; }")
        page.wait_for_timeout(400)
        assert "Activity" in page.title()
        focused = page.evaluate("""() => { const el = document.activeElement;
            return {tag: el.tagName, text: el.textContent.trim()}; }""")
        assert focused["tag"] == "H1" and "Activity" in focused["text"]
    finally:
        page.close()


def test_fragment_hash_never_redirects_to_chat(audit_browser, audit_live):
    """F-1: pure fragment hashes are left alone instead of hijacked to #/chat."""
    base, _ = audit_live
    page = audit_browser.new_page()
    try:
        wait_live(page, base)
        page.evaluate("() => { location.hash = '#view'; }")
        page.wait_for_timeout(250)
        assert page.evaluate("location.hash") == "#view"
        assert page.evaluate("document.title").startswith("hutch")
    finally:
        page.close()


def test_error_toasts_are_assertive_with_24px_dismiss(audit_browser, audit_live):
    """F-3 + N-5: error toasts announce assertively and the dismiss target is >= 24px."""
    base, _ = audit_live
    page = audit_browser.new_page(viewport={"width": 390, "height": 844})
    try:
        wait_live(page, base)
        page.evaluate("() => toast('wcag fixture failure', true)")
        page.locator(".toast.error").wait_for()
        role, box = page.evaluate("""() => { const t = document.querySelector('.toast.error');
            const c = t.querySelector('.toast-close').getBoundingClientRect();
            return [t.getAttribute('role'), [c.width, c.height]]; }""")
        assert role == "alert"
        assert box[0] >= 24 and box[1] >= 24
    finally:
        page.close()


def test_workflow_pill_meets_target_minimum(audit_browser, audit_live):
    """F-5: the 'needs you' workflow link is at least 24px tall on desktop."""
    base, app = audit_live
    seed_pending_approval(app.state.store)
    page = audit_browser.new_page(viewport={"width": 1440, "height": 960})
    try:
        wait_live(page, base)
        pill = page.locator(".workflow a.w.needs")
        pill.wait_for()
        height = pill.evaluate("el => el.getBoundingClientRect().height")
        assert height >= 24
    finally:
        page.close()


def test_tool_stream_summary_meets_target_minimum(audit_browser, audit_live):
    """M-1: the tool-stream disclosure header is at least 24px tall."""
    base, app = audit_live
    store = app.state.store
    bot = store.create_bot(Bot(name="wcag-tools", model="mock/demo", runtime=RuntimeKind.mock, tools=["files"]))
    conversation, _ = store.create_conversation(bot.id, "Tool fixture", idem_key="wcag-tool-conv",
                                                request_hash="wcag-tool-req")
    run = Run(bot_id=bot.id, prompt="read the fixture file")
    task = Task(bot_id=bot.id, kind="on_demand", prompt="read the fixture file")
    run_id, _ = store.submit_conversation_message(conversation["id"], "read the fixture file", run, task,
                                                  idem_key="wcag-tool-msg", request_hash="wcag-tool-msg-req")
    claimed = store.claim_run(run_id, "wcag-fixture", 60)
    store.transition_run(run_id, RunStatus.running, fence=claimed.fence, event={"fixture": "wcag"})
    store.append_event(Event(run_id=run_id, type=EventType.tool_call,
                             data={"tool": "read_file", "args": {"path": "notes.md"}}))
    store.flush_events()

    page = audit_browser.new_page(viewport={"width": 1440, "height": 960})
    try:
        page.goto(base + f"/#/conversation/{conversation['id']}")
        page.locator(".tool-stream summary").wait_for()
        height = page.evaluate("() => document.querySelector('.tool-stream summary').getBoundingClientRect().height")
        assert height >= 24
    finally:
        page.close()


def test_small_inline_buttons_meet_44px_on_touch(audit_browser, audit_live):
    """M-2: .btn.small inline actions reach the 44px comfort target on coarse pointers."""
    base, app = audit_live
    seed_pending_approval(app.state.store)
    context = audit_browser.new_context(viewport={"width": 390, "height": 844},
                                        is_mobile=True, has_touch=True)
    page = context.new_page()
    try:
        page.goto(base + "/#/chat")
        page.locator('#daemon-pill[data-state="live"]').wait_for(state="attached")
        # Measure the cascade directly: a labelled probe .btn.small in the live
        # document isolates the coarse-pointer rule from per-widget overrides.
        height = page.evaluate("""() => {
          const el = document.createElement('button');
          el.className = 'btn ghost small';
          el.textContent = 'wcag fixture probe';
          document.getElementById('view').append(el);
          const h = el.getBoundingClientRect().height;
          el.remove();
          return h; }""")
        assert height >= 44
    finally:
        context.close()


def test_unknown_page_renders_html_404_with_title_and_lang(audit_browser, audit_live):
    """M-4: unmatched page routes get the themed error page (title + lang)."""
    base, _ = audit_live
    page = audit_browser.new_page()
    try:
        response = page.goto(base + "/legacy/runs")
        assert response.status == 404
        assert page.evaluate("document.documentElement.getAttribute('lang')") == "en"
        assert page.title().strip() != ""
        assert page.locator("main h1").inner_text().strip() == "404"
    finally:
        page.close()


def test_prose_links_are_underlined_at_rest(audit_browser, audit_live):
    """F-4: in-prose links are identifiable by more than color."""
    base, _ = audit_live
    page = audit_browser.new_page()
    try:
        page.goto(base + "/login")
        page.locator('a[href="/pair"]').wait_for()
        decoration = page.evaluate(
            "() => getComputedStyle(document.querySelector('a[href=\"/pair\"]')).textDecorationLine")
        assert "underline" in decoration
    finally:
        page.close()
