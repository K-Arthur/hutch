"""Real-browser checks (Chromium via Playwright) of what unit tests cannot see: the live stream surviving a
network drop in the actual DOM, and the plain-POST controls doing what they say.

Skipped automatically when Playwright or its Chromium build is not installed:
    pip install playwright && playwright install chromium
"""

from __future__ import annotations

import re
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
        try:
            b = p.chromium.launch()
        except Exception as exc:  # browser build not installed
            pytest.skip(f"chromium unavailable: {exc}")
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


def test_transcript_resumes_in_the_dom_after_the_network_drops(browser, live, monkeypatch):
    base, app = live
    store, engine = app.state.store, app.state.engine
    import hutch.runtime.mock as mock_mod

    def chatty(self, run, ctx, tools, stop):
        for i in range(150):
            ctx.emit(Event(run_id=run.id, type=EventType.log, data={"note": f"event {i}"}))
            time.sleep(0.03)
        return "done"

    monkeypatch.setattr(mock_mod.MockRuntime, "execute", chatty)
    bot = store.create_bot(Bot(name="drop-bot", model="mock/demo", approval_mode=ApprovalMode.auto))
    run = engine.submit(bot, "stream a lot")
    engine.dispatch_pending()

    proxy = CuttableProxy(int(base.rsplit(":", 1)[1]))
    ctx = browser.new_context(viewport={"width": 1200, "height": 800})
    page = ctx.new_page()
    page.goto(f"http://127.0.0.1:{proxy.port}/runs/{run.id}?noreload=1")
    page.wait_for_selector("#stream-state[data-state=live]", timeout=10_000)
    time.sleep(0.8)

    proxy.cut()                                            # a real network failure mid-run
    page.wait_for_selector("#stream-state[data-state=reconnecting]", timeout=10_000)   # the UI says so
    frozen_at = page.evaluate("document.querySelectorAll('#tx-list [data-seq]').length")
    time.sleep(1.5)                                        # ~50 events happen on the server meanwhile
    assert page.evaluate("document.querySelectorAll('#tx-list [data-seq]').length") == frozen_at
    server_seq_during_outage = store.last_seq(run.id)
    assert server_seq_during_outage > frozen_at + 20, "the server must have produced events while we were cut off"
    proxy.restore()                                        # EventSource reconnects by itself, sending Last-Event-ID

    wait_for(lambda: store.get_run(run.id).status is RunStatus.succeeded, timeout=30)
    page.wait_for_selector("#stream-state[data-state=done]", timeout=20_000)
    seqs = page.eval_on_selector_all("#tx-list [data-seq]", "els => els.map(e => parseInt(e.dataset.seq, 10))")

    expected = list(range(1, store.last_seq(run.id) + 1))
    assert seqs == expected, f"DOM transcript has gaps/duplicates: missing={sorted(set(expected) - set(seqs))[:10]}"
    ctx.close()
    proxy.close()


def test_approve_and_stop_work_from_the_real_ui(browser, live):
    base, app = live
    store, engine = app.state.store, app.state.engine
    bot = store.create_bot(Bot(name="ui-bot", model="mock/demo", tools=["files", "memory"],
                               approval_mode=ApprovalMode.ask))
    run = engine.submit(bot, "write a report")
    engine.dispatch_pending()
    wait_for(lambda: store.get_run(run.id).status is RunStatus.waiting_approval)

    ctx = browser.new_context(viewport={"width": 390, "height": 844})     # phone width (UI-13)
    page = ctx.new_page()
    page.goto(f"{base}/overview")
    page.wait_for_selector("[data-approval]")
    countdown = page.inner_text("[data-countdown-to] .cd-text")
    time.sleep(2.1)
    assert page.inner_text("[data-countdown-to] .cd-text") != countdown     # the deadline visibly ticks
    assert page.inner_text("[data-countdown-to] .cd-text").startswith("denies in")

    page.click("button:has-text('Allow once')")
    wait_for(lambda: store.get_run(run.id).status is RunStatus.succeeded)   # approving really resumes the run

    # second run: Stop all from the header, a plain confirmed POST
    run2 = engine.submit(bot, "write another report")
    engine.dispatch_pending()
    wait_for(lambda: store.get_run(run2.id).status is RunStatus.waiting_approval)
    page.on("dialog", lambda d: d.accept())
    page.goto(f"{base}/overview")
    page.click("header button:has-text('Stop all')")
    wait_for(lambda: store.get_run(run2.id).status is RunStatus.stopped)
    assert re.search(r"Stopped 1 run", page.inner_text("body"))
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
    with page.expect_response(lambda r: r.url.endswith("/api/bots/chatty/run") and r.request.method == "POST") as info:
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
