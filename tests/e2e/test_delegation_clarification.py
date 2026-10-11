"""Browser journey: a specialist's clarifying question is answered from the task card.

Synthetic local fixtures only: no provider call, no external request. The specialist run is
seeded with a real pending conversation question before the server starts, so the journey is
deterministic and exercises the genuine UI -> API -> storage -> run path.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from importlib.metadata import version as package_version
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402

from hutch.models import Bot, Event, EventType, Run, RunStatus, Task  # noqa: E402
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


def _seed_clarification(store):
    """Build a coordinator task whose specialist ended by asking a question."""
    from hutch.engine import Engine

    coordinator = store.create_bot(Bot(name="clarity-coordinator", display_name="Mara",
                                       model="mock/demo", tools=[]))
    specialist = store.create_bot(Bot(name="clarity-specialist", display_name="Research Partner",
                                      model="mock/demo", tools=[]))
    store.set_workspace_coordinator(coordinator.id)
    store.set_workspace_specialists([specialist.id])
    parent, _ = store.create_conversation(coordinator.id, "Coordinator",
                                          idem_key="clarity-parent", request_hash="clarity-parent")
    source_prompt = "Compare two launch options for the plan."
    source = Run(bot_id=coordinator.id, prompt=source_prompt, conversation_id=parent["id"])
    source_id, _ = store.submit_conversation_message(
        parent["id"], source_prompt, source, Task(bot_id=coordinator.id, prompt=source_prompt),
        idem_key="clarity-source", request_hash="clarity-source")
    owned = store.claim_run(source_id, "clarity-source-owner", 60)
    assert owned is not None
    store.transition_run(source_id, RunStatus.running, fence=owned.fence)
    store.append_event(Event(run_id=source_id, type=EventType.message,
                             data={"role": "assistant", "content": "Draft comparison ready.",
                                   "message_id": "clarity-source-answer"}, owner_fence=owned.fence))
    store.flush_events()
    store.transition_run(source_id, RunStatus.succeeded, fence=owned.fence)
    messages = store.list_conversation_messages(parent["id"])
    source_user = next(message for message in messages if message["role"] == "user")
    source_answer = next(message for message in messages if message["role"] == "assistant")

    brief = "Compare two launch options and choose one."
    assumptions = "Use public information only."
    effective_prompt = brief + "\n\nUser-reviewed assumptions and constraints:\n" + assumptions
    child_id, _ = store.submit_workspace_task(
        parent_conversation_id=parent["id"], source_run_id=source_id,
        source_user_message_id=source_user["id"], source_assistant_message_id=source_answer["id"],
        target_bot_id=specialist.id, task_brief=brief, assumptions=assumptions,
        run=Run(bot_id=specialist.id, prompt=effective_prompt, origin="workspace_task"),
        task=Task(bot_id=specialist.id, prompt=effective_prompt),
        capability_snapshot=Engine.capability_snapshot(specialist),
        idem_key="clarity-task", request_hash="clarity-task")
    child = store.claim_run(child_id, "clarity-child-owner", 60)
    assert child is not None
    store.transition_run(child_id, RunStatus.running, fence=child.fence)
    question = store.create_conversation_question(
        child_id, "Which launch option should I prefer?", "single", ["Alpha", "Beta"],
        fence=child.fence)
    store.transition_run(child_id, RunStatus.succeeded, fence=child.fence, exit_reason="completed")
    return {
        "coordinator_name": coordinator.name, "parent_conversation_id": parent["id"],
        "question": "Which launch option should I prefer?", "question_id": question["id"],
        "beta_option_id": question["options"][1]["id"],
    }


@pytest.fixture()
def clarification_live(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_MAX_CONCURRENT", "4")
    from hutch.config import get_config
    from hutch.store import Store

    config = get_config()
    store = Store(config)
    seed = _seed_clarification(store)
    store.close()

    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}", app, seed
    server.should_exit = True
    thread.join(timeout=10)
    assert not thread.is_alive()


def test_specialist_question_is_answered_from_the_task_card(browser, clarification_live):
    base, app, seed = clarification_live
    output = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/delegation-clarification"
    output.mkdir(parents=True, exist_ok=True)
    viewports = {"desktop": (1440, 960), "tablet": (900, 1024), "phone": (390, 844)}
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        page.goto(f"{base}/#/chat/{seed['coordinator_name']}")
        card = page.locator("[data-workspace-task]")
        card.wait_for(timeout=15000)
        question = card.locator("[data-workspace-task-question]")
        question.wait_for(timeout=15000)
        card_text = card.inner_text()
        assert "Needs your answer" in card_text, card_text
        assert seed["question"] in question.inner_text()
        assert "Alpha" in question.inner_text() and "Beta" in question.inner_text()
        assert "Latest specialist response" not in card_text
        assert card.locator("[data-discuss-specialist-result]").count() == 0
        assert card.locator("[data-stop-run]").count() == 0, "a waiting question is not a live run to stop"

        for label, (width, height) in viewports.items():
            page.set_viewport_size({"width": width, "height": height})
            question.scroll_into_view_if_needed()
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") == 0, label
            page.screenshot(path=str(output / f"{label}-needs-answer.png"), animations="disabled")
        page.set_viewport_size({"width": 1440, "height": 960})

        # Keyboard-only answer: focus the Beta option, select it, then submit.
        beta = question.get_by_label("Beta")
        beta.focus()
        assert page.evaluate("document.activeElement === document.querySelector('[data-workspace-task-question] input[value=\"" + seed["beta_option_id"] + "\"]')")
        page.keyboard.press("Space")
        assert beta.is_checked()
        send = question.get_by_role("button", name="Send answer")
        send.focus()
        page.keyboard.press("Enter")
        question.wait_for(state="detached", timeout=15000)
        card.get_by_text("Done", exact=True).wait_for(timeout=20000)
        assert "Latest specialist response" in card.inner_text()
        assert "Test scenario finished" in card.inner_text()

        stored = app.state.store.list_workspace_tasks(seed["parent_conversation_id"])[0]
        assert stored["pending_question"] is None
        assert stored["status"] == "succeeded"
        assert stored["current_run_id"] != stored["child_run_id"]
        page.screenshot(path=str(output / "desktop-question-answered.png"), animations="disabled")

        # The answer is visible as an answered choice in the specialist's own chat.
        page.locator("[data-open-workspace-task]").click()
        answered = page.locator(".choice-card.answered")
        answered.wait_for(timeout=15000)
        assert "Beta" in answered.inner_text()
        page.screenshot(path=str(output / "specialist-chat-answered-desktop.png"), animations="disabled")
        # Reopen the coordinator chat: the answered question must not come back and the
        # card keeps the result as its audit surface. (Opening the specialist chat uses
        # replaceState, so history back would leave the app instead of the conversation.)
        page.goto(f"{base}/#/chat/{seed['coordinator_name']}")
        card = page.locator("[data-workspace-task]")
        card.wait_for(timeout=15000)
        card.get_by_text("Done", exact=True).wait_for(timeout=15000)
        assert page.locator("[data-workspace-task-question]").count() == 0
        assert "Latest specialist response" in card.inner_text()
        assert not errors, errors

        context.tracing.stop(path=str(output / "trace.zip"))
        (output / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_delegation_clarification.py::test_specialist_question_is_answered_from_the_task_card",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "browser": browser.version,
            "playwright_version": package_version("playwright"),
            "fixture": "synthetic local bots and seeded conversation question; app engine executes the answer run",
            "provider_requests": 0,
            "page_errors": errors,
            "viewports": [{"size": label, "viewport": [width, height], "horizontal_overflow": 0}
                          for label, (width, height) in viewports.items()],
            "verified": [
                "task card shows Needs your answer with the specialist identity and question options",
                "the pending question text is not presented as a produced result",
                "no result-attach or stop control is offered while the question waits",
                "keyboard selection and Send answer create the answer run in the specialist chat",
                "storage clears the pending question and follows the new run to succeeded",
                "the answered choice and the specialist response remain in the task audit surface",
            ],
        }, indent=2) + "\n")
    finally:
        try:
            context.tracing.stop()
        except Exception:
            pass
        context.close()
