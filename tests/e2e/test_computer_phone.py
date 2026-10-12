"""Actual Chromium pixels/input through Hutch HTTP + responsive panel; no live model or physical phone claim."""
from __future__ import annotations

import os
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import expect

from hutch.approvals import ApprovalGate
from hutch.computer.human import sessions
from hutch.config import get_config
from hutch.models import Bot, Run, RunStatus
from hutch.safety import PolicyEngine
from hutch.tools.base import ToolContext
from hutch.tools.browser import BrowserTool
from tests.e2e.test_computer_panel import browser, live  # noqa: F401 fixtures, real Chromium and Uvicorn


class _Page(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/receipt" and hasattr(self.server, "signed_in"):
            self.server.signed_in.set()
        body = b'''<!doctype html><title>Controlled login</title><style>body{padding:40px;font:20px sans-serif}input,button{font:inherit;margin:12px;padding:12px;display:block}</style>
        <h1>Controlled login</h1><input type=password id=password aria-label=Password>
        <button id=continue onclick="if(document.querySelector('#password').value==='SENTINEL-HUMAN-ONLY'){fetch('/receipt');document.body.innerHTML='<h1>Signed in</h1><p id=result>Human input reached the intended session</p>';history.pushState({},'', '/done')}">Continue</button>'''
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args): pass


@pytest.fixture()
def controlled(live, tmp_path):
    base, app = live
    config = get_config()
    origin = ThreadingHTTPServer(("127.0.0.1", 0), _Page)
    serving = threading.Thread(target=origin.serve_forever, daemon=True)
    serving.start()
    port = origin.server_address[1]
    bot = Bot(name="phone-controlled", tools=["browser"], remote_computer_access="control",
              local_dev_origins=[f"http://localhost:{port}"])
    store = app.state.store
    store.upsert_bot(bot)
    run = store.create_run(Run(bot_id=bot.id, prompt="Complete the controlled login", status=RunStatus.running))
    finish, ready = threading.Event(), threading.Event()
    effects, failures = {}, []

    def worker():
        class FixtureGate(ApprovalGate):
            # The setup navigation has explicit fixture consent. Human waiting and all input use the production paths.
            def decide(self, tool, action, detail, *args, **kwargs):
                assert tool == "browser" and detail.get("origin", detail.get("url", "")).startswith(f"http://localhost:{port}")
        gate = FixtureGate(store, bot, run, PolicyEngine(), store.append_event, poll_seconds=0.2)
        gate.ttl = 60
        gate.cancelled = finish.is_set
        ctx = ToolContext(bot=bot, run=run, store=store, config=config, workspace=tmp_path, gate=gate,
                          policy=PolicyEngine(), emit=store.append_event)
        tool = BrowserTool()
        try:
            ready.set()
            opened = tool.run({"action": "goto", "url": f"http://localhost:{port}/"}, ctx)
            effects["opened"] = opened
            page = tool._tabs[tool._active_tab]
            effects["signed_in"] = page.locator("#result").inner_text()
            effects["url"] = page.url
        except Exception as exc:
            failures.append(str(exc))
        finally:
            for hook in ctx.on_finish: hook()
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        assert ready.wait(5)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not sessions(config, run.id):
            time.sleep(0.05)
        assert sessions(config, run.id), failures
        # The page's real sensitive-field check must suspend the worker without capturing it for a model.
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and store.get_run(run.id).status is not RunStatus.waiting_human:
            time.sleep(0.05)
        assert store.get_run(run.id).status is RunStatus.waiting_human, effects
        yield base, app, run, bot, effects, failures, thread
    finally:
        finish.set()
        store.bus.notify(f"human:{run.id}", remote=False)
        for session in sessions(config, run.id): session.close()
        thread.join(timeout=10)
        origin.shutdown(); origin.server_close(); serving.join(timeout=3)


def _shot(page, name):
    target = os.environ.get("HUTCH_EVIDENCE_DIR")
    if target:
        Path(target).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(target) / f"phone-control-{name}.png"), full_page=False)


@pytest.mark.parametrize("width,height", [(360, 780), (768, 1024), (1440, 900)])
def test_login_control_from_panel_reaches_owned_headless_session_and_hands_back(browser, controlled, width, height):
    base, app, run, bot, effects, failures, worker = controlled
    page = browser.new_page(viewport={"width": width, "height": height}, reduced_motion="reduce")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(f"{base}/#/run/{run.id}")
        panel = page.locator(".computer-remote")
        panel.wait_for(timeout=10_000)
        assert panel.get_by_role("button", name="Refresh human frame").is_disabled()
        panel.get_by_role("button", name="Take control").click()
        panel.get_by_role("button", name="Refresh human frame").click()
        preview = panel.locator(".computer-human-preview")
        page.wait_for_function("() => document.querySelector('.computer-human-img')?.naturalWidth > 0")
        preview.scroll_into_view_if_needed()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        _shot(page, f"{width}")
        page.wait_for_timeout(250)
        # Browser CSS coordinates, mapped through the REAL preview image bounds. The page starts at 1280x720.
        image_box = panel.locator(".computer-human-img").bounding_box()
        page.mouse.click(image_box["x"] + 120 * image_box["width"] / 1280,
                         image_box["y"] + 155 * image_box["height"] / 720)
        page.wait_for_timeout(450)
        assert panel.get_by_role("button", name="Type in focused control").is_enabled(), panel.inner_text()
        panel.get_by_label("Text to type in the controlled app").fill("SENTINEL-HUMAN-ONLY")
        panel.get_by_role("button", name="Type in focused control").click()
        page.wait_for_function("() => document.querySelector('.computer-remote textarea').value === ''")
        page.wait_for_timeout(250)
        panel.get_by_label("Key to send").select_option("tab")
        panel.get_by_role("button", name="Send key").click()
        page.wait_for_timeout(450)
        panel.get_by_label("Key to send").select_option("enter")
        panel.get_by_role("button", name="Send key").click()
        page.wait_for_timeout(450)
        panel.get_by_role("button", name="Hand back to Hutch").click()
        worker.join(timeout=10)
        assert not worker.is_alive() and not failures, failures
        assert effects["signed_in"] == "Human input reached the intended session" and effects["url"].endswith("/done")
        wire = str([event.model_dump() for event in app.state.store.list_events(run.id)])
        assert "SENTINEL-HUMAN-ONLY" not in wire and "data:image/" not in wire
        assert not errors, errors
    finally:
        page.close()


def test_rotation_reflow_two_viewers_and_pagehide_pause(browser, controlled):
    from hutch.computer.control import ControlOwner
    base, app, run, bot, effects, failures, worker = controlled
    pages = [browser.new_page(viewport={"width": 360, "height": 780}, reduced_motion="reduce") for _ in range(2)]
    try:
        for page in pages:
            page.goto(f"{base}/#/run/{run.id}")
            page.locator(".computer-remote").wait_for()
        first, second = pages
        panel = first.locator(".computer-remote")
        panel.get_by_role("button", name="Take control").click()
        panel.get_by_role("button", name="Refresh human frame").click()
        first.wait_for_function("() => document.querySelector('.computer-human-img')?.naturalWidth > 0")
        channel = sessions(get_config(), run.id)[0]
        assert channel.public()["control"]["owner"] == "human"
        other = second.locator(".computer-remote")
        other.get_by_role("button", name="Take control").click()
        expect(other.get_by_role("status")).to_contain_text("another viewer")
        for name, width, height in [("landscape", 780, 360), ("reflow", 320, 900)]:
            first.set_viewport_size({"width": width, "height": height})
            panel.get_by_label("Text to type in the controlled app").focus()
            assert panel.get_by_label("Text to type in the controlled app").evaluate("node => node === document.activeElement")
            assert panel.get_by_label("Text to type in the controlled app").evaluate("node => { const r=node.getBoundingClientRect(), b=document.querySelector('.computer-control-bar').getBoundingClientRect(); return r.top >= b.bottom && r.bottom <= innerHeight; }")
            assert first.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            _shot(first, name)
        # Fault injection of the browser's page lifecycle event, not a physical-phone suspension claim.
        first.evaluate("window.dispatchEvent(new PageTransitionEvent('pagehide'))")
        deadline = time.monotonic() + 3
        while channel.lease.snapshot().owner is not ControlOwner.paused and time.monotonic() < deadline:
            time.sleep(0.02)
        assert channel.lease.snapshot().owner is ControlOwner.paused
        assert not channel.public()["controller_present"] and not channel._png and not channel._queue
        assert panel.get_by_role("button", name="Type in focused control").is_disabled()
        other.get_by_role("button", name="Take control").click()
        other.get_by_role("button", name="Pause control").click()
        assert channel.lease.snapshot().owner is ControlOwner.paused and worker.is_alive()
        target = os.environ.get("HUTCH_EVIDENCE_DIR")
        if target:
            (Path(target) / "phone-lifecycle.json").write_text(json.dumps({"environment": "Chromium viewport emulation",
                "rotations": [[360, 780], [780, 360], [320, 900]], "two_viewer_exclusivity": True,
                "pagehide": "injected lifecycle event; host paused", "typed_history": "no input in this scenario",
                "accessibility": other.aria_snapshot()}, indent=2))
    finally:
        for page in pages: page.close()


def test_normal_process_worker_accepts_http_human_input_and_exits_cleanly(browser, live, monkeypatch):
    from hutch.approvals import resolve_approval
    from hutch.models import ApprovalMode
    from tests.fakes import FakeOllama, agent_script
    base, app = live
    origin = ThreadingHTTPServer(("127.0.0.1", 0), _Page)
    origin.signed_in = threading.Event()
    serving = threading.Thread(target=origin.serve_forever, daemon=True)
    serving.start()
    provider = FakeOllama({"tiny:1b": {"params": "1.0B", "size": 500_000_000, "ctx": 8192}})
    monkeypatch.setenv("OLLAMA_HOST", provider.url)
    local = f"http://localhost:{origin.server_address[1]}"
    provider.script = agent_script([{"tool_calls": [{"name": "browser", "arguments": {"action": "goto", "url": local}}]},
                                    {"content": "finished after fresh human handback"}])
    store, engine = app.state.store, app.state.engine
    monkeypatch.setattr(engine, "executor", "process")  # hutch serve/daemon use this production executor
    bot = Bot(name="process-phone", model="ollama/tiny:1b", tools=["browser"], selfcheck=False,
              approval_mode=ApprovalMode.auto, remote_computer_access="control", local_dev_origins=[local])
    store.upsert_bot(bot)
    run = engine.submit(bot, "Open the local controlled login and wait for me.")
    page = browser.new_page(viewport={"width": 360, "height": 780}, reduced_motion="reduce")
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            current = store.get_run(run.id)
            for approval in store.pending_approvals():
                if approval.run_id == run.id:
                    assert approval.tool == "browser" and local in str(approval.detail)
                    resolve_approval(store, approval.id, True)
            if current.status is RunStatus.waiting_human or current.terminal:
                break
            time.sleep(0.1)
        current = store.get_run(run.id)
        assert current.status is RunStatus.waiting_human, current.error
        assert current.pgid != os.getpid() and current.pgid > 0
        assert not any(s.ctx.run.id == run.id for s in __import__('hutch.computer.human', fromlist=['_REGISTRY'])._REGISTRY.values())
        page.goto(f"{base}/#/run/{run.id}")
        panel = page.locator(".computer-remote")
        panel.get_by_role("button", name="Take control").click()
        panel.get_by_role("button", name="Refresh human frame").click()
        page.wait_for_function("() => document.querySelector('.computer-human-img')?.naturalWidth > 0")
        panel.get_by_role("button", name="Refresh human frame").wait_for(state="visible")
        page.wait_for_timeout(250)
        preview = panel.locator(".computer-human-img")
        preview.scroll_into_view_if_needed()
        box = preview.bounding_box()
        page.mouse.click(box["x"] + 120 * box["width"] / 1280, box["y"] + 155 * box["height"] / 720)
        expect(panel.get_by_role("button", name="Type in focused control")).to_be_enabled()
        page.wait_for_timeout(250)
        panel.get_by_label("Text to type in the controlled app").fill("SENTINEL-HUMAN-ONLY")
        panel.get_by_role("button", name="Type in focused control").click()
        page.wait_for_function("() => document.querySelector('.computer-remote textarea').value === ''")
        for key in ("tab", "enter"):
            page.wait_for_timeout(250)
            panel.get_by_label("Key to send").select_option(key)
            panel.get_by_role("button", name="Send key").click()
            expect(panel.get_by_role("button", name="Send key")).to_be_enabled()
        assert origin.signed_in.wait(3), "actual login did not reach the app's receipt endpoint"
        preview.evaluate("node => node.scrollIntoView({block: 'center'})")
        _shot(page, "process-worker-360")
        panel.get_by_role("button", name="Hand back to Hutch").click()
        deadline = time.monotonic() + 15
        while not store.get_run(run.id).terminal and time.monotonic() < deadline:
            time.sleep(0.1)
        assert store.get_run(run.id).status is RunStatus.succeeded, store.get_run(run.id).error
        wire = str([e.model_dump() for e in store.list_events(run.id)]) + str(provider.requests)
        assert "SENTINEL-HUMAN-ONLY" not in wire and "data:image/" not in wire
        assert not sessions(app.state.config, run.id, fence=current.fence)
    finally:
        page.close()
        if not store.get_run(run.id).terminal: engine.stop_run(run.id)
        provider.close()
        origin.shutdown(); origin.server_close(); serving.join(timeout=3)
