"""Real-browser checks (Chromium or Firefox via Playwright) of what unit tests cannot see: the live stream surviving a
network drop in the actual DOM, and the plain-POST controls doing what they say.

Skipped automatically when Playwright or its Chromium build is not installed:
    pip install playwright && playwright install chromium
"""

from __future__ import annotations

import threading
import time

import pytest

pw = pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402

from hutch.models import ApprovalMode, Bot, Event, EventType, RunStatus  # noqa: E402
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
            except Exception as exc:  # browser build unavailable; try another local engine
                errors.append(f"{engine.name}: {exc}")
        if b is None:
            pytest.skip("no Playwright browser is installed: " + "; ".join(errors))
        yield b
        b.close()


@pytest.fixture()
def live(tmp_path, monkeypatch):
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


class CuttableProxy:
    """A TCP forwarder between the browser and the server whose connections we can sever on demand.

    Playwright's ``set_offline`` does not terminate an already-open SSE connection in Chromium (events keep
    flowing), so it cannot prove resume. Killing the sockets does: the browser sees a real network failure.

    Retained for server-rendered SSE connectors (``/runs/{id}/stream``); the transcript page itself now
    redirects into the SPA, so the SPA transcript journey is exercised by ``test_spa_transcript_renders_a_live_run``.
    """

    def __init__(self, target_port: int):
        import socket
        self.target = target_port
        self.blocked = False
        self._conns: list = []
        self._lock = threading.Lock()
        self._srv = socket.socket()
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(64)
        self.port = self._srv.getsockname()[1]
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        import socket
        while True:
            try:
                client, _ = self._srv.accept()
            except OSError:
                return
            if self.blocked:
                client.close()
                continue
            try:
                upstream = socket.create_connection(("127.0.0.1", self.target))
            except OSError:
                client.close()
                continue
            with self._lock:
                self._conns += [client, upstream]
            for a, b in ((client, upstream), (upstream, client)):
                threading.Thread(target=self._pipe, args=(a, b), daemon=True).start()

    @staticmethod
    def _pipe(src, dst):
        try:
            while (data := src.recv(65536)):
                dst.sendall(data)
        except OSError:
            pass
        finally:
            for sock in (src, dst):
                try:
                    sock.shutdown(2)
                except OSError:
                    pass

    def cut(self):
        """Sever every live connection and refuse new ones until ``restore``."""
        self.blocked = True
        with self._lock:
            conns, self._conns = self._conns, []
        for c in conns:
            try:
                c.shutdown(2)
                c.close()
            except OSError:
                pass

    def restore(self):
        self.blocked = False

    def close(self):
        self.cut()
        self._srv.close()


def wait_for(fn, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.05)
    raise AssertionError("timed out")


def test_spa_transcript_renders_a_live_run(browser, live, monkeypatch):
    """The server transcript page now redirects into the SPA (single UI, 27a73ed).

    Keep the journey honest: a busy run must render its live transcript in the SPA
    run view and reach a terminal state, without leaking page errors.
    """
    base, app = live
    store, engine = app.state.store, app.state.engine
    import hutch.runtime.mock as mock_mod

    def chatty(self, run, ctx, tools, stop):
        for i in range(60):
            ctx.emit(Event(run_id=run.id, type=EventType.log, data={"note": f"event {i}"}))
            time.sleep(0.03)
        ctx.emit(Event(run_id=run.id, type=EventType.message,
                       data={"role": "assistant", "content": "done"}))
        return "done"

    monkeypatch.setattr(mock_mod.MockRuntime, "execute", chatty)
    bot = store.create_bot(Bot(name="drop-bot", model="mock/demo", approval_mode=ApprovalMode.auto))
    run = engine.submit(bot, "stream a lot")
    engine.dispatch_pending()

    ctx = browser.new_context(viewport={"width": 1200, "height": 800})
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{base}/#/run/{run.id}")
    page.wait_for_selector("#chat-stream .msg.agent .answer", timeout=30_000)
    assert "done" in page.inner_text("#chat-stream")
    assert not errors, errors
    ctx.close()


def test_studio_conversation_survives_reload_and_archive(browser, live):
    base, app = live
    bot = app.state.store.create_bot(Bot(name="durable-chat", model="mock/demo", tools=[]))
    context = browser.new_context(viewport={"width": 1100, "height": 800})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(base + "/#/chat/durable-chat")
    page.locator("#conversation-switcher").wait_for()
    conversation_id = page.locator("#conversation-switcher").input_value()

    page.locator("#chat-prompt").fill("First durable conversation")
    with page.expect_response(lambda r: "/api/v1/conversations/" in r.url and r.url.endswith("/messages")
                              and r.request.method == "POST") as first_response:
        page.locator("#chat-send").click()
    first_run = first_response.value.json()
    assert first_run["conversation_id"] == conversation_id
    wait_for(lambda: app.state.store.get_run(first_run["id"]).status.value == "succeeded")
    page.locator("#chat-stream").get_by_text("First durable conversation", exact=True).wait_for()
    page.locator(".msg.agent .answer").filter(has_text="First durable conversation").wait_for()

    page.reload()
    page.locator("#conversation-switcher").wait_for()
    page.locator("#chat-stream").get_by_text("First durable conversation", exact=True).wait_for()
    page.locator(".msg.agent .answer").filter(has_text="First durable conversation").wait_for()

    page.locator("#chat-prompt").fill("Continue this conversation")
    with page.expect_response(lambda r: "/api/v1/conversations/" in r.url and r.url.endswith("/messages")
                              and r.request.method == "POST") as second_response:
        page.locator("#chat-send").click()
    second_run = second_response.value.json()
    stored = app.state.store.get_run(second_run["id"])
    assert stored.conversation_context[0] == {"role": "user", "content": "First durable conversation"}
    wait_for(lambda: app.state.store.get_run(second_run["id"]).status.value == "succeeded")

    page.locator("#studio-archive-conversation").click()
    wait_for(lambda: page.locator("#conversation-switcher").input_value() != conversation_id)
    archived = app.state.store.get_conversation(conversation_id)
    assert archived["archived"] == 1
    assert len(app.state.store.list_conversation_messages(conversation_id)) >= 4
    assert not errors, errors
    context.close()


def test_stopping_status_uses_human_label_and_stays_nonterminal(browser, live, monkeypatch):
    base, app = live
    monkeypatch.setattr(app.state.engine, "tick", lambda: [])  # hold this UI fixture in cancelling
    bot = app.state.store.create_bot(Bot(name="status-bot", model="mock/demo", tools=[]))
    run = app.state.engine.submit(bot, "wait for cancellation")
    app.state.store.transition_run(run.id, RunStatus.cancelling)

    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.goto(f"{base}/#/run/{run.id}")
    chip = page.locator(".app-top-context .status")
    assert chip.inner_text() == "Stopping"
    assert chip.get_attribute("class").endswith("cancelling")
    assert page.get_by_text("cancelling", exact=True).count() == 0
    assert app.state.store.get_run(run.id).terminal is False
    page.close()


@pytest.mark.parametrize("width,height,size", [(1440, 1000, "desktop"), (900, 1024, "tablet"), (390, 844, "phone")])
def test_inference_queue_reason_and_timing_are_visible(browser, live, monkeypatch, width, height, size):
    import hashlib
    import json
    from datetime import timedelta
    from pathlib import Path
    from hutch.models import Run, Task, iso, utcnow
    base, app = live
    monkeypatch.setattr(app.state.engine, "tick", lambda: None)
    bot = app.state.store.create_bot(Bot(name="queue-fixture", model="mock/demo", tools=[]))
    reason = "waiting for local inference: queue position 2 of at most 8; one Hutch call at a time"
    conversation, _ = app.state.store.create_conversation(bot.id, "Inference queue fixture", idem_key="queue", request_hash="queue")
    run = Run(bot_id=bot.id, prompt="sanitized queue layout fixture", created_at=iso(utcnow() - timedelta(seconds=3)))
    app.state.store.submit_conversation_message(conversation["id"], run.prompt, run,
        Task(bot_id=bot.id, kind="conversation", prompt=run.prompt), idem_key="turn", request_hash="turn")
    app.state.store.transition_run(run.id, RunStatus.waiting_resources, fields={"reason": reason})
    page = browser.new_page(viewport={"width": width, "height": height}, reduced_motion="reduce")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/inference-admission"
    out.mkdir(parents=True, exist_ok=True)
    try:
        page.goto(base + "/#/conversation/" + conversation["id"])
        page.locator(".run-wait").wait_for()
        assert page.locator(".run-wait").inner_text() == reason
        if size == "desktop":
            rail = page.locator(".ws-roster").bounding_box()
            field = page.locator("#bot-search").bounding_box()
            assert field["x"] >= rail["x"] and field["x"] + field["width"] <= rail["x"] + rail["width"]
        assert not page.locator(".typing").count(), "resource waits must not claim ongoing inference"
        page.screenshot(path=str(out / f"waiting-{size}.png"), full_page=True, animations="disabled")
        app.state.store.transition_run(run.id, RunStatus.running)
        app.state.store.append_event(Event(run_id=run.id, type=EventType.step,
            data={"n": 1, "model_ms": 100, "tool_ms": 20, "overhead_ms": 10, "queue_ms": 1500}))
        app.state.store.transition_run(run.id, RunStatus.succeeded, fields={"queue_ms": 1800, "reason": "", "steps": 1})
        page.goto(base + "/#/run/" + run.id)
        page.get_by_text("Recorded step timing", exact=True).wait_for()
        assert "startup and steps" in page.locator(".run-queue-time").inner_text()
        assert "queue 1500ms" in page.locator(".timeline-legend").inner_text()
        chart = page.locator(".timeline-stack")
        assert "hutch 10ms, step queue 1500ms" in chart.get_attribute("aria-label")
        assert float(chart.locator(".s-queue").evaluate("el => el.style.width.slice(0,-1)")) > 90
        page.screenshot(path=str(out / f"timing-{size}.png"), full_page=True, animations="disabled")
        overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
        assert overflow <= 1 and not errors
        (out / f"{size}.json").write_text(json.dumps({
            "browser": browser.browser_type.name, "version": browser.version, "viewport": [width, height],
            "captured_at": iso(utcnow()), "scenario": "synthetic queue and timing; not live inference",
            "page_errors": errors, "horizontal_overflow": overflow,
            "source_sha256": {p: hashlib.sha256((out.parents[3] / p).read_bytes()).hexdigest()
                for p in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css", "src/hutch/runtime/builtin.py")},
        }, indent=2) + "\n")
    finally:
        page.close()


def test_mobile_navigation_traps_tab_and_restores_focus(browser, live):
    base, _app = live
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.goto(base, wait_until="domcontentloaded")
    page.wait_for_selector("#btn-create-first")
    toggle = page.locator("#nav-toggle")
    toggle.click()
    assert toggle.get_attribute("aria-expanded") == "true"
    assert page.evaluate("document.activeElement.classList.contains('brand')")
    assert page.evaluate("document.activeElement.tagName") not in {"INPUT", "TEXTAREA"}
    page.locator("#workspace .ws-foot-link").last.focus()
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.classList.contains('brand')")
    page.keyboard.press("Escape")
    assert toggle.get_attribute("aria-expanded") == "false"
    assert page.evaluate("document.activeElement.id") == "nav-toggle"
    assert page.evaluate("document.activeElement.tagName") not in {"INPUT", "TEXTAREA"}
    page.close()


def test_usage_budget_table_uses_labelled_phone_cards(browser, live):
    base, app = live
    app.state.store.create_bot(Bot(name="usage-responsive"))
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.goto(f"{base}/usage", wait_until="domcontentloaded")
    cell = page.locator('#caps td[data-label="Tokens today"]').first
    cell.wait_for()
    assert page.eval_on_selector('#caps td[data-label="Tokens today"]', "el => getComputedStyle(el).display") == "grid"
    assert page.eval_on_selector('#caps td[data-label="Spend today"]', "el => el.getAttribute('data-label')") == "Spend today"
    assert page.evaluate("document.documentElement.scrollWidth === innerWidth")
    page.close()


def test_approve_from_the_phone_ui_resumes_the_run(browser, live):
    """The data-approval card lives in the SPA now; the phone journey must still work."""
    base, app = live
    store, engine = app.state.store, app.state.engine
    bot = store.create_bot(Bot(name="ui-bot", model="mock/demo", tools=["files", "memory"],
                               approval_mode=ApprovalMode.ask))
    run = engine.submit(bot, "write a report")
    engine.dispatch_pending()
    wait_for(lambda: store.get_run(run.id).status is RunStatus.waiting_approval)

    ctx = browser.new_context(viewport={"width": 390, "height": 844})     # phone width (UI-13)
    page = ctx.new_page()
    page.goto(f"{base}/#/approvals")
    page.wait_for_selector("[data-approval]")
    # long status/bot text must not push the phone layout into horizontal scroll
    assert page.evaluate("document.documentElement.scrollWidth - window.innerWidth") <= 1
    countdown = page.inner_text("[data-ttl-text]")
    time.sleep(2.1)
    assert page.inner_text("[data-ttl-text]") != countdown                 # the deadline visibly ticks
    assert "left" in page.inner_text("[data-ttl-text]")

    page.click('[data-approve="1"]')
    wait_for(lambda: store.get_run(run.id).status is RunStatus.succeeded)   # approving really resumes the run
    ctx.close()


def test_a_stale_approval_click_shows_the_other_devices_decision(browser, live):
    """One request, two devices. The device that loses the race must not report success
    it did not get — it reads the server's decision and shows that instead."""
    from hutch.approvals import resolve_approval

    base, app = live
    store, engine = app.state.store, app.state.engine
    bot = store.create_bot(Bot(name="race-bot", model="mock/demo", tools=["files", "memory"],
                               approval_mode=ApprovalMode.ask))
    run = engine.submit(bot, "write a report")
    engine.dispatch_pending()
    wait_for(lambda: store.get_run(run.id).status is RunStatus.waiting_approval)

    ctx = browser.new_context(viewport={"width": 1200, "height": 800})
    page = ctx.new_page()
    page.goto(f"{base}/#/run/{run.id}")
    page.wait_for_selector("#chat-stream [data-approve]")
    approval_id = page.get_attribute("#chat-stream [data-approval]", "data-approval")

    resolve_approval(store, approval_id, approve=True, by="phone")     # the other device wins the race

    page.click('#chat-stream [data-approve="1"]')                      # our click is now stale (409)
    page.wait_for_selector("#chat-stream .approval-card-chat.resolved")
    tag = page.inner_text("#chat-stream .approval-card-chat.resolved .tag")
    assert "Approved" in tag and "phone" in tag
    ctx.close()


def test_bot_limits_can_be_saved_from_the_phone_settings(browser, live):
    base, app = live
    store = app.state.store
    store.create_bot(Bot(name="limit-bot", model="mock/demo", approval_mode=ApprovalMode.auto))
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"{base}/#/bot/limit-bot")
    page.locator("#form-limits").wait_for()
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
    page.locator('#form-limits [name="max_steps"]').fill("11")
    page.locator('#form-limits [name="daily_token_cap"]').fill("7500")
    page.locator('#form-limits [name="max_cost_usd"]').fill("0.65")
    page.locator('#form-limits button[type="submit"]').click()
    wait_for(lambda: store.get_bot("limit-bot").limits.max_steps == 11)
    limits = store.get_bot("limit-bot").limits
    assert limits.daily_token_cap == 7500 and limits.max_cost_usd == 0.65
    assert not errors, errors
    ctx.close()


# ============================================================ model switcher (composer menu + all-models dialog)

@pytest.fixture()
def switcher_env(live, monkeypatch):
    from tests.fakes import FakeOllama
    small = {"params": "1B", "size": 500_000_000}            # small enough to fit any machine that runs the tests
    fake = FakeOllama({"tiny:1b": dict(small), "small:2b": dict(small),
                       "huge:70b": {"params": "70B", "size": 45_000_000_000, "ctx": 131072}})
    monkeypatch.setenv("OLLAMA_HOST", fake.url)
    from hutch.modelchoices import reset_cache
    from hutch.runtime.ladder import reset_provider_cache
    reset_provider_cache()
    reset_cache()
    base, app = live
    app.state.store.create_bot(Bot(name="chatty", model="ollama/tiny:1b", approval_mode=ApprovalMode.auto,
                                   tools=[], selfcheck=False))
    yield base, app, fake
    fake.close()


def test_composer_switcher_menu_check_keyboard_and_per_message_override(browser, switcher_env):
    from tests.fakes import agent_script
    base, app, fake = switcher_env
    fake.script = agent_script([{"content": "answered on the small model"}])
    page = browser.new_context(viewport={"width": 1280, "height": 800}).new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base + "/")
    btn = page.locator(".ms-btn")
    btn.wait_for()
    assert "tiny:1b" in btn.inner_text()
    assert btn.get_attribute("aria-expanded") == "false"

    btn.click()
    menu = page.locator(".ms-menu")
    menu.wait_for(state="visible")
    items = page.locator(".ms-menu .ms-item[role=menuitemradio]")
    page.wait_for_function("document.querySelectorAll('.ms-menu .ms-item[role=menuitemradio]').length >= 2")
    assert items.first.get_attribute("aria-checked") == "true", "the model in use carries the check"
    assert "default" in items.first.inner_text()
    assert page.evaluate("document.activeElement.classList.contains('ms-item')"), "focus moves into the menu"
    assert btn.get_attribute("aria-expanded") == "true"
    # a model that cannot fit is not offered in the compact menu
    assert "huge:70b" not in menu.inner_text()

    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")                          # pick the next model with the keyboard
    assert menu.is_hidden() and btn.get_attribute("aria-expanded") == "false"
    assert page.evaluate("document.activeElement.classList.contains('ms-btn')"), "focus returns to the button"
    chosen = btn.inner_text().strip()
    assert chosen == "small:2b"
    assert "is-custom" in btn.get_attribute("class")

    page.locator("#chat-prompt").fill("hello there")
    with page.expect_response(lambda r: "/api/v1/conversations/" in r.url and r.url.endswith("/messages")
                              and r.request.method == "POST") as info:
        page.locator("#chat-send").click()
    body = info.value.json()
    assert body["model_override"].startswith("ollama/") and body["model_override"] == "ollama/small:2b"
    assert app.state.store.get_bot("chatty").model == "ollama/tiny:1b", "switching must not edit the bot"

    page.reload()                                           # the choice is remembered for this bot
    page.locator(".ms-btn").wait_for()
    assert page.locator(".ms-btn").inner_text().strip() == chosen
    assert not errors, errors


def test_all_models_dialog_filters_explains_and_applies(browser, switcher_env):
    base, app, fake = switcher_env
    page = browser.new_context(viewport={"width": 1280, "height": 800}).new_page()
    page.goto(base + "/")
    page.locator(".ms-btn").click()
    page.locator(".ms-more").click()
    dlg = page.locator(".modal-card")
    dlg.wait_for()
    text = dlg.inner_text()
    assert "Choose a model for this chat" in text and "huge:70b" in text
    assert "won't fit" in text, "a model that does not fit is shown, with the reason, but cannot be chosen"
    assert page.locator('input[name="ms-pick"][value="ollama/huge:70b"]').is_disabled()
    assert "anthropic" in text.lower() and "ANTHROPIC_API_KEY" in text
    assert "leaves this machine" in text
    assert page.locator('a[href="/models"]').count() == 1

    page.locator(".ms-search").fill("small")
    assert page.locator(".ms-row:visible").count() == 1
    page.locator(".ms-search").fill("zzz-nothing")
    assert page.locator(".ms-empty").is_visible()
    page.locator(".ms-search").fill("small")
    page.locator('input[name="ms-pick"][value="ollama/small:2b"]').check()
    page.locator("#modal-confirm").click()
    assert "small:2b" in page.locator(".ms-btn").inner_text()

    page.locator(".ms-btn").click()                          # Escape closes the menu and keeps the choice
    page.keyboard.press("Escape")
    assert page.locator(".ms-menu").is_hidden() and "small:2b" in page.locator(".ms-btn").inner_text()


def test_switcher_fits_a_phone_screen(browser, switcher_env):
    base, app, fake = switcher_env
    page = browser.new_context(viewport={"width": 390, "height": 844}).new_page()
    page.goto(base + "/")
    page.locator(".ms-btn").click()
    page.locator(".ms-menu").wait_for(state="visible")
    box = page.locator(".ms-menu").bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= 390, box
    assert page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 1


def test_small_workspace_has_one_roster_and_legacy_routes_do_not_trap_back(browser, live):
    base, app = live
    app.state.store.create_bot(Bot(name="one-bot", model="mock/demo", tools=[]))
    page = browser.new_page(viewport={"width": 1200, "height": 800})
    page.goto(base + "/#/chat/one-bot")
    page.locator("#conversation-switcher").wait_for()
    assert not page.locator("#fleet-nav").is_visible()
    assert not page.locator("#monitor-nav").get_attribute("open")
    assert page.get_by_text("Manage all bots", exact=True).count() == 0
    assert page.get_by_role("button", name="Context", exact=True).count() == 0
    page.get_by_role("link", name="Settings for one-bot").click()
    page.get_by_role("heading", name="one-bot settings", exact=True).wait_for()
    assert page.get_by_text("Recent runs", exact=True).count() == 0
    page.goto(base + "/#/overview")
    page.get_by_role("heading", name="Activity", exact=True).wait_for()
    page.evaluate("location.hash = '#/bots'")
    page.wait_for_url("**/#/chat")
    page.locator("#conversation-switcher").wait_for()
    page.go_back()
    page.get_by_role("heading", name="Activity", exact=True).wait_for()
    page.close()


def test_fleet_appears_at_ten_bots_with_search_and_state_filters(browser, live):
    base, app = live
    for i in range(9):
        app.state.store.create_bot(Bot(name=f"fleet-{i}", model="mock/demo", tools=[], paused=i == 2))
    page = browser.new_page(viewport={"width": 1200, "height": 800})
    page.goto(base + "/#/chat")
    page.locator("#conversation-switcher").wait_for()
    assert page.locator("#fleet-nav").is_hidden()
    app.state.store.create_bot(Bot(name="fleet-9", model="mock/demo", tools=[]))
    page.reload()
    page.locator("#conversation-switcher").wait_for()
    page.locator("#monitor-nav > summary").click()
    page.get_by_role("link", name="Fleet", exact=True).click()
    page.locator("#fleet-search").wait_for()
    assert page.locator("#fleet-count").inner_text() == "10 of 10 bots"
    page.locator("#fleet-state").select_option("paused")
    assert page.locator("#fleet-count").inner_text() == "1 of 10 bots"
    page.locator("#fleet-search").fill("fleet-9")
    assert page.locator("#fleet-count").inner_text() == "0 of 10 bots"
    page.locator("#fleet-state").select_option("all")
    assert page.locator("#fleet-count").inner_text() == "1 of 10 bots"
    page.close()


def test_bot_and_conversation_switches_isolate_unsent_drafts(browser, live):
    base, app = live
    for name in ("draft-a", "draft-b"):
        app.state.store.create_bot(Bot(name=name, model="mock/demo", tools=[]))
    page = browser.new_page(viewport={"width": 1200, "height": 800})
    page.goto(base + "/#/chat/draft-a")
    page.locator("#conversation-switcher").wait_for()
    first = page.locator("#conversation-switcher").input_value()
    page.locator("#chat-prompt").fill("Private draft for A")
    # No debounce wait: immediate navigation must preserve the draft in its own context.
    page.locator('[data-switch-bot="draft-b"]').click()
    page.wait_for_function("document.querySelector('#chat-prompt')?.placeholder.includes('draft-b')")
    assert page.locator("#chat-prompt").input_value() == ""
    page.locator('[data-switch-bot="draft-a"]').click()
    page.wait_for_function("document.querySelector('#chat-prompt')?.placeholder.includes('draft-a')")
    assert page.locator("#chat-prompt").input_value() == "Private draft for A"
    page.locator("#studio-new-conversation").click()
    page.wait_for_function("id => document.querySelector('#conversation-switcher')?.value !== id", arg=first)
    assert page.locator("#chat-prompt").input_value() == ""
    page.locator("#conversation-switcher").select_option(first)
    page.wait_for_function("document.querySelector('#chat-prompt')?.value === 'Private draft for A'")
    page.close()


def test_inline_chat_approval_is_one_click_and_preserves_conversation(browser, live):
    base, app = live
    app.state.store.create_bot(Bot(name="chat-approval", model="mock/demo", tools=["files", "memory"],
                                   approval_mode=ApprovalMode.ask))
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.goto(base + "/#/chat/chat-approval")
    page.locator("#conversation-switcher").wait_for()
    conversation = page.locator("#conversation-switcher").input_value()
    page.locator("#chat-prompt").fill("write a report")
    page.locator("#chat-send").click()
    card = page.locator("#chat-stream [data-approval-card]").first
    card.locator('[data-approve="1"]').wait_for()
    approval_id = card.get_attribute("data-approval-card")
    assert card.get_attribute("data-action-hash")
    thread = card.locator("xpath=ancestor::article[@data-run-id]")
    assert thread.locator(".msg.you").count() == 1
    assert thread.locator(".msg.you").bounding_box()["y"] < thread.locator(".msg.agent").bounding_box()["y"]
    assert not thread.locator(".answer").count(), "a waiting run must not echo the user's prompt as an assistant answer"
    card.get_by_text("Review details", exact=True).click()
    assert card.locator(".approval-detail").is_visible()
    card.locator('[data-approve="1"]').focus()
    time.sleep(3.3)  # transcript poll keeps the review expanded and the decision focused
    assert card.locator(".approval-detail").is_visible()
    assert card.locator('[data-approve="1"]').evaluate("e => e === document.activeElement")
    assert page.locator("#studio-stop-run").is_visible()
    header = page.locator(".app-top").bounding_box()
    for control in ("#conversation-switcher", "#studio-new-conversation", "#studio-stop-run"):
        box = page.locator(control).bounding_box()
        assert box["y"] >= header["y"] and box["y"] + box["height"] <= header["y"] + header["height"] + 1
    stream = page.locator("#chat-scroll").bounding_box()
    assert stream["y"] >= header["y"] + header["height"] - 1
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
    card.locator('[data-approve="1"]').click()
    wait_for(lambda: app.state.store.get_approval(approval_id).status.value == "approved")
    assert page.locator("#conversation-switcher").input_value() == conversation
    assert "#/chat/chat-approval" in page.url
    assert page.locator("#needs-you").get_attribute("open") is None
    page.close()


def test_needs_you_pages_large_queues_without_hiding_requests(browser, live, monkeypatch):
    from datetime import timedelta
    from hutch.approvals import action_fingerprint
    from hutch.models import ApprovalRequest, Run, iso, utcnow
    base, app = live
    monkeypatch.setattr(app.state.engine, "tick", lambda: None)
    bot = app.state.store.create_bot(Bot(name="queue-bot", model="mock/demo", tools=[]))
    run = app.state.store.create_run(Run(bot_id=bot.id, prompt="queue fixture", status=RunStatus.waiting_approval))
    requests = []
    for i in range(51):
        detail = {"path": f"report-{i}.txt", "content": f"Draft {i}"}
        requests.append(app.state.store.create_approval(ApprovalRequest(
            run_id=run.id, bot_id=bot.id, tool="files", action=f"write report-{i}.txt", detail=detail,
            action_hash=action_fingerprint("files", detail), expires_at=iso(utcnow() + timedelta(minutes=10)))))
    page = browser.new_page(viewport={"width": 1200, "height": 800})
    page.goto(base + "/#/chat/queue-bot")
    page.locator("#needs-you-open").click()
    page.locator("#approvals-pagination").get_by_text("1–50 of 51 requests", exact=True).wait_for()
    assert page.locator("#needs-you [data-approval-card]").count() == 50
    page.locator("#approvals-pagination").get_by_role("button", name="Next", exact=True).click()
    page.locator("#approvals-pagination").get_by_text("51–51 of 51 requests", exact=True).wait_for()
    final = page.locator("#needs-you [data-approval-card]")
    assert final.count() == 1
    final_id = final.get_attribute("data-approval-card")
    final.locator('[data-approve="0"]').click()
    wait_for(lambda: app.state.store.get_approval(final_id).status.value == "denied")
    page.locator("#approvals-pagination").get_by_text("1–50 of 50 requests", exact=True).wait_for()
    assert {a.id for a in app.state.store.pending_approvals()} == {a.id for a in requests} - {final_id}
    page.close()


def test_needs_you_drawer_preserves_review_focus_and_reports_refresh_failure(browser, live):
    base, app = live
    bot = app.state.store.create_bot(Bot(name="drawer-bot", model="mock/demo", tools=["files", "memory"],
                                       approval_mode=ApprovalMode.ask))
    run = app.state.engine.submit(bot, "write a report")
    app.state.engine.dispatch_pending()
    wait_for(lambda: app.state.store.get_run(run.id).status is RunStatus.waiting_approval)
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.goto(base + "/#/chat/drawer-bot")
    page.locator("#conversation-switcher").wait_for()
    page.locator("#nav-toggle").click()
    page.locator("#needs-you-open").click()
    card = page.locator("#needs-you [data-approval-card]").first
    card.wait_for()
    card.locator("summary").click()
    allow = card.locator('[data-approve="1"]')
    allow.focus()
    time.sleep(5.3)  # unchanged queue poll must preserve review and decision focus
    assert card.locator("details").get_attribute("open") is not None
    assert allow.evaluate("e => e === document.activeElement")
    page.keyboard.press("Escape")
    assert page.evaluate("document.activeElement.id") == "nav-toggle"
    page.route("**/api/**approvals**", lambda route: route.abort() if route.request.method == "GET" else route.continue_())
    page.locator("#nav-toggle").click()
    page.locator("#needs-you-open").click()
    page.locator("#needs-you-error").wait_for(state="visible")
    assert "may be outdated" in page.locator("#needs-you-error").inner_text()
    assert card.is_visible()  # failed fetch never means an empty/successful queue
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
    page.unroute("**/api/**approvals**")
    page.locator("#needs-you-retry").click()
    page.locator("#needs-you-error").wait_for(state="hidden")
    card.locator('[data-approve="0"]').click()
    wait_for(lambda: app.state.store.pending_approvals() == [])
    page.close()


def test_queued_chat_keeps_earlier_approval_and_live_status_fresh(browser, live):
    base, app = live
    app.state.store.create_bot(Bot(name="queue-chat", model="mock/demo", tools=["files", "memory"],
                                   approval_mode=ApprovalMode.ask))
    page = browser.new_page(viewport={"width": 1200, "height": 900})
    page.goto(base + "/#/chat/queue-chat")
    page.locator("#conversation-switcher").wait_for()
    page.locator("#chat-prompt").fill("write a report")
    page.locator("#chat-send").click()
    card = page.locator("#chat-stream [data-approval-card]").first
    card.locator('[data-approve="1"]').wait_for()
    first_approval = card.get_attribute("data-approval-card")
    first_run = app.state.store.get_approval(first_approval).run_id
    page.locator("#chat-prompt").fill("write the next report")
    page.locator("#chat-send").click()
    second = page.locator("#chat-stream [data-run-id]").last
    page.wait_for_function("document.querySelectorAll('#chat-stream [data-run-id]').length === 2")
    assert "Queued" in second.inner_text()
    assert page.locator("#studio-stop-run").get_attribute("data-stop-target") == first_run
    assert "Waiting for you" in page.locator(".ctx-meta").inner_text()
    assert not page.locator("#typing-slot .typing").count()
    # The older active run must not enter the terminal HTML cache when currentRunId changes.
    page.locator(f'[data-approval-card="{first_approval}"] [data-approve="1"]').click()
    first = page.locator(f'[data-run-id="{first_run}"]')
    first.get_by_text("Done", exact=True).wait_for()
    second.locator("[data-approval-card] [data-approve='0']").wait_for()
    second.locator("[data-approval-card] [data-approve='0']").click()
    page.close()


@pytest.mark.parametrize("width,height,size", [(1440, 1000, "desktop"), (390, 844, "phone")])
def test_old_active_approval_survives_chat_window_and_header_stop_targets_it(browser, live, monkeypatch, width, height, size):
    import hashlib
    import json
    from pathlib import Path
    from datetime import timedelta
    from hutch.approvals import action_fingerprint
    from hutch.models import ApprovalRequest, Run, Task, iso, utcnow
    base, app = live
    store = app.state.store
    monkeypatch.setattr(app.state.engine, "tick", lambda: None)
    bot = store.create_bot(Bot(name="active-window", model="mock/demo", tools=[]))
    conv, _ = store.create_conversation(bot.id, "Long queue fixture", idem_key="create", request_hash="create")
    runs = []
    for i in range(8):
        run = Run(bot_id=bot.id, prompt=f"Sanitized queued turn {i}",
                  status=RunStatus.waiting_approval if i == 0 else RunStatus.pending)
        store.submit_conversation_message(conv["id"], run.prompt, run, Task(bot_id=bot.id, prompt=run.prompt),
                                          idem_key=f"turn-{i}", request_hash=f"turn-{i}")
        runs.append(run)
    detail = {"path": "fixture.txt", "content": "sanitized review"}
    request = store.create_approval(ApprovalRequest(run_id=runs[0].id, bot_id=bot.id, tool="files",
        action="write fixture.txt", detail=detail, action_hash=action_fingerprint("files", detail),
        expires_at=iso(utcnow() + timedelta(minutes=10))))
    store.append_event(Event(run_id=runs[0].id, type=EventType.approval_request,
        data={"approval_id": request.id, "tool": request.tool, "action": request.action,
              "detail": request.detail, "action_hash": request.action_hash, "expires_at": request.expires_at}))
    store.flush_events()
    page = browser.new_page(viewport={"width": width, "height": height}, reduced_motion="reduce")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(base + "/#/chat/active-window")
    card = page.locator(f'#chat-stream [data-approval-card="{request.id}"]')
    card.locator("[data-approve='1']").wait_for()
    assert page.locator("#studio-stop-run").get_attribute("data-stop-target") == runs[0].id
    assert "Waiting for you" in page.locator(".ctx-meta").inner_text()
    assert not page.locator("#typing-slot .typing").count()
    assert page.locator("#chat-stream [data-run-id]").count() == 6
    page.route(f"**/api/runs/{runs[0].id}", lambda route: route.abort())
    page.wait_for_timeout(4400)
    assert card.is_visible(), "a failed refresh must retain the reviewable request"
    assert "may be outdated" in page.locator(".feed-refresh-error").inner_text()
    assert page.locator("#studio-stop-run").is_visible(), "a failed refresh cannot mean completion"
    assert page.locator("#studio-stop-run").get_attribute("data-stop-target") == runs[0].id
    page.unroute(f"**/api/runs/{runs[0].id}")
    page.locator("#studio-review-run").click()
    assert card.locator("summary, button").first.evaluate("e => e === document.activeElement")
    box = card.bounding_box()
    feed = page.locator("#chat-scroll").bounding_box()
    assert box["y"] >= feed["y"] - 1 and box["y"] + box["height"] <= feed["y"] + feed["height"] + 1
    if size == "phone":
        assert page.locator("#studio-review-run").bounding_box()["height"] >= 44
        assert card.locator("xpath=ancestor::article").locator(".mhead .status").evaluate(
            "e => e.scrollWidth <= e.clientWidth + 1"), "keep the complete waiting label visible"
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/conversation-authority"
    out.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out / f"{size}.png"), full_page=True, animations="disabled")
    overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
    assert overflow <= 1 and not errors
    with page.expect_response(lambda response: response.url.endswith(f"/{runs[0].id}/stop")) as stopped:
        page.locator("#studio-stop-run").click()
    assert stopped.value.status == 200
    assert store.get_run(runs[0].id).cancel_requested
    assert not store.get_run(runs[-1].id).cancel_requested
    assert store.get_approval(request.id).status.value == "expired"
    (out / f"{size}.json").write_text(json.dumps({
        "browser": browser.browser_type.name, "version": browser.version, "viewport": [width, height],
        "captured_at": iso(utcnow()), "scenario": "synthetic old approval, seven queued turns, failed run refresh, real Stop command",
        "page_errors": errors, "horizontal_overflow": overflow,
        "source_sha256": {p: hashlib.sha256((out.parents[3] / p).read_bytes()).hexdigest()
            for p in ("src/hutch/server/static/app.js", "src/hutch/store.py", "src/hutch/server/app.py")},
    }, indent=2) + "\n")
    page.close()


@pytest.mark.parametrize("width,height,size", [(1440, 1000, "desktop"), (390, 844, "phone")])
def test_fleet_attention_survives_queue_failure_and_includes_human_wait(browser, live, monkeypatch, width, height, size):
    import hashlib
    import json
    from datetime import timedelta
    from pathlib import Path
    from hutch.approvals import action_fingerprint
    from hutch.models import ApprovalRequest, Run, iso, utcnow
    base, app = live
    monkeypatch.setattr(app.state.engine, "tick", lambda: None)
    bots = [app.state.store.create_bot(Bot(name=f"attention-{i}", model="mock/demo", tools=[])) for i in range(10)]
    app.state.store.create_run(Run(bot_id=bots[0].id, prompt="older queued fixture"))
    app.state.store.create_run(Run(bot_id=bots[0].id, prompt="human session fixture", status=RunStatus.waiting_human))
    run = app.state.store.create_run(Run(bot_id=bots[9].id, prompt="request queue fixture", status=RunStatus.waiting_approval))
    for i in range(51):
        detail = {"path": f"fixture-{i}.txt", "content": "sanitized draft"}
        app.state.store.create_approval(ApprovalRequest(
            run_id=run.id, bot_id=bots[9].id, tool="files", action=f"write fixture-{i}.txt", detail=detail,
            action_hash=action_fingerprint("files", detail), expires_at=iso(utcnow() + timedelta(minutes=10))))
    page = browser.new_page(viewport={"width": width, "height": height}, reduced_motion="reduce")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    # Queue discovery is unavailable: bot lifecycle metadata must still identify both waits.
    page.route("**/api/approvals", lambda route: route.abort())
    page.goto(base + "/#/bots")
    page.locator("#fleet-state").select_option("needs")
    assert page.locator("#fleet-count").inner_text() == "2 of 10 bots"
    assert page.locator(".bot-card:visible").count() == 2
    assert "Needs you" in page.locator('[data-fleet-bot="attention-0"]').inner_text()
    assert "Waiting for you" in page.locator('[data-fleet-bot="attention-9"]').inner_text()
    assert "Needs you" in page.locator('[data-switch-bot="attention-0"]').inner_text()
    assert "Needs you" in page.locator('[data-switch-bot="attention-9"]').inner_text()
    if size == "phone":
        page.locator("#attention-bar").wait_for(state="visible")
        notice = page.locator("#attention-bar").bounding_box()
        content = page.locator("#view").bounding_box()
        assert notice["y"] + notice["height"] <= content["y"] + 1, "the notice must not cover Fleet content"
    overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
    assert overflow <= 1 and not errors
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/fleet-attention"
    out.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out / f"{size}.png"), full_page=True, animations="disabled")
    (out / f"{size}.json").write_text(json.dumps({
        "browser": browser.browser_type.name, "version": browser.version, "viewport": [width, height],
        "captured_at": iso(utcnow()), "scenario": "synthetic waits, 51 persisted requests, failed queue discovery; no live handoff",
        "page_errors": errors, "horizontal_overflow": overflow,
        "source_sha256": {p: hashlib.sha256((out.parents[3] / p).read_bytes()).hexdigest()
            for p in ("src/hutch/server/static/app.js", "src/hutch/store.py")},
    }, indent=2) + "\n")
    page.close()


@pytest.mark.parametrize("width,height,size", [(1440, 1000, "desktop"), (900, 1024, "tablet"), (390, 844, "phone")])
def test_composer_options_rehearsal_and_cancelled_notice(browser, live, width, height, size):
    import hashlib
    import json
    from pathlib import Path
    from hutch.models import Run, iso, utcnow
    base, app = live
    bot = app.state.store.create_bot(Bot(name="composer-fixture", model="mock/demo", tools=["files", "memory"],
                                       approval_mode=ApprovalMode.auto))
    page = browser.new_page(viewport={"width": width, "height": height}, reduced_motion="reduce")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(base + "/#/chat/composer-fixture")
    page.locator("#conversation-switcher").wait_for()
    assert not page.locator("#studio-stop-run").is_visible()
    assert page.locator("#chat-stop").count() == 0, "do not duplicate the primary Stop beside Send"
    page.locator("#composer-menu-btn").click()
    menu = page.locator("#composer-menu")
    assert menu.is_visible() and menu.get_attribute("role") == "dialog"
    assert menu.locator("button").first.evaluate("e => e === document.activeElement")
    box = menu.bounding_box()
    assert 0 <= box["x"] and box["x"] + box["width"] <= width + 1
    assert 0 <= box["y"] and box["y"] + box["height"] <= height + 1
    menu.get_by_text("model calls and reads still happen", exact=False).wait_for()
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/composer-integration"
    out.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out / f"options-{size}.png"), full_page=True, animations="disabled")
    menu.locator("#rehearse-opt").check()
    page.keyboard.press("Escape")
    assert not menu.is_visible()
    assert page.locator("#composer-menu-btn").evaluate("e => e === document.activeElement")
    assert "model calls and reads" in page.locator("#rehearse-flag").inner_text()
    if size == "phone":
        for control in ("#composer-menu-btn", "#chat-send"):
            assert page.locator(control).bounding_box()["height"] >= 44
    page.locator("#chat-prompt").fill("write a report")
    with page.expect_response(lambda response: response.url.endswith("/messages") and response.request.method == "POST") as sent:
        page.locator("#chat-send").click()
    run = sent.value.json()
    assert sent.value.request.post_data_json["rehearse"] is True
    wait_for(lambda: app.state.store.get_run(run["id"]).terminal)
    stored = app.state.store.get_run(run["id"])
    assert stored.rehearsal and not (Path(stored.workspace) / "report.md").exists()
    assert not app.state.store.recall_all(bot.id)
    cancelled = app.state.store.create_run(Run(bot_id=bot.id, prompt="Sanitized cancellation notice fixture",
        status=RunStatus.stopped, error="Cancelled before a model step completed", queue_ms=1250, finished_at=iso(utcnow())))
    page.goto(base + f"/#/run/{cancelled.id}")
    notice = page.locator(".run-error")
    notice.wait_for()
    assert notice.inner_text().startswith("Cancelled:") and "Failed:" not in notice.inner_text()
    assert "run-notice" in notice.get_attribute("class")
    assert "1.3s" in page.locator(".run-queue-time").inner_text()
    assert not page.locator(".timeline-stack").count(), "no completed step means no fabricated timing breakdown"
    overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
    assert overflow <= 1 and not errors
    page.screenshot(path=str(out / f"cancelled-{size}.png"), full_page=True, animations="disabled")
    (out / f"{size}.json").write_text(json.dumps({
        "browser": browser.browser_type.name, "version": browser.version, "viewport": [width, height],
        "captured_at": iso(utcnow()), "scenario": "real mock rehearsal; synthetic cancellation and admitted queue timing",
        "page_errors": errors, "horizontal_overflow": overflow,
        "source_sha256": {p: hashlib.sha256((out.parents[3] / p).read_bytes()).hexdigest()
            for p in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css")},
    }, indent=2) + "\n")
    page.close()
