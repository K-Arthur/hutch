"""Live Studio review of the selector recommendation card at narrow and wide sizes.

The event fixture is intentionally synthetic: the real built-in selector/tool/API path is
covered separately in test_runtime_builtin.py and test_workflow_routing.py.
"""
from __future__ import annotations

from tests.support.browser import wait_for_page

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
from tests.support.artifacts import artifact_path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = Path(os.environ.get("HUTCH_WORKFLOW_ROUTE_ARTIFACTS",
                              str(artifact_path("dynamic-workflows/chat-router"))))
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
        yield f"http://127.0.0.1:{port}", app.state.store, bot, conversation, definition, run.id
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive(), "local Studio preview did not stop"


def stable_workflow_card(page):
    """Read the card and action in one layout pass across live feed refreshes."""
    for _ in range(12):
        card = page.locator(".workflow-recommendation")
        try:
            card.wait_for(state="visible", timeout=1000)
            card.evaluate("el => el.scrollIntoView({block: 'nearest', behavior: 'instant'})")
            metrics = card.evaluate("""el => {
              const rect = node => {
                if (!node) return null;
                const r = node.getBoundingClientRect();
                return {x:r.x, y:r.y, width:r.width, height:r.height};
              };
              const style = getComputedStyle(el);
              return {connected:el.isConnected, card:rect(el), action:rect(el.querySelector('[data-workflow-suggestion-run]')),
                styles:{fontFamily:style.fontFamily, fontSize:style.fontSize, lineHeight:style.lineHeight,
                  padding:style.padding, borderRadius:style.borderRadius, color:style.color,
                  borderLeftColor:style.borderLeftColor}};
            }""")
        except pw.Error:
            page.wait_for_timeout(50)
            continue
        if metrics["connected"] and metrics["card"] and metrics["action"]:
            return card, metrics
        page.wait_for_timeout(50)
    raise AssertionError("workflow suggestion was repeatedly replaced before its layout settled")


def test_chat_suggestion_card_reflows_and_requires_review(browser, live_studio):
    base, store, bot, conversation, definition, run_id = live_studio
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
    accessibility_states = []
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
            card, metrics = stable_workflow_card(page)
            assert page.evaluate("Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) <= innerWidth + 1")
            box, button, styles = metrics["card"], metrics["action"], metrics["styles"]
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
                store.append_event(Event(run_id=run_id, type=EventType.message,
                                         data={"role": "assistant",
                                               "content": "Transcript refreshed while review is open."}))
                store.flush_events()
                page.evaluate("scheduleFeedRender()")
                wait_for_page(page, "feedRefreshPending === true", timeout=5000)
                dialog.locator("#modal-cancel").click()
                page.get_by_text("Transcript refreshed while review is open.", exact=True).wait_for()
                try:
                    wait_for_page(page,
                        "document.activeElement?.dataset?.workflowSuggestionRun === "
                        f"{json.dumps(definition['definition_id'])}", timeout=5000)
                except pw.TimeoutError:
                    state = page.evaluate("""() => ({
                      active: document.activeElement?.outerHTML,
                      suggestionButtons: [...document.querySelectorAll('[data-workflow-suggestion-run]')]
                        .map(button => ({id: button.dataset.workflowSuggestionRun, connected: button.isConnected})),
                      refreshText: [...document.querySelectorAll('#chat-stream *')]
                        .some(element => element.childElementCount === 0 && element.textContent.includes('Transcript refreshed')),
                      feedPending: feedRefreshPending,
                      modalOpen: Boolean(document.querySelector('#modal-root .modal-card')),
                    })""")
                    raise AssertionError(f"focus did not follow refreshed suggestion action: {state}")
                assert action.evaluate("el => el === document.activeElement"), "focus should return to the review action"

        # Exercise WCAG text-spacing overrides on the compact layout rather than
        # inferring them from the default stylesheet's responsive breakpoints.
        page.add_style_tag(content="""
          * { line-height: 1.5 !important; letter-spacing: .12em !important; word-spacing: .16em !important; }
          p { margin-block-end: 2em !important; }
        """)
        spaced_card = page.locator(".workflow-recommendation")
        spaced_card.evaluate("el => el.scrollIntoView({block: 'start', behavior: 'instant'})")
        spaced_bounds = spaced_card.bounding_box()
        spaced_heading_locator = spaced_card.locator(".workflow-panel-kicker")
        spaced_heading = spaced_heading_locator.bounding_box()
        spaced_scroll_bounds = page.locator("#chat-scroll").bounding_box()
        spaced_heading_hit = spaced_heading_locator.evaluate("""el => {
          const rect = el.getBoundingClientRect();
          const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
          return {text: el.innerText, hitTag: hit?.tagName || null,
                  hitClass: hit?.className?.toString?.() || "",
                  coveredByOtherElement: !hit || !el.contains(hit)};
        }""")
        assert spaced_bounds and spaced_scroll_bounds and spaced_heading
        assert spaced_bounds["x"] >= 0 and spaced_bounds["x"] + spaced_bounds["width"] <= 321
        assert spaced_heading["y"] >= spaced_scroll_bounds["y"] \
            and spaced_heading["y"] + spaced_heading["height"] <= spaced_scroll_bounds["y"] + spaced_scroll_bounds["height"], \
            "the card's route label must remain visible below the fixed workflow panel"
        assert not spaced_heading_hit["coveredByOtherElement"], \
            f"the route label must not be covered by another panel: {spaced_heading_hit}"
        page.screenshot(path=str(EVIDENCE / "suggestion-text-spacing-card-start-compact-phone.png"),
                        animations="disabled")

        spaced_action_locator = spaced_card.locator("[data-workflow-suggestion-run]")
        spaced_action_locator.focus()
        spaced_action_locator.scroll_into_view_if_needed()
        spaced_action = spaced_action_locator.bounding_box()
        spaced_composer = page.locator(".composer").bounding_box()
        spaced_action_scroll = page.locator("#chat-scroll").bounding_box()
        spaced_slot = page.locator("#jump-latest-slot")
        spaced_slot_bounds = spaced_slot.bounding_box() if spaced_slot.is_visible() else None
        spaced_jump = page.locator("#jump-latest")
        spaced_jump_bounds = spaced_jump.bounding_box() if spaced_jump.is_visible() else None
        spaced_scroll_metrics = page.locator("#chat-scroll").evaluate(
            "el => ({scrollHeight:el.scrollHeight, clientHeight:el.clientHeight, scrollTop:el.scrollTop})")
        spacing_overflow = page.evaluate(
            "Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) > innerWidth + 1")
        assert spaced_action and not spacing_overflow
        assert spaced_action["height"] >= 44
        assert spaced_composer and spaced_action["y"] + spaced_action["height"] <= spaced_composer["y"]
        assert spaced_action_scroll and spaced_action["y"] + spaced_action["height"] <= spaced_action_scroll["y"] + spaced_action_scroll["height"], \
            "the focused action must remain fully visible above the chat's fixed controls"
        if spaced_slot_bounds:
            assert spaced_action_scroll and spaced_slot_bounds["y"] >= spaced_action_scroll["y"] + spaced_action_scroll["height"]
            assert spaced_slot_bounds["y"] + spaced_slot_bounds["height"] <= spaced_composer["y"]
        page.screenshot(path=str(EVIDENCE / "suggestion-text-spacing-focus-compact-phone.png"),
                        animations="disabled")
        accessibility_states.append({"state": "wcag-text-spacing", "viewport": [320, 740],
                                     "document_overflow": spacing_overflow,
                                     "card_start_bounds": spaced_bounds,
                                     "heading_bounds": spaced_heading,
                                     "heading_hit_test": spaced_heading_hit,
                                     "focused_action_bounds": spaced_action,
                                     "composer_bounds": spaced_composer, "jump_bounds": spaced_jump_bounds,
                                     "jump_slot_bounds": spaced_slot_bounds,
                                     "scroll_bounds": spaced_action_scroll, "scroll_metrics": spaced_scroll_metrics,
                                     "text": spaced_card.inner_text()})

        # Forced-colors emulation checks that the content and action remain present
        # when the browser replaces author colors with the user's system palette.
        page.emulate_media(forced_colors="active")
        assert page.evaluate("matchMedia('(forced-colors: active)').matches")
        forced_card = page.locator(".workflow-recommendation")
        forced_card.evaluate("el => el.scrollIntoView({block: 'start', behavior: 'instant'})")
        forced_start_bounds = forced_card.bounding_box()
        forced_heading = forced_card.locator(".workflow-panel-kicker").bounding_box()
        forced_start_scroll = page.locator("#chat-scroll").bounding_box()
        assert forced_start_bounds and forced_heading and forced_start_scroll
        assert forced_heading["y"] >= forced_start_scroll["y"] \
            and forced_heading["y"] + forced_heading["height"] <= forced_start_scroll["y"] + forced_start_scroll["height"]
        page.screenshot(path=str(EVIDENCE / "suggestion-forced-colors-card-start-compact-phone.png"),
                        animations="disabled")
        forced_action_locator = forced_card.locator("[data-workflow-suggestion-run]")
        forced_action_locator.focus()
        forced_action_locator.scroll_into_view_if_needed()
        forced_action = forced_action_locator.bounding_box()
        forced_composer = page.locator(".composer").bounding_box()
        forced_jump = page.locator("#jump-latest")
        forced_jump_bounds = forced_jump.bounding_box() if forced_jump.is_visible() else None
        forced_slot = page.locator("#jump-latest-slot")
        forced_slot_bounds = forced_slot.bounding_box() if forced_slot.is_visible() else None
        forced_scroll_bounds = page.locator("#chat-scroll").bounding_box()
        forced_scroll_metrics = page.locator("#chat-scroll").evaluate(
            "el => ({scrollHeight:el.scrollHeight, clientHeight:el.clientHeight, scrollTop:el.scrollTop})")
        jump_layout = (forced_jump.evaluate("el => ({parentId:el.parentElement?.id, offsetParentId:el.offsetParent?.id, "
                                              "computedPosition:getComputedStyle(el).position, "
                                              "bottom:getComputedStyle(el).bottom, rect:el.getBoundingClientRect().toJSON(), "
                                              "parentRect:el.parentElement.getBoundingClientRect().toJSON()})")
                       if forced_jump.is_visible() else None)
        forced_overflow = page.evaluate(
            "Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) > innerWidth + 1")
        forced_style = forced_card.evaluate("""el => { const s=getComputedStyle(el); return {
            color:s.color, backgroundColor:s.backgroundColor, borderColor:s.borderColor,
            forcedColorAdjust:s.forcedColorAdjust}; }""")
        forced_answer = page.locator(".answer", has_text="Transcript refreshed while review is open.")
        answer_colors = forced_answer.evaluate("""el => {
          const probe = document.createElement('span');
          probe.style.color = 'CanvasText';
          document.body.append(probe);
          const expected = getComputedStyle(probe).color;
          probe.remove();
          return {actual: getComputedStyle(el).color, expected};
        }""")
        forced_bubble = page.locator(".msg.you .bubble", has_text="Review independent projects and verify the report")
        bubble_color = forced_bubble.evaluate("el => getComputedStyle(el).color")
        assert forced_action and not forced_overflow
        assert forced_action["height"] >= 44
        assert forced_composer and forced_action["y"] + forced_action["height"] <= forced_composer["y"]
        assert answer_colors["actual"] == answer_colors["expected"], \
            "live assistant text must use the system foreground in forced-colors mode"
        assert bubble_color == answer_colors["expected"], \
            "user message text must use the system foreground in forced-colors mode"
        if forced_slot_bounds:
            assert forced_scroll_bounds and forced_slot_bounds["y"] >= forced_scroll_bounds["y"] + forced_scroll_bounds["height"]
            assert forced_slot_bounds["y"] + forced_slot_bounds["height"] <= forced_composer["y"]
        assert "Review & run" in forced_card.inner_text()
        page.screenshot(path=str(EVIDENCE / "suggestion-forced-colors-focus-compact-phone.png"),
                        animations="disabled")
        accessibility_states.append({"state": "forced-colors-active", "viewport": [320, 740],
                                     "document_overflow": forced_overflow,
                                     "card_start_bounds": forced_start_bounds,
                                     "heading_bounds": forced_heading,
                                     "focused_action_bounds": forced_action,
                                     "composer_bounds": forced_composer, "jump_bounds": forced_jump_bounds,
                                     "jump_slot_bounds": forced_slot_bounds,
                                     "scroll_bounds": forced_scroll_bounds, "scroll_metrics": forced_scroll_metrics,
                                     "answer_colors": answer_colors,
                                     "user_bubble_color": bubble_color,
                                     "jump_layout": jump_layout,
                                     "computed_style": forced_style,
                                     "text": forced_card.inner_text()})
        page.emulate_media(forced_colors="none")
        jump_action = {"shown": False, "clicked": False}
        jump_button = page.locator("#jump-latest")
        if jump_button.is_visible():
            jump_action["shown"] = True
            jump_action["scroll_top_before"] = page.locator("#chat-scroll").evaluate("el => el.scrollTop")
            jump_button.click()
            wait_for_page(page, "document.querySelector('#jump-latest-slot')?.hidden === true")
            jump_action["scroll_top_after"] = page.locator("#chat-scroll").evaluate("el => el.scrollTop")
            jump_action["scroll_max_after"] = page.locator("#chat-scroll").evaluate("el => el.scrollHeight - el.clientHeight")
            assert abs(jump_action["scroll_top_after"] - jump_action["scroll_max_after"]) <= 1
            jump_action["clicked"] = True

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
            "accessibility_states": accessibility_states,
            "jump_latest_interaction": jump_action,
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
