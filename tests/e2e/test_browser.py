"""Real-browser checks (Chromium or Firefox via Playwright) of what unit tests cannot see: the live stream surviving a
network drop in the actual DOM, and the plain-POST controls doing what they say.

Skipped automatically when Playwright or its Chromium build is not installed:
    pip install playwright && playwright install chromium
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from datetime import datetime, timezone
from importlib.metadata import version as package_version
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402

from hutch.models import ApprovalMode, Bot, Event, EventType, Run, RunStatus, RuntimeKind, Task  # noqa: E402
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
    assert not t.is_alive()


def test_executor_health_status_uses_a_steady_indicator(browser, live):
    base, _ = live
    page = browser.new_page(viewport={"width": 1100, "height": 800})
    try:
        page.goto(base + "/#/chat")
        pill = page.locator('#daemon-pill[data-state="live"]')
        pill.wait_for()
        assert page.locator("#daemon-label").inner_text() == "live"
        assert page.locator(".daemon-dot").evaluate("el => getComputedStyle(el).animationName") == "none"
    finally:
        page.close()


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
    import tests.support.runtime as mock_mod

    def chatty(self, run, ctx, tools, stop):
        for i in range(60):
            ctx.emit(Event(run_id=run.id, type=EventType.log, data={"note": f"event {i}"}))
            time.sleep(0.03)
        ctx.emit(Event(run_id=run.id, type=EventType.message,
                       data={"role": "assistant", "content": "done"}))
        return "done"

    monkeypatch.setattr(mock_mod.TestScenarioRuntime, "execute", chatty)
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


def test_saved_tool_output_is_downloadable_and_verified_at_all_viewports(browser, live, monkeypatch):
    """Large tool results remain inspectable from the chat without trusting an unchecked disk path."""
    base, app = live
    store, engine = app.state.store, app.state.engine
    import tests.support.runtime as scenario_runtime
    from hutch.runtime.steps import call_tool

    original = "\n".join(f"artifact row {n:04d}: preserved outside the model context" for n in range(1200))

    def emit_large_result(self, run, ctx, tools, stop):
        (ctx.workspace / "large.txt").write_text(original, encoding="utf-8")
        call_tool(run, ctx, tools, "read_file", {"path": "large.txt"})
        call_tool(run, ctx, tools, "read_file", {"path": "large.txt"})
        run.steps += 1
        ctx.emit(Event(run_id=run.id, type=EventType.message,
                       data={"role": "assistant", "content": "The full result is available as a verified artifact."}))
        return "The full result is available as a verified artifact."

    monkeypatch.setattr(scenario_runtime.TestScenarioRuntime, "execute", emit_large_result)
    bot = store.create_bot(Bot(name="artifact-bot", model="ollama/qwen3:4b", runtime=RuntimeKind.mock, tools=["files"],
                               approval_mode=ApprovalMode.auto, tool_limits={"read_file": 256}))
    run = engine.submit(bot, "read the large output")
    engine.dispatch_pending()
    assert wait_for(lambda: store.get_run(run.id).status is RunStatus.succeeded)
    store.flush_transcripts()

    artifact_events = [e for e in store.list_events(run.id) if e.type is EventType.tool_result]
    assert [e.data["artifact"] for e in artifact_events] == [
        "artifacts/001-read_file.txt", "artifacts/002-read_file.txt"]
    artifacts = app.state.store.artifact_events(run.id)
    assert len(artifacts) == 2 and artifacts[0].seq < artifacts[1].seq
    artifact_event = artifact_events[0]
    assert artifact_event.data["chars"] == len(original)
    expected_hash = hashlib.sha256(original.encode()).hexdigest()
    assert artifact_event.data["artifact_sha256"] == expected_hash
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/versioned-artifacts"
    out.mkdir(parents=True, exist_ok=True)
    records = []
    for name, width, height in (("desktop", 1440, 1000), ("tablet", 768, 1024), ("phone", 390, 844)):
        context = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1)
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        page.goto(f"{base}/#/run/{run.id}")
        page.wait_for_selector(".tool-line-head", timeout=20_000)
        page.locator(".tool-line-head").first.click()
        link = page.locator(".artifact-download a").first
        link.wait_for(state="visible")
        href = link.get_attribute("href")
        assert href and f"/api/v1/tasks/runs/{run.id}/artifacts/" in href
        artifact_page = page.request.get(f"{base}/api/v1/tasks/runs/{run.id}/artifacts").json()
        assert [item["filename"] for item in artifact_page["artifacts"]] == [
            "001-read_file.txt", "002-read_file.txt"]
        image_path = out / f"{name}.png"
        page.screenshot(path=str(image_path), animations="disabled")
        link.focus()
        with page.expect_download() as download_info:
            page.keyboard.press("Enter")
        download = download_info.value
        downloaded = Path(download.path()).read_bytes()
        assert downloaded == original.encode("utf-8")
        assert download.suggested_filename == Path(artifact_event.data["artifact"]).name
        overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
        assert overflow <= 1 and not errors, {"overflow": overflow, "errors": errors}
        records.append({"viewport": name, "size": [width, height], "screenshot": image_path.name,
                        "screenshot_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
                        "artifact_sha256": hashlib.sha256(downloaded).hexdigest(), "overflow_px": overflow,
                        "page_errors": errors})
        context.close()

    repo = Path(__file__).resolve().parents[2]
    source_files = ("src/hutch/server/app.py", "src/hutch/server/static/app.js",
                    "src/hutch/server/static/style.css", "src/hutch/runtime/steps.py")
    (out / "results.json").write_text(json.dumps({
        "captured_at": datetime.now(timezone.utc).isoformat(), "browser": browser.browser_type.name,
        "browser_version": browser.version, "playwright": package_version("playwright"),
        "source_sha256": {name: hashlib.sha256((repo / name).read_bytes()).hexdigest()
                          for name in source_files},
        "artifacts": records, "provider_calls": 0,
        "runtime_fixture": "tests.support.TestScenarioRuntime",
        "limitation": "Fixture execution only; no Ollama service or model was invoked.",
    }, indent=2) + "\n")


def test_generated_workspace_file_is_downloadable_from_its_chat(browser, live, monkeypatch):
    """Studio exposes a verified file download without requiring tool details to be expanded."""
    base, app = live
    store, engine = app.state.store, app.state.engine
    import tests.support.runtime as scenario_runtime
    from hutch.runtime.steps import call_tool

    content = "invoice,total\nINV-042,84.50\n"

    def create_report(self, run, ctx, tools, stop):
        call_tool(run, ctx, tools, "write_file", {"path": "reports/monthly.csv", "content": content})
        run.steps += 1
        ctx.emit(Event(run_id=run.id, type=EventType.message,
                       data={"role": "assistant", "content": "Created reports/monthly.csv."}))
        return "Created reports/monthly.csv."

    monkeypatch.setattr(scenario_runtime.TestScenarioRuntime, "execute", create_report)
    bot = store.create_bot(Bot(name="generated-file-bot", model="mock/demo", runtime=RuntimeKind.mock,
                               tools=["files"], approval_mode=ApprovalMode.auto, workspace_mode="managed"))
    conversation, _ = store.create_conversation(bot.id, "Generated files", idem_key="generated-file-conversation",
                                                request_hash="generated-file-conversation-request")
    prompt = "create the monthly CSV report"
    run = Run(bot_id=bot.id, prompt=prompt)
    task = Task(bot_id=bot.id, kind="on_demand", prompt=prompt)
    run_id, _ = store.submit_conversation_message(
        conversation["id"], prompt, run, task, idem_key="generated-file-message",
        request_hash="generated-file-message-request")
    engine.dispatch_pending()
    assert wait_for(lambda: store.get_run(run_id).status is RunStatus.succeeded)
    store.flush_transcripts()

    desktop_page = browser.new_page(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
    desktop_errors = []
    desktop_page.on("pageerror", lambda error: desktop_errors.append(str(error)))
    desktop_page.goto(f"{base}/#/chat/{bot.name}")
    desktop_page.locator("#conversation-switcher").wait_for()
    assert desktop_page.locator("#conversation-switcher").input_value() == conversation["id"]
    event = next(e for e in store.list_events(run_id) if e.type is EventType.tool_result)
    descriptor = event.data["workspace_file"]
    assert descriptor["path"] == "reports/monthly.csv"
    assert hashlib.sha256(content.encode()).hexdigest() == descriptor["sha256"]

    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/generated-files"
    out.mkdir(parents=True, exist_ok=True)
    records = []
    for name, width, height in (("desktop", 1440, 1000), ("tablet", 768, 1024), ("phone", 390, 844)):
        page = desktop_page if name == "desktop" else browser.new_page(
            viewport={"width": width, "height": height}, reduced_motion="reduce")
        errors = desktop_errors if name == "desktop" else []
        if name != "desktop":
            page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            if name != "desktop":
                page.goto(f"{base}/#/chat/{bot.name}")
                page.locator("#conversation-switcher").wait_for()
            page.locator(".tool-line[data-tool-line]").wait_for()
            assert page.locator(".tool-line[data-tool-line] .tool-line-body").is_hidden(), "tool details should remain collapsed"
            link = page.locator(".workspace-file-attachments a")
            link.wait_for(state="visible")
            assert "Download monthly.csv" in link.inner_text()
            listed = page.request.get(f"{base}/api/v1/tasks/runs/{run_id}/artifacts").json()["artifacts"]
            artifact = next(item for item in listed if item["kind"] == "workspace_file")
            assert artifact["filename"] == "monthly.csv" and artifact["state"] == "available"
            image_path = out / f"{name}.png"
            page.screenshot(path=str(image_path), animations="disabled")
            link.focus()
            with page.expect_download() as download_info:
                page.keyboard.press("Enter")
            download = download_info.value
            saved = Path(download.path()).read_bytes()
            assert download.suggested_filename == "monthly.csv" and saved == content.encode("utf-8")
            assert hashlib.sha256(saved).hexdigest() == artifact["sha256"]
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1 and not errors, {"overflow": overflow, "errors": errors}
            records.append({"viewport": name, "size": [width, height], "screenshot": image_path.name,
                            "sha256": hashlib.sha256(saved).hexdigest(), "overflow_px": overflow,
                            "page_errors": errors})
        finally:
            page.close()

    repo = Path(__file__).resolve().parents[2]
    source_files = ("src/hutch/runtime/steps.py", "src/hutch/store.py", "src/hutch/server/app.py",
                    "src/hutch/server/static/app.js", "src/hutch/server/static/style.css")
    (out / "results.json").write_text(json.dumps({
        "captured_at": datetime.now(timezone.utc).isoformat(), "browser": browser.browser_type.name,
        "browser_version": browser.version, "playwright": package_version("playwright"),
        "source_sha256": {name: hashlib.sha256((repo / name).read_bytes()).hexdigest()
                          for name in source_files},
        "screenshots": {"generated_files": [record["screenshot"] for record in records]},
        "journey": "write a text file with Hutch's file tool; download its run-scoped immutable snapshot from chat",
        "runtime_fixture": "tests.support.TestScenarioRuntime", "provider_calls": 0, "captures": records,
        "limitation": "Only files written through write_file are snapshotted; arbitrary shell-created files are not attached.",
    }, indent=2) + "\n")


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


def test_real_device_pairing_and_revocation_are_usable_at_all_viewports(browser, live):
    """Exercise the one-time exchange, visible device inventory and both revoke paths."""
    import hashlib
    import json
    from hutch.models import iso, utcnow

    base, app = live
    code = app.state.store.create_pairing_code()
    other_code = app.state.store.create_pairing_code()
    app.state.store.exchange_pairing_code(other_code, "Old tablet", "192.0.2.10")
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/device-pairing"
    out.mkdir(parents=True, exist_ok=True)
    errors = []
    trace = []
    context = browser.new_context(viewport={"width": 390, "height": 844}, reduced_motion="reduce")
    page = context.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        for label, width, height in (("desktop", 1440, 1000), ("tablet", 900, 1024), ("phone", 390, 844),
                                     ("compact-phone", 320, 740)):
            page.set_viewport_size({"width": width, "height": height})
            response = page.goto(f"{base}/pair")
            assert response and response.status == 200
            assert page.get_by_role("heading", name="Pair this device").is_visible()
            assert page.locator("#primary-nav").count() == 0
            if label == "phone":
                for selector in ("[name=label]", "[name=code]", "#pair-submit"):
                    assert page.locator(selector).bounding_box()["height"] >= 44
            page.screenshot(path=str(out / f"{label}-pair-entry.png"), full_page=True, animations="disabled")
            trace.append({"step": "open_pair_page", "viewport": label, "http_status": response.status})
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, overflow)

        page.locator("[name=label]").fill("Kevin phone")
        page.locator("[name=code]").fill("AAAAAAAAAAAAAA")
        page.get_by_role("button", name="Pair device").click()
        page.locator("#pair-error").wait_for(state="visible")
        assert "invalid" in page.locator("#pair-error").inner_text()
        assert page.locator("[name=code]").input_value() == ""
        assert page.locator("[name=code]").evaluate("e => e === document.activeElement")
        trace.append({"step": "reject_invalid_code", "result": "rejected", "input": "[redacted]", "field_cleared": True})
        page.screenshot(path=str(out / "phone-invalid-code.png"), full_page=True, animations="disabled")

        page.locator("[name=code]").fill(code)
        page.get_by_role("button", name="Pair device").click()
        page.locator("#pair-success").wait_for(state="visible")
        assert not page.locator("#pair-form").is_visible()
        assert not page.locator("#pair-instructions").is_visible()
        assert page.get_by_role("link", name="Open Hutch").evaluate("e => e === document.activeElement")
        assert page.evaluate("document.cookie.includes('hutch_device')") is False
        assert page.evaluate("pairingCode => Object.values(localStorage).every(value => !value.includes(pairingCode))", code)
        trace.append({"step": "exchange_one_time_code", "result": "paired", "code": "[redacted]",
                      "session_cookie_readable_to_script": False, "focus": "Open Hutch"})
        page.screenshot(path=str(out / "phone-paired.png"), full_page=True, animations="disabled")
        page.get_by_role("link", name="Open Hutch").click()
        page.wait_for_selector("#view")
        page.goto(f"{base}/#/connections")
        page.get_by_role("heading", name="Connections").wait_for()
        page.locator(".device-manager summary").click()
        page.get_by_text("Kevin phone").wait_for()
        page.get_by_text("Old tablet").wait_for()
        current = page.locator(".device-row").filter(has_text="Kevin phone")
        assert current.get_by_text("this device").is_visible()
        assert page.locator(".device-row").filter(has_text="Old tablet").get_by_text("this device").count() == 0
        trace.append({"step": "list_paired_devices", "active_count": 2, "current_device_label": "Kevin phone"})

        for label, width, height in (("desktop", 1440, 1000), ("tablet", 900, 1024), ("phone", 390, 844),
                                     ("compact-phone", 320, 740)):
            page.set_viewport_size({"width": width, "height": height})
            if label == "phone":
                assert page.locator(".device-manager summary").bounding_box()["height"] >= 44
                assert current.get_by_role("button", name="Revoke").bounding_box()["height"] >= 44
            page.screenshot(path=str(out / f"{label}-device-manager.png"), full_page=True, animations="disabled")
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, overflow)
        old_tablet = page.locator(".device-row").filter(has_text="Old tablet")
        old_revoke = old_tablet.get_by_role("button", name="Revoke")
        old_revoke.focus()
        page.keyboard.press("Enter")
        page.locator("#modal-title").get_by_text("Revoke device", exact=True).wait_for()
        assert page.locator("#modal-confirm").evaluate("e => e === document.activeElement")
        page.keyboard.press("Escape")
        assert old_revoke.evaluate("e => e === document.activeElement")
        page.keyboard.press("Enter")
        page.locator("#modal-confirm").wait_for(state="visible")
        page.locator("#modal-confirm").click()
        page.get_by_text("Revoked Old tablet").wait_for()
        assert page.locator(".device-row").filter(has_text="Old tablet").count() == 0
        assert app.state.store.list_device_sessions()[0]["label"] == "Kevin phone"
        trace.append({"step": "revoke_other_device", "label": "Old tablet", "result": "revoked"})

        current = page.locator(".device-row").filter(has_text="Kevin phone")
        current.get_by_role("button", name="Revoke").click()
        page.locator("#modal-confirm").click()
        page.get_by_role("heading", name="Pair this device").wait_for()
        assert app.state.store.list_device_sessions() == []
        trace.append({"step": "revoke_current_device", "result": "revoked", "returned_to": "/pair"})
        overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
        assert overflow <= 1 and not errors, (overflow, errors)
        (out / "trace.json").write_text(json.dumps({
            "kind": "redacted_browser_interaction_trace",
            "browser": browser.browser_type.name,
            "browser_version": browser.version,
            "playwright_version": package_version("playwright"),
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_real_device_pairing_and_revocation_are_usable_at_all_viewports",
            "sensitive_values": "Pairing codes, cookies, request bodies, and session tokens are deliberately omitted.",
            "steps": trace,
        }, indent=2) + "\n")
        (out / "results.json").write_text(json.dumps({
            "captured_at": iso(utcnow()), "browser": browser.browser_type.name, "version": browser.version,
            "playwright_version": package_version("playwright"),
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_real_device_pairing_and_revocation_are_usable_at_all_viewports",
            "screenshots": sorted(path.name for path in out.glob("*.png")),
            "viewport_sizes": {"desktop": [1440, 1000], "tablet": [900, 1024], "phone": [390, 844], "compact_phone": [320, 740]},
            "page_errors": errors, "horizontal_overflow": 0,
            "journey": "Invalid code, successful one-use pairing, current-device labeling, other-device revoke, self-revoke",
            "device_token_in_document_cookie": False,
            "live_remote_network_or_physical_device": False,
            "source_sha256": {name: hashlib.sha256((out.parents[3] / name).read_bytes()).hexdigest() for name in (
                "src/hutch/server/app.py", "src/hutch/server/pages.py", "src/hutch/server/security.py",
                "src/hutch/server/templates/base.html", "src/hutch/server/templates/pair.html",
                "src/hutch/server/templates/login.html",
                "src/hutch/server/static/pair.js", "src/hutch/server/static/app.js",
                "src/hutch/server/static/style.css", "src/hutch/server/static/hutch-pages.css",
                "website/index.html")},
        }, indent=2) + "\n")
    finally:
        context.close()


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


def test_model_route_setting_explains_host_gated_offline_mode_and_saves_on_phone(browser, live):
    base, app = live
    store = app.state.store
    store.create_bot(Bot(name="route-bot", model="ollama/qwen3:4b", approval_mode=ApprovalMode.auto))
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.goto(f"{base}/#/bot/route-bot")
    mode = page.locator('#form-model select[name="inference_mode"]')
    mode.wait_for()
    assert mode.input_value() == "hybrid"
    offline_option = mode.locator('option[value="offline"]')
    offline_capability = next(row for row in page.request.get(f"{base}/api/v1/capabilities").json()
                              if row["id"] == "strict_offline")
    assert "Strict offline" in offline_option.inner_text()
    disabled_state = offline_option.evaluate("option => ({disabled: option.disabled, attribute: option.getAttribute('disabled'), html: option.outerHTML})")
    expected_disabled = offline_capability["status"] == "unavailable"
    if disabled_state["disabled"] != expected_disabled:
        ctx.close()
    assert disabled_state["disabled"] == expected_disabled, (offline_capability, disabled_state)
    assert page.locator("#inference-mode-help").is_visible()
    assert "separate model service" in page.locator("#inference-mode-help").inner_text()

    capture_dir = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/strict-offline"
    capture_dir.mkdir(parents=True, exist_ok=True)
    captures = []
    sizes = {"desktop": (1440, 1000), "tablet": (900, 1024), "phone": (390, 844)}
    ctx.tracing.start(screenshots=True, snapshots=True, sources=False)
    for size, (width, height) in sizes.items():
        page.set_viewport_size({"width": width, "height": height})
        page.wait_for_timeout(100)
        page.screenshot(path=str(capture_dir / f"settings-{size}.png"), full_page=True, animations="disabled")
        metrics = page.evaluate("""() => ({
            viewport: [innerWidth, innerHeight],
            document: [document.documentElement.scrollWidth, document.documentElement.scrollHeight],
            settingsVisible: Boolean(document.querySelector('#form-model'))
        })""")
        assert metrics["document"][0] - metrics["viewport"][0] <= 1
        captures.append({"size": size, **metrics, "strictOfflineDisabled": disabled_state["disabled"],
                         "capabilityStatus": offline_capability["status"]})

    page.set_viewport_size({"width": 390, "height": 844})
    mode.scroll_into_view_if_needed()
    assert mode.is_visible() and page.locator("#inference-mode-help").is_visible()
    page.screenshot(path=str(capture_dir / "settings-phone-routing.png"), animations="disabled")
    ctx.tracing.stop(path=str(capture_dir / "settings-trace.zip"))
    captures.append({"size": "phone-routing", "viewport": [390, 844], "routingVisible": mode.is_visible(),
                     "helpVisible": page.locator("#inference-mode-help").is_visible()})

    mode.select_option("local")
    page.locator('#form-model button[type="submit"]').click()
    wait_for(lambda: store.get_bot("route-bot").inference_mode.value == "local")
    assert page.locator("#form-model").is_visible()
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
    assert not errors, errors
    (capture_dir / "settings-capture.json").write_text(json.dumps({
        "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_model_route_setting_explains_host_gated_offline_mode_and_saves_on_phone",
        "browser": browser.browser_type.name,
        "browserVersion": browser.version,
        "playwrightVersion": package_version("playwright"),
        "capability": offline_capability,
        "captures": captures,
        "pageErrors": errors,
        "scenario": "synthetic bot settings; no provider or model call",
    }, indent=2) + "\n", encoding="utf-8")
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


def test_composer_switcher_menu_check_keyboard_and_per_message_override(browser, switcher_env, request):
    from tests.fakes import agent_script
    base, app, fake = switcher_env
    fake.script = agent_script([{"content": "answered on the small model"}])
    page = browser.new_context(viewport={"width": 1280, "height": 800}).new_page()
    request.addfinalizer(page.close)
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
    from hutch.models import RunStatus
    wait_for(lambda: app.state.store.get_run(body["id"]).status in {
        RunStatus.succeeded, RunStatus.failed, RunStatus.stopped, RunStatus.outcome_unknown
    })
    assert app.state.store.get_run(body["id"]).status is RunStatus.succeeded

    page.reload()                                           # the choice is remembered for this bot
    page.locator(".ms-btn").wait_for()
    assert page.locator(".ms-btn").inner_text().strip() == chosen
    assert not errors, errors


def test_all_models_dialog_filters_explains_and_applies(browser, switcher_env, request):
    base, app, fake = switcher_env
    page = browser.new_context(viewport={"width": 1280, "height": 800}).new_page()
    request.addfinalizer(page.close)
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


def test_switcher_fits_a_phone_screen(browser, switcher_env, request):
    base, app, fake = switcher_env
    page = browser.new_context(viewport={"width": 390, "height": 844}).new_page()
    request.addfinalizer(page.close)
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


@pytest.mark.parametrize("width,height,size", [(1440,1000,"desktop"),(900,1024,"tablet"),(390,844,"phone"),(320,740,"compact-phone")])
def test_bot_workspace_modes_are_clear_and_persist_across_settings(browser, live, tmp_path, width, height, size):
    import hashlib
    import json
    from hutch.models import iso, utcnow

    base, app = live
    app.state.store.create_bot(Bot(name="workspace-helper", model="mock/demo", tools=["files"]))
    folder = tmp_path / "existing-workspace"
    folder.mkdir()
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/managed-workspaces"
    out.mkdir(parents=True, exist_ok=True)
    page = browser.new_page(viewport={"width": width, "height": height}, reduced_motion="reduce")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(base + "/#/bot/workspace-helper")
        page.get_by_role("heading", name="workspace-helper settings", exact=True).wait_for()
        mode = page.locator('#form-risk [name="workspace_mode"]')
        assert mode.input_value() == "fresh"
        if width <= 390:
            assert mode.bounding_box()["height"] >= 44
        assert page.locator("#workspace-folder-field").is_hidden()

        mode.select_option("managed")
        old_form = page.locator("#form-risk").element_handle()
        with page.expect_response(lambda response: response.url.endswith("/api/bots/workspace-helper")
                                  and response.request.method == "PATCH") as saved:
            page.locator('#form-risk button[type="submit"]').click()
        assert saved.value.status == 200, saved.value.text()
        page.wait_for_function("form => !form.isConnected", arg=old_form)
        page.locator("#form-risk").wait_for(state="visible")
        page.get_by_text("Policy and workspace saved.", exact=True).wait_for()
        assert app.state.store.get_bot("workspace-helper").workspace_mode == "managed"
        assert app.state.store.get_bot("workspace-helper").workdir is None
        assert mode.input_value() == "managed" and page.locator("#workspace-folder-field").is_hidden()
        page.locator("#form-risk").scroll_into_view_if_needed()
        page.locator(".toast-root .toast").wait_for(state="detached")
        page.screenshot(path=str(out / f"{size}-managed.png"), animations="disabled")

        mode.select_option("folder")
        field = page.locator("#workspace-folder-field")
        assert field.is_visible() and field.locator("input").evaluate("e => e === document.activeElement")
        assert field.locator("input").get_attribute("required") is not None
        if width <= 390:
            assert field.locator("input").bounding_box()["height"] >= 44
        field.locator("input").fill(str(folder))
        old_form = page.locator("#form-risk").element_handle()
        with page.expect_response(lambda response: response.url.endswith("/api/bots/workspace-helper")
                                  and response.request.method == "PATCH") as saved:
            page.locator('#form-risk button[type="submit"]').click()
        assert saved.value.status == 200, saved.value.text()
        page.wait_for_function("form => !form.isConnected", arg=old_form)
        page.locator("#form-risk").wait_for(state="visible")
        stored = app.state.store.get_bot("workspace-helper")
        assert stored.workspace_mode == "folder" and stored.workdir == str(folder.resolve())
        assert mode.input_value() == "folder" and field.is_visible()
        page.locator("#form-risk").scroll_into_view_if_needed()
        page.locator(".toast-root .toast").wait_for(state="detached")
        page.screenshot(path=str(out / f"{size}-folder.png"), animations="disabled")

        overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
        assert overflow <= 1 and not errors, (overflow, errors)
        (out / f"{size}.json").write_text(json.dumps({
            "captured_at": iso(utcnow()), "browser": browser.browser_type.name, "version": browser.version,
            "playwright_version": package_version("playwright"), "viewport": [width, height],
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_bot_workspace_modes_are_clear_and_persist_across_settings",
            "journey": ["fresh default", "managed workspace saved", "existing folder selected and saved"],
            "screenshots": [f"{size}-managed.png", f"{size}-folder.png"],
            "folder_path": "[local fixture path omitted]", "page_errors": errors, "horizontal_overflow": overflow,
            "source_sha256": {p: hashlib.sha256((out.parents[3] / p).read_bytes()).hexdigest() for p in (
                "src/hutch/server/static/app.js", "src/hutch/server/static/style.css", "src/hutch/engine.py",
                "src/hutch/config.py", "src/hutch/models.py", "src/hutch/cli.py", "src/hutch/server/app.py",
                "src/hutch/server/pages.py", "src/hutch/server/templates/bot.html")},
        }, indent=2) + "\n")
    finally:
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


def test_browser_alerts_are_opt_in_private_and_open_the_review_queue(browser, live):
    from hutch.models import ApprovalRequest, Run
    base, app = live
    store = app.state.store
    bot = store.create_bot(Bot(name="alert-bot", model="ollama/qwen3:4b", tools=[]))
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.add_init_script("""(() => {
      window.__notifications = [];
      class TestNotification {
        constructor(title, options) { this.title = title; this.options = options; window.__notifications.push(this); }
        close() { this.closed = true; }
        click() { if (this.onclick) this.onclick(); }
        static permission = 'default';
        static async requestPermission() { this.permission = 'granted'; return this.permission; }
      }
      window.Notification = TestNotification;
    })();""")
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/browser-alerts"
    out.mkdir(parents=True, exist_ok=True)
    page.goto(base + "/#/chat")
    page.locator("#needs-you-open").click()
    page.locator("#browser-alerts-status").get_by_text("Optional alerts", exact=False).wait_for()
    page.locator("#browser-alerts-toggle").click()
    page.locator("#browser-alerts-status").get_by_text("On while Hutch is open", exact=False).wait_for()
    assert page.evaluate("Notification.permission") == "granted"
    page.locator("#needs-you-close").click()
    page.evaluate("Object.defineProperty(document, 'hidden', {configurable:true, get:()=>true})")

    run = store.create_run(Run(bot_id=bot.id, prompt="private approval context", status=RunStatus.waiting_approval))
    store.create_approval(ApprovalRequest(
        run_id=run.id, bot_id=bot.id, tool="files", action="Review private report content",
        detail={"path": "private.txt", "content": "must never appear in an OS notification"},
    ))
    wait_for(lambda: page.evaluate("window.__notifications.length === 1"))
    notice = page.evaluate("({title:__notifications[0].title, body:__notifications[0].options.body, tag:__notifications[0].options.tag})")
    assert notice == {
        "title": "Hutch needs you",
        "body": "An approval or action outcome is waiting for review.",
        "tag": "hutch-needs-you",
    }
    assert "private" not in json.dumps(notice).lower()
    page.evaluate("Promise.all([refreshBadge(), refreshBadge()])")
    assert page.evaluate("window.__notifications.length") == 1, "overlapping refreshes must not duplicate an alert"

    page.evaluate("window.__notifications[0].click()")
    page.locator("#needs-you[open]").wait_for()
    page.locator("#needs-you [data-approval-card]").wait_for()
    records = []
    for name, width, height in (("desktop", 1440, 1000), ("tablet", 768, 1024), ("phone", 390, 844)):
        page.set_viewport_size({"width": width, "height": height})
        page.screenshot(path=str(out / f"{name}.png"), full_page=True, animations="disabled")
        overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
        assert overflow <= 1
        records.append({"viewport": name, "size": [width, height], "overflow_px": overflow,
                        "page_errors": errors,
                        "screenshot_sha256": hashlib.sha256((out / f"{name}.png").read_bytes()).hexdigest()})
    page.locator("#browser-alerts-toggle").click()
    page.locator("#browser-alerts-status").get_by_text("Optional alerts", exact=False).wait_for()
    assert page.evaluate("JSON.parse(localStorage.getItem('hutch:browser-alerts'))") is False
    (out / "results.json").write_text(json.dumps({
        "browser": browser.browser_type.name, "browser_version": browser.version,
        "playwright": package_version("playwright"), "provider_calls": 0,
        "notification_api": "test stub; no operating-system permission or notification used",
        "private_action_text_in_notice": False, "duplicate_notices": False,
        "notification_click_opens_review_queue": True, "page_errors": errors, "captures": records,
        "source_sha256": {name: hashlib.sha256((Path(__file__).resolve().parents[2] / name).read_bytes()).hexdigest()
                          for name in ("src/hutch/server/static/index.html", "src/hutch/server/static/app.js",
                                       "src/hutch/server/static/style.css")},
    }, indent=2) + "\n")
    assert not errors, errors
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


@pytest.mark.parametrize("width,height,size", [(1440, 1000, "desktop"), (900, 1024, "tablet"), (390, 844, "phone")])
def test_transcript_mirror_error_preserves_done_and_recovers_without_losing_draft(browser, live, monkeypatch, width, height, size):
    import hashlib
    import json
    from pathlib import Path
    from hutch.models import Run, Task, iso, utcnow
    base, app = live
    store = app.state.store
    monkeypatch.setattr(app.state.engine, "tick", lambda: None)
    original = store._mirror._deliver
    released = threading.Event()
    def delivery(row):
        if not released.is_set():
            raise OSError("fixture: transcript file is temporarily unavailable")
        return original(row)
    monkeypatch.setattr(store._mirror, "_deliver", delivery)
    bot = store.create_bot(Bot(name="mirror-fixture", model="mock/demo", tools=[]))
    conv, _ = store.create_conversation(bot.id, "Audit recovery fixture", idem_key="create", request_hash="create")
    run = Run(bot_id=bot.id, prompt="Sanitized transcript recovery fixture")
    store.submit_conversation_message(conv["id"], run.prompt, run, Task(bot_id=bot.id, prompt=run.prompt),
                                     idem_key="turn", request_hash="turn")
    store.transition_run(run.id, RunStatus.running)
    store.append_event(Event(run_id=run.id, type=EventType.message,
                             data={"role": "assistant", "content": "This answer is committed in database history."}))
    store.transition_run(run.id, RunStatus.succeeded)
    deadline = time.monotonic() + 5
    while not store._mirror.status(run.id)["error"] and time.monotonic() < deadline:
        time.sleep(0.02)
    assert store._mirror.status(run.id)["error"]
    page = browser.new_page(viewport={"width": width, "height": height}, reduced_motion="reduce")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/transcript-mirror"
    out.mkdir(parents=True, exist_ok=True)
    try:
        page.goto(base + "/#/conversation/" + conv["id"])
        warning = page.locator(".run-notice").filter(has_text="Transcript file needs attention")
        warning.wait_for()
        assert "Database history remains available" in warning.inner_text()
        assert page.locator(".mhead").get_by_text("Done", exact=True).count() == 1
        assert page.get_by_text("This answer is committed in database history.", exact=True).count() == 1
        page.locator("#chat-prompt").fill("Keep this unsent draft during audit recovery")
        page.locator("#chat-prompt").focus()
        page.screenshot(path=str(out / f"{size}.png"), full_page=True, animations="disabled")
        overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
        assert overflow <= 1 and not errors
        released.set()
        store._mirror.wake.set()
        store.flush_transcripts()
        warning.wait_for(state="detached", timeout=15000)
        assert page.locator(".mhead").get_by_text("Done", exact=True).count() == 1
        assert page.locator("#chat-prompt").input_value() == "Keep this unsent draft during audit recovery"
        assert page.locator("#chat-prompt").evaluate("e => e === document.activeElement")
        (out / f"{size}.json").write_text(json.dumps({
            "captured_at": iso(utcnow()), "browser": browser.browser_type.name, "version": browser.version,
            "viewport": [width, height], "scenario": "fixture IO failure; real durable retry and invalidation; no live provider",
            "page_errors": errors, "horizontal_overflow": overflow, "draft_and_focus_preserved": True,
            "source_sha256": {p: hashlib.sha256((out.parents[3] / p).read_bytes()).hexdigest()
                for p in ("src/hutch/server/static/app.js", "src/hutch/store.py", "src/hutch/server/app.py", "src/hutch/transcript_mirror.py")},
        }, indent=2) + "\n")
    finally:
        released.set()
        page.close()


@pytest.mark.parametrize("width,height,size", [(1440, 1000, "desktop"), (390, 844, "phone")])
def test_untrusted_run_content_is_text_not_executable_html(browser, live, monkeypatch, width, height, size):
    """Prompts, model output, and tool output remain inert even when they contain HTML payloads."""
    from hutch.models import Run, Task

    base, app = live
    store = app.state.store
    monkeypatch.setattr(app.state.engine, "tick", lambda: None)
    bot = store.create_bot(Bot(name="untrusted-fixture", model="ollama/qwen3:4b", tools=["files"]))
    conversation, _ = store.create_conversation(bot.id, "Untrusted content fixture",
                                                 idem_key="create", request_hash="create")
    payload = '<img src=x onerror="window.__hutchXss=1"><svg onload="window.__hutchXss=2"></svg><a href="javascript:window.__hutchXss=3">run</a>'
    run = Run(bot_id=bot.id, prompt=payload)
    store.submit_conversation_message(conversation["id"], payload, run,
                                      Task(bot_id=bot.id, kind="conversation", prompt=payload),
                                      idem_key="turn", request_hash="turn")
    store.transition_run(run.id, RunStatus.running)
    store.append_event(Event(run_id=run.id, type=EventType.tool_call,
                             data={"tool": "files", "args": {"path": payload}}))
    store.append_event(Event(run_id=run.id, type=EventType.tool_result,
                             data={"tool": "files", "ok": True, "output": payload + " filler " * 100}))
    store.append_event(Event(run_id=run.id, type=EventType.message,
                             data={"role": "assistant", "content": payload}))
    store.transition_run(run.id, RunStatus.succeeded)

    page = browser.new_page(viewport={"width": width, "height": height}, reduced_motion="reduce")
    page.add_init_script("window.__hutchXss = 0")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/untrusted-content"
    out.mkdir(parents=True, exist_ok=True)
    try:
        page.goto(base + "/#/conversation/" + conversation["id"])
        page.locator(f'[data-run-id="{run.id}"] .answer').wait_for()
        answer = page.locator(f'[data-run-id="{run.id}"] .answer')
        assert answer.text_content() == payload
        assert page.locator(f'[data-run-id="{run.id}"] .bubble').text_content() == payload
        page.locator(f'[data-run-id="{run.id}"] .tool-line-head').click()
        tool = page.locator(f'[data-run-id="{run.id}"] .tool-line-section').filter(has_text="Output")
        assert payload in tool.text_content()
        assert answer.locator("*").count() == 0
        assert page.locator(f'[data-run-id="{run.id}"] .tool-line-section img, [data-run-id="{run.id}"] .tool-line-section svg[onload]').count() == 0
        assert page.locator(f'[data-run-id="{run.id}"] a[href^="javascript:"]').count() == 0
        page.screenshot(path=str(out / f"{size}.png"), full_page=True, animations="disabled")
        page.locator(f'[data-run-id="{run.id}"] [data-show-more]').click()
        assert page.locator(f'[data-run-id="{run.id}"] .tool-line-section img').count() == 0
        page.wait_for_timeout(100)
        assert page.evaluate("window.__hutchXss") == 0
        overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
        assert overflow <= 1 and not errors
        records = {"viewport": [width, height], "page_errors": errors, "horizontal_overflow": overflow,
                   "inert_payload": True,
                   "screenshot_sha256": hashlib.sha256((out / f"{size}.png").read_bytes()).hexdigest()}
        (out / f"{size}.json").write_text(json.dumps({
            "browser": browser.browser_type.name, "version": browser.version,
            "playwright": package_version("playwright"), "scenario": "synthetic hostile prompt/model/tool content",
            **records,
            "source_sha256": {name: hashlib.sha256((Path(__file__).resolve().parents[2] / name).read_bytes()).hexdigest()
                              for name in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css")},
        }, indent=2) + "\n")
    finally:
        page.close()


@pytest.mark.parametrize("width,height,size", [(1440, 1000, "desktop"), (900, 1024, "tablet"), (390, 844, "phone")])
def test_resource_replay_updates_chat_after_gap_without_losing_draft_or_focus(browser, live, monkeypatch, width, height, size):
    import hashlib
    import json
    from pathlib import Path
    from hutch.approvals import ApprovalGate
    from hutch.models import Run, Task, iso, utcnow
    from hutch.safety import PolicyEngine
    base, app = live
    store = app.state.store
    monkeypatch.setattr(app.state.engine, "tick", lambda: None)
    bot = store.create_bot(Bot(name="resource-replay", model="mock/demo", approval_mode=ApprovalMode.ask))
    conv, _ = store.create_conversation(bot.id, "Replay fixture", idem_key="create", request_hash="create")
    run = Run(bot_id=bot.id, prompt="Sanitized replay request", status=RunStatus.running)
    store.submit_conversation_message(conv["id"], run.prompt, run, Task(bot_id=bot.id, prompt=run.prompt),
                                     idem_key="turn", request_hash="turn")
    page = browser.new_page(viewport={"width": width, "height": height}, reduced_motion="reduce")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    # Disable the existing slow fallback readers. This must pass using durable
    # resource replay, including when no run transcript SSE hint is delivered.
    page.add_init_script("""const originalInterval = window.setInterval;
      window.setInterval = (fn, delay, ...args) => delay >= 4000 ? 0 : originalInterval(fn, delay, ...args);""")
    gap_count = []
    def gap_once(route):
        if not gap_count:
            gap_count.append(1)
            route.fulfill(status=200, content_type="text/event-stream", body=
                'event: snapshot_required\ndata: {"snapshot_url":"/api/v1/snapshot"}\n\n')
        else:
            route.continue_()
    page.route("**/api/v1/changes/stream?*", gap_once)
    page.route(f"**/api/runs/{run.id}/stream", lambda route: route.fulfill(status=200,
               content_type="text/event-stream", body=": held transcript fixture\n\n"))
    page.goto(base + "/#/chat/resource-replay")
    page.locator("#chat-prompt").fill("My unsent draft stays here")
    page.locator("#chat-prompt").focus()
    page.wait_for_function("resourceStream && resourceStream.readyState === EventSource.OPEN")
    gate = ApprovalGate(store, bot, run, PolicyEngine(), store.append_event)
    # Admission commits the real request/event/wait; only the subsequent human
    # wait is held so the test can act as the second client.
    monkeypatch.setattr(gate, "_wait", lambda *args, **kwargs: None)
    gate.decide("files", "write reviewed.txt", {"path": "reviewed.txt", "content": "Sanitized review"})
    request = store.pending_approvals()[0]
    card = page.locator(f'#chat-stream [data-approval-card="{request.id}"]')
    card.locator('[data-approve="1"]').wait_for(timeout=15000)
    assert "Waiting for you" in page.locator(".ctx-meta").inner_text()
    assert page.locator("#chat-prompt").input_value() == "My unsent draft stays here"
    assert page.locator("#chat-prompt").evaluate("e => e === document.activeElement")
    assert gap_count, "exercise explicit reconciliation before live replay"
    page.locator("#studio-review-run").click()
    box, feed = card.bounding_box(), page.locator("#chat-scroll").bounding_box()
    assert box["y"] >= feed["y"] - 1 and box["y"] + box["height"] <= feed["y"] + feed["height"] + 1
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/resource-replay"
    out.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out / f"{size}.png"), full_page=True, animations="disabled")
    overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
    assert overflow <= 1 and not errors
    (out / f"{size}.json").write_text(json.dumps({
        "captured_at": iso(utcnow()), "browser": browser.browser_type.name, "version": browser.version,
        "viewport": [width, height], "scenario": "real approval admission, fixture gap, fallback timers/transcript hints disabled",
        "page_errors": errors, "horizontal_overflow": overflow, "draft_and_focus_preserved": True,
        "source_sha256": {p: hashlib.sha256((out.parents[3] / p).read_bytes()).hexdigest()
            for p in ("src/hutch/server/static/app.js", "src/hutch/store.py", "src/hutch/server/app.py", "src/hutch/approvals.py")},
    }, indent=2) + "\n")
    # A second client's durable decision must replace the inline ask without
    # relying on a worker resolution event, which can be lost during a crash.
    from hutch.models import ApprovalStatus
    store.decide_approval(request.id, ApprovalStatus.denied, "second-fixture-client")
    card.locator(".tag.danger").wait_for(timeout=15000)
    assert "Denied" in card.inner_text() and not card.locator("[data-approve]").count()
    assert page.locator("#chat-prompt").input_value() == "My unsent draft stays here"
    page.evaluate("id => { location.hash = '#/run/' + id; }", run.id)
    page.wait_for_function("feedMode === 'run'")
    page.evaluate("location.hash = '#/bot/resource-replay'")
    settings = page.locator('#form-identity textarea[name="instructions"]')
    settings.fill("Unsaved instructions stay intact")
    settings.focus()
    before = store.list_resource_changes()["cursor"]
    other, _ = store.create_conversation(bot.id, "Other fixture conversation", idem_key="other", request_hash="other")
    assert store.list_resource_changes(before)["changes"]
    page.wait_for_timeout(1700)
    assert settings.input_value() == "Unsaved instructions stay intact"
    assert settings.evaluate("e => e === document.activeElement")
    assert page.url.endswith("#/bot/resource-replay") and not errors
    held = []
    page.route(f"**/api/runs/{run.id}", lambda route: held.append(route))
    page.evaluate("id => { location.hash = '#/run/' + id; }", run.id)
    page.wait_for_timeout(150)
    assert held, "hold a run response across navigation"
    page.evaluate("location.hash = '#/bot/resource-replay'")
    page.get_by_role("heading", name="resource-replay settings", exact=True).wait_for()
    settings.fill("Late run responses cannot replace this form")
    for route in held:
        route.continue_()
    page.wait_for_timeout(700)
    assert settings.input_value() == "Late run responses cannot replace this form" and not errors
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


@pytest.mark.parametrize("width,height,size", [(1440,1000,"desktop"),(900,1024,"tablet"),(390,844,"phone")])
def test_uncertain_action_review_in_chat_preserves_history_and_recovers_lost_response(browser, live, monkeypatch, width, height, size):
    import hashlib
    import json
    from pathlib import Path
    from hutch.models import Run, Task, iso, utcnow
    base, app = live
    store = app.state.store
    monkeypatch.setattr(app.state.engine, 'tick', lambda: None)
    bot = store.create_bot(Bot(name='receipt-review',model='mock/demo',tools=[]))
    conv, _ = store.create_conversation(bot.id,'Receipt review fixture',idem_key='create',request_hash='create')
    run = Run(bot_id=bot.id,prompt='Sanitized action with a missing execution receipt')
    store.submit_conversation_message(conv['id'],run.prompt,run,Task(bot_id=bot.id,prompt=run.prompt),idem_key='turn',request_hash='turn')
    store.transition_run(run.id,RunStatus.running)
    action_id = store.begin_action(run.id,'write_file','fixture-key','fs','write_file: report.md',
                                  arguments={'path':'report.md','content':'Sanitized report'},
                                  authority={'source':'fixture','detail':{'revision':{'exists':False}}},scope={'workspace':'/sanitized/fixture'})
    store.transition_run(run.id,RunStatus.succeeded,event={'reason':'fixture runtime success'})
    before = store.get_run(run.id).model_dump()
    before_chain = store.verify_chain(run.id)
    context = browser.new_context(viewport={'width':width,'height':height},reduced_motion='reduce')
    page = context.new_page(); errors = []; attempts = []
    page.on('pageerror',lambda error: errors.append(str(error)))
    out = Path(__file__).resolve().parents[2]/'docs/realignment/artifacts/action-receipts'
    out.mkdir(parents=True,exist_ok=True)
    context.tracing.start(screenshots=True,snapshots=True,sources=True)
    def lose_response(route):
        attempts.append(route.request.headers.get('idempotency-key'))
        if len(attempts) == 1:
            response = route.fetch()
            assert response.status == 201
            route.abort('failed')  # real server commit, lost browser response
        else:
            route.continue_()
    page.route('**/api/v1/actions/receipts/*/reconcile',lose_response)
    try:
        page.goto(base+'/#/conversation/'+conv['id'])
        card = page.locator('[data-receipt-card]'); card.wait_for()
        assert 'may already have happened' in card.inner_text()
        page.locator('#chat-prompt').fill('Keep this unsent follow-up during review')
        page.screenshot(path=str(out/f'{size}-uncertain.png'),full_page=True,animations='disabled')
        card.get_by_role('button',name='Review action outcome',exact=True).click()
        page.locator('#receipt-outcome').select_option('confirmed_done')
        page.locator('#receipt-evidence').fill('Checked report.md in the fixture workspace and compared its contents.')
        page.screenshot(path=str(out/f'{size}-review.png'),full_page=True,animations='disabled')
        page.locator('#modal-confirm').click()
        page.locator('#receipt-error').wait_for(state='visible')
        assert 'report is retained' in page.locator('#receipt-error').inner_text()
        assert page.locator('#receipt-evidence').input_value().startswith('Checked report.md')
        page.locator('#modal-confirm').click()
        page.locator('#modal-root .modal-card').wait_for(state='detached')
        page.get_by_role('button',name='View recorded outcome',exact=True).wait_for()
        page.wait_for_function("document.activeElement?.dataset.receiptReview !== undefined")
        assert len(attempts) == 2 and attempts[0] == attempts[1]
        assert page.locator('#chat-prompt').input_value() == 'Keep this unsent follow-up during review'
        assert store.get_run(run.id).model_dump() == before
        assert store.verify_chain(run.id) == before_chain
        assert store.get_action(action_id)['status'] == 'unknown'
        assert 'human report' in page.locator('[data-receipt-card]').inner_text()
        page.screenshot(path=str(out/f'{size}-recorded.png'),full_page=True,animations='disabled')
        overflow = page.evaluate('document.documentElement.scrollWidth-innerWidth')
        assert overflow <= 1 and not errors
        (out/f'{size}.json').write_text(json.dumps({
            'captured_at':iso(utcnow()),'browser':browser.browser_type.name,'version':browser.version,'viewport':[width,height],
            'scenario':'Synthetic missing receipt; real API commit, lost response and idempotent retry; no live provider effect',
            'page_errors':errors,'horizontal_overflow':overflow,'draft_and_focus_preserved':True,'sealed_history_preserved':True,
            'source_sha256':{p:hashlib.sha256((out.parents[3]/p).read_bytes()).hexdigest() for p in (
                'src/hutch/server/static/app.js','src/hutch/server/static/style.css','src/hutch/server/static/index.html',
                'src/hutch/server/app.py','src/hutch/store.py','src/hutch/action_receipts.py')},
        },indent=2)+'\n')
    finally:
        context.tracing.stop(path=str(out/f'{size}-trace.zip'))
        context.close()


@pytest.mark.parametrize('width,height,size', [(1440,1000,'desktop'),(900,1024,'tablet'),(390,844,'phone')])
def test_scoped_fact_review_revision_conflict_and_memory_off(browser, live, width, height, size):
    import hashlib
    import json
    from pathlib import Path
    from hutch.models import Run, iso, utcnow
    base, application = live
    store = application.state.store
    bot = store.create_bot(Bot(name='fact-review-bot', tools=['memory']))
    a, _ = store.create_conversation(bot.id, 'Private reference chat', idem_key='fact-chat-a', request_hash='a')
    b, _ = store.create_conversation(bot.id, 'Separate private chat', idem_key='fact-chat-b', request_hash='b')
    # A running status fixture keeps the e2e run out of the live supervisor's
    # pending queue. Production fence ownership is covered by test_fact_memory.
    run = store.create_run(Run(bot_id=bot.id, conversation_id=a['id'], prompt='synthetic fact proposal', status=RunStatus.running))
    fact = store.remember(bot.id, 'format', 'PRIVATE A: prefer short bullets. <script>window.__factInjected=true</script>',
                          run_id=run.id, expected_fence=0)
    store.transition_run(run.id, RunStatus.succeeded, fence=0)
    store.remember(bot.id, 'other-private', 'PRIVATE B MUST NOT APPEAR IN A', conversation_id=b['id'])
    context = browser.new_context(viewport={'width':width,'height':height}, reduced_motion='reduce')
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    page, errors = context.new_page(), []
    page.on('pageerror', lambda error: errors.append(str(error)))
    out = Path(__file__).resolve().parents[2]/'docs/realignment/artifacts/fact-memory'
    out.mkdir(parents=True, exist_ok=True)
    try:
        page.goto(base+'/#/chat/'+bot.name)
        page.locator('#conversation-switcher').select_option(a['id'])
        page.locator(f'[data-fact-card="{fact.id}"]').wait_for()
        assert 'PRIVATE B MUST NOT APPEAR IN A' not in page.locator('#chat-stream').inner_text()
        assert page.evaluate('window.__factInjected === undefined')
        page.locator('#chat-prompt').fill('Keep this unsent fact-review draft')
        page.screenshot(path=str(out/f'{size}-proposed.png'), full_page=True, animations='disabled')
        review_button = page.locator(f'[data-fact-review="{fact.id}"]')
        review_button.focus(); page.keyboard.press('Enter')
        page.locator('#fact-share').wait_for()
        assert not page.locator('#fact-share').is_checked()
        assert 'not proof of truth' in page.locator('.modal-body').inner_text()
        if size=='phone':
            assert page.locator('.fact-share').bounding_box()['height']>=44
            assert page.locator('#modal-confirm').bounding_box()['height']>=44
        page.screenshot(path=str(out/f'{size}-review.png'), full_page=True, animations='disabled')
        page.keyboard.press('Escape')
        wait_for(lambda: review_button.evaluate('e => e.matches(":focus")'), timeout=2)
        assert review_button.evaluate('e => e.matches(":focus")')
        review_button.click()
        newer = store.remember(bot.id, 'format', 'PRIVATE A REVISED: concise summary', conversation_id=a['id'])
        page.locator('#modal-confirm').click()
        page.locator('#fact-review-error').get_by_text('replaced', exact=False).wait_for()
        assert page.locator('#chat-prompt').input_value().startswith('Keep this unsent')
        assert store.fact_page(bot.id, conversation_id=a['id'], approved_only=True)==[]
        page.screenshot(path=str(out/f'{size}-revision-conflict.png'), full_page=True, animations='disabled')
        page.keyboard.press('Escape')
        page.locator(f'[data-fact-review="{newer.id}"]').click()
        page.locator('#fact-share').check()
        with page.expect_response(lambda r: r.request.method=='POST' and r.url.endswith('/review')) as result:
            page.locator('#modal-confirm').click()
        assert result.value.status==200
        page.locator('#modal-title').wait_for(state='hidden')
        assert page.locator('#chat-prompt').input_value().startswith('Keep this unsent')
        shared = store.fact_page(bot.id, approved_only=True)[0]
        assert shared['scope_kind']=='bot' and shared['value'].startswith('PRIVATE A REVISED')
        page.locator('#conversation-switcher').select_option(b['id'])
        page.locator('.fact-panel details summary').click()
        page.locator(f'[data-fact-card="{shared["id"]}"]').wait_for()
        assert 'PRIVATE A REVISED' in page.locator('#chat-stream').inner_text()
        page.screenshot(path=str(out/f'{size}-shared.png'), full_page=True, animations='disabled')
        page.get_by_role('link',name='Settings',exact=True).click()
        page.locator('#memory-toggle').click()
        page.get_by_role('button', name='Enable memory', exact=True).wait_for()
        assert not store.get_bot(bot.id).memory_enabled
        page.locator('#memory-archives').click()
        page.locator(f'[data-fact-card="{newer.id}"]').get_by_text('Archived',exact=True).wait_for()
        page.locator(f'[data-fact-history="{shared["id"]}"]').click()
        page.locator('#modal-title').get_by_text('Reference fact history',exact=True).wait_for()
        assert 'share · operator' in page.locator('.modal-body').inner_text()
        page.screenshot(path=str(out/f'{size}-disabled-history.png'), full_page=True, animations='disabled')
        overflow = page.evaluate('document.documentElement.scrollWidth-innerWidth')
        assert overflow<=1 and not errors
        (out/f'{size}.json').write_text(json.dumps({
            'captured_at':iso(utcnow()), 'browser':browser.browser_type.name, 'version':browser.version,
            'viewport':[width,height], 'page_errors':errors,'horizontal_overflow':overflow,
            'scenario':'Synthetic running attempt proposes a fact; real local API review/conflict/share/off/history; ownership fences have separate offline coverage',
            'draft_preserved':True,'rendered_fact_script_not_executed':True,
            'source_sha256':{p:hashlib.sha256((out.parents[3]/p).read_bytes()).hexdigest() for p in (
                'src/hutch/models.py','src/hutch/store.py','src/hutch/fact_memory.py','src/hutch/tools/memory.py',
                'src/hutch/runtime/builtin.py','src/hutch/server/app.py','src/hutch/server/static/app.js','src/hutch/server/static/style.css')}
        },indent=2)+'\n')
    finally:
        context.tracing.stop(path=str(out/f'{size}-trace.zip'))
        context.close()


def test_needs_you_receipt_queue_pages_old_actions_and_stays_keyboard_reachable(browser, live, monkeypatch):
    from hutch.models import Run
    base, app = live; store = app.state.store
    monkeypatch.setattr(app.state.engine,'tick',lambda:None)
    bot = store.create_bot(Bot(name='old-receipts',model='mock/demo',tools=[]))
    run = Run(bot_id=bot.id,prompt='Older standalone receipt fixture');store.create_run(run)
    store.transition_run(run.id,RunStatus.running)
    for i in range(22):
        store.begin_action(run.id,'shell',f'fixture-{i}','process',f'Old action {i+1}',arguments={'command':f'fixture {i+1}'})
    store.transition_run(run.id,RunStatus.failed)
    page = browser.new_page(viewport={'width':390,'height':844},reduced_motion='reduce')
    try:
        page.goto(base+'/#/chat')
        page.locator('#approval-badge').get_by_text('22',exact=True).wait_for()
        page.locator('#nav-toggle').click()
        page.locator('#needs-you-open').click()
        page.locator('#receipts-pending [data-receipt-card]').first.wait_for()
        assert page.locator('#receipts-pending [data-receipt-card]').count() == 20
        page.get_by_role('button',name='Next actions',exact=True).click()
        page.wait_for_function("document.querySelectorAll('#receipts-pending [data-receipt-card]').length === 2")
        page.locator('#receipts-pending [data-receipt-review]').first.focus()
        page.keyboard.press('Enter')
        page.locator('#receipt-outcome').wait_for()
        assert not page.locator('#needs-you').evaluate('e=>e.open')
        page.keyboard.press('Escape')
        assert page.locator('#nav-toggle').evaluate('e=>e===document.activeElement')
        assert page.evaluate('document.documentElement.scrollWidth-innerWidth') <= 1
    finally:
        page.close()


@pytest.fixture()
def restored_live(tmp_path, monkeypatch):
    from hutch.config import hutchConfig
    from hutch.models import Run, Task
    from hutch.state_snapshot import backup, restore
    from hutch.store import Store
    original = hutchConfig(tmp_path / 'source')
    source = Store(original)
    bot = source.create_bot(Bot(name='restored-bot', tools=[]))
    source.submit_run(Run(bot_id=bot.id, prompt='Sanitized unfinished snapshot fixture'),
                      Task(bot_id=bot.id, prompt='Sanitized unfinished snapshot fixture'))
    source.close()
    backup(original, tmp_path / 'snapshot')
    report = restore(tmp_path / 'snapshot', tmp_path / 'restored')
    monkeypatch.setenv('HUTCH_STATE_DIR', str(tmp_path / 'restored'))
    application = create_app()
    server = uvicorn.Server(uvicorn.Config(application, host='127.0.0.1', port=0, log_level='warning'))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        wait_for(lambda: server.started, timeout=10)
        port = server.servers[0].sockets[0].getsockname()[1]
        yield f'http://127.0.0.1:{port}', application, report
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()


@pytest.mark.parametrize('width,height,size', [(1440,1000,'desktop'),(900,1024,'tablet'),(390,844,'phone')])
def test_restored_state_is_visible_without_losing_chat_draft(browser, restored_live, width, height, size):
    import hashlib
    import json
    from pathlib import Path
    from hutch.models import iso, utcnow
    from hutch.state_snapshot import code_hash
    base, application, report = restored_live
    context = browser.new_context(viewport={'width': width, 'height': height}, reduced_motion='reduce')
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    page, errors = context.new_page(), []
    page.on('pageerror', lambda error: errors.append(str(error)))
    out = Path(__file__).resolve().parents[2] / 'docs/realignment/artifacts/restoration'
    out.mkdir(parents=True, exist_ok=True)
    try:
        page.goto(base + '/#/chat/restored-bot')
        page.locator('#execution-hold').wait_for(state='visible')
        page.locator('#chat-prompt').fill('Retain this unsent draft during restore review')
        with page.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith('/messages')) as sent:
            page.locator('#chat-send').click()
        assert sent.value.status == 409
        assert application.state.store.active_runs() == []
        assert page.locator('#chat-prompt').input_value() == 'Retain this unsent draft during restore review'
        assert page.locator('#view').bounding_box()['y'] >= page.locator('#app-top-context').bounding_box()['y']
        assert page.locator('#execution-hold').bounding_box()['y'] + page.locator('#execution-hold').bounding_box()['height'] <= page.locator('#view').bounding_box()['y'] + 1
        page.locator('#restore-report-open').focus()
        page.screenshot(path=str(out / f'{size}-held.png'), full_page=True, animations='disabled')
        page.keyboard.press('Enter')
        page.locator('#modal-title').get_by_text('Restored history', exact=True).wait_for()
        assert 'Source processes were not stopped' in page.locator('.modal-body').inner_text()
        assert 'Old attempts will not resume' in page.locator('.modal-body').inner_text()
        assert not page.locator('#modal-cancel').is_visible()
        assert page.locator('#modal-confirm').inner_text() == 'Close'
        if size == 'phone':
            for selector in ('#restore-report-open', '#modal-confirm', '#modal-close'):
                assert page.locator(selector).bounding_box()['height'] >= 44
        assert page.locator('#modal-confirm').evaluate("e => { const r = e.getBoundingClientRect(); return e.contains(document.elementFromPoint(r.x + r.width/2, r.y + r.height/2)); }")
        assert page.locator('#modal-confirm').evaluate('e => e === document.activeElement')
        page.keyboard.press('Tab')
        assert page.locator('#modal-close').evaluate('e => e === document.activeElement')
        page.keyboard.press('Shift+Tab')
        assert page.locator('#modal-confirm').evaluate('e => e === document.activeElement')
        page.screenshot(path=str(out / f'{size}-details.png'), full_page=True, animations='disabled')
        page.keyboard.press('Escape')
        assert page.locator('#restore-report-open').evaluate('e => e === document.activeElement')
        assert page.locator('#chat-prompt').input_value().startswith('Retain this unsent')
        assert application.state.store.pending_tasks() == []
        # Represents a local CLI operator review, never a browser activation endpoint.
        application.state.store.activate_restoration(report['id'], 'Sanitized isolated fixture: source stopped; excluded files reviewed')
        page.locator('#execution-hold').wait_for(state='hidden')
        assert page.locator('#chat-prompt').input_value().startswith('Retain this unsent')
        assert application.state.store.get_bot('restored-bot').paused
        page.screenshot(path=str(out / f'{size}-activated.png'), full_page=True, animations='disabled')
        overflow = page.evaluate('document.documentElement.scrollWidth - innerWidth')
        assert overflow <= 1 and not errors
        (out / f'{size}.json').write_text(json.dumps({
            'captured_at': iso(utcnow()), 'browser': browser.browser_type.name, 'version': browser.version,
            'viewport': [width, height], 'page_errors': errors, 'horizontal_overflow': overflow,
            'scenario': 'Real isolated database backup/restore with synthetic old work; no production restore or physical device',
            'draft_and_keyboard_focus_preserved': True, 'executor_ui_code_hash': code_hash(),
            'source_sha256': {p: hashlib.sha256((out.parents[3] / p).read_bytes()).hexdigest() for p in (
                'src/hutch/server/static/app.js', 'src/hutch/server/static/style.css', 'src/hutch/server/static/index.html',
                'src/hutch/server/app.py', 'src/hutch/store.py', 'src/hutch/state_snapshot.py')},
        }, indent=2) + '\n')
    finally:
        context.tracing.stop(path=str(out / f'{size}-trace.zip'))
        context.close()
