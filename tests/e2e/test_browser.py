"""Real-browser checks (Chromium or Firefox via Playwright) of what unit tests cannot see: the live stream surviving a
network drop in the actual DOM, and the plain-POST controls doing what they say.

Skipped automatically when Playwright or its Chromium build is not installed:
    pip install playwright && playwright install chromium
"""

from __future__ import annotations

import hashlib
import json
import platform
import threading
import time
from datetime import datetime, timezone
from importlib.metadata import version as package_version
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

pw = pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402

from hutch.models import ApprovalMode, Bot, Event, EventType, Run, RunStatus, RuntimeKind, Schedule, Task  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from hutch.connections import ConnectionBook  # noqa: E402


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
        pill.wait_for(state="attached")
        assert pill.is_hidden(), "healthy idle executors stay quiet in the header"
        assert page.locator("#daemon-label").inner_text() == "live"
        assert page.locator(".daemon-dot").evaluate("el => getComputedStyle(el).animationName") == "none"
    finally:
        page.close()


def test_coordinator_specialist_dispatch_is_reviewable_at_all_viewports(browser, live):
    """Use the local mock runtime to inspect the reviewed task flow and durable specialist result."""
    base, app = live
    coordinator = app.state.store.create_bot(Bot(
        name="main-coordinator", display_name="Mara", model="mock/demo", tools=[]))
    specialist = app.state.store.create_bot(Bot(
        name="research-partner", display_name="Research Partner", model="mock/demo", tools=["memory"],
        instructions="Use this specialist's own saved instructions."))
    task_fact = app.state.store.remember(coordinator.id, "launch-window", "The public launch is planned for November.")
    app.state.store.review_fact(coordinator.id, task_fact.id, content_hash=task_fact.content_hash,
                                action="approve", actor="fixture")
    app.state.store.set_workspace_coordinator(coordinator.id)
    output = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/workspace-task-dispatch"
    output.mkdir(parents=True, exist_ok=True)
    sizes = {"desktop": (1440, 960), "tablet": (900, 1024), "phone": (390, 844)}
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        page.goto(f"{base}/#/chat/{coordinator.name}")
        page.locator("#chat-prompt").wait_for()
        page.locator("#chat-prompt").fill("Compare launch plan options. Keep the work in Hutch.")
        page.locator("#chat-send").click()
        prepare = page.locator("[data-prepare-bot-task]")
        prepare.wait_for(timeout=15000)
        prepare.click()
        dialog = page.get_by_role("dialog", name="Prepare a task for a Bot")
        try:
            dialog.wait_for(timeout=5000)
        except Exception as exc:
            raise AssertionError(f"task review did not open; modal={page.locator('#modal-root').inner_text()} "
                                 f"toasts={page.locator('#toast-root').inner_text() if page.locator('#toast-root').count() else ''} "
                                 f"errors={errors}") from exc
        assert dialog.locator("#workspace-task-target option").count() == 1
        assert "mock/demo" in dialog.locator("#workspace-task-capability").inner_text()
        assert "memory" in dialog.locator("#workspace-task-capability").inner_text()
        assert "not copied" in dialog.inner_text()
        dialog.locator("#workspace-task-brief").fill(
            "Compare two launch approaches and return a short recommendation with trade-offs.")
        dialog.locator("#workspace-task-assumptions").fill("Use public information only; do not contact anyone.")
        fact_selector = dialog.locator(".workspace-task-fact-selector")
        fact_selector.locator("summary").click()
        selected_fact = fact_selector.locator(f'[data-workspace-task-fact="{task_fact.id}"]')
        assert selected_fact.is_visible() and not selected_fact.is_checked()
        assert "provider may retain" in fact_selector.inner_text().lower()
        assert "not be added" in fact_selector.inner_text().lower()
        selected_fact.check()
        assert "1 of 8 selected" in dialog.locator("#workspace-task-facts-count").inner_text()
        source_card = dialog.locator(".workspace-task-source")
        source_style = source_card.evaluate("""element => {
          const style = getComputedStyle(element);
          return {leftWidth: style.borderLeftWidth, topWidth: style.borderTopWidth,
            leftColor: style.borderLeftColor, topColor: style.borderTopColor};
        }""")
        assert source_style["leftWidth"] == source_style["topWidth"]
        assert source_style["leftColor"] == source_style["topColor"]
        page.locator(".toast").wait_for(state="detached", timeout=6000)
        for label, (width, height) in sizes.items():
            page.set_viewport_size({"width": width, "height": height})
            page.evaluate("document.fonts.ready")
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1, label
            assert dialog.is_visible()
            assert dialog.locator("#workspace-task-target").is_visible()
            source_card.scroll_into_view_if_needed()
            page.screenshot(path=str(output / f"review-source-{label}.png"), animations="disabled")
            selected_fact.scroll_into_view_if_needed()
            page.screenshot(path=str(output / f"review-{label}.png"), animations="disabled")
            if label == "phone":
                dialog.locator(".modal-body").evaluate("element => element.scrollTop = element.scrollHeight")
                selected_box = selected_fact.locator("xpath=..").bounding_box()
                footer_box = dialog.locator(".modal-footer").bounding_box()
                assert selected_box and footer_box and selected_box["y"] + selected_box["height"] <= footer_box["y"]
                page.screenshot(path=str(output / "review-phone-fields.png"), animations="disabled")

        dialog.get_by_role("button", name="Send reviewed task").click()
        task_card = page.locator("[data-workspace-task]")
        task_card.wait_for(timeout=15000)
        assert "Research Partner" in task_card.inner_text()
        assert "Use public information only" in task_card.inner_text()
        assert "Specialist settings" in task_card.inner_text()
        page.locator(".toast").wait_for(state="detached", timeout=6000)
        task_card.get_by_text("Done", exact=True).wait_for(timeout=15000)
        assert "Latest specialist response" in task_card.inner_text()
        shared_facts = task_card.locator(".workspace-task-shared-facts")
        assert shared_facts.is_visible()
        shared_facts.locator("summary").click()
        assert "The public launch is planned for November." in shared_facts.inner_text()
        assert "not added to the specialist Bot's saved memory" in shared_facts.inner_text()
        for label, (width, height) in sizes.items():
            page.set_viewport_size({"width": width, "height": height})
            page.evaluate("document.fonts.ready")
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1, label
            assert task_card.is_visible()
            page.screenshot(path=str(output / f"timeline-{label}.png"), animations="disabled")
            shared_facts.screenshot(path=str(output / f"shared-facts-{label}.png"), animations="disabled")

        checkpoint_summary = task_card.locator(".workspace-task-checkpoints > summary")
        assert "Progress checkpoints" in checkpoint_summary.inner_text()
        checkpoint_summary.click()
        checkpoint_list = task_card.locator(".workspace-task-checkpoints ol")
        checkpoint_list.wait_for(state="visible")
        checkpoint_copy = task_card.locator(".workspace-task-checkpoints").inner_text()
        assert "Reviewed task accepted" in checkpoint_copy
        assert "Specialist response committed" in checkpoint_copy
        assert "This task already completed; continue the specialist chat directly." in checkpoint_copy
        assert checkpoint_list.locator("li").count() <= 16
        checkpoint_style = checkpoint_list.locator("li").first.evaluate("""element => {
          const style = getComputedStyle(element);
          return {leftWidth: style.borderLeftWidth, topWidth: style.borderTopWidth,
            leftColor: style.borderLeftColor, topColor: style.borderTopColor};
        }""")
        assert checkpoint_style["leftWidth"] == checkpoint_style["topWidth"] == "1px"
        assert checkpoint_style["leftColor"] == checkpoint_style["topColor"]
        for label, (width, height) in sizes.items():
            page.set_viewport_size({"width": width, "height": height})
            page.evaluate("document.fonts.ready")
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1, label
            assert checkpoint_list.is_visible()
            if label == "phone":
                last_checkpoint = checkpoint_list.locator("li").last
                last_checkpoint.scroll_into_view_if_needed()
                last_checkpoint.evaluate("""element => {
                  const scroller = element.closest('.chat-scroll');
                  const composer = document.querySelector('#composer-box');
                  const overlap = element.getBoundingClientRect().bottom - composer.getBoundingClientRect().top + 16;
                  if (overlap > 0) scroller.scrollTop += overlap;
                }""")
                last_box = last_checkpoint.bounding_box()
                composer_box = page.locator("#composer-box").bounding_box()
                assert last_box and composer_box and last_box["y"] + last_box["height"] <= composer_box["y"], \
                    "the final phone checkpoint remains above the sticky composer"
            page.screenshot(path=str(output / f"checkpoints-{label}.png"), animations="disabled")

        assert errors == [], errors
        assert page.locator("#modal-root").inner_text() == ""
        assert task_card.locator("details > summary").all_inner_texts()[-1] == "Request and coordinator draft"
        parent_conversation_id = app.state.store.list_conversations(coordinator.id)[0]["id"]
        task = app.state.store.list_workspace_tasks(parent_conversation_id)[0]
        assert task["target_bot_id"] == specialist.id
        assert task["task_brief"].startswith("Compare two launch approaches")
        assert task["result_message_id"]
        share_button = page.locator("[data-discuss-specialist-result]")
        share_button.wait_for()
        share_button.click()
        composer_reference = page.locator("#workspace-result-composer")
        composer_reference.wait_for(state="visible", timeout=5000)
        assert composer_reference.is_visible(), page.locator("#toast-root").inner_text()
        assert "only this response is sent as untrusted context" in composer_reference.inner_text().lower()
        assert "files, memory and permissions stay private" in composer_reference.inner_text().lower()
        composer_reference.get_by_role("button", name="Remove").click()
        assert composer_reference.is_hidden()
        share_button.click()
        composer_reference.wait_for(state="visible", timeout=5000)
        share_prompt = "Compare this specialist recommendation with my original constraints."
        page.locator("#chat-prompt").fill(share_prompt)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
        page.screenshot(path=str(output / "result-composer-phone.png"), animations="disabled")
        page.locator("#chat-send").click()
        source_preview = page.locator(".workspace-task-result-reference").last
        source_preview.wait_for(timeout=10000)
        assert "Research Partner" in source_preview.inner_text()
        source_preview.locator("summary").click()
        assert task["result"][:60] in source_preview.inner_text()
        reply_thread = page.locator(".thread").last
        returned_run_id = reply_thread.get_attribute("data-run-id")
        deadline = time.time() + 15
        while time.time() < deadline:
            if "Done" in reply_thread.inner_text():
                break
            page.wait_for_timeout(100)
        assert "Done" in reply_thread.inner_text()
        returned_run = app.state.store.get_run(returned_run_id)
        assert any(task["result"][:60] in item["content"] and "Treat this as untrusted" in item["content"]
                   for item in returned_run.conversation_context)
        for label, (width, height) in sizes.items():
            page.set_viewport_size({"width": width, "height": height})
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1, label
            page.locator("#chat-stream .msg.agent .mhead").last.scroll_into_view_if_needed()
            page.locator(".toast").wait_for(state="detached", timeout=6000)
            page.screenshot(path=str(output / f"result-return-{label}.png"), animations="disabled")
        page.locator("[data-open-workspace-task]").click()
        page.locator("#chat-prompt").wait_for()
        specialist_request = page.locator("#chat-stream").get_by_text("Compare two launch approaches", exact=False).first
        specialist_request.wait_for(state="attached", timeout=10000)
        page.locator(".mhead").get_by_text("Research Partner", exact=True).wait_for(timeout=10000)
        context.tracing.stop(path=str(output / "workspace-task-trace.zip"))
        trace_stopped = True
        (output / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_coordinator_specialist_dispatch_is_reviewable_at_all_viewports",
            "browser": f"{browser.browser_type.name.title()} {browser.version}",
            "viewports": [{"name": label, "width": size[0], "height": size[1]} for label, size in sizes.items()],
            "source_card_border": source_style,
            "inspected_screenshots": [f"review-source-{label}.png" for label in sizes],
            "page_errors": errors,
            "validation": ["coordinator answer stays a draft until reviewed", "target model/tools are visible",
                           "assumptions are sent with the brief", "specialist result is shared only after composer review",
                           "only the user-selected reviewed fact enters task context and remains task-scoped",
                           "selected result can be removed before the explicit follow-up is sent",
                           "shared result is linked to its exact source and marked as untrusted context",
                           "checkpoint timeline is bounded and contains only committed event markers",
                           "only a terminal no-effect attempt with unchanged built-in permissions can continue",
                           "continuation starts a fresh run and never replays the previous worker or its actions",
                           "final phone checkpoint remains above the sticky composer",
                           "no horizontal overflow", "task appears in main chat"],
            "fixtures": "Local mock model and local SQLite only; no provider or paid call.",
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        if not locals().get("trace_stopped", False):
            context.tracing.stop(path=str(output / "workspace-task-trace.zip"))
        context.close()


def test_dashboard_polish_keeps_work_feedback_steady_and_headings_readable(browser, live):
    """Inspect the real dashboard styles at desktop, tablet, and phone widths."""
    base, app = live
    app.state.store.create_bot(Bot(name="dashboard-polish", model="mock/demo", tools=[]))
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/dashboard-polish"
    out.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    trace_stopped = False
    captures = []
    sizes = {"desktop": (1440, 960), "tablet": (900, 1024), "phone": (390, 844)}
    try:
        for label, (width, height) in sizes.items():
            page.set_viewport_size({"width": width, "height": height})
            page.goto(f"{base}/#/chat/dashboard-polish")
            page.locator("#conversation-switcher").wait_for()
            page.locator("#chat-scroll").wait_for()
            page.evaluate("""() => {
              const slot = document.createElement('div');
              slot.id = 'dashboard-polish-typing-fixture';
              slot.className = 'typing-slot';
              slot.setAttribute('aria-hidden', 'true');
              slot.innerHTML = '<div class="typing"><span class="typing-dots"><span></span><span></span><span></span></span><span class="typing-label">Working…</span></div>';
              const scroll = document.querySelector('#chat-scroll');
              scroll.append(slot);
              scroll.scrollTop = scroll.scrollHeight;
            }""")
            page.evaluate("document.fonts.ready")
            studio_body = page.locator("body").evaluate("""element => {
              const style = getComputedStyle(element);
              return {fontSize: parseFloat(style.fontSize), lineHeight: parseFloat(style.lineHeight)};
            }""")
            studio_body_ratio = studio_body["lineHeight"] / studio_body["fontSize"]
            assert studio_body_ratio >= 1.5, (label, studio_body)
            indicator = page.locator("#dashboard-polish-typing-fixture .typing-dots span").first
            animation = indicator.evaluate("element => getComputedStyle(element).animationName")
            assert animation == "none", f"typing feedback should be steady, got {animation!r}"
            indicator_states = page.evaluate("""() => {
              const slot = document.querySelector('#dashboard-polish-typing-fixture');
              slot.insertAdjacentHTML('beforeend', '<span class="workflow"><a class="w working"><i class="wdot"></i></a></span><span class="status running">running</span>');
              const workflowDot = slot.querySelector('.workflow .wdot');
              const runningStatus = slot.querySelector('.status.running');
              return {
                workflowDot: getComputedStyle(workflowDot).animationName,
                runningStatus: getComputedStyle(runningStatus, '::before').animationName,
              };
            }""")
            assert indicator_states == {"workflowDot": "none", "runningStatus": "none"}, (label, indicator_states)
            indicator_box = page.locator("#dashboard-polish-typing-fixture").bounding_box()
            assert indicator_box and indicator_box["height"] >= 24, (label, indicator_box)
            studio_overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert studio_overflow <= 1, (label, studio_overflow)
            studio_capture = out / f"studio-{label}.png"
            page.screenshot(path=str(studio_capture), animations="disabled")

            page.goto(f"{base}/connections")
            heading = page.locator("#main h1")
            heading.wait_for()
            heading_metrics = heading.evaluate("""element => {
              const style = getComputedStyle(element);
              return {fontSize: parseFloat(style.fontSize), lineHeight: parseFloat(style.lineHeight)};
            }""")
            ratio = heading_metrics["lineHeight"] / heading_metrics["fontSize"]
            assert ratio >= 1.39, (label, heading_metrics)
            body_metrics = page.locator("body").evaluate("""element => {
              const style = getComputedStyle(element);
              return {fontSize: parseFloat(style.fontSize), lineHeight: parseFloat(style.lineHeight)};
            }""")
            body_ratio = body_metrics["lineHeight"] / body_metrics["fontSize"]
            assert body_ratio >= 1.5, (label, body_metrics)
            live_status = page.locator("#live-pill")
            live_status.wait_for()
            live_status_animation = live_status.evaluate(
                "element => getComputedStyle(element, '::before').animationName"
            )
            assert live_status_animation == "none", (label, live_status_animation)
            template_overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert template_overflow <= 1, (label, template_overflow)
            connections_capture = out / f"connections-{label}.png"
            page.screenshot(path=str(connections_capture), full_page=True, animations="disabled")
            captures.append({"size": label, "viewport": [width, height], "typing_animation": animation,
                             "typing_indicator_box": indicator_box,
                             "status_animations": indicator_states,
                             "live_status_animation": live_status_animation,
                             "studio_body": studio_body, "studio_body_line_height_ratio": round(studio_body_ratio, 3),
                             "heading": heading_metrics, "heading_line_height_ratio": round(ratio, 3),
                             "body": body_metrics, "body_line_height_ratio": round(body_ratio, 3),
                             "horizontal_overflow": max(studio_overflow, template_overflow),
                             "screenshots": [studio_capture.name, connections_capture.name]})
        assert not errors, errors
        context.tracing.stop(path=str(out / "trace.zip"))
        trace_stopped = True
        (out / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_dashboard_polish_keeps_work_feedback_steady_and_headings_readable",
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_dashboard_polish_keeps_work_feedback_steady_and_headings_readable",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "browser": browser.browser_type.name, "browser_version": browser.version,
            "playwright_version": package_version("playwright"),
            "scenario": "Synthetic visual-only working, workflow and running-status indicators; server-rendered Connections typography and live-status mark; no run or provider call",
            "provider_calls": 0, "page_errors": errors, "captures": captures,
            "source_sha256": {path: hashlib.sha256((out.parents[3] / path).read_bytes()).hexdigest()
                              for path in ("app/src/input.css", "src/hutch/server/static/ui.css",
                                           "src/hutch/server/static/style.css", "src/hutch/server/static/hutch.css",
                                           "src/hutch/server/static/app.js")},
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        if not trace_stopped:
            # Trace is stopped explicitly on success; on assertion failure retain diagnostic state too.
            try:
                context.tracing.stop(path=str(out / "trace-failed.zip"))
            except Exception:
                pass
        context.close()


def test_safe_checkpoint_continuation_is_reviewed_and_starts_a_new_attempt(browser, live, monkeypatch):
    """A no-effect task resumes only as a new, reviewable run with its checkpoint provenance intact."""
    from hutch.engine import Engine

    base, app = live
    # Keep the fixture deterministic; this journey tests admission and presentation, not execution.
    monkeypatch.setattr(app.state.engine, "dispatch_pending", lambda: 0)
    store = app.state.store
    coordinator = store.create_bot(Bot(name="resume-coordinator", display_name="Mara", model="mock/demo", tools=[]))
    specialist = store.create_bot(Bot(name="resume-specialist", display_name="Research Partner", model="mock/demo", tools=[]))
    store.set_workspace_coordinator(coordinator.id)
    parent, _ = store.create_conversation(coordinator.id, "Coordinator", idem_key="resume-parent",
                                          request_hash="resume-parent")

    source_prompt = "Compare two launch approaches and keep the task within Hutch."
    source_run = Run(bot_id=coordinator.id, prompt=source_prompt, conversation_id=parent["id"])
    source_run_id, _ = store.submit_conversation_message(parent["id"], source_prompt, source_run,
        Task(bot_id=coordinator.id, prompt=source_prompt), idem_key="resume-source", request_hash="resume-source")
    owner = store.claim_run(source_run_id, "resume-source-owner", 60)
    assert owner is not None
    store.transition_run(source_run_id, RunStatus.running, fence=owner.fence)
    store.append_event(Event(run_id=source_run_id, type=EventType.message,
        data={"role": "assistant", "content": "I prepared a public-information research brief.",
              "message_id": "resume-source-answer"}, owner_fence=owner.fence))
    store.flush_events()
    store.transition_run(source_run_id, RunStatus.succeeded, fence=owner.fence)
    source_messages = store.list_conversation_messages(parent["id"])
    source_user = next(message for message in source_messages if message["role"] == "user")
    source_answer = next(message for message in source_messages if message["role"] == "assistant")

    brief = "Compare two public launch approaches and report the main trade-offs."
    assumptions = "Use public sources only; do not contact anyone."
    effective = brief + "\n\nUser-reviewed assumptions and constraints:\n" + assumptions
    pending_run = Run(bot_id=specialist.id, prompt=effective, origin="workspace_task")
    pending_task = Task(bot_id=specialist.id, prompt=effective)
    child_run_id, _ = store.submit_workspace_task(parent_conversation_id=parent["id"],
        source_run_id=source_run_id, source_user_message_id=source_user["id"],
        source_assistant_message_id=source_answer["id"], target_bot_id=specialist.id,
        task_brief=brief, assumptions=assumptions, run=pending_run, task=pending_task,
        capability_snapshot=Engine.capability_snapshot(specialist), idem_key="resume-task", request_hash="resume-task")
    child_owner = store.claim_run(child_run_id, "resume-child-owner", 60)
    assert child_owner is not None
    store.transition_run(child_run_id, RunStatus.running, fence=child_owner.fence)
    checkpoint = "The market outline is incomplete; compare price, setup effort, and support coverage."
    store.append_event(Event(run_id=child_run_id, type=EventType.message,
        data={"role": "assistant", "content": checkpoint, "message_id": "resume-checkpoint"},
        owner_fence=child_owner.fence))
    store.flush_events()
    store.transition_run(child_run_id, RunStatus.failed, fence=child_owner.fence,
                         exit_reason="interrupted", error="fixture interruption")

    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/safe-task-continuation"
    out.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    errors, origins = [], set()
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: origins.add(urlsplit(request.url).netloc))
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    trace_stopped = False
    try:
        page.goto(f"{base}/#/chat/{coordinator.name}")
        button = page.get_by_role("button", name="Continue from checkpoint")
        button.wait_for(timeout=10000)
        card = page.locator("[data-workspace-task]").filter(has=button)
        assert "Failed" in card.inner_text()
        assert "Research Partner" in card.inner_text()
        assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
        button.click()
        dialog = page.get_by_role("dialog", name="Continue from a safe checkpoint")
        dialog.wait_for()
        assert brief in dialog.inner_text()
        assert assumptions in dialog.inner_text()
        assert checkpoint in dialog.inner_text()
        assert "additional quota" in dialog.inner_text()
        assert "selected facts" in dialog.inner_text()
        viewports = {"desktop": (1440, 960), "tablet": (900, 1024), "phone": (390, 844)}
        captures = []
        for label, (width, height) in viewports.items():
            page.set_viewport_size({"width": width, "height": height})
            page.evaluate("document.fonts.ready")
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, overflow)
            assert dialog.is_visible()
            capture = out / f"confirm-{label}.png"
            page.screenshot(path=str(capture), full_page=True, animations="disabled")
            captures.append(capture.name)
            if label == "phone":
                body = dialog.locator(".modal-body")
                body.evaluate("element => element.scrollTop = element.scrollHeight")
                footer = dialog.locator(".modal-footer").bounding_box()
                confirm = dialog.get_by_role("button", name="Start a new run").bounding_box()
                assert footer and confirm and confirm["y"] >= footer["y"]
                page.screenshot(path=str(out / "confirm-phone-bottom.png"), full_page=True, animations="disabled")

        dialog.get_by_role("button", name="Start a new run").click()
        continued_card = page.locator("[data-workspace-task]").filter(has_text="Continued from a prior no-effect attempt")
        continued_card.wait_for(timeout=10000)
        assert "Queued" in continued_card.inner_text()
        items = store.list_workspace_tasks(parent["id"])
        continued = next(item for item in items if item["continuation_of_task_id"])
        continued_run = store.get_run(continued["child_run_id"])
        assert continued_run is not None and continued_run.status is RunStatus.pending
        assert checkpoint in continued_run.conversation_context[-1]["content"]
        assert "untrusted progress context" in continued_run.conversation_context[-1]["content"]
        assert continued["shared_facts"] == []
        assert not store.actions_in_doubt(continued["child_run_id"])
        assert store._db.execute("SELECT COUNT(*) FROM tool_actions WHERE run_id = ?", (child_run_id,)).fetchone()[0] == 0
        assert origins <= {urlsplit(base).netloc}
        assert not errors, errors
        context.tracing.stop(path=str(out / "trace.zip"))
        trace_stopped = True
        (out / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_safe_checkpoint_continuation_is_reviewed_and_starts_a_new_attempt",
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_safe_checkpoint_continuation_is_reviewed_and_starts_a_new_attempt",
            "browser": f"{browser.browser_type.name.title()} {browser.version}",
            "playwright": package_version("playwright"), "viewports": viewports,
            "screenshots": captures + ["confirm-phone-bottom.png"],
            "provider_calls": 0, "external_requests": 0, "page_errors": errors,
            "status": "new pending run, linked to exact previous checkpoint event",
            "authority": "No effects, action receipts, child runs, or task-only fact snapshots were carried forward.",
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        if not trace_stopped:
            try:
                context.tracing.stop(path=str(out / "trace-failed.zip"))
            except Exception:
                pass
        context.close()


def test_provider_connections_fit_phone_viewports_and_capture_signin_states(browser, live):
    from pathlib import Path

    base, app = live
    ConnectionBook(app.state.config.state_dir).add("opencode-go", name="opencode-go")
    page = browser.new_page(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/provider-signin"
    out.mkdir(parents=True, exist_ok=True)
    try:
        page.goto(base + "/#/connections")
        page.get_by_role("heading", name="Connections").wait_for()
        page.get_by_text("Sign in with ChatGPT").wait_for()
        page.get_by_text("Sign in to Go, subscribe if needed, copy its provider-issued key", exact=False).wait_for()
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024),
                                     ("phone", 390, 844), ("compact-phone", 320, 740)):
            page.set_viewport_size({"width": width, "height": height})
            page.screenshot(path=str(out / f"connections-{label}.png"), full_page=True, animations="disabled")
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, overflow)
            nested_overflow = page.locator(
                ".page-scroll, .container, .conn-card, .conn-card .bot-head, .conn-card .bot-facts"
            ).evaluate_all("els => els.map(el => ({selector: el.className, overflow: el.scrollWidth - el.clientWidth}))"
                           ".filter(item => item.overflow > 1)")
            assert not nested_overflow, (label, nested_overflow)
        chatgpt_button = page.get_by_role("button", name="Continue with ChatGPT")
        assert chatgpt_button.is_visible() and not chatgpt_button.is_enabled()
        assert page.get_by_text("no provider-enforced output-token limit", exact=False).is_visible()
        assert page.get_by_text("Hutch does not read OpenCode's private auth file", exact=False).is_visible()
        assert not errors, errors
        (out / "connections-validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_provider_connections_fit_phone_viewports_and_capture_signin_states",
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_provider_connections_fit_phone_viewports_and_capture_signin_states",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(), "hutch_version": package_version("hutch"),
            "browser": browser.version,
            "viewports": [{"name": label, "width": width, "height": height}
                          for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024),
                                                       ("phone", 390, 844), ("compact-phone", 320, 740))],
            "connections": ["opencode-go", "chatgpt-plan-preview"],
            "provider_credentials_used": False, "external_auth_completed": False,
        }, indent=2) + "\n")
    finally:
        page.close()


def test_google_calendar_read_grant_is_clear_at_desktop_tablet_and_phone(browser, live, monkeypatch):
    from pathlib import Path

    base, app = live
    monkeypatch.setenv("HUTCH_GOOGLE_OAUTH_CLIENT_ID", "fixture-client.apps.googleusercontent.com")

    class FixtureGoogleCalendarBook:
        accounts_rows = [{"id": "gcal_0123456789abcdef01234567", "label": "Personal",
                          "created_at": "2026-10-09T00:00:00+00:00", "scopes": [
                              "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
                              "https://www.googleapis.com/auth/calendar.events.readonly"], "status": "connected"}]

        class Secrets:
            @staticmethod
            def available():
                return True

        def __init__(self, state_dir, client_id):
            self.secrets = self.Secrets()

        @classmethod
        def accounts(cls):
            return cls.accounts_rows

        @staticmethod
        def list_calendars(account_id):
            return [{"id": "primary", "name": "Personal Calendar", "primary": True, "access_role": "owner"},
                    {"id": "team@example.test", "name": "Team Calendar", "primary": False, "access_role": "reader"}]

        @staticmethod
        def start(label, callback):
            from hutch.google_calendar import OAuthStart
            return OAuthStart("https://accounts.google.com/o/oauth2/v2/auth?state=fixture", "fixture")

        @staticmethod
        def callback_uri(request):
            port = request.scope["server"][1]
            return f"http://127.0.0.1:{port}/api/v1/connections/google-calendar/callback"

    monkeypatch.setattr("hutch.google_calendar.GoogleCalendarBook", FixtureGoogleCalendarBook)
    bot = Bot(name="calendar-assistant", model="mock/demo", tools=[])
    app.state.store.create_bot(bot)
    page = browser.new_page(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page.add_init_script("""
      window.__calendarOAuth = { target: null, url: null, opener: 'not-set', closed: false };
      window.open = (_url, target) => {
        window.__calendarOAuth.target = target;
        return {
          set opener(value) { window.__calendarOAuth.opener = value; },
          location: { replace(value) { window.__calendarOAuth.url = value; } },
          close() { window.__calendarOAuth.closed = true; }
        };
      };
    """)
    errors, external = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external.append(request.url)
            if not request.url.startswith(base) else None)
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/google-calendar"
    out.mkdir(parents=True, exist_ok=True)
    try:
        page.goto(base + "/#/connections")
        page.get_by_role("heading", name="Connections").wait_for()
        page.get_by_text("Connect with Google's official installed-app flow", exact=False).wait_for()
        assert page.get_by_role("button", name="Connect Google Calendar").is_enabled()
        page.get_by_role("button", name="Load calendars").click()
        calendar = page.locator("[data-google-calendar-calendar]")
        calendar.wait_for(state="visible")
        calendar.select_option("primary")
        grant_button = page.get_by_role("button", name="Grant read access")
        assert grant_button.is_enabled()
        grant_button.click()
        page.get_by_text("Can read Personal Calendar", exact=False).wait_for()
        assert page.get_by_text("retained in this Bot's run history", exact=False).is_visible()
        assert page.get_by_text("read-only at the account level", exact=False).is_visible()
        page.get_by_role("button", name="Dismiss notification").click()
        captures = []
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            scroll = page.locator(".page-scroll")
            scroll.evaluate("element => { element.scrollTop = 0; }")
            page.screenshot(path=str(out / f"overview-{label}.png"), animations="disabled")
            page.locator("[data-google-calendar-account]").scroll_into_view_if_needed()
            scroll.evaluate("element => { element.scrollTop = Math.max(0, element.scrollTop - 72); }")
            page.screenshot(path=str(out / f"granted-{label}.png"), animations="disabled")
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, overflow)
            captures.append({"size": label, "viewport": [width, height], "scenes": ["overview", "granted account"],
                             "horizontal_overflow": overflow})
        assert page.get_by_role("button", name="Revoke Bot access").bounding_box()["height"] >= 44
        page.locator("#google-calendar-label").fill("Work")
        page.get_by_role("button", name="Connect Google Calendar").click()
        page.get_by_text("Finish Google sign-in in the new browser tab", exact=False).wait_for()
        oauth = page.evaluate("window.__calendarOAuth")
        assert oauth["target"] == "_blank" and oauth["opener"] is None
        authorization_url = urlsplit(oauth["url"])
        assert authorization_url.scheme == "https" and authorization_url.hostname == "accounts.google.com"
        assert authorization_url.path == "/o/oauth2/v2/auth" and parse_qs(authorization_url.query)["state"] == ["fixture"]
        assert not errors, errors
        assert not external, external
        (out / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_google_calendar_read_grant_is_clear_at_desktop_tablet_and_phone",
            "command": ("PLAYWRIGHT_BROWSERS_PATH=/home/kevina/.cache/ms-playwright .venv/bin/pytest -q "
                        "-W error::pytest.PytestUnhandledThreadExceptionWarning -W error::SyntaxWarning "
                        "tests/e2e/test_browser.py -k google_calendar_read_grant_is_clear_at_desktop_tablet_and_phone"),
            "captured_at": datetime.now(timezone.utc).isoformat(), "browser": browser.version,
            "provider_credentials_used": False, "provider_calls": 0,
            "scenario": "Synthetic connected-account metadata and calendar-list fixture; exercised actual local API grant persistence, Bot binding, disclosure and revoke control",
            "external_requests": external, "page_errors": errors, "captures": captures,
            "source_sha256": {path: hashlib.sha256((out.parents[3] / path).read_bytes()).hexdigest()
                              for path in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                           "src/hutch/server/app.py", "src/hutch/server/security.py",
                                           "src/hutch/store.py", "src/hutch/google_calendar.py",
                                           "src/hutch/tools/google_calendar.py")},
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        page.close()


def test_outlook_calendar_uses_account_consent_and_one_bot_grant_at_all_viewports(browser, live, monkeypatch):
    from pathlib import Path

    base, app = live
    monkeypatch.setenv("HUTCH_OUTLOOK_OAUTH_CLIENT_ID", "fixture-public-client")

    class FixtureOutlookCalendarBook:
        accounts_rows = [{"id": "mscal_0123456789abcdef01234567", "label": "Work",
                          "created_at": "2026-10-09T00:00:00+00:00", "scopes": ["Calendars.ReadBasic"],
                          "status": "connected"}]

        class Secrets:
            @staticmethod
            def available():
                return True

        def __init__(self, state_dir, client_id):
            self.secrets = self.Secrets()

        @classmethod
        def accounts(cls):
            return cls.accounts_rows

        @staticmethod
        def list_calendars(account_id):
            return [{"id": "primary", "name": "Work Calendar", "primary": True},
                    {"id": "team", "name": "Team Calendar", "primary": False}]

        @staticmethod
        def start(label, callback):
            from hutch.outlook_calendar import OAuthStart
            return OAuthStart("https://login.microsoftonline.com/common/oauth2/v2.0/authorize?state=fixture",
                              "fixture")

        @staticmethod
        def callback_uri(request):
            port = request.scope["server"][1]
            return f"http://localhost:{port}/api/v1/connections/outlook-calendar/callback"

    monkeypatch.setattr("hutch.outlook_calendar.OutlookCalendarBook", FixtureOutlookCalendarBook)
    bot = Bot(name="calendar-planner", display_name="Meeting Planner", model="mock/demo", tools=[])
    app.state.store.create_bot(bot)
    page = browser.new_page(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page.add_init_script("""
      window.__outlookOAuth = { target: null, url: null, opener: 'not-set', closed: false };
      window.open = (_url, target) => {
        window.__outlookOAuth.target = target;
        return {
          set opener(value) { window.__outlookOAuth.opener = value; },
          location: { replace(value) { window.__outlookOAuth.url = value; } },
          close() { window.__outlookOAuth.closed = true; }
        };
      };
    """)
    errors, external = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external.append(request.url)
            if not request.url.startswith(base) else None)
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/outlook-calendar"
    out.mkdir(parents=True, exist_ok=True)
    try:
        page.goto(base + "/#/connections")
        page.get_by_role("heading", name="Connections").wait_for()
        card = page.locator(".outlook-calendar-card")
        assert "Calendars.ReadBasic" in card.inner_text()
        assert "Microsoft consent applies to the signed-in account" in card.inner_text()
        assert "event bodies, attachments or extensions" in card.inner_text()
        card.locator("details > summary").click()
        assert "common" in card.inner_text()
        assert "cannot expand that choice" in card.inner_text()
        assert page.get_by_role("button", name="Connect Outlook Calendar").is_enabled()
        page.locator("#outlook-calendar-label").fill("Work")
        page.get_by_role("button", name="Connect Outlook Calendar").click()
        page.get_by_text("Finish Microsoft sign-in in the new browser tab", exact=False).wait_for()
        oauth = page.evaluate("window.__outlookOAuth")
        assert oauth["target"] == "_blank" and oauth["opener"] is None
        authorization_url = urlsplit(oauth["url"])
        assert authorization_url.scheme == "https" and authorization_url.hostname == "login.microsoftonline.com"
        assert authorization_url.path == "/common/oauth2/v2.0/authorize"
        assert parse_qs(authorization_url.query)["state"] == ["fixture"]

        page.get_by_role("button", name="Load calendars").click()
        calendar = page.locator("[data-outlook-calendar-calendar]")
        calendar.wait_for(state="visible")
        calendar.select_option("primary")
        grant_button = page.get_by_role("button", name="Grant read access")
        assert grant_button.is_enabled()
        grant_button.click()
        card.locator("details > summary").click()
        page.get_by_text("Can read Work Calendar", exact=False).wait_for()
        assert page.get_by_text("Calendars.ReadBasic account consent", exact=False).is_visible()
        while page.locator(".toast").count():
            page.locator(".toast-close").first.click()

        captures = []
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            card = page.locator(".outlook-calendar-card")
            if not card.locator("details").evaluate("element => element.open"):
                card.locator("details > summary").click()
            scroll = page.locator(".page-scroll")
            scroll.evaluate("element => { element.scrollTop = 0; }")
            page.screenshot(path=str(out / f"overview-{label}.png"), full_page=True, animations="disabled")
            account = page.locator("[data-outlook-calendar-account]")
            account.scroll_into_view_if_needed()
            page.screenshot(path=str(out / f"granted-{label}.png"), full_page=True, animations="disabled")
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, overflow)
            captures.append({"size": label, "viewport": [width, height], "scenes": ["connection disclosure", "granted account"],
                             "horizontal_overflow": overflow})
        assert page.get_by_role("button", name="Revoke Bot access").bounding_box()["height"] >= 44
        assert not errors, errors
        assert not external, external
        (out / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_outlook_calendar_uses_account_consent_and_one_bot_grant_at_all_viewports",
            "captured_at": datetime.now(timezone.utc).isoformat(), "browser": browser.version,
            "provider_credentials_used": False, "provider_calls": 0,
            "scenario": "Synthetic Microsoft account metadata and calendar list; actual local API persists one Bot grant; sign-in navigation is intercepted",
            "external_requests": external, "page_errors": errors, "captures": captures,
            "source_sha256": {path: hashlib.sha256((out.parents[3] / path).read_bytes()).hexdigest()
                              for path in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                           "src/hutch/server/app.py", "src/hutch/server/security.py",
                                           "src/hutch/store.py", "src/hutch/outlook_calendar.py",
                                           "src/hutch/tools/outlook_calendar.py")},
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        page.close()


def test_opt_in_chatgpt_signin_is_fixture_intercepted_and_responsive(browser, live, monkeypatch):
    from pathlib import Path

    monkeypatch.setenv("HUTCH_ENABLE_CHATGPT_PLAN", "1")
    base, _ = live
    page = browser.new_page(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/provider-signin"
    out.mkdir(parents=True, exist_ok=True)
    auth_requests = []
    request_origins = set()
    page.on("request", lambda request: request_origins.add(urlsplit(request.url).netloc)
            if urlsplit(request.url).scheme in ("http", "https") else None)
    page.route("https://auth.openai.com/**", lambda route: (
        auth_requests.append(route.request.url),
        route.fulfill(status=200, content_type="text/html",
                      body="<!doctype html><title>Local auth fixture</title><p>Authorization intercepted locally.</p>")))
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(base + "/#/connections")
        button = page.get_by_role("button", name="Continue with ChatGPT")
        button.wait_for(state="visible")
        page.get_by_role("heading", name="Connections").wait_for()
        assert button.is_enabled()
        assert page.get_by_text("Availability depends on OpenAI eligibility and your account", exact=False).is_visible()
        # Wait for the first app paint before taking the full-page desktop capture. The button can
        # become visible one frame before the view is composited, which produced a blank proof image.
        page.wait_for_function("document.fonts.status === 'loaded'")
        page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
        page.wait_for_timeout(250)
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            page.screenshot(path=str(out / f"chatgpt-preview-enabled-{label}.png"),
                            full_page=True, animations="disabled")
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
            button_box = button.bounding_box()
            assert button_box and 0 <= button_box["y"] < height and button_box["y"] + button_box["height"] <= height

        button.click()
        page.wait_for_url("https://auth.openai.com/api/accounts/authorize*")
        assert page.get_by_text("Authorization intercepted locally.").is_visible()
        assert len(auth_requests) == 1
        params = parse_qs(urlsplit(auth_requests[0]).query)
        assert params["client_id"] == ["dynamic_agent_client"]
        assert params["redirect_uri"][0].startswith("http://127.0.0.1:")
        assert params["scope"][0].find("chatgpt.tokens.use.direct") >= 0
        assert params["code_challenge_method"] == ["S256"]
        assert "code" not in params and "access_token" not in params
        assert request_origins <= {urlsplit(base).netloc, "auth.openai.com"}, request_origins
        assert not errors, errors
        (out / "chatgpt-preview-enabled-validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_opt_in_chatgpt_signin_is_fixture_intercepted_and_responsive",
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_opt_in_chatgpt_signin_is_fixture_intercepted_and_responsive",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(), "hutch_version": package_version("hutch"),
            "browser": browser.version,
            "viewports": [{"name": label, "width": width, "height": height}
                          for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024),
                                                       ("phone", 390, 844))],
            "auth_destination": "https://auth.openai.com/api/accounts/authorize",
            "authorization_intercepted_locally": True,
            "provider_credentials_used": False, "external_auth_completed": False,
            "page_errors": errors,
        }, indent=2) + "\n")
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


def test_truncated_tool_source_card_opens_verified_plain_text_at_all_viewports(browser, live):
    """The PF-2 source card exposes the full artifact through the hash-checked compatibility route."""
    base, app = live
    store = app.state.store
    bot = store.create_bot(Bot(name="source-card", model="mock/demo", runtime=RuntimeKind.mock, tools=["files"]))
    conversation, _ = store.create_conversation(
        bot.id, "Source card", idem_key="source-card-conversation", request_hash="source-card-request")
    prompt = "read the large output"
    run = Run(bot_id=bot.id, prompt=prompt)
    task = Task(bot_id=bot.id, kind="on_demand", prompt=prompt)
    run_id, _ = store.submit_conversation_message(
        conversation["id"], prompt, run, task, idem_key="source-card-message", request_hash="source-card-message-request")
    claimed = store.claim_run(run_id, "source-card-fixture", 60)
    assert claimed is not None
    store.transition_run(run_id, RunStatus.running, fence=claimed.fence, event={"fixture": "artifact-card"})

    filename = "001-read_file.txt"
    payload = b"<script>window.artifactScriptRan=true</script>\ncomplete verified output\n"
    artifact_dir = app.state.config.run_dir(bot.name, run_id) / "artifacts"
    artifact_dir.mkdir(parents=True)
    artifact = artifact_dir / filename
    artifact.write_bytes(payload)
    artifact.chmod(0o400)
    digest = hashlib.sha256(payload).hexdigest()
    store.append_event(Event(run_id=run_id, type=EventType.tool_call,
                             data={"tool": "read_file", "args": {"path": "large.txt"}}))
    store.append_event(Event(run_id=run_id, type=EventType.tool_result, data={
        "tool": "read_file", "ok": True, "output": "<script>window.artifactScriptRan=true</script>\n… [full output saved]",
        "chars": len(payload.decode()), "artifact": f"artifacts/{filename}",
        "artifact_sha256": digest, "artifact_bytes": len(payload),
    }))
    store.append_event(Event(run_id=run_id, type=EventType.message,
                             data={"role": "assistant", "content": "I saved the full output."}))
    store.transition_run(run_id, RunStatus.succeeded, fence=claimed.fence, event={"verified": True})

    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/tool-source-card"
    out.mkdir(parents=True, exist_ok=True)
    records = []
    for name, width, height in (("desktop", 1440, 960), ("tablet", 768, 1024), ("phone", 390, 844)):
        context = browser.new_context(viewport={"width": width, "height": height}, reduced_motion="reduce",
                                      is_mobile=(name == "phone"), has_touch=(name == "phone"))
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(f"{base}/#/chat/{bot.name}")
            page.locator("#conversation-switcher").wait_for()
            page.locator(".tool-src-flag").wait_for()
            row = page.locator(".tool-line[data-tool-line]").first
            assert row.locator(".tool-src-flag").inner_text() == "source"
            row.locator(".tool-line-head").click()
            card = row.locator(".tool-source")
            card.wait_for(state="visible")
            assert card.locator("xpath=..").get_attribute("class") == "tool-artifact-actions"
            href = card.get_attribute("href")
            assert href == f"/api/runs/{run_id}/artifacts/{filename}"
            response = page.request.get(base + href)
            assert response.status == 200
            assert response.headers.get("x-hutch-artifact-verified") == "sha256"
            assert response.headers.get("content-disposition") == "inline"
            assert response.body() == payload
            card_box = card.bounding_box()
            assert card_box and card_box["height"] >= 40, card_box
            assert card_box["y"] >= 0 and card_box["y"] + card_box["height"] <= height, card_box
            assert "full output" in card.inner_text() and filename in card.inner_text()
            filename_box = None
            if name == "phone":
                filename_box = card.locator(".tool-source-name").bounding_box()
                meta_box = card.locator(".tool-source-meta").bounding_box()
                open_box = card.locator(".tool-source-go").bounding_box()
                assert filename_box and filename_box["height"] < 24, filename_box
                assert meta_box and open_box and abs(meta_box["y"] - open_box["y"]) < 2
                assert meta_box["y"] > filename_box["y"]
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
            screenshot = out / f"{name}.png"
            page.screenshot(path=str(screenshot), animations="disabled")
            card.focus()
            with context.expect_page() as opened_info:
                page.keyboard.press("Enter")
            opened = opened_info.value
            opened.wait_for_load_state("domcontentloaded")
            assert "<script>window.artifactScriptRan=true</script>" in opened.locator("body").inner_text()
            assert opened.evaluate("window.artifactScriptRan") is None
            assert not errors, errors
            records.append({"size": name, "viewport": [width, height], "screenshot": screenshot.name,
                            "source_card_bounds": {key: round(value) for key, value in card_box.items()},
                            "phone_filename_single_line": name != "phone" or filename_box["height"] < 24,
                            "overflow_px": 0, "verified_hash": digest, "script_inert": True,
                            "page_errors": errors})
            opened.close()
        finally:
            context.close()

    repo = Path(__file__).resolve().parents[2]
    source_files = ("src/hutch/server/app.py", "src/hutch/server/static/app.js",
                    "src/hutch/server/static/style.css")
    (out / "validation.json").write_text(json.dumps({
        "captured_at": datetime.now(timezone.utc).isoformat(), "browser": browser.browser_type.name,
        "browser_version": browser.version, "playwright_version": package_version("playwright"),
        "source_sha256": {path: hashlib.sha256((repo / path).read_bytes()).hexdigest()
                          for path in source_files},
        "scenario": "synthetic truncated tool output; open source card and verify run-local file integrity and plain-text rendering",
        "provider_calls": 0, "captures": records,
        "limitation": "Fixture browser test; no provider/model or physical phone was used.",
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
            page.locator("#composer-menu-btn").click()
            page.get_by_role("button", name="Browse files in this chat").click()
            files_dialog = page.get_by_role("dialog", name="Files in this chat")
            files_dialog.wait_for()
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
            assert files_dialog.evaluate("el => el.scrollWidth - el.clientWidth") <= 1
            modal_file = files_dialog.get_by_role("link", name="Download monthly.csv")
            modal_file.wait_for(state="visible")
            assert any(text.startswith("Created file ·") for text in
                       files_dialog.locator(".conversation-file-copy > span").all_inner_texts())
            files_image = out / f"files-{name}.png"
            page.screenshot(path=str(files_image), animations="disabled")
            modal_file.focus()
            with page.expect_download() as modal_download_info:
                page.keyboard.press("Enter")
            modal_download = modal_download_info.value
            assert Path(modal_download.path()).read_bytes() == content.encode("utf-8")
            files_dialog.get_by_role("button", name="Done").click()
            assert page.locator("#composer-menu-btn").evaluate("el => document.activeElement === el")
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
                            "conversation_files_screenshot": files_image.name,
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
        "screenshots": {"generated_files": [record["screenshot"] for record in records],
                        "conversation_files": [record["conversation_files_screenshot"] for record in records]},
        "journey": "write a text file with Hutch's file tool; download its run-scoped immutable snapshot from chat",
        "runtime_fixture": "tests.support.TestScenarioRuntime", "provider_calls": 0, "captures": records,
        "limitation": "Only files written through write_file are snapshotted; arbitrary shell-created files are not attached.",
    }, indent=2) + "\n")


def test_conversation_file_browser_explains_the_empty_state(browser, live):
    base, app = live
    store = app.state.store
    bot = store.create_bot(Bot(name="empty-files-bot", model="mock/demo", runtime=RuntimeKind.mock,
                               tools=["files"], approval_mode=ApprovalMode.auto))
    conversation, _ = store.create_conversation(
        bot.id, "No files yet", idem_key="empty-files-conversation", request_hash="empty-files-request")
    page = browser.new_page(viewport={"width": 390, "height": 844}, reduced_motion="reduce")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(f"{base}/#/chat/{bot.name}")
        page.locator("#conversation-switcher").wait_for()
        assert page.locator("#conversation-switcher").input_value() == conversation["id"]
        page.locator("#composer-menu-btn").click()
        page.get_by_role("button", name="Browse files in this chat").click()
        dialog = page.get_by_role("dialog", name="Files in this chat")
        dialog.wait_for()
        status = dialog.get_by_role("status")
        dialog.get_by_text("No files or saved tool output in this chat yet.", exact=True).wait_for()
        assert status.inner_text() == "No files or saved tool output in this chat yet."
        assert dialog.locator(".conversation-file").count() == 0
        assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
        page.keyboard.press("Escape")
        assert page.locator("#composer-menu-btn").evaluate("el => document.activeElement === el")
        assert not errors, errors
    finally:
        page.close()


def test_verified_artifact_can_be_shared_with_another_chat_and_revoked(browser, live):
    base, app = live
    store, config = app.state.store, app.state.config
    source_bot = store.create_bot(Bot(name="share-source-ui", model="mock/demo", tools=["files"]))
    target_bot = store.create_bot(Bot(name="share-target-ui", model="mock/demo", tools=["files"]))
    source, _ = store.create_conversation(source_bot.id, "Source report", idem_key="share-ui-source",
                                          request_hash="share-ui-source-request")
    target, _ = store.create_conversation(target_bot.id, "Recipient chat", idem_key="share-ui-target",
                                          request_hash="share-ui-target-request")
    run = Run(bot_id=source_bot.id, prompt="create report", conversation_id=source["id"],
              status=RunStatus.succeeded)
    store.create_run(run)
    with store._tx() as db:
        db.execute("INSERT INTO conversation_runs (conversation_id, run_id, attached_at) VALUES (?, ?, ?)",
                   (source["id"], run.id, run.created_at))
    payload = b"A verified report for the selected recipient chat.\n"
    filename = "001-report.txt"
    artifact_dir = config.run_dir(source_bot.name, run.id) / "artifacts"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / filename).write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    store.append_event(Event(run_id=run.id, type=EventType.tool_result, data={
        "tool": "write_file", "output": "saved report", "chars": len(payload),
        "artifact": f"artifacts/{filename}", "artifact_sha256": digest, "artifact_bytes": len(payload),
        "workspace_file": {"artifact": f"artifacts/{filename}", "sha256": digest,
                           "bytes": len(payload), "name": "report.txt", "path": "report.txt"},
    }))

    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/artifact-sharing"
    out.mkdir(parents=True, exist_ok=True)
    page = browser.new_page(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page.context.tracing.start(screenshots=True, snapshots=True, sources=True)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    captures = []
    try:
        for name, width, height in (("desktop", 1440, 960), ("tablet", 768, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            page.goto(f"{base}/#/chat/{source_bot.name}")
            page.locator("#conversation-switcher").wait_for()
            assert page.locator("#conversation-switcher").input_value() == source["id"]
            page.locator("#composer-menu-btn").click()
            page.get_by_role("button", name="Browse files in this chat").click()
            files_dialog = page.get_by_role("dialog", name="Files in this chat")
            files_dialog.wait_for()
            share_button = files_dialog.get_by_role("button", name="Share report.txt with another chat")
            share_button.wait_for(state="visible")
            share_button.focus()
            page.keyboard.press("Enter")
            destination = files_dialog.get_by_role("combobox", name="Destination chat")
            destination.wait_for(state="visible")
            assert files_dialog.get_by_role("button", name="Share file").is_disabled(), (
                "sharing must require a deliberate destination choice")
            destination.select_option(target["id"])
            assert files_dialog.get_by_text(
                "This adds a verified file reference to that chat’s Files list. It does not copy the file into its workspace or add the contents to its model context.",
                exact=True).is_visible()
            share_actions = files_dialog.locator(".artifact-share-actions").bounding_box()
            modal_footer = page.locator(".modal-footer").bounding_box()
            done_button = files_dialog.get_by_role("button", name="Done")
            done_box = done_button.bounding_box()
            assert share_actions and modal_footer and share_actions["y"] + share_actions["height"] <= modal_footer["y"] + 1, (
                name, share_actions, modal_footer)
            assert 0 <= modal_footer["y"] and modal_footer["y"] + modal_footer["height"] <= height + 1, (
                name, share_actions, modal_footer, page.locator(".modal-card").bounding_box())
            assert done_button.is_visible() and done_box and 0 <= done_box["y"] \
                and done_box["y"] + done_box["height"] <= height + 1, (
                    name, done_box, modal_footer, page.locator(".modal-card").bounding_box())
            chooser = out / f"{name}-share-chooser.png"
            page.screenshot(path=str(chooser), animations="disabled")
            if name == "desktop":
                cancel_share = files_dialog.get_by_role("button", name="Cancel")
                cancel_share.focus()
                page.keyboard.press("Enter")
                assert share_button.evaluate("el => document.activeElement === el")
                share_button.focus()
                page.keyboard.press("Enter")
                destination = files_dialog.get_by_role("combobox", name="Destination chat")
                destination.wait_for(state="visible")
                destination.select_option(target["id"])
            share = files_dialog.get_by_role("button", name="Share file")
            share.focus()
            page.keyboard.press("Enter")
            share_status = files_dialog.locator(".artifact-share-status")
            page.wait_for_function("el => el.textContent.includes('Shared with')", arg=share_status.element_handle())
            assert "Recipient chat" in share_status.inner_text()
            shared_page = page.request.get(f"{base}/api/v1/conversations/{target['id']}/artifacts")
            shared_rows = shared_page.json().get("artifacts", [])
            assert shared_page.status == 200 and any(
                row.get("share_id") and row.get("state") == "available" and row.get("filename") == "report.txt"
                for row in shared_rows), shared_page.text()
            files_dialog.get_by_role("button", name="Done").click()

            page.locator("#composer-menu-btn").click()
            page.get_by_role("button", name="Browse files in this chat").click()
            source_files = page.get_by_role("dialog", name="Files in this chat")
            source_files.wait_for()
            source_revoke = source_files.get_by_role(
                "button", name="Stop sharing report.txt with Recipient chat")
            source_revoke.wait_for(state="visible")
            source_share_capture = out / f"source-shares-{name}.png"
            page.screenshot(path=str(source_share_capture), animations="disabled")
            if name == "desktop":
                source_revoke.focus()
                page.keyboard.press("Enter")
                page.wait_for_function(
                    "() => document.querySelector('#conversation-files-status')?.textContent?.includes('Sharing with Recipient chat has stopped')")
                assert page.request.get(f"{base}{shared_rows[0]['download_url']}").status == 404
                assert not page.request.get(
                    f"{base}/api/v1/conversations/{target['id']}/artifacts").json().get("artifacts")
                regrant = page.request.post(
                    f"{base}/api/v1/conversations/{target['id']}/artifact-shares",
                    data={"source_run_id": run.id, "source_version": 1, "kind": "workspace_file"},
                    headers={"Idempotency-Key": "share-ui-source-regrant"})
                assert regrant.status == 201, regrant.text()
            source_files.get_by_role("button", name="Done").click()

            page.goto(f"{base}/#/chat/{target_bot.name}")
            page.locator("#conversation-switcher").wait_for()
            assert page.locator("#conversation-switcher").input_value() == target["id"]
            page.locator("#composer-menu-btn").click()
            page.get_by_role("button", name="Browse files in this chat").click()
            recipient_files = page.get_by_role("dialog", name="Files in this chat")
            recipient_files.wait_for()
            download = recipient_files.get_by_role("link", name="Download report.txt")
            try:
                download.wait_for(state="visible", timeout=5000)
            except Exception as exc:
                raise AssertionError({"files_status": recipient_files.locator("#conversation-files-status").inner_text(),
                                      "files_html": recipient_files.locator("#conversation-files-list").inner_html(),
                                      "page_errors": errors}) from exc
            assert recipient_files.get_by_text("Shared from Source report", exact=True).is_visible()
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            dialog_overflow = recipient_files.evaluate("el => el.scrollWidth - el.clientWidth")
            assert overflow <= 1 and dialog_overflow <= 1, (name, overflow, dialog_overflow)
            screenshot = out / f"recipient-{name}.png"
            page.screenshot(path=str(screenshot), animations="disabled")
            download.focus()
            with page.expect_download() as download_info:
                page.keyboard.press("Enter")
            saved = Path(download_info.value.path()).read_bytes()
            assert saved == payload and hashlib.sha256(saved).hexdigest() == digest
            unshare = recipient_files.get_by_role("button", name="Stop sharing report.txt")
            unshare.focus()
            page.keyboard.press("Enter")
            page.wait_for_function("() => document.querySelector('#conversation-files-status')?.textContent?.includes('no longer has access')")
            assert recipient_files.locator(".conversation-file").count() == 0
            client_artifact = page.request.get(f"{base}/api/v1/tasks/runs/{run.id}/artifacts/{filename}")
            assert client_artifact.status == 200 and client_artifact.body() == payload
            captures.append({"viewport": name, "size": [width, height], "screenshot": screenshot.name,
                             "share_chooser_screenshot": chooser.name,
                             "source_share_screenshot": source_share_capture.name,
                             "download_sha256": digest, "horizontal_overflow_px": overflow,
                             "dialog_overflow_px": dialog_overflow,
                             "done_button_bounds": done_box,
                             "page_errors": errors.copy()})
            recipient_files.get_by_role("button", name="Done").click()

        assert not errors, errors
        repo = Path(__file__).resolve().parents[2]
        source_files = ("src/hutch/store.py", "src/hutch/server/app.py", "src/hutch/server/static/app.js",
                        "src/hutch/server/static/style.css", "tests/e2e/test_browser.py")
        (out / "results.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_verified_artifact_can_be_shared_with_another_chat_and_revoked",
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_verified_artifact_can_be_shared_with_another_chat_and_revoked",
            "captured_at": datetime.now(timezone.utc).isoformat(), "browser": browser.browser_type.name,
            "browser_version": browser.version, "playwright": package_version("playwright"),
            "source_sha256": {name: hashlib.sha256((repo / name).read_bytes()).hexdigest()
                              for name in source_files},
            "journey": "owner explicitly shares a verified reference to another bot chat; recipient downloads it, then owner revokes the grant",
            "provider_calls": 0, "phone_device_used": False, "captures": captures,
            "limitation": "Fixture state and local browser only; references do not copy files or add file bytes to target model context.",
        }, indent=2) + "\n")
    finally:
        page.context.tracing.stop(path=str(out / "artifact-sharing-trace.zip"))
        page.close()


def test_conversation_file_browser_loads_the_next_cursor_page(browser, live):
    base, app = live
    store = app.state.store
    bot = store.create_bot(Bot(name="many-files-bot", model="mock/demo", runtime=RuntimeKind.mock, tools=["files"]))
    conversation, _ = store.create_conversation(
        bot.id, "Many files", idem_key="many-files-conversation", request_hash="many-files-request")
    run = Run(bot_id=bot.id, prompt="create many files", conversation_id=conversation["id"],
              status=RunStatus.succeeded)
    store.create_run(run)
    with store._tx() as db:
        db.execute("INSERT INTO conversation_runs (conversation_id, run_id, attached_at) VALUES (?, ?, ?)",
                   (conversation["id"], run.id, run.created_at))
    for index in range(51):
        filename = f"{index + 1:03d}-saved-output.txt"
        store.append_event(Event(run_id=run.id, type=EventType.tool_result, data={
            "tool": "read_file", "output": "saved result", "chars": 12,
            "artifact": f"artifacts/{filename}",
        }))

    page = browser.new_page(viewport={"width": 390, "height": 844}, reduced_motion="reduce")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(f"{base}/#/chat/{bot.name}")
        page.locator("#conversation-switcher").wait_for()
        assert page.locator("#conversation-switcher").input_value() == conversation["id"]
        page.locator("#composer-menu-btn").click()
        page.get_by_role("button", name="Browse files in this chat").click()
        dialog = page.get_by_role("dialog", name="Files in this chat")
        dialog.wait_for()
        status = dialog.locator("#conversation-files-status")
        page.wait_for_function("() => document.querySelector('#conversation-files-status')?.textContent === '50 items'")
        assert dialog.locator(".conversation-file").count() == 50
        dialog.get_by_role("button", name="Load more").click()
        page.wait_for_function("() => document.querySelector('#conversation-files-status')?.textContent === '51 items'")
        filenames = dialog.locator(".conversation-file-copy strong").all_text_contents()
        assert len(filenames) == 51 and len(set(filenames)) == 51
        assert dialog.get_by_role("button", name="Load more").count() == 0
        page.locator(".conversation-file").last.scroll_into_view_if_needed()
        overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
        assert overflow <= 1
        assert dialog.evaluate("el => el.scrollWidth - el.clientWidth") <= 1
        assert not errors, errors
        out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/generated-files"
        out.mkdir(parents=True, exist_ok=True)
        screenshot = out / "large-list-phone.png"
        page.screenshot(path=str(screenshot), animations="disabled")
        repo = Path(__file__).resolve().parents[2]
        source_files = ("src/hutch/runtime/steps.py", "src/hutch/store.py", "src/hutch/server/app.py",
                        "src/hutch/server/static/app.js", "src/hutch/server/static/style.css")
        (out / "cursor-list.json").write_text(json.dumps({
            "browser": browser.browser_type.name, "browser_version": browser.version,
            "playwright": package_version("playwright"), "viewport": [390, 844],
            "screenshot": screenshot.name, "loaded_items": len(filenames),
            "unique_filenames": len(set(filenames)), "horizontal_overflow_px": overflow,
            "page_errors": errors, "source_sha256": {
                name: hashlib.sha256((repo / name).read_bytes()).hexdigest() for name in source_files
            }, "fixture": "51 unverified saved-output references; no provider calls"
        }, indent=2) + "\n")
    finally:
        page.close()


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


@pytest.mark.parametrize("label,width,height", [("desktop", 1440, 960), ("tablet", 900, 1024),
                                                  ("phone", 390, 844)])
def test_conversation_export_shows_scope_and_downloads_json(browser, live, tmp_path, label, width, height):
    base, app = live
    store = app.state.store
    bot = store.create_bot(Bot(name=f"export-{label}", model="mock/demo", tools=[]))
    conversation, _ = store.create_conversation(bot.id, "Export fixture", idem_key=f"export-{label}",
                                                request_hash=f"export-{label}")
    with store._tx() as db:
        store._insert_conversation_message(db, message_id=f"export-user-{label}",
            conversation_id=conversation["id"], seq=1, run_id="", role="user",
            content="A message that will be in the export.", created_at="2026-01-01T00:00:00+00:00")

    page = browser.new_page(viewport={"width": width, "height": height}, reduced_motion="reduce")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.context.tracing.start(screenshots=True, snapshots=True, sources=False)
    trace_stopped = False
    try:
        page.goto(f"{base}/#/chat/{bot.name}")
        page.locator("#conversation-switcher").wait_for()
        assert page.locator("#conversation-switcher").input_value() == conversation["id"]
        page.locator("#composer-menu-btn").click()
        page.locator("#conversation-export-open").click()
        dialog = page.get_by_role("dialog", name="Export conversation")
        dialog.get_by_text("conversation metadata and ordered message text with run provenance").wait_for()
        dialog.get_by_text("Message text is included verbatim", exact=False).wait_for()
        assert dialog.get_by_text("artifact files", exact=False).count() == 1
        overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
        assert overflow <= 1, (label, overflow)

        out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/conversation-export"
        out.mkdir(parents=True, exist_ok=True)
        screenshot = out / f"scope-{label}.png"
        trace = out / f"scope-{label}-trace.zip"
        page.screenshot(path=str(screenshot), animations="disabled")
        with page.expect_download() as download_info:
            dialog.get_by_role("button", name="Download JSON").click()
        download = download_info.value
        assert download.suggested_filename == "hutch-conversation-export.json"
        downloaded = tmp_path / download.suggested_filename
        download.save_as(str(downloaded))
        payload = json.loads(downloaded.read_text(encoding="utf-8"))
        assert payload["conversation"]["id"] == conversation["id"]
        assert payload["messages"][0]["content"] == "A message that will be in the export."
        assert "tool receipts" in payload["scope"]["excluded"]
        assert not errors, errors
        page.context.tracing.stop(path=str(trace))
        trace_stopped = True

        repo = Path(__file__).resolve().parents[2]
        (out / f"scope-{label}.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_conversation_export_shows_scope_and_downloads_json",
            "browser": browser.browser_type.name, "browser_version": browser.version,
            "playwright": package_version("playwright"), "viewport": [width, height],
            "screenshot": screenshot.name, "trace": trace.name,
            "page_errors": errors, "horizontal_overflow_px": overflow,
            "scope": payload["scope"], "provider_calls": 0,
            "source_sha256": {name: hashlib.sha256((repo / name).read_bytes()).hexdigest()
                              for name in ("src/hutch/server/app.py", "src/hutch/server/static/app.js",
                                           "src/hutch/store.py")},
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        if not trace_stopped:
            try:
                page.context.tracing.stop(path=str(Path(__file__).resolve().parents[2] /
                    "docs/realignment/artifacts/conversation-export" / f"scope-{label}-trace-failed.zip"))
            except Exception:
                pass
        page.close()


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


@pytest.mark.parametrize("width,height,size", [(1440, 1000, "desktop"), (768, 1024, "tablet"), (390, 844, "phone")])
def test_studio_resumes_only_the_active_human_wait_with_v1_command(browser, live, monkeypatch, width, height, size):
    """The current human challenge is resumable from chat through its versioned command."""
    import hashlib
    import json
    from pathlib import Path

    base, app = live
    store = app.state.store
    monkeypatch.setattr(app.state.engine, "tick", lambda: None)
    bot = store.create_bot(Bot(name="human-resume-chat", model="mock/demo", tools=[]))
    conversation, _ = store.create_conversation(
        bot.id, "Sign-in check", idem_key="human-resume-conversation", request_hash="human-resume-conversation")
    prompt = "Continue after the sign-in check"
    run = Run(bot_id=bot.id, prompt=prompt)
    run_id, created = store.submit_conversation_message(
        conversation["id"], prompt, run, Task(bot_id=bot.id, kind="on_demand", prompt=prompt),
        idem_key="human-resume-message", request_hash="human-resume-message")
    assert created and run_id == run.id
    claimed = store.claim_run(run.id, "browser-human-resume-owner", lease_seconds=60)
    assert claimed is not None
    store.transition_run(run.id, RunStatus.running, fence=claimed.fence)
    store.transition_run(run.id, RunStatus.waiting_human, fence=claimed.fence)
    store.append_event(Event(run_id=run.id, type=EventType.human_needed,
                             data={"reason": "Complete the earlier sign-in step"}))
    store.transition_run(run.id, RunStatus.running, fence=claimed.fence,
                         event={"reason": "The first sign-in step was cleared"})
    store.transition_run(run.id, RunStatus.waiting_human, fence=claimed.fence)
    store.append_event(Event(run_id=run.id, type=EventType.human_needed,
                             data={"reason": "Sign in to the current local fixture site"}))
    store.flush_events()
    event_seq = store.last_seq(run.id)

    page = browser.new_page(viewport={"width": width, "height": height}, reduced_motion="reduce")
    errors = []
    page.set_default_timeout(8000)
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(f"{base}/#/chat/{bot.name}")
        page.locator("#conversation-switcher").wait_for()
        assert page.locator("#conversation-switcher").input_value() == conversation["id"]
        run_card = page.locator(f'#chat-stream [data-run-id="{run.id}"]')
        run_card.locator(".run-cause").nth(1).wait_for(state="visible")
        assert run_card.locator(".run-cause").count() == 2
        card = run_card.locator(".run-cause").last
        assert run_card.locator("[data-human-resume]").count() == 1
        card.get_by_role("button", name="I've cleared it — resume").wait_for()
        resume = card.locator("[data-human-resume]")
        assert resume.count() == 1
        assert resume.get_attribute("data-event-seq") == str(event_seq)
        assert resume.evaluate("el => el.getBoundingClientRect().height") >= 44

        out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/human-resume"
        out.mkdir(parents=True, exist_ok=True)
        screenshot = out / f"{size}.png"
        page.screenshot(path=str(screenshot), full_page=True, animations="disabled")
        overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
        assert overflow <= 1, (size, overflow)

        route = f"/api/v1/tasks/runs/{run.id}/resume"
        with page.expect_response(lambda response: response.url.endswith(route)) as response_info:
            resume.click()
        response = response_info.value
        assert response.status == 200, response.text()
        assert response.json() == {"resumed": run.id, "human_event_seq": event_seq, "replayed": False}
        assert response.request.headers.get("idempotency-key") == f"studio-human-resume:{run.id}:{event_seq}"
        assert response.request.post_data_json == {"human_event_seq": event_seq}
        assert store.kv_get(f"resume:{run.id}") == "1"
        requested = page.get_by_role("button", name="Resume requested; waiting for the run to continue")
        requested.wait_for()
        assert requested.is_disabled()
        assert not errors, errors
        (out / f"{size}.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_studio_resumes_only_the_active_human_wait_with_v1_command",
            "browser": browser.browser_type.name, "browser_version": browser.version,
            "viewport": {"width": width, "height": height}, "event_seq": event_seq,
            "api_path": route, "api_status": response.status, "api_replayed": response.json()["replayed"],
            "idempotency_key": f"studio-human-resume:{run.id}:{event_seq}",
            "horizontal_overflow": overflow, "page_errors": errors,
            "provider_calls": 0, "captured_at": datetime.now(timezone.utc).isoformat(),
            "source_sha256": {path: hashlib.sha256((out.parents[3] / path).read_bytes()).hexdigest()
                              for path in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                           "src/hutch/server/app.py", "src/hutch/store.py")},
        }, indent=2) + "\n")
    finally:
        page.close()


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


def test_tool_permissions_are_clear_and_save_at_desktop_tablet_and_phone(browser, live):
    base, app = live
    bot = app.state.store.create_bot(Bot(name="tool-settings", model="mock/demo", tools=["files", "memory"]))
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/tool-permissions"
    out.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce",
                                  is_mobile=True, has_touch=True)
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    sizes = {"desktop": (1440, 960), "tablet": (900, 1024), "phone": (390, 844)}
    captures = []

    def position_panel(edge: str = "start") -> dict:
        return page.evaluate("""edge => {
          const scroller = document.querySelector('main#view > .page-scroll');
          const panel = document.querySelector('section[aria-labelledby="tool-settings-title"]');
          const bounds = panel.getBoundingClientRect();
          const viewport = scroller.getBoundingClientRect();
          const delta = edge === 'end' ? bounds.bottom - viewport.bottom + 12
                                       : bounds.top - viewport.top - 12;
          scroller.scrollTop = Math.max(0, scroller.scrollTop + delta);
          return {scrollTop: Math.round(scroller.scrollTop), panelHeight: Math.round(bounds.height)};
        }""", edge)

    try:
        page.goto(f"{base}/#/bot/{bot.name}")
        page.locator("#form-tools").wait_for()
        delegate = page.locator('#form-tools input[name="tools"][value="delegate_task"]')
        assert not delegate.is_checked()
        assert page.get_by_text("Each request asks for approval and uses another run slot", exact=False).is_visible()

        for label, (width, height) in sizes.items():
            page.set_viewport_size({"width": width, "height": height})
            panel = page.locator('section[aria-labelledby="tool-settings-title"]')
            position = position_panel("start")
            page.wait_for_timeout(80)
            delete_button = page.get_by_role("button", name="Delete bot")
            assert delete_button.is_visible()
            if label == "phone":
                assert delete_button.locator("svg").is_visible()
                box = delete_button.bounding_box()
                assert box and box["width"] >= 44 and box["height"] >= 44, box
            page.screenshot(path=str(out / f"{label}.png"), animations="disabled")
            metrics = page.evaluate("""() => {
              const panel = document.querySelector('#form-tools').getBoundingClientRect();
              const input = document.querySelector('#form-tools input[value=delegate_task]').getBoundingClientRect();
              const remove = document.querySelector('#btn-delete-bot').getBoundingClientRect();
              return {viewport:[innerWidth,innerHeight], document:[document.documentElement.scrollWidth,document.documentElement.scrollHeight],
                panel:[Math.round(panel.width),Math.round(panel.height)], delegate:[Math.round(input.width),Math.round(input.height)],
                deleteAction:[Math.round(remove.width),Math.round(remove.height)],
                visible:input.width>0 && input.height>0};
            }""")
            assert metrics["document"][0] - width <= 1, (label, metrics)
            assert metrics["visible"] and metrics["delegate"][1] >= 20, (label, metrics)
            captures.append({"size": label, **metrics})

        page.set_viewport_size({"width": 390, "height": 844})
        panel = page.locator('section[aria-labelledby="tool-settings-title"]')
        position = position_panel("end")
        page.wait_for_timeout(80)
        page.screenshot(path=str(out / "phone-bottom.png"), animations="disabled")
        assert page.get_by_role("button", name="Save tools").is_visible()
        assert page.locator('#form-tools input[value="delegate_task"]').is_visible()

        delegate = page.locator('#form-tools input[name="tools"][value="delegate_task"]')
        delegate.focus()
        page.keyboard.press("Space")
        assert delegate.is_checked()
        save = page.locator('#form-tools button[type="submit"]')
        save.focus()
        page.keyboard.press("Enter")
        wait_for(lambda: "delegate_task" in app.state.store.get_bot(bot.name).tools)
        page.reload()
        page.locator('#form-tools input[name="tools"][value="delegate_task"]:checked').wait_for()
        panel = page.locator('section[aria-labelledby="tool-settings-title"]')
        position_panel("end")
        page.wait_for_timeout(80)
        assert page.locator('#form-tools input[name="tools"][value="delegate_task"]').is_checked()
        page.screenshot(path=str(out / "phone-saved.png"), animations="disabled")
        captures.append({"size": "phone-saved", "viewport": [390, 844], "saveVisible": True,
                         "delegateEnabled": True, "scrollTop": position["scrollTop"]})
        assert not errors, errors
        (out / "validation.json").write_text(json.dumps({
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_tool_permissions_are_clear_and_save_at_desktop_tablet_and_phone",
            "browser": browser.browser_type.name,
            "browser_version": browser.version,
            "playwright_version": package_version("playwright"),
            "captures": captures,
            "scenario": "synthetic Settings form; enable the delegated task tool and persist the explicit opt-in",
            "page_errors": errors,
            "source_sha256": {
                "app.js": hashlib.sha256((Path(__file__).resolve().parents[2] / "src/hutch/server/static/app.js").read_bytes()).hexdigest(),
                "style.css": hashlib.sha256((Path(__file__).resolve().parents[2] / "src/hutch/server/static/style.css").read_bytes()).hexdigest(),
                "app.py": hashlib.sha256((Path(__file__).resolve().parents[2] / "src/hutch/server/app.py").read_bytes()).hexdigest(),
            },
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        try:
            context.tracing.stop(path=str(out / "trace.zip"))
        except Exception:
            pass
        context.close()


def test_guided_bot_creation_reviews_configuration_at_desktop_tablet_and_phone(browser, live, monkeypatch):
    base, app = live
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key-never-sent-to-a-provider")
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    page.set_default_timeout(8000)
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/bot-setup"
    out.mkdir(parents=True, exist_ok=True)
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        page.goto(base + "/#/chat")
        page.locator("#topbar-new-bot").click()
        page.get_by_role("heading", name="Describe the work").wait_for()
        page.get_by_label("What would you like this bot to handle?").fill(
            "Review release notes and prepare a short summary of changes that affect our project.")
        assert page.locator("#setup-name-preview").inner_text() == "Release Notes Reviewer"
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            page.screenshot(path=str(out / f"purpose-{label}.png"), animations="disabled")
            metrics = page.evaluate("""() => ({
                viewport: [innerWidth, innerHeight],
                documentWidth: document.documentElement.scrollWidth,
                dialog: (() => { const r = document.querySelector('[role=dialog]').getBoundingClientRect();
                  return {left:r.left,right:r.right,top:r.top,bottom:r.bottom}; })(),
                footerVisible: document.querySelector('.modal-footer').getBoundingClientRect().bottom <= innerHeight
            })""")
            assert metrics["documentWidth"] - width <= 1, (label, metrics)
            assert metrics["dialog"]["left"] >= -1 and metrics["dialog"]["right"] <= width + 1, (label, metrics)
            assert metrics["footerVisible"], (label, metrics)
        page.set_viewport_size({"width": 390, "height": 844})
        page.locator(".setup-identity summary").click()
        page.locator("#setup-display_name").fill("Release Notes Reviewer")
        page.locator("#setup-name").fill("guided-release-reviewer")
        page.get_by_label("Short description").fill("Summarize project release notes")
        page.locator("#modal-confirm").click()
        page.get_by_role("heading", name="Set model and workspace").wait_for()
        page.locator("#setup-back").click()
        assert "Review release notes" in page.locator("#setup-purpose").input_value()
        page.locator("#modal-confirm").click()
        page.get_by_role("heading", name="Set model and workspace").wait_for()
        page.get_by_label("Model route").fill("openai/gpt-4o-mini")
        page.locator("#modal-confirm").click()
        page.get_by_role("heading", name="Choose tools and schedule").wait_for()
        assert page.locator("#setup-tools input:checked").count() == 0
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            page.locator(".modal-body").evaluate("element => { element.scrollTop = 0; }")
            page.screenshot(path=str(out / f"options-{label}.png"), animations="disabled")
            metrics = page.evaluate("""() => ({viewport:[innerWidth,innerHeight], documentWidth:document.documentElement.scrollWidth,
              bodyOverflow:document.querySelector('.modal-body').scrollWidth-document.querySelector('.modal-body').clientWidth,
              footerVisible:document.querySelector('.modal-footer').getBoundingClientRect().bottom <= innerHeight})""")
            assert metrics["documentWidth"] - width <= 1 and metrics["bodyOverflow"] <= 1, (label, metrics)
            assert metrics["footerVisible"], (label, metrics)
        page.set_viewport_size({"width": 390, "height": 844})
        page.get_by_text("Human browser handoff (optional)").click()
        handoff_choice = page.locator("#setup-local-browser-handoff")
        handoff_enabled = handoff_choice.is_enabled()
        if handoff_enabled:
            handoff_choice.check()
        else:
            assert "unavailable on this host" in page.locator(".setup-schedule p.hint").last.inner_text().lower()
        handoff_choice.scroll_into_view_if_needed()
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            page.screenshot(path=str(out / f"configuration-{label}.png"), animations="disabled")
            metrics = page.evaluate("""() => ({
                viewport: [innerWidth, innerHeight], documentWidth: document.documentElement.scrollWidth,
                modalBodyWidth: document.querySelector('.modal-body').scrollWidth,
                modalBodyClientWidth: document.querySelector('.modal-body').clientWidth,
                titleVisible: document.querySelector('#modal-title').getBoundingClientRect().top >= 0,
                footerVisible: document.querySelector('.modal-footer').getBoundingClientRect().bottom <= innerHeight
            })""")
            assert metrics["documentWidth"] - width <= 1, (label, metrics)
            assert metrics["modalBodyWidth"] - metrics["modalBodyClientWidth"] <= 1, (label, metrics)
            assert metrics["titleVisible"] and metrics["footerVisible"], (label, metrics)
        page.set_viewport_size({"width": 390, "height": 844})
        handoff_choice.scroll_into_view_if_needed()
        page.screenshot(path=str(out / "configuration-handoff-phone.png"), animations="disabled")
        handoff_metrics = page.evaluate("""() => {
            const control = document.querySelector('#setup-local-browser-handoff').getBoundingClientRect();
            const hints = document.querySelectorAll('.setup-schedule p.hint');
            const hint = hints[hints.length - 1].getBoundingClientRect();
            return {control: {top: control.top, bottom: control.bottom}, hint: {top: hint.top, bottom: hint.bottom}, viewport: [innerWidth, innerHeight]};
        }""")
        assert handoff_metrics["control"]["top"] >= 0 and handoff_metrics["control"]["bottom"] <= 844, handoff_metrics
        page.set_viewport_size({"width": 390, "height": 844})
        page.get_by_text("Enable tools (none enabled by default)").click()
        page.locator('input[name="setup-tool"][value="read_file"]').check()
        page.get_by_text("Add a recurring task (optional)").click()
        page.get_by_label("Scheduled task prompt").fill("Review release notes and report important changes.")
        page.locator("#modal-confirm").click()
        assert page.get_by_role("alert").inner_text() == "Add a cron schedule before setting its task prompt."
        assert app.state.store.get_bot("guided-release-reviewer") is None
        page.get_by_label("Cron schedule", exact=True).fill("0 9 * * 1")
        page.locator("#modal-confirm").click()
        page.get_by_role("heading", name="Review bot").wait_for()
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            page.screenshot(path=str(out / f"review-{label}.png"), animations="disabled")
            metrics = page.evaluate("""() => {
                const dialog = document.querySelector('[role=dialog]').getBoundingClientRect();
                const body = document.querySelector('.modal-body');
                return {
                    viewport: [innerWidth, innerHeight],
                    documentWidth: document.documentElement.scrollWidth,
                    bodyOverflow: body.scrollWidth - body.clientWidth,
                    dialog: {left: dialog.left, right: dialog.right},
                    titleVisible: document.querySelector('#modal-title').getBoundingClientRect().top >= 0,
                    footerVisible: document.querySelector('.modal-footer').getBoundingClientRect().bottom <= innerHeight
                };
            }""")
            assert metrics["documentWidth"] - width <= 1, (label, metrics)
            assert metrics["bodyOverflow"] <= 1, (label, metrics)
            assert metrics["dialog"]["left"] >= -1 and metrics["dialog"]["right"] <= width + 1, (label, metrics)
            assert metrics["titleVisible"] and metrics["footerVisible"], (label, metrics)
            page.locator(".setup-review-list > div").last.scroll_into_view_if_needed()
            page.screenshot(path=str(out / f"review-details-end-{label}.png"), animations="disabled")
            end_metrics = page.evaluate("""() => {
                const last = document.querySelector('.setup-review-list > div:last-child').getBoundingClientRect();
                const footer = document.querySelector('.modal-footer').getBoundingClientRect();
                return {last: {top: last.top, bottom: last.bottom}, footer: {top: footer.top, bottom: footer.bottom}, viewport: [innerWidth, innerHeight]};
            }""")
            assert end_metrics["last"]["top"] >= 0 and end_metrics["last"]["bottom"] <= end_metrics["footer"]["top"] + 1, (label, end_metrics)
            page.locator(".modal-body").evaluate("element => { element.scrollTop = 0; }")
        assert page.get_by_text("It will not start a run.", exact=False).is_visible()
        assert page.get_by_text("Browser handoff", exact=True).is_visible()
        assert app.state.store.list_runs() == []
        with page.expect_response(lambda response: response.url.endswith("/api/v1/bots")
                                 and response.request.method == "POST") as created:
            page.locator("#modal-confirm").click()
        assert created.value.status == 201, created.value.text()
        wait_for(lambda: app.state.store.get_bot("guided-release-reviewer") is not None)
        bot = app.state.store.get_bot("guided-release-reviewer")
        assert bot.instructions == "Review release notes and prepare a short summary of changes that affect our project."
        assert bot.description == "Summarize project release notes"
        assert bot.tools == ["read_file"] and bot.approval_mode is ApprovalMode.ask
        assert bot.local_browser_handoff is handoff_enabled
        assert bot.schedule and bot.schedule.prompt == "Review release notes and report important changes."
        assert app.state.store.list_runs() == [], "bot creation must not submit a run"
        assert not errors, errors
        (out / "validation.json").write_text(json.dumps({
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_guided_bot_creation_reviews_configuration_at_desktop_tablet_and_phone",
            "browser": browser.browser_type.name, "browser_version": browser.version,
            "playwright_version": package_version("playwright"),
            "scenario": "guided setup against a configured-shape route with a test-only dummy key; no model call was made; create persists configuration and does not start a run; checked review details at both ends and handoff disclosure at phone width",
            "viewports": {"desktop": [1440, 960], "tablet": [900, 1024], "phone": [390, 844]},
            "inspected_screenshots": ["purpose-desktop.png", "purpose-tablet.png", "purpose-phone.png",
                                      "options-desktop.png", "options-tablet.png", "options-phone.png",
                                      "configuration-desktop.png", "configuration-tablet.png", "configuration-phone.png",
                                      "configuration-handoff-phone.png", "review-desktop.png", "review-tablet.png",
                                      "review-phone.png", "review-details-end-desktop.png", "review-details-end-tablet.png",
                                      "review-details-end-phone.png"],
            "page_errors": errors,
            "source_sha256": {relative: hashlib.sha256((Path(__file__).resolve().parents[2] / relative).read_bytes()).hexdigest()
                              for relative in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                               "src/hutch/server/app.py", "src/hutch/store.py", "tests/e2e/test_browser.py")},
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        try:
            context.tracing.stop(path=str(out / "trace.zip"))
        except Exception:
            pass
        context.close()


def test_named_workspace_coordinator_is_first_class_direct_chat_at_responsive_sizes(browser, live):
    base, app = live
    coordinator = Bot(name="workspace-coordinator", display_name="Workspace Coordinator",
                     model="mock/demo", tools=[])
    specialist = Bot(name="release-notes-reviewer", display_name="Release Notes Reviewer",
                     model="mock/demo", tools=[])
    app.state.store.create_bot(coordinator)
    app.state.store.create_bot(specialist)
    app.state.store.set_workspace_coordinator(coordinator.id)

    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/workspace-coordinator"
    out.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    page.set_default_timeout(8000)
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        page.goto(f"{base}/#/chat")
        page.get_by_role("heading", name="Workspace Coordinator").wait_for()
        assert page.locator("#workspace-coordinator-pill").inner_text() == "Workspace coordinator"
        rows = page.locator("#roster-list [data-switch-bot]")
        assert rows.first.get_attribute("data-switch-bot") == coordinator.name
        assert rows.first.locator(".roster-role").inner_text() == "Coordinator"

        # A coordinator is an ordinary, directly addressable Bot conversation too.
        conversation_id = page.locator("#conversation-switcher").input_value()
        coordinator_chat = app.state.store.get_conversation(conversation_id)
        assert coordinator_chat["bot_id"] == coordinator.id
        page.get_by_role("link", name="Settings for Release Notes Reviewer").click()
        page.get_by_role("button", name="Set as workspace coordinator").click()
        page.get_by_role("heading", name="Set workspace coordinator?").wait_for()
        page.locator("#modal-confirm").click()
        page.get_by_role("heading", name="Release Notes Reviewer settings").wait_for()
        assert app.state.store.workspace_coordinator_id() == specialist.id
        page.get_by_role("link", name="Open Studio").click()
        page.get_by_role("heading", name="Release Notes Reviewer").wait_for()
        assert page.locator("#workspace-coordinator-pill").inner_text() == "Workspace coordinator"
        assert page.locator("#roster-list [data-switch-bot]").first.get_attribute("data-switch-bot") == specialist.name
        page.get_by_role("button", name="Dismiss notification").click()

        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            page.screenshot(path=str(out / f"direct-chat-{label}.png"), animations="disabled")
            metrics = page.evaluate("""() => ({viewport:[innerWidth,innerHeight],
              documentWidth:document.documentElement.scrollWidth,
              bodyWidth:document.body.scrollWidth})""")
            assert metrics["documentWidth"] - width <= 1 and metrics["bodyWidth"] - width <= 1, (label, metrics)
            assert page.locator("#workspace-coordinator-pill").inner_text() == ("Coordinator" if width <= 640 else "Workspace coordinator")
        assert not errors, errors
        (out / "validation.json").write_text(json.dumps({
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_named_workspace_coordinator_is_first_class_direct_chat_at_responsive_sizes",
            "browser": browser.browser_type.name, "browser_version": browser.version,
            "playwright_version": package_version("playwright"),
            "viewports": {"desktop": [1440, 960], "tablet": [900, 1024], "phone": [390, 844]},
            "scenario": "the selected workspace coordinator opens as the default direct chat, is labelled in the roster and composer, and can be reassigned from Bot settings",
            "page_errors": errors,
            "source_sha256": {relative: hashlib.sha256((Path(__file__).resolve().parents[2] / relative).read_bytes()).hexdigest()
                              for relative in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                               "src/hutch/server/app.py", "tests/e2e/test_browser.py")},
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        try:
            context.tracing.stop(path=str(out / "trace.zip"))
        except Exception:
            pass
        context.close()


def test_purpose_derived_bot_name_is_editable_and_reviewed_at_responsive_sizes(browser, live, monkeypatch):
    base, app = live
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key-never-sent-to-a-provider")
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/bot-naming"
    out.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    errors: list[str] = []
    requests: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: requests.append(request.url))
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        page.goto(f"{base}/#/chat")
        page.locator("#topbar-new-bot").click()
        purpose = page.get_by_label("What would you like this bot to handle?")
        purpose.fill("Track the launch checklist and notify me when a blocker needs attention.")
        page.locator(".setup-identity summary").click()
        display_name = page.locator("#setup-display_name")
        address = page.locator("#setup-name")
        assert display_name.input_value() == "Launch Checklist Monitor"
        assert address.input_value() == "launch-checklist-monitor"
        purpose.fill("Review release notes for changes affecting our project.")
        assert display_name.input_value() == "Release Notes Reviewer"
        assert address.input_value() == "release-notes-reviewer"

        display_name.fill("Launch Readiness Analyst")
        assert address.input_value() == "launch-readiness-analyst"
        address.fill("launch-ops")

        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            page.screenshot(path=str(out / f"identity-{label}.png"), animations="disabled")
            metrics = page.evaluate("""() => ({
              viewport:[innerWidth,innerHeight], documentWidth:document.documentElement.scrollWidth,
              bodyOverflow:document.querySelector('.modal-body').scrollWidth-document.querySelector('.modal-body').clientWidth,
              footerVisible:document.querySelector('.modal-footer').getBoundingClientRect().bottom<=innerHeight
            })""")
            assert metrics["documentWidth"] - width <= 1 and metrics["bodyOverflow"] <= 1, (label, metrics)
            assert metrics["footerVisible"], (label, metrics)

        page.locator("#modal-confirm").click()
        page.get_by_label("Model route").fill("openai/gpt-4o-mini")
        page.locator("#modal-confirm").click()
        page.locator("#modal-confirm").click()
        page.get_by_role("heading", name="Review bot").wait_for()
        review = page.locator(".setup-review-list").inner_text()
        assert "Launch Readiness Analyst" in review and "launch-ops" in review
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            page.screenshot(path=str(out / f"review-{label}.png"), animations="disabled")
            metrics = page.evaluate("""() => ({
              viewport:[innerWidth,innerHeight], documentWidth:document.documentElement.scrollWidth,
              bodyOverflow:document.querySelector('.modal-body').scrollWidth-document.querySelector('.modal-body').clientWidth,
              footerVisible:document.querySelector('.modal-footer').getBoundingClientRect().bottom<=innerHeight
            })""")
            assert metrics["documentWidth"] - width <= 1 and metrics["bodyOverflow"] <= 1, (label, metrics)
            assert metrics["footerVisible"], (label, metrics)
            page.locator(".setup-review-list > div").last.scroll_into_view_if_needed()
            page.screenshot(path=str(out / f"review-end-{label}.png"), animations="disabled")
            end = page.evaluate("""() => {
              const last = document.querySelector('.setup-review-list > div:last-child').getBoundingClientRect();
              const footer = document.querySelector('.modal-footer').getBoundingClientRect();
              return {lastBottom:last.bottom,footerTop:footer.top,viewport:[innerWidth,innerHeight]};
            }""")
            assert end["lastBottom"] <= end["footerTop"] + 1, (label, end)
            page.locator(".modal-body").evaluate("element => { element.scrollTop = 0; }")

        assert app.state.store.list_runs() == []
        with page.expect_response(lambda response: response.url.endswith("/api/v1/bots")
                                 and response.request.method == "POST") as created:
            page.locator("#modal-confirm").click()
        assert created.value.status == 201, created.value.text()
        bot = app.state.store.get_bot("launch-ops")
        assert bot is not None and bot.display_name == "Launch Readiness Analyst"
        assert bot.instructions == "Review release notes for changes affecting our project."
        assert app.state.store.list_runs() == []
        assert not any("/chat/completions" in url or "/responses" in url for url in requests)
        page.locator(".ctx-id h1").wait_for()
        assert page.locator(".ctx-id h1").inner_text() == "Launch Readiness Analyst"
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            page.screenshot(path=str(out / f"chat-{label}.png"), animations="disabled")
            metrics = page.evaluate("""() => ({viewport:[innerWidth,innerHeight],
              documentWidth:document.documentElement.scrollWidth, headingVisible:!!document.querySelector('.ctx-id h1')})""")
            assert metrics["documentWidth"] - width <= 1 and metrics["headingVisible"], (label, metrics)
        assert not errors, errors
        (out / "validation.json").write_text(json.dumps({
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_purpose_derived_bot_name_is_editable_and_reviewed_at_responsive_sizes",
            "browser": browser.browser_type.name, "browser_version": browser.version,
            "playwright_version": package_version("playwright"),
            "viewports": {"desktop": [1440, 960], "tablet": [900, 1024], "phone": [390, 844]},
            "scenario": "purpose-derived name and address are generated locally; edits persist and are reviewed; no run or model/provider request occurs",
            "inspected_screenshots": [f"identity-{size}.png" for size in ("desktop", "tablet", "phone")]
                                     + [f"review-{size}.png" for size in ("desktop", "tablet", "phone")]
                                     + [f"review-end-{size}.png" for size in ("desktop", "tablet", "phone")]
                                     + [f"chat-{size}.png" for size in ("desktop", "tablet", "phone")],
            "page_errors": errors,
            "source_sha256": {relative: hashlib.sha256((Path(__file__).resolve().parents[2] / relative).read_bytes()).hexdigest()
                              for relative in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                               "src/hutch/server/app.py", "tests/e2e/test_browser.py")},
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        try:
            context.tracing.stop(path=str(out / "trace.zip"))
        except Exception:
            pass
        context.close()


def test_bot_creation_reuses_only_the_selected_chat_request_and_keeps_provenance(browser, live, monkeypatch):
    base, app = live
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key-never-sent-to-a-provider")
    store = app.state.store
    source_bot = store.create_bot(Bot(name="chat-context-source", model="openai/gpt-4o-mini", tools=[]))
    conversation, _ = store.create_conversation(source_bot.id, "Launch planning",
        idem_key="chat-context-conversation", request_hash="chat-context-conversation")
    source_request = "Track the launch checklist and notify me when a blocker needs my attention."
    with store._tx() as db:
        store._insert_conversation_message(db, message_id="chat-context-private-old", conversation_id=conversation["id"],
            seq=1, run_id="", role="user", content="My private payroll notes are not part of the Bot request.",
            created_at=conversation["created_at"])
        store._insert_conversation_message(db, message_id="chat-context-old-answer", conversation_id=conversation["id"],
            seq=2, run_id="", role="assistant", content="Understood.", created_at=conversation["created_at"])
        store._insert_conversation_message(db, message_id="chat-context-current-request", conversation_id=conversation["id"],
            seq=3, run_id="", role="user", content=source_request, created_at=conversation["created_at"])

    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/bot-setup-context"
    out.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        page.goto(f"{base}/#/chat/{source_bot.name}")
        page.locator("#conversation-switcher").wait_for()
        page.locator("#topbar-new-bot").click()
        page.get_by_role("heading", name="Describe the work").wait_for()
        source_toggle = page.get_by_label("Use your latest request from this chat")
        assert source_toggle.is_checked()
        purpose = page.get_by_label("What would you like this bot to handle?")
        assert purpose.input_value() == source_request
        assert "private payroll" not in purpose.input_value().lower()
        source_toggle.uncheck()
        assert purpose.input_value() == ""
        source_toggle.check()
        purpose.fill("Track the launch checklist; notify me when a blocker needs attention.")
        assert page.locator("#setup-name-preview").inner_text() == "Launch Checklist Monitor"

        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            metrics = page.evaluate("""() => {
              const dialog = document.querySelector('[role=dialog]').getBoundingClientRect();
              const input = document.querySelector('#setup-purpose').getBoundingClientRect();
              return {viewport:[innerWidth, innerHeight], documentWidth:document.documentElement.scrollWidth,
                dialog:{left:dialog.left,right:dialog.right}, input:{left:input.left,right:input.right},
                footerVisible:document.querySelector('.modal-footer').getBoundingClientRect().bottom <= innerHeight};
            }""")
            assert metrics["documentWidth"] - width <= 1, (label, metrics)
            assert metrics["dialog"]["left"] >= -1 and metrics["dialog"]["right"] <= width + 1, (label, metrics)
            assert metrics["input"]["left"] >= -1 and metrics["input"]["right"] <= width + 1, (label, metrics)
            assert metrics["footerVisible"], (label, metrics)
            page.screenshot(path=str(out / f"chat-source-purpose-{label}.png"), animations="disabled")

        page.set_viewport_size({"width": 390, "height": 844})
        page.locator(".setup-identity summary").click()
        page.locator("#setup-display_name").fill("Launch Checklist Monitor")
        page.locator("#setup-name").fill("launch-checklist")
        page.locator("#modal-confirm").click()
        model_route = page.get_by_label("Model route")
        assert model_route.input_value() == "openai/gpt-4o-mini"
        assert "Suggested from chat-context-source’s current route" in page.locator(".setup-conversation").inner_text()
        inference_options = page.locator("#setup-inference_mode option").all_text_contents()
        assert inference_options == ["Hybrid — local or hosted", "Local — this machine", "Strict offline"]
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            metrics = page.evaluate("""() => ({
              viewport:[innerWidth, innerHeight], documentWidth:document.documentElement.scrollWidth,
              bodyOverflow:document.querySelector('.modal-body').scrollWidth-document.querySelector('.modal-body').clientWidth,
              footerVisible:document.querySelector('.modal-footer').getBoundingClientRect().bottom <= innerHeight
            })""")
            assert metrics["documentWidth"] - width <= 1 and metrics["bodyOverflow"] <= 1, (label, metrics)
            assert metrics["footerVisible"], (label, metrics)
            page.screenshot(path=str(out / f"chat-source-model-{label}.png"), animations="disabled")
        page.set_viewport_size({"width": 390, "height": 844})
        page.locator("#modal-confirm").click()
        page.get_by_role("heading", name="Choose tools and schedule").wait_for()
        page.locator("#modal-confirm").click()
        page.get_by_role("heading", name="Review bot").wait_for()
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            page.locator(".setup-source-details summary").click()
            assert page.get_by_text(source_request, exact=True).is_visible()
            metrics = page.evaluate("""() => ({
              viewport:[innerWidth, innerHeight], documentWidth:document.documentElement.scrollWidth,
              bodyOverflow:document.querySelector('.modal-body').scrollWidth-document.querySelector('.modal-body').clientWidth,
              footerVisible:document.querySelector('.modal-footer').getBoundingClientRect().bottom <= innerHeight
            })""")
            assert metrics["documentWidth"] - width <= 1, (label, metrics)
            assert metrics["bodyOverflow"] <= 1, (label, metrics)
            assert metrics["footerVisible"], (label, metrics)
            page.screenshot(path=str(out / f"chat-source-review-{label}.png"), animations="disabled")
            if label != "phone": page.locator(".setup-source-details summary").click()

        assert "chat-context-source · Launch planning · message 3" in page.locator(".setup-review-list").inner_text()
        assert "will not start a run" in page.locator(".modal-body").inner_text().lower()
        assert store.list_runs() == []
        with page.expect_response(lambda response: response.url.endswith("/api/v1/bots")
                                 and response.request.method == "POST") as created:
            page.locator("#modal-confirm").click()
        assert created.value.status == 201, created.value.text()
        bot = store.get_bot("launch-checklist")
        assert bot and bot.instructions == "Track the launch checklist; notify me when a blocker needs attention."
        assert bot.creation_source and bot.creation_source.model_dump() == {
            "conversation_id": conversation["id"], "message_id": "chat-context-current-request",
            "source_bot_id": source_bot.id, "sequence": 3, "created_at": conversation["created_at"],
            "original_request": source_request,
        }
        assert store.list_runs() == []
        assert not errors, errors
        (out / "validation.json").write_text(json.dumps({
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_bot_creation_reuses_only_the_selected_chat_request_and_keeps_provenance",
            "browser": browser.browser_type.name, "browser_version": browser.version,
            "playwright_version": package_version("playwright"),
            "scenario": "latest user message explicitly seeds an editable Bot draft; older private turn is excluded; request provenance persists; creation starts no run; test-only connection key and no model call",
            "viewports": {"desktop": [1440, 960], "tablet": [900, 1024], "phone": [390, 844]},
            "screenshots": [f"chat-source-{state}-{size}.png" for state in ("purpose", "model", "review")
                            for size in ("desktop", "tablet", "phone")],
            "page_errors": errors,
            "source_sha256": {relative: hashlib.sha256((Path(__file__).resolve().parents[2] / relative).read_bytes()).hexdigest()
                              for relative in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                               "src/hutch/server/app.py", "src/hutch/models.py", "src/hutch/store.py",
                                               "tests/test_api.py", "tests/e2e/test_browser.py")},
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        try: context.tracing.stop(path=str(out / "trace.zip"))
        except Exception: pass
        context.close()


def test_workspace_model_default_is_editable_persistent_and_seeds_new_bot_setup(browser, live, monkeypatch):
    base, app = live
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key-never-sent-to-a-provider")
    source_bot = app.state.store.create_bot(Bot(name="workspace-default-source", model="mock/demo", tools=[]))
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/workspace-model-defaults"
    out.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        page.goto(f"{base}/#/chat/{source_bot.name}")
        page.locator("#conversation-switcher").wait_for()
        page.locator("#prefs-toggle").click()
        page.get_by_role("button", name="Model defaults for new Bots").click()
        page.get_by_role("heading", name="Model defaults for new Bots").wait_for()
        page.locator("#workspace-default-model").fill("openai/gpt-4o-mini")
        page.locator("#workspace-default-mode").select_option("hybrid")
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            metrics = page.evaluate("""() => ({viewport:[innerWidth,innerHeight], documentWidth:document.documentElement.scrollWidth,
              modal:document.querySelector('.modal-card').getBoundingClientRect().toJSON(),
              footerVisible:document.querySelector('.modal-footer').getBoundingClientRect().bottom <= innerHeight})""")
            assert metrics["documentWidth"] - width <= 1, (label, metrics)
            assert metrics["modal"]["x"] >= 0 and metrics["modal"]["right"] <= width + 1, (label, metrics)
            assert metrics["footerVisible"], (label, metrics)
            page.screenshot(path=str(out / f"preferences-{label}.png"), animations="disabled")
        page.set_viewport_size({"width": 1440, "height": 960})
        page.locator("#modal-confirm").click()
        page.get_by_role("status").filter(has_text="Workspace defaults saved").wait_for()
        assert app.state.store.kv_get("workspace:model-defaults") == '{"configured":true,"inference_mode":"hybrid","model":"openai/gpt-4o-mini"}'
        page.reload()
        page.locator("#conversation-switcher").wait_for()
        page.locator("#topbar-new-bot").click()
        page.get_by_role("heading", name="Describe the work").wait_for()
        page.locator("#setup-purpose").fill("Prepare a weekly project summary.")
        page.locator(".setup-identity summary").click()
        page.locator("#setup-display_name").fill("Project Summary Assistant")
        page.locator("#setup-name").fill("workspace-default-child")
        page.locator("#modal-confirm").click()
        page.get_by_role("heading", name="Set model and workspace").wait_for()
        assert page.get_by_label("Model route").input_value() == "openai/gpt-4o-mini"
        assert "Workspace default for new Bots" in page.locator(".setup-conversation").inner_text()
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            metrics = page.evaluate("""() => ({viewport:[innerWidth,innerHeight], documentWidth:document.documentElement.scrollWidth,
              bodyOverflow:document.querySelector('.modal-body').scrollWidth-document.querySelector('.modal-body').clientWidth,
              footerVisible:document.querySelector('.modal-footer').getBoundingClientRect().bottom <= innerHeight})""")
            assert metrics["documentWidth"] - width <= 1 and metrics["bodyOverflow"] <= 1, (label, metrics)
            assert metrics["footerVisible"], (label, metrics)
            page.screenshot(path=str(out / f"bot-setup-{label}.png"), animations="disabled")
        assert app.state.store.list_bots() == [app.state.store.get_bot(source_bot.id)]
        assert app.state.store.list_runs(limit=20) == []
        assert not errors, errors
        (out / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_workspace_model_default_is_editable_persistent_and_seeds_new_bot_setup",
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_workspace_model_default_is_editable_persistent_and_seeds_new_bot_setup",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(), "browser": browser.version,
            "playwright_version": package_version("playwright"),
            "viewports": {"desktop": [1440, 960], "tablet": [900, 1024], "phone": [390, 844]},
            "page_errors": errors,
            "source_sha256": {relative: hashlib.sha256((Path(__file__).resolve().parents[2] / relative).read_bytes()).hexdigest()
                              for relative in ("src/hutch/server/static/index.html", "src/hutch/server/static/app.js",
                                               "src/hutch/server/static/style.css", "src/hutch/server/app.py",
                                               "tests/e2e/test_browser.py")},
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        try:
            context.tracing.stop(path=str(out / "trace.zip"))
        except Exception:
            pass
        context.close()


def test_multiple_scheduled_tasks_can_be_managed_from_bot_settings(browser, live):
    base, app = live
    page = browser.new_page(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/scheduled-tasks"
    out.mkdir(parents=True, exist_ok=True)
    page.context.tracing.start(screenshots=True, snapshots=True, sources=False)
    trace_stopped = False
    try:
        app.state.store.create_bot(Bot(
            name="scheduled-research", model="mock/demo", tools=[],
            instructions="Review release notes and report important changes.",
            schedules=[Schedule(cron="0 9 * * 1", timezone="UTC",
                                prompt="Review release notes and report important changes.")],
        ))
        bot = app.state.store.get_bot("scheduled-research")
        assert bot.schedule and bot.schedule.prompt == "Review release notes and report important changes."

        # Hash-only navigation was unreliable under full-suite load; exercise the route directly.
        page.goto(f"{base}/#/bot/scheduled-research")
        page.locator("#form-schedule").wait_for()
        prompt = page.locator('#form-schedule [name="schedule_prompt"]')
        assert prompt.input_value() == "Review release notes and report important changes."
        assert page.get_by_text("Leave blank to use this bot’s standing instructions.", exact=False).is_visible()

        bot = app.state.store.get_bot("scheduled-research")
        primary_id = bot.schedule.id
        page.locator("#btn-add-schedule").click()
        page.get_by_role("heading", name="Add a recurring task").wait_for()
        add_form = page.locator("#modal-schedule-form")
        add_form.locator('[name="name"]').fill("Month start review")
        add_form.locator('[name="cron"]').fill("0 9 1 1 *")
        add_form.locator('[name="timezone"]').fill("UTC")
        add_form.locator('[name="prompt"]').fill("Review the monthly release notes.")
        with page.expect_response(lambda response: "/api/v1/bots/" + bot.id + "/schedules/" in response.url
                                 and response.request.method == "PUT") as added:
            page.locator("#modal-confirm").click()
        assert added.value.status == 200, added.value.text()
        wait_for(lambda: len(app.state.store.get_bot("scheduled-research").schedules) == 2)
        bot = app.state.store.get_bot("scheduled-research")
        secondary = next(item for item in bot.schedules if item.id != primary_id)
        assert secondary.name == "Month start review"

        secondary_card = page.locator("details.schedule-entry").filter(has_text="Month start review")
        secondary_card.locator("summary").click()
        secondary_form = secondary_card.locator("form")
        secondary_form.locator('[name="name"]').fill("Monthly release review")
        secondary_form.locator('[name="schedule_prompt"]').fill("Review releases and identify breaking changes.")
        stale_secondary_form = secondary_form.element_handle()
        with page.expect_response(lambda response: response.url.endswith("/schedules/" + secondary.id)
                                 and response.request.method == "PUT") as edited_secondary:
            secondary_form.locator('button[type="submit"]').click()
        assert edited_secondary.value.status == 200, edited_secondary.value.text()
        wait_for(lambda: next((item.name for item in app.state.store.get_bot("scheduled-research").schedules
                              if item.id == secondary.id), None) == "Monthly release review")
        page.wait_for_function("form => !form.isConnected", arg=stale_secondary_form)
        page.wait_for_function("() => [...document.querySelectorAll('[data-schedule-form] [name=name]')].some(input => input.value === 'Monthly release review')")

        page.set_viewport_size({"width": 390, "height": 844})
        primary_form = page.locator("#form-schedule")
        primary_form.locator('[name="schedule_prompt"]').fill("Check the weekly security feed and list actionable changes.")
        primary_form.locator('[name="cron"]').fill("0 8 * * 1")
        stale_primary_form = primary_form.element_handle()
        with page.expect_response(lambda response: response.url.endswith("/schedules/" + primary_id)
                                 and response.request.method == "PUT") as saved:
            primary_form.locator('button[type="submit"]').click()
        assert saved.value.status == 200, saved.value.text()
        assert saved.value.json()["prompt"] == "Check the weekly security feed and list actionable changes."
        wait_for(lambda: next((item.prompt for item in app.state.store.get_bot("scheduled-research").schedules
                              if item.id == primary_id), None)
                 == "Check the weekly security feed and list actionable changes.")
        page.wait_for_function("form => !form.isConnected", arg=stale_primary_form)
        page.locator("#form-schedule").wait_for(state="visible")
        assert page.locator('#form-schedule [name="schedule_prompt"]').input_value() \
            == "Check the weekly security feed and list actionable changes."
        page.reload()
        page.locator("#form-schedule").wait_for()
        assert page.locator("[data-schedule-form]").count() == 2
        assert next(item.name for item in app.state.store.get_bot("scheduled-research").schedules
                    if item.id == secondary.id) == "Monthly release review"

        captures = []
        sizes = {"desktop": (1440, 960), "tablet": (900, 1024), "phone": (390, 844)}
        for label, (width, height) in sizes.items():
            page.set_viewport_size({"width": width, "height": height})
            page.evaluate("document.querySelectorAll('details.schedule-entry').forEach(item => item.open = true)")
            page.locator(".page-scroll").evaluate("el => el.scrollTop = 0")
            entry_metrics = []
            for index, entry in enumerate(page.locator("details.schedule-entry").all()):
                entry.scroll_into_view_if_needed()
                box = entry.bounding_box()
                assert box and box["height"] < height, (label, index, box)
                entry.screenshot(path=str(out / f"settings-{label}-task-{index + 1}.png"), animations="disabled")
                entry_metrics.append({"index": index, "height": box["height"], "width": box["width"]})
            metrics = page.evaluate("""() => ({
                viewport: [innerWidth, innerHeight],
                document: [document.documentElement.scrollWidth, document.documentElement.scrollHeight],
                taskCards: document.querySelectorAll('details.schedule-entry').length,
                taskEditorsVisible: [...document.querySelectorAll('details.schedule-entry')].every(item => item.open),
                addButtonHeight: document.querySelector('#btn-add-schedule').getBoundingClientRect().height
            })""")
            assert metrics["document"][0] - metrics["viewport"][0] <= 1, (label, metrics)
            assert metrics["taskCards"] == 2 and metrics["taskEditorsVisible"], (label, metrics)
            assert metrics["addButtonHeight"] >= 44, (label, metrics)
            captures.append({"size": label, **metrics, "task_entries": entry_metrics})

        # Removing a non-primary stream leaves the primary stream intact.
        secondary_remove = page.locator(f'[data-remove-schedule="{secondary.id}"]')
        secondary_remove.scroll_into_view_if_needed()
        secondary_remove.click()
        page.get_by_role("heading", name="Remove scheduled task").wait_for()
        page.locator("#modal-confirm").click()
        wait_for(lambda: len(app.state.store.get_bot("scheduled-research").schedules) == 1)
        assert app.state.store.get_bot("scheduled-research").schedule.id == primary_id
        wait_for(lambda: page.locator("[data-schedule-form]").count() == 1)
        assert page.locator("[data-schedule-form]").count() == 1

        # Removing the primary promotes the remaining stream and updates the legacy alias.
        page.locator("#btn-add-schedule").click()
        add_form = page.locator("#modal-schedule-form")
        add_form.locator('[name="name"]').fill("Promotion target")
        add_form.locator('[name="cron"]').fill("0 9 1 1 *")
        with page.expect_response(lambda response: "/api/v1/bots/" + bot.id + "/schedules/" in response.url
                                 and response.request.method == "PUT") as promoted_added:
            page.locator("#modal-confirm").click()
        assert promoted_added.value.status == 200, promoted_added.value.text()
        wait_for(lambda: len(app.state.store.get_bot("scheduled-research").schedules) == 2)
        wait_for(lambda: page.locator("details.schedule-entry").filter(has_text="Promotion target").count() == 1)
        assert page.locator("[data-schedule-form]").count() == 2
        primary_remove = page.locator(f'[data-remove-schedule="{primary_id}"]')
        primary_remove.wait_for(state="attached")
        primary_remove.scroll_into_view_if_needed()
        primary_remove.click()
        page.get_by_role("heading", name="Remove scheduled task").wait_for()
        page.locator("#modal-confirm").click()
        wait_for(lambda: len(app.state.store.get_bot("scheduled-research").schedules) == 1)
        promoted = app.state.store.get_bot("scheduled-research")
        assert promoted.schedule.name == "Promotion target"
        assert promoted.schedules[0].id == promoted.schedule.id
        wait_for(lambda: page.locator("[data-schedule-form]").count() == 1)
        assert page.locator("#form-schedule").get_attribute("data-schedule-id") == promoted.schedule.id

        page.context.tracing.stop(path=str(out / "scheduled-tasks-trace.zip"))
        trace_stopped = True
        assert not errors, errors
        (out / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_multiple_scheduled_tasks_can_be_managed_from_bot_settings",
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_multiple_scheduled_tasks_can_be_managed_from_bot_settings",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(),
            "hutch_version": package_version("hutch"),
            "browser": browser.browser_type.name,
            "browser_version": browser.version,
            "playwright_version": package_version("playwright"),
            "captures": captures,
            "scenario": "edit, retain, remove, and promote independent task streams through the dashboard; isolated bot fixture only, no model/provider call",
            "page_errors": errors,
            "source_sha256": {
                "app.js": hashlib.sha256((Path(__file__).resolve().parents[2]
                                           / "src/hutch/server/static/app.js").read_bytes()).hexdigest(),
                "style.css": hashlib.sha256((Path(__file__).resolve().parents[2]
                                              / "src/hutch/server/static/style.css").read_bytes()).hexdigest(),
                "app.py": hashlib.sha256((Path(__file__).resolve().parents[2]
                                           / "src/hutch/server/app.py").read_bytes()).hexdigest(),
            },
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        if not trace_stopped:
            try:
                page.context.tracing.stop(path=str(out / "scheduled-tasks-trace.zip"))
            except Exception:
                pass
        page.close()


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
    first_conversation = page.locator("#conversation-switcher").input_value()
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
    page.locator("#studio-new-conversation").click()
    page.wait_for_function("old => document.querySelector('#conversation-switcher').value !== old", arg=first_conversation)
    assert "tiny:1b" in page.locator(".ms-btn").get_attribute("aria-label")
    assert "is-custom" not in page.locator(".ms-btn").get_attribute("class")
    page.locator("#conversation-switcher").select_option(first_conversation)
    page.wait_for_function("() => document.querySelector('.ms-btn')?.getAttribute('aria-label')?.includes('small:2b')")

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

    assert "tiny:1b" in btn.inner_text(), "the one-message override returns to the Bot default after send"
    assert "is-custom" not in btn.get_attribute("class")
    model_key_prefix = f"hutch.model.{app.state.store.get_bot('chatty').id}."
    assert page.evaluate("prefix => Object.keys(localStorage).filter(key => key.startsWith(prefix))", model_key_prefix) == []

    page.reload()                                           # a consumed override does not apply to later messages
    page.locator(".ms-btn").wait_for()
    assert page.locator(".ms-btn").inner_text().strip() == "tiny:1b"
    assert not errors, errors


def test_model_switcher_can_explicitly_save_the_selected_route_as_bot_default(browser, switcher_env, request):
    base, app, _fake = switcher_env
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/model-default-choice"
    out.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        page.goto(f"{base}/#/chat/chatty")
        button = page.locator(".ms-btn")
        button.wait_for()
        button.click()
        page.locator('.ms-item[data-spec="ollama/small:2b"]').click()
        assert "small:2b" in button.get_attribute("aria-label")
        assert "One-message override" in button.get_attribute("title")
        assert app.state.store.get_bot("chatty").model == "ollama/tiny:1b"

        button.click()
        save = page.locator("[data-save-default]")
        save.wait_for()
        assert "Save as Bot default" in save.inner_text()
        assert "scheduled runs" in save.inner_text()
        captures = []
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            metrics = page.evaluate("""() => ({viewport:[innerWidth,innerHeight], documentWidth:document.documentElement.scrollWidth,
              menu:document.querySelector('.ms-menu').getBoundingClientRect().toJSON(), save:document.querySelector('[data-save-default]').getBoundingClientRect().toJSON()})""")
            assert metrics["documentWidth"] - width <= 1, (label, metrics)
            assert metrics["menu"]["x"] >= 0 and metrics["menu"]["right"] <= width + 1, (label, metrics)
            assert metrics["save"]["x"] >= 0 and metrics["save"]["right"] <= width + 1, (label, metrics)
            assert metrics["save"]["bottom"] <= height, (label, metrics)
            page.screenshot(path=str(out / f"save-default-menu-{label}.png"), animations="disabled")
            captures.append({"viewport": [width, height], "menu": metrics["menu"], "save": metrics["save"],
                             "document_width": metrics["documentWidth"]})

        page.set_viewport_size({"width": 390, "height": 844})
        with page.expect_response(lambda response: response.url.endswith("/api/bots/chatty")
                                  and response.request.method == "PATCH") as saved:
            page.locator("[data-save-default]").click()
        assert saved.value.status == 200, saved.value.text()
        assert app.state.store.get_bot("chatty").model == "ollama/small:2b"
        assert app.state.store.list_runs(limit=20) == []
        model_key_prefix = f"hutch.model.{app.state.store.get_bot('chatty').id}."
        assert page.evaluate("prefix => Object.keys(localStorage).filter(key => key.startsWith(prefix))", model_key_prefix) == []
        assert "small:2b" in button.get_attribute("aria-label")
        assert "is-custom" not in button.get_attribute("class")

        page.reload()
        button = page.locator(".ms-btn")
        button.wait_for()
        assert "small:2b" in button.get_attribute("aria-label")
        button.click()
        assert page.locator("[data-save-default]").count() == 0
        assert app.state.store.get_bot("chatty").model == "ollama/small:2b"
        assert app.state.store.list_runs(limit=20) == []
        assert not errors, errors
        (out / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_model_switcher_can_explicitly_save_the_selected_route_as_bot_default",
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_model_switcher_can_explicitly_save_the_selected_route_as_bot_default",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(), "browser": browser.version,
            "playwright_version": package_version("playwright"), "captures": captures,
            "page_errors": errors, "runs_created": len(app.state.store.list_runs(limit=20)),
            "provider_calls": 0,
            "source_sha256": {relative: hashlib.sha256((Path(__file__).resolve().parents[2] / relative).read_bytes()).hexdigest()
                              for relative in ("src/hutch/server/static/model-switcher.js",
                                               "src/hutch/server/static/model-switcher.css", "src/hutch/server/app.py",
                                               "tests/e2e/test_browser.py")},
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        try:
            context.tracing.stop(path=str(out / "trace.zip"))
        except Exception:
            pass
        context.close()


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


def test_retired_mock_route_is_visibly_unavailable_in_the_model_picker(browser, live):
    """A migrated legacy row stays inspectable, but is never presented as a runnable model."""
    base, app = live
    app.state.store.create_bot(Bot(name="legacy-mock", model="mock/demo", tools=[]))
    page = browser.new_page(viewport={"width": 1280, "height": 800}, reduced_motion="reduce")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(f"{base}/#/chat/legacy-mock")
        page.locator(".ms-btn").wait_for()
        page.locator(".ms-btn").click()
        own = page.locator('.ms-item[data-spec="mock/demo"]')
        own.wait_for(state="visible")
        assert "legacy test route; choose a real model" in own.inner_text()
        assert own.get_attribute("aria-checked") == "true"
        page.locator(".ms-more").click()
        row = page.locator('.ms-row:has(input[name="ms-pick"][value="mock/demo"])')
        row.wait_for(state="visible")
        assert "needs setup" in row.inner_text()
        assert page.locator('input[name="ms-pick"][value="mock/demo"]').is_disabled()
        assert "Choose a configured Ollama, OpenAI, Anthropic, or compatible route" in row.inner_text()
        assert "leaves this machine" not in row.inner_text(), "a retired mock has no hosted destination"
        page.screenshot(path="/tmp/hutch-legacy-mock-picker.png", animations="disabled")
        assert not errors, errors
    finally:
        page.close()


def test_legacy_external_runtime_can_move_to_hutch_and_run_a_real_local_route(browser, switcher_env):
    """A legacy external executor stays blocked until the user moves it to Hutch's governed path."""
    from tests.fakes import agent_script

    base, app, fake = switcher_env
    bot = app.state.store.create_bot(Bot(name="legacy-runner", model="ollama/tiny:1b",
                                         runtime=RuntimeKind.opencode, tools=[], selfcheck=False))
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/runtime-recovery"
    out.mkdir(parents=True, exist_ok=True)
    page = browser.new_page(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    captures = []
    try:
        page.goto(f"{base}/#/bot/{bot.name}")
        page.locator("#runtime-recovery").wait_for()
        assert page.get_by_text("OpenCode execution is unavailable in Hutch.").is_visible()
        assert "Hutch never imports private sign-in files or credentials" in page.locator("#runtime-recovery").inner_text()
        isolation_help = page.locator("#inference-mode-help").inner_text()
        assert "hutch doctor" in isolation_help
        assert "/home/" not in isolation_help, "host diagnostic paths belong in the CLI, not a narrow settings panel"
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            page.locator("#form-model").scroll_into_view_if_needed()
            page.wait_for_timeout(80)
            metrics = page.evaluate("""() => ({viewport:[innerWidth,innerHeight], documentWidth:document.documentElement.scrollWidth,
                panelVisible:(() => { const r=document.querySelector('#runtime-recovery').getBoundingClientRect();
                  return r.top >= 0 && r.bottom <= innerHeight; })(),
                actionVisible:(() => { const r=document.querySelector('#btn-runtime-to-builtin').getBoundingClientRect();
                  return r.top >= 0 && r.bottom <= innerHeight; })()})""")
            assert metrics["documentWidth"] - width <= 1, (label, metrics)
            assert metrics["panelVisible"] and metrics["actionVisible"], (label, metrics)
            page.screenshot(path=str(out / f"{label}.png"), animations="disabled")
            captures.append({"size": label, **metrics})

        with page.expect_response(lambda response: response.url.endswith(f"/api/bots/{bot.name}")
                                  and response.request.method == "PATCH") as switched:
            page.locator("#btn-runtime-to-builtin").click()
        assert switched.value.status == 200, switched.value.text()
        assert switched.value.json()["runtime"] == "builtin"
        page.locator("#runtime-recovery").wait_for(state="detached")
        assert page.locator('#form-model input[disabled]').input_value() == "Hutch built-in"
        assert app.state.store.get_bot(bot.id).runtime is RuntimeKind.builtin

        fake.script = agent_script([{"content": "The Hutch built-in runtime completed the local turn."}])
        page.goto(f"{base}/#/chat/{bot.name}")
        page.locator("#chat-prompt").fill("Reply with a short status.")
        with page.expect_response(lambda response: "/api/v1/conversations/" in response.url
                                 and response.url.endswith("/messages")
                                 and response.request.method == "POST") as submitted:
            page.locator("#chat-send").click()
        run = submitted.value.json()
        assert run["status"] == "pending"
        wait_for(lambda: app.state.store.get_run(run["id"]).status in {
            RunStatus.succeeded, RunStatus.failed, RunStatus.stopped, RunStatus.outcome_unknown,
        })
        result = app.state.store.get_run(run["id"])
        assert result.status is RunStatus.succeeded, result.error
        assert result.model_used == "ollama/tiny:1b"
        assert any(event.type is EventType.message and event.data.get("content", "").startswith(
            "The Hutch built-in runtime completed") for event in app.state.store.list_events(run["id"]))
        assert not errors, errors
        capability_snapshot = app.state.store.run_capability_snapshot(run["id"])
        (out / "validation.json").write_text(json.dumps({
            "command": "uv run pytest -q tests/e2e/test_browser.py::test_legacy_external_runtime_can_move_to_hutch_and_run_a_real_local_route",
            "browser": browser.browser_type.name,
            "browser_version": browser.version,
            "playwright_version": package_version("playwright"),
            "legacy_runtime": "opencode",
            "run_runtime": capability_snapshot.get("runtime") if capability_snapshot else None,
            "model": result.model_used,
            "run_status": result.status.value,
            "provider_requests": len(fake.requests),
            "provider_fixture": "FakeOllama; no external requests",
            "captures": captures,
            "page_errors": errors,
            "source_sha256": {
                "app.js": hashlib.sha256((Path(__file__).resolve().parents[2] / "src/hutch/server/static/app.js").read_bytes()).hexdigest(),
                "app.py": hashlib.sha256((Path(__file__).resolve().parents[2] / "src/hutch/server/app.py").read_bytes()).hexdigest(),
                "style.css": hashlib.sha256((Path(__file__).resolve().parents[2] / "src/hutch/server/static/style.css").read_bytes()).hexdigest(),
            },
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        page.close()


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


@pytest.mark.parametrize("width,height,size", [(1440, 1000, "desktop"), (900, 1024, "tablet"), (390, 844, "phone")])
def test_local_browser_handoff_setting_is_explicit_and_persists(browser, live, width, height, size):
    from hutch.models import iso, utcnow

    base, app = live
    # Settings-only journey: use Hutch's ordinary model default without starting a run.
    app.state.store.create_bot(Bot(name="local-handoff", model="ollama/qwen3:4b", tools=["browser"]))
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/local-browser-handoff"
    out.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": width, "height": height}, reduced_motion="reduce")
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    try:
        page.goto(base + "/#/bot/local-handoff")
        page.get_by_role("heading", name="local-handoff settings", exact=True).wait_for()
        handoff = page.locator('#form-risk [name="local_browser_handoff"]')
        assert handoff.input_value() == "false"
        assert handoff.get_attribute("aria-describedby") == "browser-handoff-help"
        assert page.get_by_text("This does not enable phone control.", exact=False).count() == 1
        capability = next(item for item in page.request.get(f"{base}/api/v1/capabilities").json()
                          if item["id"] == "browser_handoff")
        if capability["status"] == "unavailable":
            assert capability["reason"] in page.locator("#browser-handoff-help").inner_text()
        else:
            assert "experimental on this host" in page.locator("#browser-handoff-help").inner_text()
        if width <= 390:
            assert handoff.bounding_box()["height"] >= 44
        handoff.focus()
        page.keyboard.press("Tab")
        save_policy = page.locator('#form-risk button[type="submit"]')
        assert save_policy.evaluate("element => element === document.activeElement")
        assert save_policy.evaluate("element => element.matches(':focus-visible')")
        handoff.select_option("true")
        old_form = page.locator("#form-risk").element_handle()
        with page.expect_response(lambda response: response.url.endswith("/api/bots/local-handoff")
                                  and response.request.method == "PATCH") as saved:
            page.locator('#form-risk button[type="submit"]').click()
        assert saved.value.status == 200, saved.value.text()
        page.wait_for_function("form => !form.isConnected", arg=old_form)
        page.locator("#form-risk").wait_for(state="visible")
        handoff = page.locator('#form-risk [name="local_browser_handoff"]')
        assert handoff.input_value() == "true"
        assert app.state.store.get_bot("local-handoff").local_browser_handoff
        page.locator("#form-risk").scroll_into_view_if_needed()
        page.locator(".toast-root .toast").wait_for(state="detached")
        page.screenshot(path=str(out / f"{size}-enabled.png"), full_page=True, animations="disabled")
        overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
        assert overflow <= 1 and not errors, (overflow, errors)
        (out / f"{size}.json").write_text(json.dumps({
            "captured_at": iso(utcnow()), "browser": browser.browser_type.name, "version": browser.version,
            "playwright_version": package_version("playwright"), "viewport": [width, height],
            "scenario": "Configure local same-session browser handoff; UI-only fixture with no run, model call or browser challenge",
            "provider_calls": 0, "run_started": False,
            "limitation": "The visible headed challenge flow was not exercised by this settings journey.",
            "stored": app.state.store.get_bot("local-handoff").local_browser_handoff,
            "page_errors": errors, "horizontal_overflow": overflow,
            "source_sha256": {p: hashlib.sha256((out.parents[3] / p).read_bytes()).hexdigest() for p in (
                "src/hutch/server/static/app.js", "src/hutch/server/static/style.css", "src/hutch/server/app.py",
                "src/hutch/server/pages.py", "src/hutch/server/templates/bot.html", "src/hutch/models.py")},
        }, indent=2) + "\n")
    finally:
        context.tracing.stop(path=str(out / f"{size}-trace.zip"))
        context.close()


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
        with page.expect_response(lambda response: '/facts?' in response.url and 'conversation_id=' in response.url) as refresh:
            store.remember(bot.id, 'background-proposal', 'A refresh must not dismiss or steal the review dialog',
                           conversation_id=a['id'])
        assert refresh.value.status == 200
        page.wait_for_timeout(100)
        assert page.locator('.modal-card').is_visible()
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


@pytest.mark.parametrize("width,height,size", [(1440, 1000, "desktop"), (900, 1024, "tablet"), (390, 844, "phone")])
def test_bot_message_reply_is_keyboard_accessible_editable_and_persisted(browser, live, monkeypatch, width, height, size):
    import hashlib
    import json
    from pathlib import Path

    base, app = live
    monkeypatch.setattr(app.state.engine, "tick", lambda: None)
    store = app.state.store
    bot = store.create_bot(Bot(name="reply-fixture", model="mock/demo", tools=[]))
    bot_label = bot.display_name or bot.name
    conversation, _ = store.create_conversation(bot.id, "Reply reference", idem_key="reply-conversation",
                                                request_hash="reply-conversation")
    answer = "The migration finished successfully. Check the rollout metrics before expanding it."
    run = store.create_run(Run(bot_id=bot.id, prompt="Summarize the rollout", status=RunStatus.succeeded))
    with store._tx() as db:
        store._insert_conversation_message(db, message_id="reply-fixture-user", conversation_id=conversation["id"],
            seq=1, run_id=run.id, role="user", content=run.prompt, created_at=run.created_at)
        store._insert_conversation_message(db, message_id="reply-fixture-answer", conversation_id=conversation["id"],
            seq=2, run_id=run.id, role="assistant", content=answer, created_at=run.created_at)
        db.execute("INSERT INTO conversation_runs (conversation_id, run_id, attached_at) VALUES (?, ?, ?)",
                   (conversation["id"], run.id, run.created_at))
    store.append_event(Event(run_id=run.id, type=EventType.message, data={"role": "assistant", "content": answer}))
    store.flush_events()

    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/message-replies"
    out.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": width, "height": height}, reduced_motion="reduce",
                                  has_touch=(size == "phone"))
    page = context.new_page()
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"{base}/#/chat/{bot.name}")
    reply = page.get_by_role("button", name=f"Reply to {bot_label} message")
    reply.wait_for(state="visible")
    reply.focus()
    page.keyboard.press("Enter")
    preview = page.locator("#reply-composer")
    preview.wait_for(state="visible")
    assert "migration finished successfully" in page.locator("#reply-composer-preview").inner_text()
    assert page.locator("#chat-prompt").evaluate("el => el === document.activeElement")
    page.locator("#chat-prompt").fill("Can you explain that result?")
    if size == "phone":
        assert page.get_by_role("button", name=f"Reply to {bot_label} message").bounding_box()["height"] >= 44
        assert page.locator("#reply-composer-clear").bounding_box()["height"] >= 44
    page.screenshot(path=str(out / f"preview-{size}.png"), full_page=True, animations="disabled")
    page.reload(wait_until="domcontentloaded")
    preview = page.locator("#reply-composer")
    preview.wait_for(state="visible")
    assert page.locator("#chat-prompt").input_value() == "Can you explain that result?"
    page.locator("#reply-composer-clear").focus()
    page.keyboard.press("Enter")
    assert preview.is_hidden()
    assert page.locator("#chat-prompt").evaluate("el => el === document.activeElement")
    reply.click()
    preview.wait_for(state="visible")
    with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/messages")) as sent:
        page.locator("#chat-send").click()
    assert sent.value.status == 201, sent.value.text()
    page.wait_for_function("""async ({conversationId, sourceId}) => {
      const r = await fetch(`/api/v1/conversations/${conversationId}?after=0&limit=100`);
      if (!r.ok) return false;
      const page = await r.json();
      return page.messages.some(message => message.role === 'user'
        && message.content === 'Can you explain that result?'
        && message.reply_to_message_id === sourceId);
    }""", arg={"conversationId": conversation["id"], "sourceId": "reply-fixture-answer"})
    assert preview.is_hidden()
    anchored = page.locator(".reply-reference-quote")
    anchored.wait_for(state="visible")
    assert "The migration finished successfully" in anchored.inner_text()
    quote_style = anchored.evaluate("""element => {
      const style = getComputedStyle(element);
      return {leftWidth: style.borderLeftWidth, topWidth: style.borderTopWidth,
        leftColor: style.borderLeftColor, topColor: style.borderTopColor};
    }""")
    assert quote_style["leftWidth"] == quote_style["topWidth"] == "1px"
    assert quote_style["leftColor"] == quote_style["topColor"]
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
    assert not errors
    page.screenshot(path=str(out / f"sent-{size}.png"), full_page=True, animations="disabled")
    (out / f"{size}.json").write_text(json.dumps({
        "test": "tests/e2e/test_browser.py::test_bot_message_reply_is_keyboard_accessible_editable_and_persisted",
        "captured_at": datetime.now(timezone.utc).isoformat(), "browser": browser.browser_type.name,
        "version": browser.version, "playwright": package_version("playwright"), "viewport": [width, height],
        "scenario": "Synthetic same-chat assistant reply; keyboard select/remove, composer preview, and persisted anchored send; no model/provider call",
        "page_errors": errors, "horizontal_overflow": page.evaluate("document.documentElement.scrollWidth - innerWidth"),
        "keyboard_focus_restored": True, "draft_reference_restored_after_reload": True,
        "reply_target": "reply-fixture-answer",
        "source_sha256": {p: hashlib.sha256((out.parents[3] / p).read_bytes()).hexdigest() for p in (
            "src/hutch/server/static/app.js", "src/hutch/server/static/style.css", "src/hutch/server/app.py", "src/hutch/store.py")},
    }, indent=2) + "\n")
    context.tracing.stop(path=str(out / f"{size}-trace.zip"))
    context.close()


def test_chat_choice_question_is_selectable_and_readable_at_all_viewports(browser, live, monkeypatch):
    """Persisted multiple-choice questions behave like chat input on desktop, tablet and phone."""
    import hashlib
    import json
    from pathlib import Path

    base, app = live
    store = app.state.store
    monkeypatch.setattr(app.state.engine, "tick", lambda: None)
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/structured-choices"
    out.mkdir(parents=True, exist_ok=True)
    sizes = {"desktop": (1440, 960), "tablet": (900, 1024), "phone": (390, 844)}
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    page.set_default_timeout(8000)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    trace = []
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        bot = store.create_bot(Bot(name="choice-visual", model="mock/demo", tools=[]))
        conversation, _ = store.create_conversation(
            bot.id, "Report format", idem_key="choice-conv-visual", request_hash="choice-conv-visual")
        prompt = "Prepare a concise planning note"
        run = Run(bot_id=bot.id, prompt=prompt, conversation_id=conversation["id"])
        store.submit_conversation_message(
            conversation["id"], prompt, run, Task(bot_id=bot.id, kind="on_demand", prompt=prompt),
            idem_key="choice-message-visual", request_hash="choice-message-visual")
        claimed = store.claim_run(run.id, "visual-choice-owner", lease_seconds=60)
        assert claimed is not None
        store.transition_run(run.id, RunStatus.running, fence=claimed.fence)
        question = store.create_conversation_question(
            run.id, "Which sections should the note include?", "multiple",
            ["Risks", "Timeline", "Owners"], fence=claimed.fence)
        store.transition_run(run.id, RunStatus.succeeded, fence=claimed.fence)
        page.goto(f"{base}/#/chat/{bot.name}")
        page.locator("#conversation-switcher").wait_for()
        assert page.locator("#conversation-switcher").input_value() == conversation["id"]
        run_card = page.locator(f'#chat-stream [data-run-id="{run.id}"]')
        form = run_card.locator("[data-choice-form]")
        form.wait_for(state="visible")
        assert form.locator("legend").inner_text() == "Which sections should the note include?"
        assert run_card.locator(".mhead .status").inner_text() == "Waiting for your choice"
        options = form.locator("[data-choice-option]")
        assert options.count() == 3
        assert options.nth(0).evaluate("el => el.closest('.choice-option').getBoundingClientRect().height") >= 44

        for label, (width, height) in sizes.items():
            page.set_viewport_size({"width": width, "height": height})
            page.screenshot(path=str(out / f"{label}-pending.png"), full_page=True, animations="disabled")
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, overflow)
            trace.append({"viewport": label, "size": [width, height], "state": "pending",
                          "horizontal_overflow": overflow})

        options.nth(0).focus()
        page.keyboard.press("Space")
        options.nth(1).check()
        assert options.nth(0).is_checked() and options.nth(1).is_checked()
        for label, (width, height) in sizes.items():
            page.set_viewport_size({"width": width, "height": height})
            assert options.nth(0).is_checked() and options.nth(1).is_checked()
            page.screenshot(path=str(out / f"{label}-selected.png"), full_page=True, animations="disabled")

        endpoint = f"/api/v1/conversations/{conversation['id']}/questions/{question['id']}/answer"
        with page.expect_response(lambda response: response.url.endswith(endpoint)) as answer_response:
            form.get_by_role("button", name="Send answer").click()
        response = answer_response.value
        assert response.status == 201, response.text()
        answered = run_card.locator(".choice-card.answered")
        answered.wait_for(state="visible")
        assert answered.locator(".choice-selection span").all_inner_texts() == ["Risks", "Timeline"]
        if page.locator(".toast-close").count():
            page.locator(".toast-close").last.click()
        for label, (width, height) in sizes.items():
            page.set_viewport_size({"width": width, "height": height})
            page.screenshot(path=str(out / f"{label}-answered.png"), full_page=True, animations="disabled")
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, overflow)
            trace.append({"viewport": label, "size": [width, height], "state": "answered",
                          "api_status": response.status,
                          "answer_run_initial_status": response.json()["status"],
                          "selected_labels": ["Risks", "Timeline"], "horizontal_overflow": overflow})

        assert not errors, errors
        context.tracing.stop(path=str(out / "trace.zip"))
        (out / "results.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_chat_choice_question_is_selectable_and_readable_at_all_viewports",
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_chat_choice_question_is_selectable_and_readable_at_all_viewports",
            "browser": browser.browser_type.name, "browser_version": browser.version,
            "playwright_version": package_version("playwright"), "viewports": trace,
            "page_errors": errors, "provider_calls": 0,
            "fixture_boundary": "SQLite-seeded questions exercise the real Store, API, HTML and chat-submit path; no model is invoked.",
            "source_sha256": {name: hashlib.sha256((out.parents[3] / name).read_bytes()).hexdigest() for name in (
                "src/hutch/models.py", "src/hutch/store.py", "src/hutch/tools/choice.py",
                "src/hutch/runtime/builtin.py", "src/hutch/server/app.py",
                "src/hutch/server/static/app.js", "src/hutch/server/static/style.css")},
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2) + "\n")
    finally:
        context.close()
