"""Live Studio review of the selector recommendation card at narrow and wide sizes.

The event fixture is intentionally synthetic: the real built-in selector/tool/API path is
covered separately in test_runtime_builtin.py and test_workflow_routing.py.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from importlib.metadata import version as package_version
from pathlib import Path
from urllib.parse import urlsplit

import pytest

pw = pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402

from hutch.models import Bot, Event, EventType, Run, RunStatus, Task  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from hutch.workflow import persistence as wstore  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = Path(os.environ.get("HUTCH_WORKFLOW_ROUTE_ARTIFACTS",
                              str(ROOT / "docs/realignment/artifacts/dynamic-workflows/chat-router")))
SOURCES = (
    "src/hutch/runtime/builtin.py",
    "src/hutch/runtime/steps.py",
    "src/hutch/tools/workflow_route.py",
    "src/hutch/server/static/app.js",
    "src/hutch/server/static/style.css",
    "tests/e2e/test_workflow_route_card.py",
)


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as playwright:
        selected = None
        errors = []
        for engine in (playwright.chromium, playwright.firefox):
            try:
                selected = engine.launch()
                break
            except Exception as exc:
                errors.append(f"{engine.name}: {exc}")
        if selected is None:
            pytest.skip("no Playwright browser is installed: " + "; ".join(errors))
        yield selected
        selected.close()


@pytest.fixture()
def live_studio(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_MAX_CONCURRENT", "2")
    app = create_app()
    store = app.state.store
    bot = store.create_bot(Bot(name="workflow-route-review", display_name="Workflow review",
                               model="mock/demo", tools=[], workflow_mode="suggest"))
    conversation, _ = store.create_conversation(
        bot.id, "Workflow card review", idem_key="workflow-route-conversation", request_hash="visual-v1")
    plan = {
        "name": "quarterly-analysis-" + "long-label-" * 7,
        "inputs": {}, "envelope": {"tools": []},
        "budget": {"max_nodes": 4, "max_model_calls": 0, "max_fanout": 1},
        "nodes": [{"kind": "transform", "id": "summary", "op": "constant",
                   "args": {"value": "Reviewed source results"}}],
    }
    definition = wstore.save_definition(store, name=plan["name"], plan=plan,
                                        source="operator", activate=False)
    prompt = "Review independent projects and verify the report"
    run = Run(bot_id=bot.id, prompt=prompt, conversation_id=conversation["id"],
              status=RunStatus.succeeded)
    store.submit_conversation_message(
        conversation["id"], prompt, run, Task(bot_id=bot.id, kind="on_demand", prompt=prompt),
        idem_key="workflow-route-message", request_hash="visual-message-v1")
    store.append_event(Event(run_id=run.id, type=EventType.tool_call,
                             data={"tool": "recommend_workflow", "args": {"signals": {
                                 "repeatable_procedure": True, "known_inputs": True},
                                 "workflow": definition["definition_id"]}}))
    store.append_event(Event(run_id=run.id, type=EventType.tool_result,
                             data={"tool": "recommend_workflow", "ok": True, "output": "Suggestion returned.",
                                   "workflow_recommendation": {
                                       "route": "saved_workflow", "why": "The saved method covers this recurring "
                                       "sequence, and each result is checked before the summary is accepted.",
                                       "simpler": "Run the direct checks once if this is a one-off request.",
                                       "bounds": {"max_fanout": 8}, "suggested_plan_name": plan["name"],
                                       "policy": "suggest", "status": "suggested",
                                       "definition_id": definition["definition_id"],
                                   }}))
    store.append_event(Event(run_id=run.id, type=EventType.message,
                             data={"role": "assistant", "content": "I found a reviewed method you can inspect."}))

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    assert server.started, "local Studio preview did not start"
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}", app.state.store, bot, conversation, definition
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive(), "local Studio preview did not stop"


def test_chat_suggestion_card_reflows_and_requires_review(browser, live_studio):
    base, store, bot, conversation, definition = live_studio
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(reduced_motion="reduce")
    page = context.new_page()
    errors: list[str] = []
    failed_requests: list[str] = []
    external_requests: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("requestfailed", lambda request: failed_requests.append(request.url))
    page.on("request", lambda request: external_requests.append(request.url)
            if urlsplit(request.url).hostname not in {"127.0.0.1", "localhost"} else None)
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    states = []
    try:
        sizes = (("desktop", 1440, 960), ("tablet", 768, 1024),
                 ("phone", 360, 800), ("compact-phone", 320, 740))
        for label, width, height in sizes:
            page.set_viewport_size({"width": width, "height": height})
            page.goto(f"{base}/#/chat/{bot.name}", wait_until="domcontentloaded")
            card = page.locator(".workflow-recommendation")
            card.wait_for(state="visible", timeout=15_000)
            assert page.locator("#conversation-switcher").input_value() == conversation["id"]
            assert "Suggestion · nothing started" in card.inner_text()
            assert "direct checks once" in card.inner_text()
            assert card.locator("[data-workflow-suggestion-run]").get_attribute(
                "data-workflow-suggestion-run") == definition["definition_id"]
            assert card.locator("[data-workflow-suggestion-run]").inner_text() == "Review & run"
            card.scroll_into_view_if_needed()
            assert page.evaluate("Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) <= innerWidth + 1")
            box = card.bounding_box()
            button = card.locator("[data-workflow-suggestion-run]").bounding_box()
            styles = card.evaluate("el => { const s = getComputedStyle(el); return {fontFamily:s.fontFamily, "
                                   "fontSize:s.fontSize, lineHeight:s.lineHeight, padding:s.padding, "
                                   "borderRadius:s.borderRadius, color:s.color, "
                                   "borderLeftColor:s.borderLeftColor}; }")
            panel = page.locator("#workflow-panel").bounding_box()
            assert box and button and box["width"] <= width and button["height"] >= 44
            page.screenshot(path=str(EVIDENCE / f"suggestion-{label}.png"), animations="disabled")
            states.append({"label": label, "viewport": [width, height],
                           "document_width": page.evaluate("document.documentElement.scrollWidth"),
                           "card_bounds": box, "button_bounds": button,
                           "panel_bounds": panel, "computed_style": styles,
                           "card_text": card.inner_text()})

            if label == "desktop":
                action = card.locator("[data-workflow-suggestion-run]")
                action.focus()
                action.press("Enter")
                dialog = page.locator('.modal-card[role="dialog"]')
                dialog.wait_for(state="visible")
                assert "Starting this saved workflow is an explicit action" in dialog.inner_text()
                assert dialog.locator("#modal-confirm").inner_text() == "Start workflow"
                page.screenshot(path=str(EVIDENCE / "suggestion-review-dialog.png"), animations="disabled")
                dialog.locator("#modal-cancel").click()
                assert action.evaluate("el => el === document.activeElement"), "focus should return to the review action"

        assert not errors, errors
        assert not failed_requests, failed_requests
        assert not external_requests, external_requests
        assert wstore.list_workflow_runs(store, bot_id=bot.id) == []
        context.tracing.stop(path=str(EVIDENCE / "trace.zip"))
        artifacts = sorted(EVIDENCE.glob("suggestion-*.png")) + [EVIDENCE / "trace.zip"]
        (EVIDENCE / "results.json").write_text(json.dumps({
            "test": "tests/e2e/test_workflow_route_card.py::test_chat_suggestion_card_reflows_and_requires_review",
            "browser": f"{browser.browser_type.name.title()} {browser.version}",
            "playwright": package_version("playwright"),
            "viewports": states,
            "interaction": "Enter opens the explicit saved-workflow review dialog; Cancel restores focus; no workflow started",
            "page_errors": errors,
            "failed_requests": failed_requests,
            "external_requests": external_requests,
            "artifact_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in artifacts},
            "source_sha256": {relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
                              for relative in SOURCES},
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        if context.tracing:
            try:
                context.tracing.stop()
            except Exception:
                pass
        context.close()
