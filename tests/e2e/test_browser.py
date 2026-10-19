"""Real-browser checks (Chromium or Firefox via Playwright) of what unit tests cannot see: the live stream surviving a
network drop in the actual DOM, and the plain-POST controls doing what they say.

Skipped automatically when Playwright or its Chromium build is not installed:
    pip install playwright && playwright install chromium
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import secrets
import subprocess
import threading
import time
from datetime import datetime, timezone
from importlib.metadata import version as package_version
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

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


def test_paired_phone_uses_supervision_view_and_hides_data_after_revocation(browser, live):
    base, app = live
    store = app.state.store
    bot = Bot(name="phone-private-bot", display_name="Private phone fixture", model="ollama/qwen3:4b", tools=[],
              remote_start_enabled=True)
    store.upsert_bot(bot)
    run = store.create_run(Run(bot_id=bot.id, prompt="Review the progress safely", status=RunStatus.running))
    store.append_event(Event(run_id=run.id, type=EventType.message,
                             data={"role": "assistant", "content": "Phone transcript fixture marker."}))
    store.flush_events()
    code = store.create_pairing_code()
    enrollment, outcome = store.exchange_pairing_code(code, "Phone fixture", "browser-test")
    assert outcome == "ok" and enrollment
    handle = store.webauthn_user_handle()
    paired = store.finish_passkey_enrollment(enrollment["token"], {
        "credential_id": secrets.token_bytes(24), "public_key": b"browser-test-key", "sign_count": 0,
        "backup_eligible": True, "backed_up": True, "user_handle": handle,
    })
    store._db.execute("UPDATE paired_credentials SET capabilities_json='[\"monitor\"]' WHERE id=?",
                      (paired["id"],))
    store._db.commit()
    assert store.authenticate_session(paired["session_token"])["capabilities"] == ["monitor"]

    page = browser.new_page(viewport={"width": 390, "height": 844})
    forbidden_responses = []
    page.on("response", lambda response: forbidden_responses.append(response.url)
            if response.status == 403 else None)
    try:
        page.context.add_cookies([{"name": "hutch_session", "value": paired["session_token"], "url": base}])
        page.goto(base + "/")
        page.locator("#phone-root .phone-brand").wait_for()
        page.get_by_text("Private phone fixture").first.wait_for()
        assert page.locator("body").evaluate("el => el.classList.contains('paired-phone')")
        assert page.locator(".app-shell").is_hidden()
        assert page.locator(".phone-start-form").count() == 0
        assert page.locator('.phone-tabs [data-phone-tab="review"]').count() == 0, (
            f"session={page.evaluate('hutchSession.capabilities')} tabs={page.locator('.phone-tabs').get_attribute('class')}")
        assert forbidden_responses == []
        assert "Monitor only" in page.locator("#phone-root").inner_text()
        page.get_by_role("button", name="Runs").click()
        page.locator(f'[data-phone-run="{run.id}"]').click()
        page.locator(".phone-run-detail").wait_for()
        assert page.locator("[data-phone-stop], [data-phone-resume]").count() == 0
        assert page.locator(".phone-run-detail").get_by_text("Phone transcript fixture marker.").is_visible()
        started_at = page.locator(".phone-run-detail .phone-card .phone-sub").first.inner_text()
        transcript_time = page.locator(".phone-transcript li > span").first.inner_text()
        assert "Started " in started_at and not re.search(r"\d{4}-\d{2}-\d{2}T", started_at)
        assert not re.search(r"\d{4}-\d{2}-\d{2}T", transcript_time)
        store.revoke_device_session(paired["id"])
        page.locator(".phone-locked").wait_for(timeout=4000)
        assert "Private phone fixture" not in page.locator("body").inner_text()
        assert "Phone transcript fixture marker." not in page.locator("body").inner_text()
    finally:
        page.close()


def test_delegated_wait_status_is_responsive_and_reviewable(browser, live, monkeypatch):
    """Capture the parked-parent state in the local app and the paired review view."""
    base, app = live
    store, engine = app.state.store, app.state.engine
    monkeypatch.setattr(engine, "tick", lambda: None)
    bot = store.create_bot(Bot(name="delegated-wait-visual", model="mock/demo", tools=["delegate_task"]))
    root = store.create_run(Run(bot_id=bot.id, prompt="Coordinate a bounded child task."))
    claimed = store.claim_run(root.id, "delegated-wait-visual-owner", 60)
    assert claimed is not None
    root = store.transition_run(root.id, RunStatus.running, fence=claimed.fence,
                                capability_snapshot=engine.capability_snapshot(bot))
    child, inserted = store.submit_delegated_run(
        parent_run_id=root.id, parent_fence=root.fence,
        run=Run(bot_id=bot.id, prompt="Inspect the bounded area."),
        task=Task(bot_id=bot.id, kind="delegated", prompt="Inspect the bounded area."),
        idem_key="visual-child", request_hash="visual-child-v1")
    assert inserted
    root = store.transition_run(
        root.id, RunStatus.waiting_child, fence=root.fence,
        child_wait=(child.id, {"version": 1, "messages": [], "tool_call": {
            "id": "call-visual", "name": "delegate_task", "arguments": {"task": child.prompt}}}),
        event={"reason": "delegated child is working"})

    artifacts = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/delegation-wait-20261011"
    artifacts.mkdir(parents=True, exist_ok=True)
    page_errors, failed_requests = [], []
    context = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=1,
                                 has_touch=True, reduced_motion="reduce")
    page = context.new_page()
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.on("console", lambda message: page_errors.append(message.text) if message.type == "error" else None)
    page.on("requestfailed", lambda request: failed_requests.append({"url": request.url,
                                                                      "failure": request.failure}))
    local_views = {}
    try:
        page.goto(f"{base}/#/run/{root.id}")
        reduced_motion = page.evaluate("""() => ({
          matched: matchMedia('(prefers-reduced-motion: reduce)').matches,
          fast_duration: getComputedStyle(document.documentElement).getPropertyValue('--dur-fast').trim()
        })""")
        assert reduced_motion["matched"] and reduced_motion["fast_duration"] == "0ms"
        status = page.locator(".status.waiting_child:visible")
        status.first.wait_for()
        stop = page.locator("#stop-this-run")
        stop.wait_for()
        assert status.first.inner_text() == "Waiting for delegated work"
        assert stop.is_enabled()
        waiting_style = status.first.evaluate("""el => {
          const style = getComputedStyle(el);
          return {color: style.color, borderColor: style.borderColor};
        }""")
        assert waiting_style["color"] == "rgb(251, 191, 36)"
        header_status = page.locator("#workflow")
        header_status.get_by_text("1 waiting", exact=True).wait_for()
        header_status.get_by_text("1 queued", exact=True).wait_for()
        assert header_status.get_by_text("working", exact=False).count() == 0
        for width, height, label in ((1440, 1000, "desktop-1440"), (768, 1024, "tablet-768"),
                                     (360, 800, "phone-360"), (320, 800, "compact-320")):
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(120)
            metrics = page.evaluate("() => ({client: document.documentElement.clientWidth, "
                                     "scroll: document.documentElement.scrollWidth})")
            assert metrics["scroll"] <= metrics["client"] + 1, (width, metrics)
            path = artifacts / f"{label}.png"
            page.screenshot(path=str(path), full_page=True)
            local_views[label] = {"viewport": {"width": width, "height": height},
                                  "document_width": metrics["scroll"], "client_width": metrics["client"],
                                  "screenshot": path.name}
        spacing_override = page.add_style_tag(content="""
          * { line-height: 1.5 !important; letter-spacing: .12em !important;
              word-spacing: .16em !important; }
          p { margin-block-end: 2em !important; }
        """)
        spacing_metrics = page.evaluate("() => ({client: document.documentElement.clientWidth, "
                                           "scroll: document.documentElement.scrollWidth})")
        assert spacing_metrics["scroll"] <= spacing_metrics["client"] + 1, spacing_metrics
        assert status.first.is_visible() and stop.is_enabled()
        spacing_stop_box = stop.bounding_box()
        assert spacing_stop_box and spacing_stop_box["width"] >= 44 and spacing_stop_box["height"] >= 44
        page.screenshot(path=str(artifacts / "text-spacing-320.png"), full_page=True)
        spacing_override.evaluate("el => el.remove()")
        page.emulate_media(forced_colors="active")
        forced_colors = page.evaluate("matchMedia('(forced-colors: active)').matches")
        assert forced_colors
        forced_status_style = status.first.evaluate("""el => {
          const style = getComputedStyle(el);
          const canvasProbe = document.createElement('span');
          canvasProbe.style.cssText = 'position:fixed;color:CanvasText;background-color:Canvas';
          document.body.append(canvasProbe);
          const canvasColor = getComputedStyle(canvasProbe).backgroundColor;
          canvasProbe.remove();
          const rgb = value => value.match(/[\\d.]+/g).slice(0, 3).map(Number);
          const luminance = value => value.map(channel => {
            channel /= 255;
            return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
          }).reduce((sum, channel, index) => sum + channel * [0.2126, 0.7152, 0.0722][index], 0);
          const [foreground, background] = [luminance(rgb(style.color)), luminance(rgb(canvasColor))]
            .sort((a, b) => b - a);
          return {color: style.color, canvas: canvasColor,
                  contrast: (foreground + 0.05) / (background + 0.05)};
        }""")
        assert forced_status_style["contrast"] >= 4.5, forced_status_style
        forced_metrics = page.evaluate("() => ({client: document.documentElement.clientWidth, "
                                         "scroll: document.documentElement.scrollWidth})")
        assert forced_metrics["scroll"] <= forced_metrics["client"] + 1, forced_metrics
        assert status.first.is_visible() and stop.is_enabled()
        page.screenshot(path=str(artifacts / "forced-colors-320.png"), full_page=True)
        page.emulate_media(forced_colors="none")
        owner_stop_box = stop.bounding_box()
        assert owner_stop_box and owner_stop_box["width"] >= 44 and owner_stop_box["height"] >= 44
        stop.focus()
        assert page.evaluate("el => document.activeElement === el", stop.element_handle())
    finally:
        try:
            context.tracing.stop(path=str(artifacts / "trace.zip"))
        finally:
            context.close()

    enrollment, outcome = store.exchange_pairing_code(store.create_pairing_code(), "Delegation review", "browser-test")
    assert outcome == "ok" and enrollment
    paired = store.finish_passkey_enrollment(enrollment["token"], {
        "credential_id": secrets.token_bytes(24), "public_key": b"delegated-wait-review-key", "sign_count": 0,
        "backup_eligible": True, "backed_up": True, "user_handle": store.webauthn_user_handle(),
    })
    session = store.authenticate_session(paired["session_token"])
    assert "review" in session["capabilities"]
    phone_context = browser.new_context(viewport={"width": 320, "height": 844}, device_scale_factor=1,
                                       has_touch=True, reduced_motion="reduce")
    phone = phone_context.new_page()
    try:
        phone_context.add_cookies([{"name": "hutch_session", "value": paired["session_token"], "url": base}])
        phone.goto(base + "/")
        phone.locator("#phone-root .phone-brand").wait_for()
        phone.get_by_role("button", name="Runs").click()
        phone.locator(f'[data-phone-run="{root.id}"]').click()
        phone.locator(".phone-run-detail").wait_for()
        phone.locator(".phone-run-detail .phone-status").get_by_text(
            "Waiting for delegated work", exact=True).wait_for()
        phone_progress = phone.locator(".phone-transcript")
        phone_progress.get_by_text("Waiting for delegated work", exact=True).wait_for()
        assert "reason" not in phone_progress.inner_text()
        phone_stop = phone.get_by_role("button", name="Stop run")
        phone_stop.wait_for()
        phone_stop_box = phone_stop.bounding_box()
        assert phone_stop_box and phone_stop_box["width"] >= 44 and phone_stop_box["height"] >= 44
        phone_stop.focus()
        assert phone.evaluate("el => document.activeElement === el", phone_stop.element_handle())
        phone_metrics = phone.evaluate("() => ({client: document.documentElement.clientWidth, "
                                       "scroll: document.documentElement.scrollWidth})")
        assert phone_metrics["scroll"] <= phone_metrics["client"] + 1, phone_metrics
        phone.screenshot(path=str(artifacts / "paired-review-320.png"), full_page=True)
    finally:
        phone_context.close()

    source_paths = [Path(__file__), Path(__file__).resolve().parents[2] / "src/hutch/server/static/app.js",
                    Path(__file__).resolve().parents[2] / "src/hutch/server/static/style.css"]
    artifact_paths = sorted(path for path in artifacts.iterdir() if path.is_file() and path.name != "validation.json")
    validation = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "browser": {"name": browser.browser_type.name, "version": browser.version},
        "fixture": {"run_id": root.id, "status": root.status.value, "child_run_id": child.id,
                    "child_status": child.status.value, "provider_calls": 0},
        "owner_views": local_views,
        "owner_wait_status_style": waiting_style,
        "reduced_motion": {"requested": "reduce", **reduced_motion},
        "text_spacing_override": {"line_height": 1.5, "letter_spacing_em": 0.12,
                                  "word_spacing_em": 0.16, "paragraph_spacing_em": 2,
                                  "document_width": spacing_metrics["scroll"],
                                  "client_width": spacing_metrics["client"],
                                  "stop_target_css_px": {"width": spacing_stop_box["width"],
                                                         "height": spacing_stop_box["height"]}},
        "forced_colors": {"requested": "active", "matched": forced_colors,
                           "waiting_status": forced_status_style,
                           "document_width": forced_metrics["scroll"],
                           "client_width": forced_metrics["client"]},
        "owner_stop_target_css_px": {"width": owner_stop_box["width"], "height": owner_stop_box["height"]},
        "paired_review_view": {"viewport": {"width": 320, "height": 844},
                                "document_width": phone_metrics["scroll"],
                                "client_width": phone_metrics["client"],
                                "stop_target_css_px": {"width": phone_stop_box["width"],
                                                       "height": phone_stop_box["height"]},
                                "stop_action_available": True},
        "console_errors": page_errors,
        "failed_requests": failed_requests,
        "source_sha256": {str(path.relative_to(Path(__file__).resolve().parents[2])):
                          hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths},
        "artifact_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in artifact_paths},
    }
    (artifacts / "validation.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    assert page_errors == []
    assert failed_requests == []


def test_paired_phone_monitors_and_reviews_redacted_workflows(browser, live):
    """Exercise real workflow rows through phone list, question answer, and durable Stop."""
    from hutch.workflow import persistence as wstore
    from hutch.workflow.submit import submit_workflow

    base, app = live
    store = app.state.store
    bot = store.create_bot(Bot(name="phone-workflow-review", display_name="Workflow review fixture",
                               model="mock/demo", tools=[]))
    ask_plan = {"name": "phone-review-workflow", "inputs": {"private_note": {"type": "string"}},
                "envelope": {"tools": []}, "budget": {"max_nodes": 3, "max_model_calls": 0},
                "nodes": [{"kind": "ask", "id": "confirm", "question": "Continue with the review?",
                           "options": ["yes", "no"], "timeout_seconds": 300}]}
    review_workflow = submit_workflow(store, bot=bot, plan=ask_plan,
                                      inputs={"private_note": "PRIVATE_PHONE_INPUT_SENTINEL"},
                                      definition_name=ask_plan["name"])
    stop_plan = {**ask_plan, "name": "phone-stop-workflow"}
    stop_workflow = submit_workflow(store, bot=bot, plan=stop_plan, inputs={"private_note": "stop secret"},
                                    definition_name=stop_plan["name"])
    deadline = time.monotonic() + 20
    review_question = stop_question = None
    while time.monotonic() < deadline:
        review_question = next(iter(wstore.questions(store, review_workflow.workflow_run_id, status="pending")), None)
        stop_question = next(iter(wstore.questions(store, stop_workflow.workflow_run_id, status="pending")), None)
        if review_question and stop_question:
            break
        time.sleep(0.05)
    assert review_question and stop_question, "the real workflow supervisor should park both ask nodes"
    deadline = time.monotonic() + 10
    parked_attempt = wstore.workflow_attempt_quiescence(store, stop_workflow.attempt_run_id)
    while time.monotonic() < deadline and not parked_attempt["attempt_parked"]:
        time.sleep(0.05)
        parked_attempt = wstore.workflow_attempt_quiescence(store, stop_workflow.attempt_run_id)
    assert parked_attempt["attempt_parked"]
    assert wstore.workflow_pause_controls(store, stop_workflow.workflow_run_id)["pause_available"]
    pause_child = Run(bot_id=bot.id, prompt="phone pause projection child", kind="step")
    with store._tx() as db:
        db.execute("INSERT INTO runs (id, bot_id, doc, status, created_at, parent_run_id, kind) "
                   "VALUES (?, ?, ?, 'waiting_human', ?, ?, 'step')",
                   (pause_child.id, bot.id, pause_child.model_dump_json(),
                    datetime.now(timezone.utc).isoformat(), stop_workflow.attempt_run_id))
    assert not wstore.workflow_attempt_quiescence(
        store, stop_workflow.attempt_run_id)["owned_work_quiet"]
    pause_projection = wstore.set_workflow_pause(
        store, stop_workflow.workflow_run_id, paused=True,
        expected_revision_id=stop_workflow.revision_id,
        expected_generation=stop_workflow.attempt_run_id,
        idem_key="browser-phone-pause-requested", request_hash="browser-phone-pause-requested")
    assert pause_projection["parked"] is False
    assert wstore.workflow_pause_controls(store, stop_workflow.workflow_run_id)["pause_ready"] is False
    wstore.set_workflow_pause(
        store, review_workflow.workflow_run_id, paused=True,
        expected_revision_id=review_workflow.revision_id,
        expected_generation=review_workflow.attempt_run_id,
        idem_key="phone-workflow-paused-fixture", request_hash="phone-workflow-paused-fixture")

    enrollment, outcome = store.exchange_pairing_code(store.create_pairing_code(), "Workflow review phone", "browser-test")
    assert outcome == "ok" and enrollment
    paired = store.finish_passkey_enrollment(enrollment["token"], {
        "credential_id": secrets.token_bytes(24), "public_key": b"browser-workflow-phone-key", "sign_count": 0,
        "backup_eligible": True, "backed_up": True, "user_handle": store.webauthn_user_handle(),
    })
    artifacts = Path(__file__).parents[2] / "docs/realignment/artifacts/workflow-studio/phone"
    artifacts.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1)
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        context.add_cookies([{"name": "hutch_session", "value": paired["session_token"], "url": base}])
        page.goto(base + "/")
        page.locator("#phone-root .phone-brand").wait_for()
        page.get_by_role("button", name="Workflows").click()
        page.locator(f'[data-phone-workflow="{review_workflow.workflow_run_id}"]').wait_for()
        page.locator(f'[data-phone-workflow="{stop_workflow.workflow_run_id}"]').wait_for()
        page.locator(f'[data-phone-workflow="{review_workflow.workflow_run_id}"]').click()
        page.locator(".phone-workflow-detail").wait_for()
        assert page.locator(".phone-planned-steps .phone-step-title").filter(has_text="confirm").is_visible()
        assert page.locator(".phone-planned-steps .phone-step-status").inner_text() == "Planned"
        assert "Paused" in page.locator(".phone-workflow-heading").inner_text()
        assert page.get_by_role("button", name="Pause workflow").count() == 0
        assert page.get_by_role("button", name="Resume workflow").count() == 0
        assert "PRIVATE_PHONE_INPUT_SENTINEL" not in page.locator("#phone-root").inner_text()
        page.screenshot(path=str(artifacts / "workflow-detail-390.png"), full_page=True, animations="disabled")

        page.get_by_role("button", name="Review").click()
        question_card = page.locator(f'.phone-workflow-answer-form[data-question-id="{review_question["id"]}"]').locator("..")
        question_card.get_by_text(review_question["id"], exact=False).wait_for()
        assert "Continue with the review?" in question_card.inner_text()
        assert "PRIVATE_PHONE_INPUT_SENTINEL" not in question_card.inner_text()
        for question in (review_question, stop_question):
            prompt_name = re.compile(
                rf"Question ID {re.escape(question['id'])}.*Continue with the review\?"
            )
            accessible_form = page.get_by_role("form", name=prompt_name)
            assert accessible_form.count() == 1
            answer_name = re.compile(
                rf"Question ID {re.escape(question['id'])}.*Continue with the review\?.*Answer"
            )
            answer = accessible_form.get_by_role(
                "combobox", name=answer_name,
                description=re.compile(r"Answering this resolves only this question"),
            )
            assert answer.count() == 1
        page.set_viewport_size({"width": 320, "height": 780})
        question_dimensions_320 = page.evaluate(
            "({viewport: innerWidth, document: document.documentElement.scrollWidth})")
        assert question_dimensions_320["document"] <= question_dimensions_320["viewport"]
        question_answer_heights = page.locator(
            ".phone-workflow-answer-form button[type=submit]").evaluate_all(
                "items => items.map(el => Math.round(el.getBoundingClientRect().height))")
        assert len(question_answer_heights) == 2 and min(question_answer_heights) >= 44
        page.screenshot(path=str(artifacts / "workflow-questions-320.png"),
                        full_page=True, animations="disabled")
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(artifacts / "workflow-question-390.png"), full_page=True, animations="disabled")
        question_card.locator('select[name="answer"]').select_option("yes")
        with page.expect_response(lambda response: response.url.endswith(
                f"/api/v1/phone/workflows/questions/{review_question['id']}/answer")) as answered:
            question_card.get_by_role("button", name="Send answer").click()
        answer_response = answered.value
        assert answer_response.status == 200, answer_response.text()
        assert answer_response.request.headers.get("x-hutch-csrf")
        assert answer_response.request.headers.get("idempotency-key")
        assert answer_response.request.post_data_json == {"answer": "yes"}
        assert answer_response.json()["question_id"] == review_question["id"]
        assert "yes" not in answer_response.text()
        assert wstore.workflow_run(store, review_workflow.workflow_run_id)["pause_requested"] is True

        page.reload()
        page.locator("#phone-root .phone-brand").wait_for()
        page.get_by_role("button", name="Workflows").click()
        page.locator(f'[data-phone-workflow="{stop_workflow.workflow_run_id}"]').click()
        assert "Pause requested" in page.locator(".phone-workflow-heading").inner_text()
        assert page.get_by_role("button", name="Pause workflow").count() == 0
        assert page.get_by_role("button", name="Resume workflow").count() == 0
        page.screenshot(path=str(artifacts / "workflow-pause-requested-390.png"),
                        full_page=True, animations="disabled")
        with store._tx() as db:
            db.execute("UPDATE runs SET status='failed' WHERE id=?", (pause_child.id,))
        stop_button = page.get_by_role("button", name="Stop workflow")
        stop_button.wait_for()
        with page.expect_response(lambda response: response.url.endswith(
                f"/api/v1/phone/workflows/runs/{stop_workflow.workflow_run_id}/stop")) as stopped:
            stop_button.click()
        stop_response = stopped.value
        assert stop_response.status == 200, stop_response.text()
        assert stop_response.request.headers.get("x-hutch-csrf")
        assert stop_response.request.headers.get("idempotency-key")
        assert stop_response.request.post_data_json == {"expected_revision_id": stop_workflow.revision_id}
        assert stop_response.json()["stop_requested"] is True
        wait_for(lambda: wstore.workflow_run(store, stop_workflow.workflow_run_id)["stop_requested"])
        page.get_by_text("stop requested", exact=False).wait_for()
        assert page.get_by_role("button", name="Stop workflow").count() == 0

        page.set_viewport_size({"width": 320, "height": 780})
        page.screenshot(path=str(artifacts / "workflow-detail-320.png"), full_page=True, animations="disabled")
        dimensions_320 = page.evaluate("({ viewport: innerWidth, document: document.documentElement.scrollWidth, body: document.body.scrollWidth })")
        assert dimensions_320["document"] <= dimensions_320["viewport"]
        page.set_viewport_size({"width": 390, "height": 844})
        target_heights = page.locator(".phone-tabs button, .phone-header-actions .btn, .phone-workflow-detail .btn").evaluate_all(
            "items => items.map(el => Math.round(el.getBoundingClientRect().height))")
        assert target_heights and min(target_heights) >= 44
        store._db.execute("UPDATE paired_credentials SET capabilities_json='[\"monitor\"]' WHERE id=?",
                          (paired["id"],))
        store._db.commit()
        page.locator("[data-phone-refresh]").click()
        page.locator(".phone-tabs.monitor-only").wait_for()
        assert page.locator('.phone-tabs [data-phone-tab="review"]').count() == 0
        assert page.locator(".phone-question-card").count() == 0
        assert not errors, errors
    finally:
        context.tracing.stop(path=str(artifacts / "paired-phone-workflows-trace.zip"))
        context.close()

    screenshots = ["workflow-detail-390.png", "workflow-question-390.png", "workflow-questions-320.png",
                   "workflow-detail-320.png", "workflow-pause-requested-390.png"]
    source_paths = ["src/hutch/server/workflows_api.py", "src/hutch/server/static/app.js",
                    "src/hutch/server/static/style.css", "tests/e2e/test_browser.py"]
    hashes = {name: hashlib.sha256((artifacts / name).read_bytes()).hexdigest() for name in screenshots}
    hashes["paired-phone-workflows-trace.zip"] = hashlib.sha256(
        (artifacts / "paired-phone-workflows-trace.zip").read_bytes()).hexdigest()
    hashes["visual-review.md"] = hashlib.sha256((artifacts / "visual-review.md").read_bytes()).hexdigest()
    (artifacts / "paired-phone-workflows-results.json").write_text(json.dumps({
        "fixture_boundary": "Real SQLite workflow submission, supervisor ask nodes, phone API, CSRF/idempotency and browser UI; no model request.",
        "viewports": {"review_and_detail": [390, 844], "reflow": [320, 780]},
        "reflow_dimensions_320": dimensions_320,
        "minimum_phone_target_height_px": min(target_heights),
        "computed_accessibility": {
            "simultaneous_named_question_forms": 2,
            "answer_control_names_include_durable_question_ids_and_prompts": True,
            "authority_boundary_is_associated_as_description": True,
            "operating_system_screen_reader": "not tested",
        },
        "question_reflow_320": question_dimensions_320,
        "question_answer_min_height_320_px": min(question_answer_heights),
        "question_answer_status": answer_response.status,
        "workflow_stop_status": stop_response.status,
        "page_errors": errors,
        "screenshots_sha256": hashes,
        "source_sha256": {name: hashlib.sha256((Path(__file__).parents[2] / name).read_bytes()).hexdigest()
                          for name in source_paths},
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2) + "\n")


def test_paired_phone_reviews_the_exact_approval_once(browser, live):
    base, app = live
    store, engine = app.state.store, app.state.engine
    bot = store.create_bot(Bot(name="phone-approval", model="mock/demo", tools=["files"],
                               approval_mode=ApprovalMode.ask))
    run = engine.submit(bot, "write a report")
    engine.dispatch_pending()
    wait_for(lambda: store.get_run(run.id).status is RunStatus.waiting_approval)
    approval = store.pending_approvals()[0]
    enrollment, outcome = store.exchange_pairing_code(store.create_pairing_code(), "Approval phone", "browser-test")
    assert outcome == "ok" and enrollment
    paired = store.finish_passkey_enrollment(enrollment["token"], {
        "credential_id": secrets.token_bytes(24), "public_key": b"browser-approval-key", "sign_count": 0,
        "backup_eligible": True, "backed_up": True, "user_handle": store.webauthn_user_handle(),
    })

    artifacts = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/workflow-studio/phone"
    artifacts.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        context.add_cookies([{"name": "hutch_session", "value": paired["session_token"], "url": base}])
        page.goto(base + "/")
        page.locator("#phone-root .phone-brand").wait_for()
        page.get_by_role("button", name="Review").click()
        card = page.locator(f'.approval-card [data-phone-approve="{approval.id}"]').locator("..").locator("..")
        card.wait_for()
        assert card.get_by_role("heading", name=approval.action).is_visible()
        assert card.get_by_text(approval.id, exact=True).is_visible()
        page.screenshot(path=str(artifacts / "phone-approval-390.png"), full_page=True, animations="disabled")
        page.set_viewport_size({"width": 320, "height": 780})
        overflow_320 = page.evaluate("document.documentElement.scrollWidth - innerWidth")
        assert overflow_320 <= 1
        target_heights_320 = card.locator(".phone-actions button").evaluate_all(
            "items => items.map(el => Math.round(el.getBoundingClientRect().height))")
        assert target_heights_320 and min(target_heights_320) >= 44
        page.screenshot(path=str(artifacts / "phone-approval-320.png"), full_page=True, animations="disabled")
        page.set_viewport_size({"width": 390, "height": 844})
        card.locator("summary").click()
        assert card.locator("pre").is_visible()
        button = card.get_by_role("button", name="Allow once")
        assert button.get_attribute("data-action-hash") == approval.action_hash
        describedby = button.get_attribute("aria-describedby").split()
        description = " ".join(page.locator(f'[id="{element_id}"]').inner_text() for element_id in describedby)
        assert approval.action in description and approval.id in description
        assert page.get_by_role("button", name="Allow once",
                                description=re.compile(re.escape(approval.action) + r".*" + re.escape(approval.id))).is_visible()
        with page.expect_response(lambda response: response.url.endswith(
                f"/api/v1/actions/approvals/{approval.id}/approve")) as response_info:
            button.click()
        response = response_info.value
        assert response.status == 200, response.text()
        assert response.request.headers.get("x-hutch-csrf")
        assert response.request.headers.get("idempotency-key")
        assert response.request.post_data_json == {"always": False, "action_hash": approval.action_hash}
        wait_for(lambda: store.get_run(run.id).status is RunStatus.succeeded)
        assert store.get_approval(approval.id).status.value == "approved"
        assert not errors, errors
    finally:
        context.tracing.stop(path=str(artifacts / "phone-approval-trace.zip"))
        context.close()
    artifact_names = ["phone-approval-390.png", "phone-approval-320.png",
                      "phone-approval-trace.zip", "visual-review.md"]
    (artifacts / "phone-approval-results.json").write_text(json.dumps({
        "test": "tests/e2e/test_browser.py::test_paired_phone_reviews_the_exact_approval_once",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "browser": browser.browser_type.name, "browser_version": browser.version,
        "playwright": package_version("playwright"), "approval_id": approval.id,
        "approval_id_visible": True, "decision": store.get_approval(approval.id).status.value,
        "viewport_css_px": {"phone": [390, 844], "compact_phone": [320, 780]},
        "compact_phone_overflow_px": overflow_320,
        "compact_phone_action_min_height_px": min(target_heights_320),
        "page_errors": errors,
        "artifact_sha256": {name: hashlib.sha256((artifacts / name).read_bytes()).hexdigest()
                            for name in artifact_names},
        "source_sha256": {name: hashlib.sha256((Path(__file__).resolve().parents[2] / name).read_bytes()).hexdigest()
                          for name in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                       "tests/e2e/test_browser.py")},
    }, indent=2) + "\n")


@pytest.mark.parametrize("decision_order", [("question", "approval"), ("approval", "question")])
def test_paired_phone_keeps_mixed_question_and_approval_pending_in_either_order(
        browser, live, decision_order):
    from hutch.workflow import persistence as wstore
    from hutch.workflow.submit import submit_workflow

    base, app = live
    store, engine = app.state.store, app.state.engine
    bot = store.create_bot(Bot(name="phone-mixed-review", model="mock/demo", tools=["files"],
                               approval_mode=ApprovalMode.ask))
    action_run = engine.submit(bot, "write a report")
    engine.dispatch_pending()
    wait_for(lambda: store.get_run(action_run.id).status is RunStatus.waiting_approval)
    approval = store.pending_approvals()[0]
    question_plan = {
        "name": "phone-mixed-review-question",
        "envelope": {"tools": []},
        "budget": {"max_nodes": 2, "max_model_calls": 0},
        "nodes": [{"kind": "ask", "id": "confirm", "question": "May I continue this workflow?",
                   "options": ["yes", "no"], "timeout_seconds": 300}],
    }
    workflow = submit_workflow(store, bot=bot, plan=question_plan,
                               definition_name=question_plan["name"])
    deadline = time.monotonic() + 20
    pending_question = None
    while time.monotonic() < deadline:
        pending_question = next(iter(wstore.questions(
            store, workflow.workflow_run_id, status="pending")), None)
        attempt = store.get_run(workflow.attempt_run_id)
        if pending_question and attempt and attempt.status is RunStatus.waiting_workflow:
            break
        time.sleep(0.05)
    assert pending_question is not None

    enrollment, outcome = store.exchange_pairing_code(
        store.create_pairing_code(), "Mixed review phone", "browser-test")
    assert outcome == "ok" and enrollment
    paired = store.finish_passkey_enrollment(enrollment["token"], {
        "credential_id": secrets.token_bytes(24), "public_key": b"mixed-review-phone-key", "sign_count": 0,
        "backup_eligible": True, "backed_up": True, "user_handle": store.webauthn_user_handle(),
    })
    artifacts = (Path(__file__).resolve().parents[2]
                 / "docs/realignment/artifacts/workflow-studio/mixed-review-2026-10-11")
    artifacts.mkdir(parents=True, exist_ok=True)
    order_label = "-".join(decision_order)
    capture_names = [f"needs-you-{order_label}-390.png", f"needs-you-{order_label}-320.png",
                     f"mixed-review-{order_label}-trace.zip"]
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        context.add_cookies([{"name": "hutch_session", "value": paired["session_token"], "url": base}])
        page.goto(base + "/")
        page.locator("#phone-root .phone-brand").wait_for()
        page.locator('.phone-tabs [data-phone-tab="review"]').click()
        question_card = page.locator(
            f'.phone-question-card [data-question-id="{pending_question["id"]}"]').locator("..")
        approval_card = page.locator(
            f'.approval-card [data-phone-approve="{approval.id}"]').locator("..").locator("..")
        question_card.wait_for()
        approval_card.wait_for()
        assert page.locator(".phone-question-card").count() == 1
        assert page.locator(".approval-card").count() == 1
        assert question_card.get_by_text(pending_question["id"], exact=True).is_visible()
        assert approval_card.get_by_text(approval.id, exact=True).is_visible()
        page.screenshot(path=str(artifacts / capture_names[0]), full_page=True, animations="disabled")

        page.set_viewport_size({"width": 320, "height": 780})
        overflow_320 = page.evaluate("document.documentElement.scrollWidth - innerWidth")
        assert overflow_320 <= 1
        button_heights_320 = page.locator(
            ".phone-list .phone-actions button, .phone-list .phone-workflow-answer-form button"
        ).evaluate_all("items => items.map(el => Math.round(el.getBoundingClientRect().height))")
        assert button_heights_320 and min(button_heights_320) >= 44
        page.screenshot(path=str(artifacts / capture_names[1]), full_page=True, animations="disabled")
        page.set_viewport_size({"width": 390, "height": 844})

        for decision_index, decision in enumerate(decision_order):
            if decision == "question":
                current_question = page.locator(
                    f'.phone-workflow-answer-form[data-question-id="{pending_question["id"]}"]').locator("..")
                current_question.locator('select[name="answer"]').select_option("yes")
                with page.expect_response(lambda response: response.url.endswith(
                        f"/api/v1/phone/workflows/questions/{pending_question['id']}/answer")) as answered:
                    current_question.get_by_role("button", name="Send answer").click()
                assert answered.value.status == 200, answered.value.text()
                wait_for(lambda: page.locator(".phone-question-card").count() == 0)
                expected_approval_count = 1 if decision_index == 0 else 0
                wait_for(lambda: page.locator(".approval-card").count() == expected_approval_count)
                if expected_approval_count:
                    assert page.get_by_text(approval.id, exact=True).is_visible()
            else:
                allow = page.locator(f'.approval-card [data-phone-approve="{approval.id}"]')
                with page.expect_response(lambda response: response.url.endswith(
                        f"/api/v1/actions/approvals/{approval.id}/approve")) as approved:
                    allow.click()
                assert approved.value.status == 200, approved.value.text()
                wait_for(lambda: store.get_run(action_run.id).status is RunStatus.succeeded)
                wait_for(lambda: page.locator(".approval-card").count() == 0)
                expected_question_count = 1 if decision_index == 0 else 0
                wait_for(lambda: page.locator(".phone-question-card").count() == expected_question_count)
                if expected_question_count:
                    assert page.get_by_text(pending_question["id"], exact=True).is_visible()

        wait_for(lambda: wstore.workflow_run(store, workflow.workflow_run_id)["status"] == "succeeded")
        assert store.get_approval(approval.id).status.value == "approved"
        assert page.locator(".phone-question-card, .approval-card").count() == 0
        assert not errors, errors
    finally:
        context.tracing.stop(path=str(artifacts / capture_names[2]))
        context.close()

    (artifacts / f"results-{order_label}.json").write_text(json.dumps({
        "test": "tests/e2e/test_browser.py::test_paired_phone_keeps_mixed_question_and_approval_pending_in_either_order",
        "decision_order": list(decision_order),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "browser": browser.browser_type.name, "browser_version": browser.version,
        "playwright": package_version("playwright"),
        "workflow_question_id": pending_question["id"], "approval_id": approval.id,
        "final_workflow_status": wstore.workflow_run(store, workflow.workflow_run_id)["status"],
        "final_approval_status": store.get_approval(approval.id).status.value,
        "pending_work_after_first_decision": "the other request remained visible and pending",
        "viewports_css_px": {"phone": [390, 844], "compact_phone": [320, 780]},
        "compact_phone_overflow_px": overflow_320,
        "compact_phone_action_min_height_px": min(button_heights_320),
        "page_errors": errors,
        "artifact_sha256": {name: hashlib.sha256((artifacts / name).read_bytes()).hexdigest()
                            for name in capture_names},
        "source_sha256": {name: hashlib.sha256((Path(__file__).resolve().parents[2] / name).read_bytes()).hexdigest()
                          for name in ("src/hutch/server/static/app.js", "src/hutch/server/workflows_api.py",
                                       "tests/e2e/test_browser.py")},
    }, indent=2) + "\n")



@pytest.mark.parametrize("decision_order", [(0, 1), (1, 0)])
def test_paired_phone_keeps_multiple_approvals_independently_pending(
        browser, live, decision_order):
    base, app = live
    store, engine = app.state.store, app.state.engine
    approvals = []
    runs = []
    for index in range(2):
        bot = store.create_bot(Bot(name=f"phone-approval-order-{index}", model="mock/demo",
                                   tools=["files"], approval_mode=ApprovalMode.ask))
        run = engine.submit(bot, "write a report")
        runs.append(run)
        engine.dispatch_pending()
        wait_for(lambda run_id=run.id: store.get_run(run_id).status is RunStatus.waiting_approval)
        approval = next(a for a in store.pending_approvals() if a.run_id == run.id)
        approvals.append(approval)

    enrollment, outcome = store.exchange_pairing_code(
        store.create_pairing_code(), "Multiple approval phone", "browser-test")
    assert outcome == "ok" and enrollment
    paired = store.finish_passkey_enrollment(enrollment["token"], {
        "credential_id": secrets.token_bytes(24), "public_key": b"multiple-phone-approval-key",
        "sign_count": 0, "backup_eligible": True, "backed_up": True,
        "user_handle": store.webauthn_user_handle(),
    })
    artifacts = (Path(__file__).resolve().parents[2]
                 / "docs/realignment/artifacts/workflow-studio/multiple-approvals-2026-10-11")
    artifacts.mkdir(parents=True, exist_ok=True)
    order_label = "-".join(str(index) for index in decision_order)
    capture_names = [f"approvals-{order_label}-390.png", f"approvals-{order_label}-320.png",
                     f"approvals-{order_label}-trace.zip"]
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        context.add_cookies([{"name": "hutch_session", "value": paired["session_token"], "url": base}])
        page.goto(base + "/")
        page.locator("#phone-root .phone-brand").wait_for()
        page.locator('.phone-tabs [data-phone-tab="review"]').click()
        cards = page.locator(".approval-card")
        wait_for(lambda: cards.count() == 2)
        for approval in approvals:
            card = page.locator(f'.approval-card [data-phone-approve="{approval.id}"]').locator(
                "xpath=ancestor::article[contains(@class,'approval-card')]"
            )
            assert card.get_by_text(approval.id, exact=True).is_visible()
            assert card.get_by_role("heading", name=approval.action).is_visible()
            for name in ("Allow once", "Deny"):
                button = card.get_by_role("button", name=name)
                describedby = button.get_attribute("aria-describedby").split()
                description = " ".join(page.locator(f'[id="{element_id}"]').inner_text()
                                       for element_id in describedby)
                assert approval.action in description and approval.id in description
                assert card.get_by_role(
                    "button", name=name,
                    description=re.compile(re.escape(approval.action) + r".*" + re.escape(approval.id)),
                ).is_visible()
        page.screenshot(path=str(artifacts / capture_names[0]), full_page=True, animations="disabled")

        page.set_viewport_size({"width": 320, "height": 780})
        overflow_320 = page.evaluate("document.documentElement.scrollWidth - innerWidth")
        assert overflow_320 <= 1
        target_heights_320 = cards.locator(".phone-actions button").evaluate_all(
            "items => items.map(el => Math.round(el.getBoundingClientRect().height))")
        assert len(target_heights_320) == 4 and min(target_heights_320) >= 44
        page.screenshot(path=str(artifacts / capture_names[1]), full_page=True, animations="disabled")
        page.set_viewport_size({"width": 390, "height": 844})

        for decision_index, approval_index in enumerate(decision_order):
            approval = approvals[approval_index]
            button = page.locator(f'.approval-card [data-phone-approve="{approval.id}"]')
            assert button.is_visible()
            with page.expect_response(lambda response, aid=approval.id: response.url.endswith(
                    f"/api/v1/actions/approvals/{aid}/approve")) as response_info:
                button.click()
            assert response_info.value.status == 200, response_info.value.text()
            wait_for(lambda run_id=runs[approval_index].id:
                     store.get_run(run_id).status is RunStatus.succeeded)
            expected_card_count = 1 if decision_index == 0 else 0
            wait_for(lambda expected=expected_card_count: cards.count() == expected)
            remaining_index = decision_order[decision_index + 1] if decision_index == 0 else None
            if remaining_index is not None:
                remaining = approvals[remaining_index]
                assert store.get_approval(remaining.id).status.value == "pending"
                assert page.get_by_text(remaining.id, exact=True).is_visible()
                assert page.locator(f'.approval-card [data-phone-approve="{remaining.id}"]').is_visible()
            assert store.get_approval(approval.id).status.value == "approved"

        wait_for(lambda: cards.count() == 0)
        assert all(store.get_approval(approval.id).status.value == "approved" for approval in approvals)
        assert not errors, errors
    finally:
        context.tracing.stop(path=str(artifacts / capture_names[2]))
        context.close()

    (artifacts / f"results-{order_label}.json").write_text(json.dumps({
        "test": "tests/e2e/test_browser.py::test_paired_phone_keeps_multiple_approvals_independently_pending",
        "decision_order": [approvals[index].id for index in decision_order],
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "browser": browser.browser_type.name, "browser_version": browser.version,
        "playwright": package_version("playwright"),
        "approval_ids": [approval.id for approval in approvals],
        "approval_controls_reference_action_and_id_in_aria_description": True,
        "pending_after_first_decision": approvals[decision_order[1]].id,
        "final_approval_statuses": [store.get_approval(approval.id).status.value for approval in approvals],
        "viewports_css_px": {"phone": [390, 844], "compact_phone": [320, 780]},
        "compact_phone_overflow_px": overflow_320,
        "compact_phone_action_min_height_px": min(target_heights_320),
        "page_errors": errors,
        "artifact_sha256": {name: hashlib.sha256((artifacts / name).read_bytes()).hexdigest()
                            for name in capture_names},
        "source_sha256": {name: hashlib.sha256((Path(__file__).resolve().parents[2] / name).read_bytes()).hexdigest()
                          for name in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                       "src/hutch/server/workflows_api.py", "tests/e2e/test_browser.py")},
    }, indent=2) + "\n")

def test_workflow_publishes_a_verified_chart_that_renders_in_a_browser(browser, live):
    import base64
    from hutch.workflow.submit import status as workflow_status, submit_workflow

    base, app = live
    store, engine = app.state.store, app.state.engine
    bot = store.create_bot(Bot(name="workflow-chart-browser", model="mock/demo", tools=[]))
    plan = {
        "name": "category-chart-preview",
        "inputs": {"rows": {"type": "array", "max_items": 8}},
        "envelope": {"tools": [], "models": []},
        "budget": {"max_nodes": 4, "max_model_calls": 0, "max_wall_seconds": 60},
        "nodes": [
            {"kind": "transform", "id": "counts", "op": "group_count",
             "args": {"items": {"ref": "input.rows"}, "by": "category"}},
            {"kind": "transform", "id": "chart", "op": "bar_chart_svg",
             "args": {"values": {"ref": "counts"}, "title": "Purchases by category"}},
            {"kind": "publish", "id": "deliver", "artifacts": [
                {"name": "category-chart", "ref": "chart", "media_type": "image/svg+xml",
                 "primary": True}]},
            {"kind": "verify", "id": "verify", "checks": [
                {"kind": "artifact", "ref": "deliver.artifacts[0]", "min_bytes": 300}]},
        ],
        "outputs": ["chart", "deliver"],
    }
    submission = submit_workflow(store, bot=bot, plan=plan, inputs={"rows": [
        {"category": "hardware"}, {"category": "hardware"}, {"category": "services"},
        {"category": "software"}, {"category": "software"}, {"category": "software"},
    ]}, definition_name="category-chart-preview")
    deadline = time.monotonic() + 20
    view = None
    while time.monotonic() < deadline:
        engine.tick()
        view = workflow_status(store, submission.workflow_run_id)
        if view["workflow"]["status"] in {"succeeded", "failed", "stopped", "outcome_unknown"}:
            break
        time.sleep(0.05)
    assert view and view["workflow"]["status"] == "succeeded", view
    nodes = {node["site_id"]: node for node in view["nodes"]}
    assert nodes["verify"]["result"]["verified"] is True
    artifact = view["workflow"]["result"]["artifacts"][0]
    assert artifact["media_type"] == "image/svg+xml"

    artifacts = (Path(__file__).resolve().parents[2]
                 / "docs/realignment/artifacts/dynamic-workflows/expense-chart")
    artifacts.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 960, "height": 420})
    page = context.new_page()
    errors, external = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external.append(request.url)
            if urlsplit(request.url).hostname not in {"127.0.0.1", "localhost", None} else None)
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        downloaded = page.request.get(
            f"{base}/api/v1/tasks/runs/{submission.attempt_run_id}/artifacts/"
            f"{Path(artifact['artifact']).name}")
        assert downloaded.status == 200
        assert downloaded.headers.get("x-hutch-artifact-verified") == "sha256"
        assert downloaded.headers.get("etag", "").strip('"') == artifact["sha256"]
        svg = downloaded.body().decode("utf-8")
        assert 'role="img"' in svg and "hardware: 2" in svg and "software: 3" in svg
        (artifacts / "category-chart.svg").write_text(svg)
        data_uri = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode("ascii")
        page.set_content(f'''<!doctype html><html lang="en"><meta charset="utf-8">
          <style>body{{margin:0;padding:24px;background:#eef2f0;font-family:system-ui,sans-serif}}
          main{{width:min(100%,760px);margin:auto;padding:20px;background:#fff;border:1px solid #cbd5d0;
          border-radius:12px}}img{{display:block;max-width:100%;height:auto}}</style>
          <main><img id="verified-chart" alt="Purchases by category chart" src="{data_uri}"></main>
          </html>''')
        page.locator("#verified-chart").evaluate("element => element.decode()")
        box = page.locator("#verified-chart").bounding_box()
        assert box and box["width"] == 720 and box["height"] > 100
        overflow_px = page.evaluate("document.documentElement.scrollWidth - innerWidth")
        assert overflow_px <= 1
        page.screenshot(path=str(artifacts / "category-chart-preview.png"), full_page=True,
                        animations="disabled")
        assert not errors and not external, {"page_errors": errors, "external_requests": external}
    finally:
        context.tracing.stop(path=str(artifacts / "category-chart-trace.zip"))
        context.close()

    source_paths = ("src/hutch/workflow/ops.py", "src/hutch/workflow/engine.py",
                    "tests/test_workflow_ops.py", "tests/test_workflow_csv_acceptance.py",
                    "tests/e2e/test_browser.py")
    artifact_paths = ("category-chart.svg", "category-chart-preview.png", "category-chart-trace.zip")
    (artifacts / "results.json").write_text(json.dumps({
        "test": "tests/e2e/test_browser.py::test_workflow_publishes_a_verified_chart_that_renders_in_a_browser",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "browser": browser.browser_type.name, "browser_version": browser.version,
        "playwright": package_version("playwright"), "workflow_id": submission.workflow_run_id,
        "artifact_sha256": artifact["sha256"], "artifact_bytes": artifact["bytes"],
        "verification": nodes["verify"]["result"],
        "rendered_svg_css_px": [box["width"], box["height"]],
        "horizontal_overflow_px": overflow_px,
        "page_errors": errors, "external_requests": external,
        "artifact_file_sha256": {name: hashlib.sha256((artifacts / name).read_bytes()).hexdigest()
                                  for name in artifact_paths},
        "source_sha256": {name: hashlib.sha256((Path(__file__).resolve().parents[2] / name).read_bytes()).hexdigest()
                          for name in source_paths},
    }, indent=2) + "\n")


def test_workflow_studio_lists_and_resolves_every_pending_question(browser, live):
    import hashlib
    from datetime import datetime, timezone
    from pathlib import Path

    from hutch.workflow import persistence as workflow_store

    base, app = live
    store = app.state.store
    bot = Bot(name="workflow-multiple-questions", display_name="Multi question fixture",
              model="mock/demo", tools=[])
    store.upsert_bot(bot)
    conversation, _ = store.create_conversation(
        bot.id, "Workflow question review", idem_key="workflow-multi-question-conversation",
        request_hash="workflow-multi-question-conversation")
    title = "review-two-independent-settings"
    plan = {
        "name": title,
        "inputs": {"settings": {"type": "array", "max_items": 2}},
        "envelope": {"tools": [], "max_parallel_steps": 2},
        "budget": {"max_nodes": 8, "max_model_calls": 0},
        "nodes": [
            {"kind": "map", "id": "review", "over": {"ref": "input.settings"},
             "item_key": "key", "concurrency": 2, "max_items": 2, "body": [
                 {"kind": "ask", "id": "confirm", "inputs": {"label": {"ref": "item.label"}},
                  "question": "How should {{label}} be configured?", "timeout_seconds": 600}]},
            {"kind": "transform", "id": "combine", "op": "to_json",
             "args": {"value": {"ref": "review.items"}}},
        ],
    }
    out = Path(__file__).resolve().parents[2] / \
        "docs/realignment/artifacts/workflow-studio/multiple-questions-2026-10-11"
    out.mkdir(parents=True, exist_ok=True)
    page = browser.new_page(viewport={"width": 1440, "height": 960}, device_scale_factor=1)
    context = page.context
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    trace = []
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        saved = page.request.post(f"{base}/api/v1/workflows", data={"name": title, "plan": plan},
                                  headers={"Idempotency-Key": "workflow-multi-question-save"})
        assert saved.status == 201, saved.text()
        definition = saved.json()
        launched = page.request.post(
            f"{base}/api/v1/workflows/{definition['id']}/runs",
            data={"bot": bot.name, "conversation_id": conversation["id"],
                  "inputs": {"settings": [{"key": "first", "label": "First setting"},
                                          {"key": "second", "label": "Second setting"}]}},
            headers={"Idempotency-Key": "workflow-multi-question-launch"})
        assert launched.status == 201, launched.text()
        workflow_id = launched.json()["workflow_run_id"]
        deadline = time.monotonic() + 20
        pending_questions = []
        while time.monotonic() < deadline:
            pending_questions = workflow_store.questions(store, workflow_id, status="pending")
            workflow = workflow_store.workflow_run(store, workflow_id)
            attempt = store.get_run(workflow["attempt_run_id"]) if workflow else None
            if len(pending_questions) == 2 and attempt is not None and attempt.status is RunStatus.waiting_workflow:
                break
            time.sleep(0.05)
        assert {question["site_id"] for question in pending_questions} == {"review.confirm"}
        assert len({question["instance_key"] for question in pending_questions}) == 2

        authoritative = page.request.get(f"{base}/api/v1/workflows/runs/{workflow_id}")
        assert authoritative.status == 200, authoritative.text()
        workflow_detail = authoritative.json()
        question_projection = {question["id"]: question for question in workflow_detail["questions"]}
        for question in pending_questions:
            projected = question_projection[question["id"]]
            assert projected["revision_id"] == workflow_detail["workflow"]["revision_id"]
            assert projected["attempt_run_id"] == workflow_detail["workflow"]["attempt_run_id"]

        page.goto(f"{base}/#/chat/{bot.name}")
        panel = page.locator("#workflow-panel")
        panel.wait_for(state="visible")
        page.get_by_role("heading", name="Review Two Independent Settings").wait_for()
        panel.get_by_role("heading", name="Needs you").wait_for()
        panel.get_by_text("2 pending questions", exact=True).wait_for()
        forms = panel.locator("[data-workflow-question-form]")
        assert forms.count() == 2
        assert {forms.nth(index).get_attribute("data-question-id") for index in range(2)} == {
            question["id"] for question in pending_questions}
        assert "2 discovered instances" in panel.locator(".workflow-panel-meta").inner_text()
        discovered = panel.locator('[aria-label="Discovered workflow instances"] li')
        assert discovered.count() == 2
        assert {discovered.nth(index).inner_text().splitlines()[1] for index in range(2)} == {
            question["instance_key"] for question in pending_questions}
        assert all("Waiting" in discovered.nth(index).inner_text() for index in range(2))
        assert panel.get_by_text("How should First setting be configured?", exact=True).count() == 1
        assert panel.get_by_text("How should Second setting be configured?", exact=True).count() == 1
        for question in pending_questions:
            prompt = question["question"]
            question_name = re.compile(
                rf"Question {re.escape(question['id'])}\s+{re.escape(prompt)}"
            )
            accessible_form = panel.get_by_role("form", name=question_name)
            assert accessible_form.count() == 1
            answer_name = re.compile(
                rf"Question {re.escape(question['id'])}\s+{re.escape(prompt)}\s+Your answer"
            )
            answer = accessible_form.get_by_role(
                "textbox",
                name=answer_name,
                description=re.compile(r"This answer resolves only this question"),
            )
            assert answer.count() == 1
        trace.append({"state": "computed-accessibility-semantics", "named_forms": len(pending_questions),
                      "textbox_names_include_question_id_and_prompt": True,
                      "authority_boundary_is_a_textbox_description": True,
                      "operating_system_screen_reader": "not tested"})

        sizes = [("desktop", 1440, 960), ("tablet", 768, 1024),
                 ("phone", 360, 800), ("compact-phone", 320, 800)]
        for label, width, height in sizes:
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(80)
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, f"{label} has horizontal overflow: {overflow}px"
            viewport_forms = panel.locator("[data-workflow-question-form]")
            assert viewport_forms.count() == 2
            page.screenshot(path=str(out / f"waiting-{label}.png"),
                            full_page=True, animations="disabled")
            panel.evaluate("element => element.querySelectorAll('[data-workflow-question-form]')[1]?.scrollIntoView({block: 'center'})")
            geometry = page.evaluate("""() => {
              const panel = document.querySelector('#workflow-panel');
              const forms = panel?.querySelectorAll('[data-workflow-question-form]') || [];
              const question = forms[1]?.querySelector('p');
              const button = forms[1]?.querySelector('[type=submit]');
              if (!panel || !question || !button) return null;
              const rect = element => {
                const box = element.getBoundingClientRect();
                return {x: box.x, y: box.y, width: box.width, height: box.height};
              };
              return {panel: rect(panel), question: rect(question), button: rect(button)};
            }""")
            assert geometry
            panel_bounds, question_bounds = geometry["panel"], geometry["question"]
            answer_button_bounds = geometry["button"]
            assert (question_bounds["y"] >= panel_bounds["y"]
                    and question_bounds["y"] + question_bounds["height"] <= panel_bounds["y"] + panel_bounds["height"] + 1), (
                        label, panel_bounds, question_bounds)
            if width <= 820:
                assert answer_button_bounds["height"] >= 44, (label, answer_button_bounds)
            page.screenshot(path=str(out / f"second-question-{label}.png"),
                            full_page=True, animations="disabled")
            panel.evaluate("""element => {
              const list = element.querySelector('[aria-label="Discovered workflow instances"]');
              const top = list.getBoundingClientRect().top - element.getBoundingClientRect().top + element.scrollTop;
              element.scrollTo({top: Math.max(0, top - 48), behavior: 'instant'});
            }""")
            instance_rows = panel.locator('[aria-label="Discovered workflow instances"] li')
            assert instance_rows.count() == 2
            assert all(question["instance_key"] in instance_rows.nth(index).inner_text()
                       for index, question in enumerate(sorted(pending_questions,
                                                               key=lambda item: item["instance_key"])))
            page.screenshot(path=str(out / f"discovered-{label}.png"),
                            full_page=True, animations="disabled")
            panel.evaluate("element => element.scrollTo({top: 0, behavior: 'instant'})")
            trace.append({"viewport": label, "size": [width, height], "pending_question_forms": 2,
                          "horizontal_overflow_px": overflow,
                          "second_answer_button_height_px": answer_button_bounds["height"],
                          "question_backed_discovered_instances": instance_rows.count(),
                          "second_question_id_visible_in_scroll_panel": True})

        first = panel.locator(f'[data-question-id="{pending_questions[0]["id"]}"]')
        first.locator("textarea[name=answer]").fill("Alpha setting")
        with page.expect_response(lambda response: response.url.endswith(
                f"/v1/workflows/questions/{pending_questions[0]['id']}/answer")) as answer_response:
            first.get_by_role("button", name="Send answer").click()
        assert answer_response.value.status == 200, answer_response.value.text()
        panel.locator(f'[data-question-id="{pending_questions[1]["id"]}"]').wait_for(state="visible")
        assert panel.locator("[data-workflow-question-form]").count() == 1
        panel.get_by_text("1 pending question", exact=True).wait_for()
        panel.get_by_text("Current reason: waiting for 1 answer(s)", exact=True).wait_for()
        assert "2 discovered instances" in panel.locator(".workflow-panel-meta").inner_text()
        partial_rows = panel.locator('[aria-label="Discovered workflow instances"] li')
        assert partial_rows.count() == 2
        assert {partial_rows.nth(index).inner_text().splitlines()[-1] for index in range(2)} == {
            "Answer received", "Waiting"}
        page.set_viewport_size({"width": 360, "height": 800})
        page.screenshot(path=str(out / "partial-answer-phone.png"), full_page=True,
                        animations="disabled")
        panel.evaluate("""element => {
          const list = element.querySelector('[aria-label="Discovered workflow instances"]');
          const top = list.getBoundingClientRect().top - element.getBoundingClientRect().top + element.scrollTop;
          element.scrollTo({top: Math.max(0, top - 48), behavior: 'instant'});
        }""")
        page.screenshot(path=str(out / "partial-discovered-phone.png"), full_page=True,
                        animations="disabled")
        panel.evaluate("element => element.scrollTo({top: 0, behavior: 'instant'})")
        trace.append({"state": "one-answer-received", "discovered_instances": [
            partial_rows.nth(index).inner_text().splitlines()[-1] for index in range(2)],
            "pending_question_forms": 1})
        wait_for_page(page,
            """questionId => document.activeElement?.closest('[data-workflow-question-form]')?.dataset.questionId === questionId""",
            arg=pending_questions[1]["id"])
        remaining = panel.locator(f'[data-question-id="{pending_questions[1]["id"]}"]')
        remaining.locator("textarea[name=answer]").fill("Beta setting")
        with page.expect_response(lambda response: response.url.endswith(
                f"/v1/workflows/questions/{pending_questions[1]['id']}/answer")) as answer_response:
            remaining.get_by_role("button", name="Send answer").click()
        assert answer_response.value.status == 200, answer_response.value.text()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            current = workflow_store.workflow_run(store, workflow_id)
            if current and current["status"] == "succeeded":
                break
            time.sleep(0.05)
        assert workflow_store.workflow_run(store, workflow_id)["status"] == "succeeded"
        page.get_by_role("button", name="Refresh").click()
        wait_for_page(page, "document.querySelector('#workflow-panel .workflow-panel-head')?.innerText.includes('Finished')")
        assert "4 discovered instances" in panel.locator(".workflow-panel-meta").inner_text()
        completed_rows = panel.locator('[aria-label="Discovered workflow instances"] li')
        assert completed_rows.count() == 4
        assert all("Completed" in completed_rows.nth(index).inner_text() for index in range(4))
        completed_question_rows = [completed_rows.nth(index).inner_text() for index in range(4)
                                   if "review.confirm" in completed_rows.nth(index).inner_text()]
        assert len(completed_question_rows) == 2
        assert all("Completed" in row for row in completed_question_rows)
        assert not errors, errors
        trace.append({"state": "answers-submitted", "answer_order": [
            pending_questions[0]["id"], pending_questions[1]["id"]], "workflow_status": "succeeded",
            "page_errors": errors})
        page.set_viewport_size({"width": 360, "height": 800})
        panel.evaluate("""element => {
          const list = element.querySelector('[aria-label="Discovered workflow instances"]');
          const top = list.getBoundingClientRect().top - element.getBoundingClientRect().top + element.scrollTop;
          element.scrollTo({top: Math.max(0, top - 48), behavior: 'instant'});
        }""")
        page.screenshot(path=str(out / "discovered-complete-phone.png"), full_page=True, animations="disabled")
        panel.evaluate("element => element.scrollTo({top: 0, behavior: 'instant'})")
        page.screenshot(path=str(out / "answered-phone.png"), full_page=True, animations="disabled")
        results_path = out / "results.json"
        results = {
            "test": "tests/e2e/test_browser.py::test_workflow_studio_lists_and_resolves_every_pending_question",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "browser": browser.browser_type.name, "browser_version": browser.version,
            "playwright": package_version("playwright"),
            "scenario": "A bounded map exposes two independent durable questions; answering one preserves the other, then the workflow completes.",
            "workflow_status": "succeeded", "question_ids": [question["id"] for question in pending_questions],
            "trace": trace, "page_errors": errors,
            "map_item_behavior": {
                "browser_scope": "one independent ask per map item, shown together up to unresolved-item concurrency",
                "engine_coverage": "same-item independent asks publish together; dependent asks wait for prerequisites",
                "tests": [
                    "tests/test_workflow_engine.py::test_bounded_map_collects_independent_questions_within_an_item_after_restart",
                    "tests/test_workflow_engine.py::test_bounded_map_holds_dependent_question_until_its_answer_arrives",
                    "tests/test_workflow_engine.py::test_bounded_map_exposes_one_question_per_item_up_to_concurrency_after_restart",
                ],
            },
            "partial_answer_state": {
                "pending_question_forms": 1,
                "discovered_statuses": ["Answer received", "Waiting"],
                "workflow_reason": "waiting for 1 answer(s)",
                "focus_moves_to_remaining_question": True,
            },
            "terminal_discovered_instances": {
                "count": completed_rows.count(),
                "rows": [completed_rows.nth(index).inner_text() for index in range(completed_rows.count())],
                "label": "Completed (not verified)",
            },
            "verification": {
                "browser_result": "passed; this artifact is written only after all browser assertions succeed",
                "focused_engine_api_phone_effect_result": "116 passed in 59.59s on the preceding behavior slice; this slice changes only accessible names/descriptions and evidence",
                "static_checks": "Python compilation, JavaScript syntax check, and git diff --check passed",
                "provider_calls": 0,
            },
            "visual_validation": {
                "viewports_css_px": {"desktop": [1440, 960], "tablet": [768, 1024],
                                     "phone": [360, 800], "compact_phone": [320, 800]},
                "horizontal_overflow_px": {item["viewport"]: item["horizontal_overflow_px"]
                                           for item in trace if "viewport" in item},
                "phone_answer_target_min_height_px": 44,
                "opened_captures": ["waiting-desktop.png", "second-question-compact-phone.png"],
                "actual_browser_zoom": "unverified; this headless Chromium build does not support CDP Browser.setZoomLevel",
                "visual_observation": "The semantic change does not alter layout. The internal scroll keeps the second question reachable; the 320px view wraps its durable ID and prompt without horizontal overflow.",
            },
            "source_sha256": {
                path: hashlib.sha256((Path(__file__).resolve().parents[2] / path).read_bytes()).hexdigest()
                for path in (
                    "src/hutch/workflow/engine.py", "src/hutch/workflow/persistence.py",
                    "src/hutch/server/workflows_api.py", "src/hutch/server/static/app.js",
                    "src/hutch/server/static/style.css", "tests/e2e/test_browser.py",
                    "tests/test_workflow_engine.py", "tests/test_workflow_api.py",
                    "tests/test_remote_pairing.py", "tests/test_workflow_effect_receipts.py",
                )
            },
        }
        context.tracing.stop(path=str(out / "trace.zip"))
        results["artifact_sha256"] = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(out.iterdir()) if path.is_file() and path != results_path
        }
        results_path.write_text(json.dumps(results, indent=2) + "\n")
    finally:
        if context.tracing:
            try:
                context.tracing.stop(path=str(out / "trace.zip"))
            except Exception:
                pass
        context.close()


def test_workflow_studio_policy_steps_start_answer_and_stop_at_all_viewports(browser, live):
    from hutch.workflow import persistence as workflow_store

    base, app = live
    store = app.state.store
    bot = Bot(name="workflow-studio", display_name="Workflow studio fixture", model="mock/demo", tools=[],
              approval_mode=ApprovalMode.auto)
    store.upsert_bot(bot)
    conversation, _ = store.create_conversation(
        bot.id, "Dynamic workflow review", idem_key="workflow-studio-conversation",
        request_hash="workflow-studio-conversation")
    workflow_title = "review-source-findings-with-independent-check"
    plan = {
        "name": workflow_title,
        "envelope": {"tools": []},
        "budget": {"max_nodes": 8, "max_model_calls": 0},
        "nodes": [{"kind": "ask", "id": "review", "title": "Review findings",
                   "question": "Which findings should be included?", "options": ["All", "Only verified"],
                   "timeout_seconds": 600},
                  {"kind": "transform", "id": "carry_answer", "op": "constant",
                   "args": {"value": {"ref": "review.answer"}}}],
    }
    artifacts = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/workflow-studio/pause-resume-2026-10-11"
    artifacts.mkdir(parents=True, exist_ok=True)
    page = browser.new_page(viewport={"width": 1440, "height": 960}, device_scale_factor=1)
    context = page.context
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    trace = []
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        saved = page.request.post(f"{base}/api/v1/workflows", data={"name": workflow_title, "plan": plan},
                                  headers={"Idempotency-Key": "workflow-studio-save"})
        assert saved.status == 201, saved.text()
        definition = saved.json()
        first = page.request.post(f"{base}/api/v1/workflows/{definition['id']}/runs",
                                  data={"bot": bot.name, "conversation_id": conversation["id"], "inputs": {}},
                                  headers={"Idempotency-Key": "workflow-studio-first-run"})
        assert first.status == 201, first.text()
        first_workflow_id = first.json()["workflow_run_id"]
        deadline = time.monotonic() + 20
        pending_questions = []
        while time.monotonic() < deadline:
            pending_questions = workflow_store.questions(store, first_workflow_id, status="pending")
            if pending_questions:
                break
            time.sleep(0.05)
        assert pending_questions

        page.goto(f"{base}/#/chat/{bot.name}")
        panel = page.locator("#workflow-panel")
        panel.wait_for(state="visible")
        page.get_by_role("heading", name="Review Source Findings With Independent Check").wait_for()
        panel.get_by_text("Waiting · saved workflow", exact=True).wait_for()
        panel.get_by_text("Planned structure", exact=True).wait_for()
        panel.get_by_text("Discovered instances", exact=True).wait_for()
        question_form = panel.locator("[data-workflow-question-form]")
        question_form.wait_for(state="visible")
        question_id = question_form.get_attribute("data-question-id")
        assert question_id == pending_questions[0]["id"]

        sizes = [("desktop", 1440, 960), ("tablet", 768, 1024), ("phone", 360, 800),
                 ("compact-phone", 320, 800)]
        for label, width, height in sizes:
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(80)
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, f"{label} has horizontal overflow: {overflow}px"
            page.screenshot(path=str(artifacts / f"{label}-waiting.png"), full_page=True, animations="disabled")
            card_box = panel.bounding_box()
            title_locator = panel.locator("h2")
            actions_locator = panel.locator(".workflow-panel-actions")
            title_locator.wait_for(state="visible")
            actions_locator.wait_for(state="visible")
            # Chat events can trigger a workflow refresh while the page is
            # resizing. Measure both elements in one browser turn so an atomic
            # panel replacement cannot split the geometry sample.
            def panel_header_bounds():
                return page.evaluate("""() => {
                  const title = document.querySelector('#workflow-panel h2');
                  const actions = document.querySelector('#workflow-panel .workflow-panel-actions');
                  const visible = element => element && element.isConnected &&
                    element.getClientRects().length && getComputedStyle(element).visibility !== 'hidden';
                  if (!visible(title) || !visible(actions)) return null;
                  const bounds = element => {
                    const rect = element.getBoundingClientRect();
                    return {x: rect.x, y: rect.y, width: rect.width, height: rect.height};
                  };
                  return {title: bounds(title), actions: bounds(actions)};
                }""")

            header_bounds = wait_for(panel_header_bounds, timeout=5)
            title_box, actions_box = header_bounds["title"], header_bounds["actions"]
            assert card_box and card_box["x"] >= 0 and card_box["x"] + card_box["width"] <= width + 1
            assert title_box and actions_box
            if width <= 820:
                assert title_box["width"] >= card_box["width"] * 0.7
                assert title_box["y"] + title_box["height"] <= actions_box["y"] + 1
            trace.append({"viewport": label, "size": [width, height], "state": "waiting",
                          "horizontal_overflow_px": overflow,
                          "panel_bounds": {key: round(value, 2) for key, value in card_box.items()},
                          "title_bounds": {key: round(value, 2) for key, value in title_box.items()},
                          "actions_bounds": {key: round(value, 2) for key, value in actions_box.items()}})

        page.set_viewport_size({"width": 1440, "height": 960})
        page.wait_for_timeout(80)
        selected = page.request.get(f"{base}/api/v1/workflows/runs/{first_workflow_id}").json()
        assert selected["pause_available"] is True
        pause_body = {"expected_revision_id": selected["workflow"]["revision_id"],
                      "expected_generation": selected["workflow"]["attempt_run_id"]}
        pause = panel.get_by_role("button", name="Pause workflow")
        with page.expect_response(lambda response: response.url.endswith(f"/workflows/runs/{first_workflow_id}/pause")) as pause_response:
            pause.click()
        assert pause_response.value.status == 200, pause_response.value.text()
        assert pause_response.value.request.headers.get("idempotency-key")
        assert pause_response.value.request.post_data_json == pause_body
        assert pause_response.value.json()["paused"] is True
        panel.get_by_text("Paused · saved workflow", exact=True).wait_for()
        resume_after_pause = panel.get_by_role("button", name="Resume workflow")
        assert resume_after_pause.count() == 1
        wait_for_page(page, "document.activeElement?.dataset.workflowAction === 'resume'", timeout=2000)
        assert resume_after_pause.evaluate("element => document.activeElement === element"), page.evaluate(
            "({tag: document.activeElement?.tagName, id: document.activeElement?.id, "
            "action: document.activeElement?.dataset.workflowAction, "
            "workflow: document.activeElement?.dataset.workflowId, "
            "html: document.activeElement?.outerHTML?.slice(0, 300)})")
        paused_detail = page.request.get(f"{base}/api/v1/workflows/runs/{first_workflow_id}").json()
        assert paused_detail["workflow"]["pause_requested"] is True
        assert paused_detail["resume_available"] is True
        for label, width, height in sizes:
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(80)
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, f"{label} paused view has horizontal overflow: {overflow}px"
            action = panel.locator(".workflow-panel-actions")
            action.wait_for(state="visible")
            resume_target = wait_for(lambda: page.evaluate("""() => {
              const element = document.querySelector('#workflow-panel [data-workflow-action="resume"]');
              if (!element || !element.isConnected || !element.getClientRects().length ||
                  getComputedStyle(element).visibility === 'hidden') return null;
              const rect = element.getBoundingClientRect();
              return {x: rect.x, y: rect.y, width: rect.width, height: rect.height};
            }"""), timeout=5)
            assert resume_target and resume_target["height"] >= (44 if width <= 820 else 24)
            page.screenshot(path=str(artifacts / f"{label}-paused.png"), full_page=True, animations="disabled")
            trace.append({"viewport": label, "size": [width, height], "state": "paused",
                          "horizontal_overflow_px": overflow,
                          "resume_target": {key: round(value, 2) for key, value in resume_target.items()}})
        page.set_viewport_size({"width": 1440, "height": 960})
        page.wait_for_timeout(80)

        question_form = panel.locator("[data-workflow-question-form]")
        answer_field = question_form.locator("textarea[name=answer]")
        answer_field.fill("Include only findings with independent evidence.")
        answer_field.press("Tab")
        send_answer = question_form.get_by_role("button", name="Send answer")
        assert send_answer.evaluate("element => document.activeElement === element")
        page.keyboard.press("Enter")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            held = page.request.get(f"{base}/api/v1/workflows/runs/{first_workflow_id}").json()
            if held["questions"][0]["status"] == "answered":
                break
            time.sleep(0.05)
        assert held["workflow"]["pause_requested"] is True
        assert held["workflow"]["attempt_run_id"] == paused_detail["workflow"]["attempt_run_id"]
        assert held["attempt"]["status"] == "waiting_workflow"
        assert "carry_answer" not in {node["site_id"] for node in held["nodes"]}
        page.wait_for_timeout(2200)
        still_held = page.request.get(f"{base}/api/v1/workflows/runs/{first_workflow_id}").json()
        assert still_held["workflow"]["attempt_run_id"] == held["workflow"]["attempt_run_id"]
        page.screenshot(path=str(artifacts / "desktop-answered-while-paused.png"), full_page=True, animations="disabled")

        resume_button = panel.get_by_role("button", name="Resume workflow")
        with page.expect_response(lambda response: response.url.endswith(f"/workflows/runs/{first_workflow_id}/resume")) as resume_response:
            resume_button.click()
        assert resume_response.value.status == 200, resume_response.value.text()
        assert resume_response.value.request.headers.get("idempotency-key")
        assert resume_response.value.request.post_data_json == pause_body
        assert resume_response.value.json()["paused"] is False
        wait_for_page(page, "document.activeElement?.dataset.workflowAction === 'refresh'", timeout=2000)
        assert panel.get_by_role("button", name="Refresh").evaluate(
            "element => document.activeElement === element")
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            current = workflow_store.workflow_run(store, first_workflow_id)
            if current and current["status"] == "succeeded":
                break
            time.sleep(0.05)
        assert workflow_store.workflow_run(store, first_workflow_id)["status"] == "succeeded"
        panel.get_by_role("button", name="Refresh").click()
        panel.get_by_text("Finished · saved workflow", exact=True).wait_for()
        assert panel.evaluate("element => element.scrollTop") == 0
        assert panel.locator("h2").is_visible()
        page.wait_for_timeout(300)
        page.screenshot(path=str(artifacts / "desktop-finished.png"), full_page=True, animations="disabled")

        page.locator("#studio-conversation-options").click()
        page.locator("#chat-workflow-mode").wait_for(state="visible")
        assert page.locator("#chat-workflow-mode option[value=auto]").is_disabled()
        page.locator("#chat-workflow-mode").select_option("off")
        wait_for(lambda: store.get_conversation_workflow_policy(conversation["id"])["mode"] == "off")
        assert page.locator("#chat-workflow-mode-help").inner_text().strip()
        page.screenshot(path=str(artifacts / "desktop-policy-off.png"), full_page=True, animations="disabled")
        page.keyboard.press("Escape")

        panel.locator("summary", has_text="Saved workflows").click()
        panel.get_by_role("button", name="Run").click()
        page.get_by_role("button", name="Start workflow").click()
        panel.locator("[data-workflow-question-form]").wait_for(state="visible")
        panel.get_by_role("button", name="Stop workflow").click()
        deadline = time.monotonic() + 20
        newest = None
        while time.monotonic() < deadline:
            runs = workflow_store.list_workflow_runs(store, bot_id=bot.id, limit=20)
            newest = next((row for row in runs if row["id"] != first_workflow_id), None)
            if newest and newest["status"] == "stopped":
                break
            time.sleep(0.05)
        assert newest and newest["status"] == "stopped"
        panel.get_by_text("Stopped · saved workflow", exact=True).wait_for()
        assert panel.get_by_role("button", name="Stop workflow").count() == 0
        pw.expect(page.locator("#toast-root .toast")).to_have_count(0, timeout=6000)
        page.screenshot(path=str(artifacts / "desktop-stopped.png"), full_page=True, animations="disabled")
        assert not errors, errors

        context.tracing.stop(path=str(artifacts / "trace.zip"))
        sources = ("src/hutch/models.py", "src/hutch/store.py", "src/hutch/workflow/persistence.py",
                   "src/hutch/workflow/submit.py", "src/hutch/server/workflows_api.py",
                   "src/hutch/server/static/app.js", "src/hutch/server/static/style.css")
        images_and_trace = {file.name: hashlib.sha256(file.read_bytes()).hexdigest()
                            for file in artifacts.iterdir() if file.suffix in {".png", ".zip"}}
        (artifacts / "results.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_workflow_studio_policy_steps_start_answer_and_stop_at_all_viewports",
            "command": "uv run pytest tests/e2e/test_browser.py::test_workflow_studio_policy_steps_start_answer_and_stop_at_all_viewports -q",
            "browser": browser.browser_type.name, "browser_version": browser.version,
            "playwright_version": package_version("playwright"), "viewports": trace,
            "question_id": question_id, "first_workflow_id": first_workflow_id,
            "stopped_workflow_id": newest["id"], "policy_override": store.get_conversation_workflow_policy(conversation["id"]),
            "keyboard_path": ["focus answer", "Tab to Send answer", "Enter submits"],
            "page_errors": errors, "provider_calls": 0,
            "fixture_boundary": "A saved declarative ask workflow uses the real SQLite, supervisor, API and browser path; no model/provider call is made.",
            "source_sha256": {name: hashlib.sha256((Path(__file__).resolve().parents[2] / name).read_bytes()).hexdigest()
                              for name in sources},
            "visual_artifact_sha256": images_and_trace,
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2) + "\n")
    finally:
        context.close()


def test_workflow_question_draft_survives_tcp_disconnect_and_reconnect(browser, live):
    from hutch.workflow import persistence as workflow_store

    base, app = live
    store = app.state.store
    bot = Bot(name="workflow-reconnect", display_name="Workflow reconnect fixture", model="mock/demo", tools=[])
    store.upsert_bot(bot)
    conversation, _ = store.create_conversation(
        bot.id, "Reconnect review", idem_key="workflow-reconnect-conversation",
        request_hash="workflow-reconnect-conversation")
    workflow_title = "review-findings-after-a-connection-drop"
    plan = {
        "name": workflow_title,
        "envelope": {"tools": []},
        "budget": {"max_nodes": 6, "max_model_calls": 0},
        "nodes": [{"kind": "ask", "id": "review", "title": "Review findings",
                   "question": "Which findings should be included?", "options": ["All", "Only verified"],
                   "timeout_seconds": 600},
                  {"kind": "transform", "id": "carry_answer", "op": "constant",
                   "args": {"value": {"ref": "review.answer"}}}],
    }
    artifacts = Path(__file__).resolve().parents[2] / (
        "docs/realignment/artifacts/workflow-studio/workflow-reconnect-2026-10-11")
    artifacts.mkdir(parents=True, exist_ok=True)
    saved = page = context = proxy = None
    errors = []
    try:
        saved = browser.new_page(viewport={"width": 1440, "height": 960})
        created = saved.request.post(f"{base}/api/v1/workflows", data={"name": workflow_title, "plan": plan},
                                     headers={"Idempotency-Key": "workflow-reconnect-save"})
        assert created.status == 201, created.text()
        definition = created.json()
        launched = saved.request.post(
            f"{base}/api/v1/workflows/{definition['id']}/runs",
            data={"bot": bot.name, "conversation_id": conversation["id"], "inputs": {}},
            headers={"Idempotency-Key": "workflow-reconnect-run"})
        assert launched.status == 201, launched.text()
        workflow_id = launched.json()["workflow_run_id"]
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            pending = workflow_store.questions(store, workflow_id, status="pending")
            if pending:
                break
            time.sleep(0.05)
        assert pending
        question_id = pending[0]["id"]

        proxy = CuttableProxy(urlsplit(base).port)
        proxied_base = f"http://127.0.0.1:{proxy.port}"
        context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        context.tracing.start(screenshots=True, snapshots=True, sources=False)
        page.goto(f"{proxied_base}/#/chat/{bot.name}")
        panel = page.locator("#workflow-panel")
        panel.wait_for(state="visible")
        panel.get_by_text("Waiting · saved workflow", exact=True).wait_for()
        question_form = panel.locator(f'[data-workflow-question-form][data-question-id="{question_id}"]')
        question_form.wait_for(state="visible")
        answer = question_form.locator("textarea[name=answer]")
        draft = "Keep this answer draft through reconnect."
        answer.fill(draft)
        answer.focus()
        assert answer.evaluate("element => document.activeElement === element")
        answer.scroll_into_view_if_needed()

        proxy.cut()
        page.evaluate("() => refreshWorkflowPanel(currentStudioBot, currentConversationId, studioGeneration, true)")
        panel.locator(".workflow-panel-error").wait_for(state="visible")
        assert question_form.count() == 1, "failed refresh must retain the pending question card"
        assert answer.input_value() == draft, "failed refresh must retain the answer draft"
        assert answer.evaluate("element => document.activeElement === element"), "failed refresh must retain focus"
        answer.scroll_into_view_if_needed()
        page.screenshot(path=str(artifacts / "offline-question-draft.png"), full_page=True, animations="disabled")

        proxy.restore()
        page.evaluate("() => refreshWorkflowPanel(currentStudioBot, currentConversationId, studioGeneration, true)")
        panel.locator(".workflow-panel-error").wait_for(state="detached")
        answer = panel.locator(f'[data-workflow-question-form][data-question-id="{question_id}"] textarea[name=answer]')
        assert answer.input_value() == draft, "successful reconnect refresh must retain the answer draft"
        assert answer.evaluate("element => document.activeElement === element"), "successful refresh must restore answer focus"
        answer.scroll_into_view_if_needed()
        page.screenshot(path=str(artifacts / "reconnected-question-draft.png"), full_page=True, animations="disabled")

        answer.press("Tab")
        send_answer = panel.get_by_role("button", name="Send answer")
        assert send_answer.evaluate("element => document.activeElement === element")
        page.keyboard.press("Enter")
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            latest = workflow_store.workflow_run(store, workflow_id)
            if latest and latest["status"] == "succeeded":
                break
            time.sleep(0.05)
        assert latest and latest["status"] == "succeeded"
        assert workflow_store.questions(store, workflow_id, status="answered")[0]["id"] == question_id
        assert not errors, errors
        context.tracing.stop(path=str(artifacts / "trace.zip"))
        screenshots = ["offline-question-draft.png", "reconnected-question-draft.png", "trace.zip"]
        sources = ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                   "src/hutch/server/workflows_api.py", "tests/e2e/test_browser.py")
        (artifacts / "results.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_workflow_question_draft_survives_tcp_disconnect_and_reconnect",
            "browser": browser.version, "playwright_version": package_version("playwright"),
            "viewport": [1440, 960], "tcp_connections_cut": True, "question_id": question_id,
            "temp_dir_override": os.environ.get("TMPDIR"),
            "answer_draft_preserved_offline_and_after_reconnect": True,
            "focus_preserved_offline_and_after_reconnect": True, "question_answered_by_keyboard": True,
            "workflow_status_after_answer": latest["status"], "provider_calls": 0,
            "page_errors": errors,
            "fixture_boundary": "Real SQLite workflow, supervisor, browser and local TCP proxy; saved ask node only, no model/provider calls.",
            "source_sha256": {name: hashlib.sha256((Path(__file__).resolve().parents[2] / name).read_bytes()).hexdigest()
                              for name in sources},
            "visual_artifact_sha256": {name: hashlib.sha256((artifacts / name).read_bytes()).hexdigest()
                                       for name in screenshots},
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2) + "\n")
    finally:
        if proxy:
            proxy.close()
        if context:
            if context.tracing is not None:
                try:
                    context.tracing.stop()
                except Exception:
                    pass
            context.close()
        if saved:
            saved.close()


def test_workflow_studio_pause_after_active_work_at_all_viewports(browser, live, monkeypatch):
    """A pause request holds the next step while the current owner operation settles."""
    from hutch.workflow.engine import Interpreter
    from hutch.workflow import persistence as workflow_store

    base, app = live
    store = app.state.store
    entered = threading.Event()
    release = threading.Event()
    original_transform = Interpreter._transform

    def slow_transform(self, node, scope):
        if node.id == "in_flight":
            entered.set()
            assert release.wait(45), "browser test did not release the in-flight node"
        return original_transform(self, node, scope)

    monkeypatch.setattr(Interpreter, "_transform", slow_transform)
    bot = Bot(name="workflow-active-pause", display_name="Active pause fixture", model="mock/demo", tools=[])
    store.upsert_bot(bot)
    conversation, _ = store.create_conversation(
        bot.id, "Pause at a safe boundary", idem_key="workflow-active-pause-conversation",
        request_hash="workflow-active-pause-conversation")
    plan = {
        "name": "pause-after-the-current-work-settles-at-a-safe-boundary",
        "envelope": {"tools": []},
        "budget": {"max_nodes": 6, "max_model_calls": 0},
        "nodes": [
            {"kind": "transform", "id": "in_flight", "title": "Current calculation",
             "op": "constant", "args": {"value": "settled"}},
            {"kind": "transform", "id": "next_step", "title": "Next calculation",
             "op": "constant", "args": {"value": {"ref": "in_flight"}}},
        ],
    }
    artifacts = Path(__file__).resolve().parents[2] / (
        "docs/realignment/artifacts/workflow-studio/pause-resume-2026-10-11")
    artifacts.mkdir(parents=True, exist_ok=True)
    page = browser.new_page(viewport={"width": 1440, "height": 960}, device_scale_factor=1)
    context = page.context
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    capture_log = []
    try:
        submitted = page.request.post(
            f"{base}/api/v1/workflows/plans",
            data={"plan": plan, "bot": bot.name, "conversation_id": conversation["id"]},
            headers={"Idempotency-Key": "workflow-active-pause-submit"})
        assert submitted.status == 201, submitted.text()
        workflow_id = submitted.json()["workflow_run_id"]
        assert entered.wait(15), "the first transform did not enter its in-flight operation"

        page.goto(f"{base}/#/chat/{bot.name}")
        panel = page.locator("#workflow-panel")
        panel.wait_for(state="visible")
        display_title = "Pause After The Current Work Settles At A Safe Boundary"
        page.get_by_role("heading", name=display_title).wait_for()
        panel.get_by_text("Running · saved workflow", exact=True).wait_for()
        pause_button = panel.get_by_role("button", name="Pause after current work")
        pause_button.wait_for(state="visible")
        sizes = [("desktop", 1440, 960), ("tablet", 768, 1024),
                 ("phone", 360, 800), ("compact-phone", 320, 800)]

        def capture_state(state: str, expected_button: str | None) -> None:
            for label, width, height in sizes:
                page.set_viewport_size({"width": width, "height": height})
                page.wait_for_timeout(80)
                assert panel.get_by_text(f"{state} · saved workflow", exact=True).is_visible()
                overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
                assert overflow <= 1, f"{label} {state} view has horizontal overflow: {overflow}px"
                action = panel.get_by_role("button", name=expected_button) if expected_button else None
                target_bounds = action.bounding_box() if action else None
                if action:
                    assert target_bounds is not None
                    assert target_bounds["height"] >= (44 if width <= 520 else 24)
                image_name = f"active-pause-{state.lower().replace(' ', '-')}-{label}.png"
                page.screenshot(path=str(artifacts / image_name), full_page=True, animations="disabled")
                capture_log.append({
                    "viewport": label, "size": [width, height], "state": state.lower().replace(" ", "-"),
                    "horizontal_overflow_px": overflow,
                    "control": expected_button,
                    "control_bounds": ({key: round(value, 2) for key, value in target_bounds.items()}
                                       if target_bounds else None),
                })

        capture_state("Running", "Pause after current work")
        page.set_viewport_size({"width": 1440, "height": 960})
        active = page.request.get(f"{base}/api/v1/workflows/runs/{workflow_id}").json()
        assert active["workflow"]["status"] == "running" and active["pause_available"] is True
        pause_body = {"expected_revision_id": active["workflow"]["revision_id"],
                      "expected_generation": active["workflow"]["attempt_run_id"]}
        with page.expect_response(lambda response: response.url.endswith(
                f"/workflows/runs/{workflow_id}/pause")) as pause_response:
            pause_button.click()
        response = pause_response.value
        assert response.status == 200, response.text()
        assert response.request.headers.get("idempotency-key")
        assert response.request.post_data_json == pause_body
        assert response.json()["paused"] is True and response.json()["parked"] is False
        panel.get_by_text("Pause requested · saved workflow", exact=True).wait_for()
        panel.get_by_text("Current work will settle before the next step is held.", exact=True).wait_for()
        assert panel.get_by_role("button", name="Pause after current work").count() == 0
        assert panel.get_by_role("button", name="Resume workflow").count() == 0
        wait_for_page(page, "document.activeElement?.dataset.workflowAction === 'refresh'", timeout=2000)
        assert panel.get_by_role("button", name="Refresh").evaluate(
            "element => element === document.activeElement")
        capture_state("Pause requested", None)

        release.set()
        deadline = time.monotonic() + 20
        parked = None
        while time.monotonic() < deadline:
            parked = page.request.get(f"{base}/api/v1/workflows/runs/{workflow_id}").json()
            if parked["resume_available"]:
                break
            time.sleep(0.05)
        assert parked and parked["resume_available"] is True, parked
        assert parked["attempt"]["status"] == "waiting_workflow"
        assert {node["site_id"] for node in parked["nodes"]} == {"in_flight"}
        assert next(node for node in parked["nodes"] if node["site_id"] == "in_flight")["result"] == "settled"
        panel.get_by_role("button", name="Refresh").click()
        panel.get_by_text("Paused · saved workflow", exact=True).wait_for()
        capture_state("Paused", "Resume workflow")

        page.set_viewport_size({"width": 1440, "height": 960})
        with page.expect_response(lambda response: response.url.endswith(
                f"/workflows/runs/{workflow_id}/resume")) as resume_response:
            panel.get_by_role("button", name="Resume workflow").click()
        assert resume_response.value.status == 200, resume_response.value.text()
        assert resume_response.value.request.headers.get("idempotency-key")
        assert resume_response.value.json()["paused"] is False
        deadline = time.monotonic() + 20
        finished = None
        while time.monotonic() < deadline:
            finished = workflow_store.workflow_run(store, workflow_id)
            if finished and finished["status"] in ("succeeded", "failed", "stopped", "outcome_unknown"):
                break
            time.sleep(0.05)
        assert finished and finished["status"] == "succeeded", finished
        assert not errors, errors
        context.tracing.stop(path=str(artifacts / "active-pause-trace.zip"))
        sources = ("src/hutch/workflow/persistence.py", "src/hutch/workflow/engine.py",
                   "src/hutch/workflow/runtime.py", "src/hutch/server/workflows_api.py",
                   "src/hutch/server/static/app.js", "src/hutch/server/static/style.css")
        images_and_trace = {file.name: hashlib.sha256(file.read_bytes()).hexdigest()
                            for file in artifacts.iterdir()
                            if file.name.startswith("active-pause-") and file.suffix in {".png", ".zip"}}
        (artifacts / "active-pause-results.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_workflow_studio_pause_after_active_work_at_all_viewports",
            "command": "uv run pytest tests/e2e/test_browser.py::test_workflow_studio_pause_after_active_work_at_all_viewports -q",
            "browser": browser.browser_type.name, "browser_version": browser.version,
            "playwright_version": package_version("playwright"), "viewports": capture_log,
            "workflow_run_id": workflow_id, "keyboard_path": "Pause action focused Refresh after a deferred pause request.",
            "page_errors": errors, "provider_calls": 0,
            "fixture_boundary": "A saved declarative two-transform plan uses the real SQLite store, supervisor, HTTP API, and browser. The first transform blocks on a test event; no model/provider call is made.",
            "verified_transitions": ["running", "pause requested", "parked after current node settled", "resumed", "succeeded"],
            "source_sha256": {name: hashlib.sha256((Path(__file__).resolve().parents[2] / name).read_bytes()).hexdigest()
                              for name in sources},
            "visual_artifact_sha256": images_and_trace,
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2) + "\n")
    finally:
        release.set()
        if context.tracing:
            try:
                context.tracing.stop(path=str(artifacts / "active-pause-trace.zip"))
            except Exception:
                pass
        context.close()


def test_paired_phone_can_stop_a_run_and_resume_the_current_human_wait(browser, live, monkeypatch):
    """Phone commands carry session CSRF/idempotency and target the exact live run state."""
    base, app = live
    store, engine = app.state.store, app.state.engine
    monkeypatch.delenv("HUTCH_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(engine, "tick", lambda: None)
    stop_bot = store.create_bot(Bot(name="phone-stop", model="mock/demo", tools=[]))
    stop_run = engine.submit(stop_bot, "stop this pending task")

    resume_bot = store.create_bot(Bot(name="phone-resume", model="mock/demo", tools=[]))
    resume_run = store.create_run(Run(bot_id=resume_bot.id, prompt="resume after sign-in"))
    claimed = store.claim_run(resume_run.id, "phone-resume-fixture-owner", lease_seconds=60)
    assert claimed is not None
    store.transition_run(resume_run.id, RunStatus.running, fence=claimed.fence)
    store.transition_run(resume_run.id, RunStatus.waiting_human, fence=claimed.fence)
    store.append_event(Event(run_id=resume_run.id, type=EventType.human_needed,
                             data={"reason": "Complete the local sign-in step"}))
    store.flush_events()
    human_event_seq = store.last_seq(resume_run.id)

    enrollment, outcome = store.exchange_pairing_code(store.create_pairing_code(), "Phone controls", "browser-test")
    assert outcome == "ok" and enrollment
    paired = store.finish_passkey_enrollment(enrollment["token"], {
        "credential_id": secrets.token_bytes(24), "public_key": b"browser-phone-controls-key", "sign_count": 0,
        "backup_eligible": True, "backed_up": True, "user_handle": store.webauthn_user_handle(),
    })

    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    try:
        context.add_cookies([{"name": "hutch_session", "value": paired["session_token"], "url": base}])
        page.goto(base + "/")
        page.locator("#phone-root .phone-brand").wait_for()
        page.get_by_role("button", name="Runs").click()

        page.locator(f'[data-phone-run="{stop_run.id}"]').click()
        stop_button = page.get_by_role("button", name="Stop run")
        stop_button.wait_for()
        with page.expect_response(lambda response: response.url.endswith(
                f"/api/v1/tasks/runs/{stop_run.id}/stop")) as stopped:
            stop_button.click()
        stop_response = stopped.value
        assert stop_response.status == 200, stop_response.text()
        assert stop_response.request.headers.get("x-hutch-csrf")
        assert stop_response.request.headers.get("idempotency-key")
        wait_for(lambda: store.get_run(stop_run.id).status is RunStatus.stopped)

        page.get_by_role("button", name="All runs").click()
        page.locator(f'[data-phone-run="{resume_run.id}"]').click()
        resume_button = page.get_by_role("button", name="Resume after completing the requested step")
        resume_button.wait_for()
        assert resume_button.get_attribute("data-human-seq") == str(human_event_seq)
        with page.expect_response(lambda response: response.url.endswith(
                f"/api/v1/tasks/runs/{resume_run.id}/resume")) as resumed:
            resume_button.click()
        resume_response = resumed.value
        assert resume_response.status == 200, resume_response.text()
        assert resume_response.request.headers.get("x-hutch-csrf")
        assert resume_response.request.headers.get("idempotency-key")
        assert resume_response.request.post_data_json == {"human_event_seq": human_event_seq}
        assert resume_response.json() == {"resumed": resume_run.id, "human_event_seq": human_event_seq,
                                          "replayed": False}
        assert store.kv_get(f"resume:{resume_run.id}") == "1"
        assert store.get_run(resume_run.id).status is RunStatus.waiting_human
    finally:
        context.close()


def test_paired_phone_recovers_approval_after_lost_response_with_same_key(browser, live):
    """A committed decision with a dropped response is reconciled by the original idempotency key."""
    base, app = live
    store, engine = app.state.store, app.state.engine
    bot = store.create_bot(Bot(name="phone-approval-retry", model="mock/demo", tools=["files"],
                               approval_mode=ApprovalMode.ask))
    run = engine.submit(bot, "write a report")
    engine.dispatch_pending()
    wait_for(lambda: store.get_run(run.id).status is RunStatus.waiting_approval)
    approval = store.pending_approvals()[0]
    enrollment, outcome = store.exchange_pairing_code(store.create_pairing_code(), "Recovery phone", "browser-test")
    assert outcome == "ok" and enrollment
    paired = store.finish_passkey_enrollment(enrollment["token"], {
        "credential_id": secrets.token_bytes(24), "public_key": b"browser-phone-recovery-key", "sign_count": 0,
        "backup_eligible": True, "backed_up": True, "user_handle": store.webauthn_user_handle(),
    })

    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    target = f"**/api/v1/actions/approvals/{approval.id}/approve"
    captured = []

    def commit_then_drop_response(route):
        response = route.fetch()
        captured.append({"status": response.status, "key": route.request.headers.get("idempotency-key"),
                         "body": route.request.post_data_json})
        route.abort("connectionreset")

    try:
        context.add_cookies([{"name": "hutch_session", "value": paired["session_token"], "url": base}])
        page.goto(base + "/")
        page.locator("#phone-root .phone-brand").wait_for()
        page.get_by_role("button", name="Review").click()
        card = page.locator(f'.approval-card [data-phone-approve="{approval.id}"]').locator("..")
        button = card.get_by_role("button", name="Allow once")
        button.wait_for()
        page.route(target, commit_then_drop_response)
        button.click()
        retry = page.get_by_role("button", name="Retry same request")
        retry.wait_for()
        assert len(captured) == 1 and captured[0]["status"] == 200
        assert captured[0]["key"] and captured[0]["body"] == {"always": False, "action_hash": approval.action_hash}
        assert store.get_approval(approval.id).status.value == "approved"

        page.unroute(target, commit_then_drop_response)
        with page.expect_response(lambda response: response.url.endswith(
                f"/api/v1/actions/approvals/{approval.id}/approve")) as retried:
            retry.click()
        retry_response = retried.value
        assert retry_response.status == 200, retry_response.text()
        assert retry_response.request.headers.get("idempotency-key") == captured[0]["key"]
        assert retry_response.request.post_data_json == captured[0]["body"]
        assert store.get_approval(approval.id).status.value == "approved"
        retry.wait_for(state="detached")
    finally:
        context.close()


def test_schedule_overview_shows_local_times_and_pauses_only_future_occurrences(browser, live):
    base, app = live
    store = app.state.store
    bots = [
        Bot(name="schedule-west", display_name="West Coast Review", model="ollama/qwen3:4b", tools=[],
            schedules=[Schedule(name="Weekly review", cron="0 9 * * 1", timezone="America/Vancouver",
                                prompt="Review the weekly notes.")]),
        Bot(name="schedule-london", display_name="London Digest", model="ollama/qwen3:4b", tools=[],
            schedules=[Schedule(name="Morning digest", cron="30 8 * * 1-5", timezone="Europe/London",
                                prompt="Prepare a morning digest.")]),
        Bot(name="schedule-personal-paused", display_name="Paused Reminder", model="ollama/qwen3:4b", tools=[], paused=True,
            schedules=[Schedule(name="Personal reminder", cron="0 10 * * *", timezone="America/Toronto",
                                prompt="Review the reminder.")]),
    ]
    for bot in bots:
        store.create_bot(bot)
    live_run = store.create_run(Run(bot_id=bots[0].id, prompt="already admitted work", status=RunStatus.running))

    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/schedules"
    out.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    page.set_default_timeout(8000)
    errors: list[str] = []
    requests: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: requests.append(request.url))
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    captures = []
    empty_captures = []
    try:
        page.goto(f"{base}/#/schedules")
        page.get_by_role("heading", name="Scheduled work", exact=True).wait_for()
        page.get_by_role("heading", name="Upcoming scheduled work").wait_for()
        assert page.get_by_role("listitem").count() == 3
        assert page.get_by_text("America/Vancouver", exact=True).count() == 1
        assert page.get_by_text("Europe/London", exact=True).count() == 1
        assert page.get_by_text("Paused for this assistant", exact=True).count() == 1
        assert page.get_by_role("link", name="Edit schedule").count() == 3
        timing = page.locator(".schedule-overview-details").first
        assert timing.locator("summary").inner_text() == "Timing details"
        assert not timing.locator("code").is_visible()
        timing.locator("summary").click()
        timing.get_by_text("If a time is missed").wait_for()
        assert timing.evaluate("element => element.open")
        assert timing.locator("dd").nth(2).inner_text().strip() in {
            "Run once for missed times", "Skip missed times"
        }
        assert timing.locator("code").is_visible()
        page.screenshot(path=str(out / "timing-details-desktop.png"), animations="disabled")
        timing.locator("summary").click()

        with page.expect_response(lambda response: response.url.endswith("/api/v1/schedules/control")
                                  and response.request.method == "PUT") as paused:
            page.get_by_role("button", name="Pause scheduled work").click()
        assert paused.value.status == 200 and paused.value.json()["paused"] is True
        wait_for(lambda: store.workspace_schedule_control()["paused"] is True)
        page.get_by_role("button", name="Resume scheduled work").wait_for()
        assert page.evaluate("document.activeElement?.id") == "schedule-control-toggle"
        assert store.get_run(live_run.id).status is RunStatus.running
        wait_for(lambda: page.get_by_text("Paused for now", exact=True).count() == 2)
        page.locator(".schedule-overview-list .tag").get_by_text("Paused", exact=True).wait_for()
        page.get_by_text("each task follows its saved choice for missed times", exact=False).wait_for()
        while page.locator("#toast-root .toast").count():
            page.locator("#toast-root .toast-close").first.click()

        sizes = {"desktop": (1440, 960), "tablet": (900, 1024), "phone": (390, 844)}
        for label, (width, height) in sizes.items():
            page.set_viewport_size({"width": width, "height": height})
            metrics = page.evaluate("""() => ({
              viewport: [innerWidth, innerHeight],
              document: [document.documentElement.scrollWidth, document.documentElement.scrollHeight],
              rows: document.querySelectorAll('.schedule-overview-row').length,
              actionHeight: document.querySelector('#schedule-control-toggle').getBoundingClientRect().height,
              actionWidth: document.querySelector('#schedule-control-toggle').getBoundingClientRect().width,
              actionFontSize: parseFloat(getComputedStyle(document.querySelector('#schedule-control-toggle')).fontSize),
              nextTimeCount: document.querySelectorAll('.schedule-overview-next time').length
            })""")
            assert metrics["document"][0] - metrics["viewport"][0] <= 1, (label, metrics)
            assert metrics["rows"] == 3 and metrics["nextTimeCount"] == 3, (label, metrics)
            if width <= 640:
                assert metrics["actionHeight"] >= 44, metrics
                assert metrics["actionWidth"] >= 150 and metrics["actionFontSize"] >= 12, metrics
            path = out / f"{label}.png"
            page.screenshot(path=str(path), full_page=True, animations="disabled")
            captures.append({"size": label, "viewport": [width, height], **metrics, "screenshot": path.name})
            if label == "phone":
                scroll = page.locator("main#view > .page-scroll")
                scroll_metrics = scroll.evaluate("el => ({height: el.scrollHeight, viewport: el.clientHeight})")
                assert scroll_metrics["height"] > scroll_metrics["viewport"], scroll_metrics
                page.locator(".schedule-overview-row").last.scroll_into_view_if_needed()
                bottom_path = out / "phone-bottom.png"
                page.screenshot(path=str(bottom_path), full_page=True, animations="disabled")
                captures.append({"size": "phone-bottom", "viewport": [width, height],
                                 "scrollHeight": scroll_metrics["height"],
                                 "scrollViewportHeight": scroll_metrics["viewport"],
                                 "screenshot": bottom_path.name})

        page.reload()
        page.get_by_role("button", name="Resume scheduled work").wait_for()
        page.get_by_text("each task follows its saved choice for missed times", exact=False).wait_for()
        with page.expect_response(lambda response: response.url.endswith("/api/v1/schedules/control")
                                  and response.request.method == "PUT") as resumed:
            page.get_by_role("button", name="Resume scheduled work").click()
        assert resumed.value.status == 200 and resumed.value.json()["paused"] is False
        wait_for(lambda: store.workspace_schedule_control()["paused"] is False)
        page.get_by_role("button", name="Pause scheduled work").wait_for()
        assert page.evaluate("document.activeElement?.id") == "schedule-control-toggle"
        wait_for(lambda: page.locator(".schedule-overview-list .tag").get_by_text("On", exact=True).count() == 2)
        assert page.get_by_text("Paused for this assistant", exact=True).count() == 1
        assert store.get_run(live_run.id).status is RunStatus.running

        for bot in bots:
            for schedule in bot.schedules:
                assert store.delete_schedule(bot.id, schedule.id) is not None
        page.reload()
        page.get_by_role("heading", name="No recurring tasks yet").wait_for()
        assert page.get_by_role("link", name="Set up West Coast Review").count() == 0
        page.locator(".schedule-empty-bots summary").click()
        assert page.get_by_role("link", name="Set up West Coast Review").count() == 1
        assert page.get_by_role("link", name="Set up London Digest").count() == 1
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024),
                                     ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, overflow)
            empty_path = out / f"empty-{label}.png"
            page.screenshot(path=str(empty_path), full_page=True, animations="disabled")
            empty_captures.append({"size": label, "viewport": [width, height], "overflow": overflow,
                                  "screenshot": empty_path.name})

        outside = [url for url in requests if urlsplit(url).netloc not in {urlsplit(base).netloc, ""}]
        assert not outside, outside
        assert not errors, errors
        (out / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_schedule_overview_shows_local_times_and_pauses_only_future_occurrences",
            "command": ".venv/bin/pytest -q tests/e2e/test_browser.py::test_schedule_overview_shows_local_times_and_pauses_only_future_occurrences",
            "browser": browser.version, "playwright": package_version("playwright"),
            "fixture_only": True, "provider_calls": 0, "external_requests": len(outside),
            "page_errors": errors, "captures": captures, "empty_captures": empty_captures,
            "verified": ["next times in each schedule's own time zone", "per-Bot paused status",
                         "workspace pause persisted through reload", "pause prevents only future scheduled admissions",
                         "already-running work continues", "Bot-specific pause remains after workspace resume",
                         "keyboard focus restoration after pause/resume", "responsive rows, scrollable phone list and touch target",
                         "empty state links to existing Bot settings", "no external browser requests"],
            "source_sha256": {
                relative: hashlib.sha256((Path(__file__).resolve().parents[2] / relative).read_bytes()).hexdigest()
                for relative in ("src/hutch/server/static/index.html", "src/hutch/server/static/app.js",
                                 "src/hutch/server/static/style.css", "src/hutch/server/app.py",
                                 "src/hutch/store.py", "src/hutch/engine.py", "src/hutch/scheduler.py")},
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        try:
            context.tracing.stop(path=str(out / "trace.zip"))
        except Exception:
            pass
        context.close()


def test_chatgpt_background_permission_is_explicit_responsive_and_reversible(browser, live):
    """Exercise the ChatGPT plan permission using only a local synthetic account."""
    from hutch.chatgpt_auth import ChatGPTAuthBook, PLAN_SCOPE

    base, app = live
    account_id = "acct_0123456789abcdef01234567"
    ChatGPTAuthBook(app.state.config.state_dir)._write_accounts({"version": 1, "host_id": "fixture-host", "accounts": {
        account_id: {"access_token": "fixture-token", "refresh_token": "", "expires_at": 9_999_999_999,
                     "scopes": [PLAN_SCOPE], "client_id": "fixture-client", "subject": "fixture-subject"}
    }})
    connection = ConnectionBook(app.state.config.state_dir).add_chatgpt_account(account_id, "Fixture account")
    bot = app.state.store.create_bot(Bot(name="weekly-review", display_name="Weekly Project Reviewer",
                                         model=f"{connection.name}/gpt-fixture", tools=[]))
    output = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/chatgpt-background-consent"
    output.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    errors: list[str] = []
    external: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external.append(request.url)
            if not request.url.startswith(base) else None)
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    viewports = (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844))
    try:
        page.goto(f"{base}/#/bot/{bot.name}")
        open_assistant_customization(page)
        page.get_by_role("heading", name="Weekly Project Reviewer").wait_for()
        panel = page.get_by_role("region", name="ChatGPT plan for unattended runs")
        assert "Permission required" in panel.inner_text()
        for label, width, height in viewports:
            page.set_viewport_size({"width": width, "height": height})
            panel.scroll_into_view_if_needed()
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") == 0, label
            page.screenshot(path=str(output / f"needs-consent-{label}.png"), animations="disabled")

        trigger = page.get_by_role("button", name="Review and allow")
        trigger.click()
        dialog = page.get_by_role("dialog", name="Allow scheduled ChatGPT plan use?")
        assert "Fixture account" in dialog.inner_text()
        assert "only for this Bot" in dialog.inner_text()
        page.screenshot(path=str(output / "permission-review-phone.png"), animations="disabled")
        page.locator("#modal-confirm").focus()
        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement.id") == "modal-close"
        page.keyboard.press("Shift+Tab")
        assert page.evaluate("document.activeElement.id") == "modal-confirm"
        page.get_by_role("button", name="Allow background use").click()
        page.get_by_role("button", name="Revoke").wait_for()
        assert page.evaluate("document.activeElement.dataset.backgroundProvider") == connection.name
        page.set_viewport_size({"width": 390, "height": 844})
        panel.scroll_into_view_if_needed()
        assert page.evaluate("document.documentElement.scrollWidth - innerWidth") == 0
        page.screenshot(path=str(output / "allowed-phone.png"), animations="disabled")
        page.set_viewport_size({"width": 1440, "height": 960})
        assert "Allowed for this route" in panel.inner_text()
        panel.evaluate("el => el.scrollIntoView({block: 'start', behavior: 'instant'})")
        page.screenshot(path=str(output / "allowed-desktop.png"), animations="disabled")

        page.get_by_role("button", name="Revoke").click()
        page.get_by_role("dialog", name="Revoke ChatGPT background use?").get_by_role(
            "button", name="Revoke permission").click()
        page.get_by_role("button", name="Review and allow").wait_for()
        assert page.evaluate("document.activeElement.dataset.backgroundProvider") == connection.name
        assert not app.state.store.get_bot(bot.id).background_provider_consents
        assert not errors, errors
        assert not external, external
        context.tracing.stop(path=str(output / "trace.zip"))
        (output / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_chatgpt_background_permission_is_explicit_responsive_and_reversible",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "browser": browser.version,
            "playwright_version": package_version("playwright"),
            "synthetic_account": True,
            "provider_requests": 0,
            "external_requests": external,
            "page_errors": errors,
            "viewports": [{"size": label, "viewport": [width, height], "horizontal_overflow": 0}
                          for label, width, height in viewports],
            "allowed_permission_viewports": {"desktop": [1440, 960], "phone": [390, 844]},
            "verified": ["permission is explicit", "modal keyboard focus is trapped", "focus returns to refreshed control",
                         "permission can be revoked", "no provider calls", "no external requests"],
        }, indent=2) + "\n")
    finally:
        try:
            context.tracing.stop()
        except Exception:
            pass
        context.close()


def test_run_detail_reports_transcript_chain_verification_and_tampering(browser, live):
    """Show the result of the real persisted event-chain verifier without starting a model run."""
    import hashlib
    import json
    from pathlib import Path

    base, app = live
    store = app.state.store
    bot = store.create_bot(Bot(name="integrity-review", model="mock/demo", tools=[]))
    # Keep the fixture terminal so the live test supervisor cannot turn it into a real execution.
    run = Run(bot_id=bot.id, prompt="Check this persisted transcript.", status=RunStatus.succeeded,
              finished_at=datetime.now(timezone.utc).isoformat())
    store.create_run(run)
    store.append_event(Event(run_id=run.id, type=EventType.message,
                             data={"role": "assistant", "content": "The transcript is intact."}))
    store.flush_events()
    initial_verification = store.verify_chain(run.id)
    assert initial_verification["ok"] is True and initial_verification["checked"] > 0

    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    errors: list[str] = []
    external: list[str] = []
    verification_responses: list[dict[str, str | int]] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external.append(request.url)
            if not request.url.startswith(base) else None)
    page.on("response", lambda response: verification_responses.append({"url": response.url, "status": response.status})
            if response.url.endswith(f"/api/v1/tasks/runs/{run.id}/verify") else None)
    output = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/transcript-integrity"
    output.mkdir(parents=True, exist_ok=True)
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        page.goto(f"{base}/#/run/{run.id}")
        page.get_by_role("heading", name="Task details").wait_for()
        technical_details = page.locator("#run-technical-details")
        assert technical_details.get_attribute("open") is None
        assert not page.locator("[data-run-integrity-run]").is_visible()
        assert page.locator("#chat-stream .mrun").count() == 1
        assert not page.locator("#chat-stream .mrun").is_visible()
        expected_verified = (f"{initial_verification['checked']} chained event"
                             f"{'s' if initial_verification['checked'] != 1 else ''} verified")
        viewport_results = []
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            if page.viewport_size != {"width": width, "height": height}:
                page.set_viewport_size({"width": width, "height": height})
            # Reload each size independently. This avoids measuring a stale
            # disclosure after browser resize and mirrors a fresh responsive visit.
            page.goto(f"{base}/#/run/{run.id}")
            page.get_by_role("heading", name="Task details").wait_for()
            technical_details = page.locator("#run-technical-details")
            if not technical_details.evaluate("element => element.open"):
                technical_details.locator(":scope > summary").click()
            wait_for_page(page, "document.querySelector('#run-technical-details')?.open === true")
            page.locator("[data-run-integrity-run]").wait_for(state="visible")
            result = page.locator("[data-run-integrity-result]")
            verify_control = page.evaluate("""() => {
              const button = document.querySelector('[data-verify-run-history]');
              const rect = button?.getBoundingClientRect();
              const style = button && getComputedStyle(button);
              return {exists:!!button, connected:button?.isConnected, text:button?.textContent.trim(),
                display:style?.display, visibility:style?.visibility, width:rect?.width, height:rect?.height};
            }""")
            assert verify_control["exists"] and verify_control["width"] > 0 and verify_control["height"] > 0, (
                label, verify_control)
            # The run view can refresh after its initial snapshot. Dispatch the
            # click against the current connected control in one browser turn.
            page.evaluate("document.querySelector('[data-verify-run-history]')?.click()")
            wait_for_page(page, """expected => {
                  const node = document.querySelector('[data-run-integrity-result]');
                  return node && node.dataset.state === 'verified' && node.textContent.includes(expected);
                }""", arg=expected_verified, timeout=5000)
            result_state = page.evaluate("""() => {
              const node = document.querySelector('[data-run-integrity-result]');
              if (!node) return {text:'missing',visible:false,rect:null,chain:[]};
              const chain = [];
              for (let parent = node; parent; parent = parent.parentElement) {
                const style = getComputedStyle(parent);
                chain.push({tag:parent.tagName,id:parent.id,className:parent.className,display:style.display,
                  visibility:style.visibility,opacity:style.opacity,open:parent instanceof HTMLDetailsElement ? parent.open : null,
                  rect:parent.getBoundingClientRect().toJSON()});
              }
              const rect = node.getBoundingClientRect();
              const style = getComputedStyle(node);
              return {text:node.textContent,rect:rect.toJSON(),connected:node.isConnected,
                visible:style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0,
                chain};
            }""")
            assert result_state["visible"], (label, result_state)
            result_text = result_state["text"]
            assert expected_verified in result_text, (label, result_text, verification_responses)
            assert "legacy events are not chained" not in result_text
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow == 0, f"{label} viewport overflows by {overflow}px"
            page.screenshot(path=str(output / f"verified-{label}.png"), animations="disabled")
            viewport_results.append({"size": label, "viewport": [width, height], "status": "verified",
                                    "horizontal_overflow": overflow})

        page.set_viewport_size({"width": 1440, "height": 960})
        legacy_run = Run(bot_id=bot.id, prompt="Check an older transcript.", status=RunStatus.succeeded,
                         finished_at=datetime.now(timezone.utc).isoformat())
        store.create_run(legacy_run)
        store.append_event(Event(run_id=legacy_run.id, type=EventType.message,
                                 data={"role": "assistant", "content": "This event predates hashing."}))
        store.flush_events()
        with store._lock:
            store._db.execute("UPDATE events SET hash = '' WHERE run_id = ? AND seq = 1", (legacy_run.id,))
            store._db.commit()
        legacy_verification = store.verify_chain(legacy_run.id)
        assert legacy_verification["ok"] and legacy_verification["legacy"] == 1
        page.goto(f"{base}/#/run/{legacy_run.id}")
        page.get_by_role("heading", name="Task details").wait_for()
        page.locator("#run-technical-details > summary").click()
        page.get_by_role("button", name="Verify event history").click()
        wait_for_page(page, """() => {
          const node = document.querySelector('[data-run-integrity-result]');
          return node && node.dataset.state === 'partial' && node.textContent.includes('older event');
        }""", timeout=5000)
        legacy_result = result.text_content() or ""
        assert legacy_result == "0 chained events verified; 1 older event has no hash.", legacy_result
        assert result.get_attribute("data-state") == "partial"
        assert page.evaluate("document.documentElement.scrollWidth - innerWidth") == 0
        page.screenshot(path=str(output / "legacy-desktop.png"), animations="disabled")

        page.goto(f"{base}/#/run/{run.id}")
        page.get_by_role("heading", name="Task details").wait_for()
        page.locator("#run-technical-details > summary").click()
        store.flush_events()
        with store._lock:
            store._db.execute("UPDATE events SET data = ? WHERE run_id = ? AND seq = 1",
                              ('{"role":"assistant","content":"changed after commit"}', run.id))
            store._db.commit()
        page.get_by_role("button", name="Verify event history").click()
        wait_for_page(page, """() => {
          const node = document.querySelector('[data-run-integrity-result]');
          return node && node.dataset.state === 'failed' && node.textContent.includes('event 1');
        }""", timeout=5000)
        assert result.get_attribute("role") == "alert"
        assert store.verify_chain(run.id)["ok"] is False
        assert page.evaluate("document.documentElement.scrollWidth - innerWidth") == 0
        page.screenshot(path=str(output / "tampered-desktop.png"), animations="disabled")
        assert not errors, errors
        assert not external, external
        (output / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_run_detail_reports_transcript_chain_verification_and_tampering",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "browser": browser.version,
            "playwright_version": package_version("playwright"),
            "provider_calls": 0,
            "scenario": "Locally persisted event hash chain is verified through the run UI, then detects a changed event payload",
            "external_requests": external,
            "verification_responses": verification_responses,
            "page_errors": errors,
            "captures": viewport_results,
            "legacy_result": legacy_result,
            "legacy_capture": "legacy-desktop.png",
            "legacy_viewport": [1440, 960],
            "tampering_detected_at_seq": 1,
            "tamper_capture": "tampered-desktop.png",
            "tamper_viewport": [1440, 960],
            "source_sha256": {path: hashlib.sha256((output.parents[3] / path).read_bytes()).hexdigest()
                              for path in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                           "src/hutch/server/app.py", "src/hutch/store.py")},
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        context.tracing.stop(path=str(output / "trace.zip"))
        context.close()


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
    app.state.store.set_workspace_specialists([specialist.id])
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
        dialog = page.get_by_role("dialog", name="Refine a task for a specialist")
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
        assert dialog.locator("#workspace-task-boundary").is_visible()
        assert dialog.get_by_label("Expected deliverable (optional)").is_visible()
        dialog.locator("#workspace-task-brief").fill("x" * 20000)
        dialog.get_by_label("Expected deliverable (optional)").fill("y")
        dialog.get_by_role("button", name="Send reviewed task").click()
        assert "limited to 20,000 characters" in dialog.get_by_role("alert").inner_text()
        dialog.locator("#workspace-task-brief").fill(
            "Compare two launch approaches and return a short recommendation with trade-offs.")
        dialog.get_by_label("Expected deliverable (optional)").fill("A one-page comparison table and recommendation.")
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
        assert task["original_request"] == "Compare launch plan options. Keep the work in Hutch."
        assert task["task_brief"].startswith("Compare two launch approaches")
        assert "Expected deliverable:\nA one-page comparison table and recommendation." in task["task_brief"]
        assert "User-reviewed assumptions and constraints:\nUse public information only; do not contact anyone." in app.state.store.get_run(task["child_run_id"]).prompt
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


def test_opencode_coding_handoff_is_reviewed_and_responsive(browser, live, tmp_path, monkeypatch):
    """Review a code task in chat; this fixture never starts OpenCode or calls a model provider."""
    from hutch import code_handoff

    base, app = live
    project = tmp_path / "code-project"
    project.mkdir()
    subprocess.run(["git", "-C", str(project), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(project), "config", "user.email", "hutch-test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(project), "config", "user.name", "Hutch Test"], check=True)
    (project / "README.md").write_text("A small project for a local coding handoff fixture.\n")
    subprocess.run(["git", "-C", str(project), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(project), "commit", "-qm", "base"], check=True)
    bot = app.state.store.create_bot(Bot(
        name="docs-coding-helper", display_name="Documentation Partner", model="mock/demo", tools=[],
        workspace_mode="folder", workdir=str(project)))
    contract = {"available": False}

    def check_cli():
        if not contract["available"]:
            raise code_handoff.CodeHandoffError("Fixture: install OpenCode CLI v2.0.24 or newer.")
        return "/fixture/opencode", "2.0.24"

    monkeypatch.setattr(code_handoff, "inspect_opencode", check_cli)
    output = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/opencode-handoff"
    output.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    context.grant_permissions(["clipboard-read", "clipboard-write"], origin=base)
    page = context.new_page()
    errors: list[str] = []
    external: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external.append(request.url) if not request.url.startswith(base) else None)
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    viewports = (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844),
                 ("compact", 320, 844))
    try:
        page.goto(f"{base}/#/chat/{bot.name}")
        page.locator("#chat-prompt").wait_for()
        page.locator("#chat-prompt").fill("Help me make this project README easier for new contributors.")
        page.locator("#chat-send").click()
        prepare = page.get_by_role("button", name="Prepare coding task")
        prepare.wait_for(timeout=15000)
        page.locator("#toast-root .toast-close").first.click()
        prepare.click()
        dialog = page.get_by_role("dialog", name="Prepare a coding task for OpenCode")
        dialog.wait_for()
        brief = dialog.locator("#code-task-brief")
        assert "new contributors" in brief.input_value()
        assert "not copied" in dialog.inner_text()
        assert "hutch code login" in dialog.inner_text()
        assert "private OpenCode profile" in dialog.inner_text()
        assert "does not copy your regular OpenCode sign-in" in dialog.inner_text()
        assert "Hutch does not broker or sandbox them" in dialog.inner_text()
        assert "passwords, access tokens, or other secrets" in dialog.inner_text()
        assert str(project) not in dialog.inner_text()
        assert page.evaluate("document.activeElement.id") == "code-task-brief"
        page.keyboard.press("Shift+Tab")
        assert page.evaluate("document.activeElement.id") == "modal-close"
        page.keyboard.press("Shift+Tab")
        assert page.evaluate("document.activeElement.id") == "modal-confirm"
        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement.id") == "modal-close"
        brief.focus()
        for label, width, height in viewports:
            page.set_viewport_size({"width": width, "height": height})
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1, label
            dialog.locator(".modal-body").evaluate("element => element.scrollTop = 0")
            page.screenshot(path=str(output / f"review-{label}.png"), animations="disabled")
            assert dialog.evaluate("el => el.scrollWidth <= el.clientWidth + 1"), label

        confirm = dialog.get_by_role("button", name="Prepare reviewed task")
        confirm.click()
        assert "Fixture: install OpenCode CLI" in dialog.get_by_role("alert").inner_text()
        contract["available"] = True
        confirm.click()
        card = page.locator("[data-code-handoff]")
        card.wait_for(timeout=10000)
        assert "Ready to launch locally" in card.inner_text()
        assert "OpenCode coding task" in card.inner_text()
        disclosure = card.locator("details")
        disclosure.locator("summary").click()
        assert "OpenCode" in disclosure.inner_text() and "not Hutch’s budgets" in disclosure.inner_text()
        disclosure.locator("summary").click()
        command = card.locator("[data-copy-code-command]")
        command.click()
        assert page.evaluate("navigator.clipboard.readText()") == command.locator("xpath=../code").inner_text()
        assert "terminal on the Linux Hutch host" in page.locator(".toast").filter(has_text="Launch command copied").inner_text()
        page.locator("#toast-root .toast-close").evaluate_all("buttons => buttons.forEach(button => button.click())")
        for label, width, height in viewports:
            page.set_viewport_size({"width": width, "height": height})
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1, label
            assert card.evaluate("el => el.scrollWidth <= el.clientWidth + 1"), label
            card.scroll_into_view_if_needed()
            page.screenshot(path=str(output / f"prepared-{label}.png"), animations="disabled")

        assert not errors, errors
        assert not external, external
        validation = {
            "test": "tests/e2e/test_browser.py::test_opencode_coding_handoff_is_reviewed_and_responsive",
            "command": "uv run pytest -q tests/e2e/test_browser.py::test_opencode_coding_handoff_is_reviewed_and_responsive --no-header",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(), "hutch_version": package_version("hutch"),
            "browser": browser.version,
            "viewports": [{"name": name, "width": width, "height": height}
                          for name, width, height in viewports],
            "states": ["review", "unavailable_cli_error", "prepared", "copied_command"],
            "external_requests": external, "provider_credentials_used": False,
            "opencode_process_started": False, "provider_request_made": False,
            "source_bot_id": bot.id,
        }
        (output / "validation.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    finally:
        context.tracing.stop(path=str(output / "trace.zip"))
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
              slot.style.cssText = 'position:fixed;left:-10000px;top:0;';
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

            page.goto(f"{base}/legacy/connections")
            heading = page.locator("#main h1")
            heading.wait_for()
            page.evaluate("document.fonts.ready")
            heading_metrics = heading.evaluate("""element => {
              const style = getComputedStyle(element);
              return {
                fontSize: parseFloat(style.fontSize),
                lineHeight: parseFloat(style.lineHeight),
                fontFamily: style.fontFamily,
              };
            }""")
            ratio = heading_metrics["lineHeight"] / heading_metrics["fontSize"]
            assert heading_metrics["fontSize"] == (22 if width <= 720 else 24), (label, heading_metrics)
            assert ratio == pytest.approx(1.25), (label, heading_metrics)
            assert "Archivo" in heading_metrics["fontFamily"], (label, heading_metrics)
            assert page.evaluate("document.fonts.check('700 24px Archivo')"), (label, heading_metrics)
            body_metrics = page.locator("body").evaluate("""element => {
              const style = getComputedStyle(element);
              return {
                fontSize: parseFloat(style.fontSize),
                lineHeight: parseFloat(style.lineHeight),
                fontFamily: style.fontFamily,
              };
            }""")
            body_ratio = body_metrics["lineHeight"] / body_metrics["fontSize"]
            assert body_metrics["fontSize"] == 16, (label, body_metrics)
            assert body_ratio >= 1.5, (label, body_metrics)
            live_status = page.locator("#live-pill")
            live_status.wait_for()
            live_status_animation = live_status.evaluate(
                "element => getComputedStyle(element, '::before').animationName"
            )
            assert live_status_animation == "none", (label, live_status_animation)
            page.evaluate("""() => {
              const main = document.querySelector('#main');
              main.insertAdjacentHTML('beforebegin', `
                <div class="flash notice" id="visual-notice" role="status">
                  <svg class="ico" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m5 12 4 4L19 7"/></svg>
                  <span>Settings saved. This is a visual review fixture.</span>
                </div>
                <div class="flash error" id="visual-error" role="alert">
                  <svg class="ico" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M12 4 22 20H2z"/><path d="M12 10v4"/></svg>
                  <span>Connection failed. This is a visual review fixture.</span>
                </div>`);
            }""")
            flash_styles = page.evaluate("""() => {
              const read = selector => {
                const node = document.querySelector(selector);
                const style = getComputedStyle(node);
                return {
                  leftWidth: style.borderLeftWidth,
                  topWidth: style.borderTopWidth,
                  leftColor: style.borderLeftColor,
                  topColor: style.borderTopColor,
                  textColor: style.color,
                  iconColor: getComputedStyle(node.querySelector('.ico')).color,
                  role: node.getAttribute('role'),
                };
              };
              return {notice: read('#visual-notice'), error: read('#visual-error')};
            }""")
            for kind, expected_role in (("notice", "status"), ("error", "alert")):
                style = flash_styles[kind]
                assert style["leftWidth"] == style["topWidth"] == "1px", (label, kind, style)
                assert style["leftColor"] == style["topColor"], (label, kind, style)
                assert style["textColor"] != style["iconColor"], (label, kind, style)
                assert style["role"] == expected_role, (label, kind, style)
            page.locator("#visual-notice, #visual-error").evaluate_all("nodes => nodes.forEach(node => node.remove())")
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
                             "flash_styles": flash_styles,
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
            "scenario": "Offscreen fixture assertions for working, workflow, running-status and success/error styles; clean Studio and server-rendered Connections captures; no run or provider call",
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


def test_activity_omits_empty_sections_when_attention_is_needed(browser, live):
    """Keep an active Activity view focused on the one populated section."""
    import json
    import platform

    base, app = live
    for bot in (
        Bot(name="design-partner", display_name="Design Partner", model="mock/demo", tools=[]),
        Bot(name="research-partner", display_name="Research Partner", model="mock/demo", tools=[]),
        Bot(name="calendar-helper", display_name="Calendar Helper", model="mock/demo", tools=[]),
        Bot(name="writing-partner", display_name="Writing Partner", model="mock/demo", tools=[]),
    ):
        app.state.store.create_bot(bot)
    payload = {
        "stats": {"bots": 4, "runs_today": 2, "tokens_today": 0, "spend_today": 0},
        "needs_count": 1,
        "approvals": [{"bot_name": "design-partner", "bot_display_name": "Design Partner",
                       "tool": "gmail_send", "risk": "high", "action": "Send the reviewed follow-up"}],
        "humans": [], "failures": [], "running": [], "stale": [],
    }
    output = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/ui-surface-review"
    output.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    errors: list[str] = []
    external: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external.append(request.url)
            if not request.url.startswith(base) else None)
    page.route("**/api/overview", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(payload)))
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    viewports = (("desktop", 1440, 960), ("phone", 390, 844))
    try:
        for label, width, height in viewports:
            page.set_viewport_size({"width": width, "height": height})
            page.goto(f"{base}/#/overview")
            page.get_by_role("heading", name="Activity", exact=True).wait_for()
            section = page.locator(".ov-col.loud")
            assert section.count() == 1 and section.is_visible()
            assert section.get_by_role("heading", name="Needs you 1").is_visible()
            assert section.get_by_text("Send the reviewed follow-up", exact=True).is_visible()
            assert section.get_by_text("Gmail", exact=True).is_visible()
            assert section.get_by_text("gmail_send", exact=True).count() == 0
            assert page.locator("#roster-list [data-switch-bot]").count() == 4
            assert page.locator(".ov-col").count() == 1
            assert page.locator(".ov-all-clear").count() == 0
            assert page.get_by_text("Working now", exact=False).count() == 0
            assert page.get_by_text("Schedule check", exact=False).count() == 0
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
            page.screenshot(path=str(output / f"activity-needs-{label}.png"), full_page=True, animations="disabled")
        assert not errors, errors
        assert not external, external
        validation = {
            "test": "tests/e2e/test_browser.py::test_activity_omits_empty_sections_when_attention_is_needed",
            "command": ".venv/bin/pytest -q -W error::pytest.PytestUnhandledThreadExceptionWarning -W error::SyntaxWarning tests/e2e/test_browser.py::test_activity_omits_empty_sections_when_attention_is_needed",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(), "hutch_version": package_version("hutch"),
            "browser": browser.version,
            "viewports": [{"name": name, "width": width, "height": height}
                          for name, width, height in viewports],
            "state": "one approval; empty activity sections omitted",
            "external_requests": external, "provider_credentials_used": False,
            "provider_request_made": False,
            "source_sha256": {
                name: hashlib.sha256((Path(__file__).resolve().parents[2] / path).read_bytes()).hexdigest()
                for name, path in (("app.js", "src/hutch/server/static/app.js"),
                                   ("style.css", "src/hutch/server/static/style.css"))
            },
        }
        (output / "activity-needs-validation.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    finally:
        context.tracing.stop(path=str(output / "activity-needs-trace.zip"))
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
    store.set_workspace_specialists([specialist.id])
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
        page.get_by_role("heading", name="Apps & AI").wait_for()
        assert page.locator(".service-tile .service-mark-chatgpt img").evaluate(
            "img => img.complete && img.naturalWidth === 721")
        page.locator("#connection-management > summary").click()
        page.get_by_text("Sign in with ChatGPT", exact=True).wait_for()
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


def test_workflow_amendment_preview_adoption_is_explicit_and_responsive(browser, live):
    from hutch.workflow import persistence as workflow_store
    from hutch.workflow import submit as workflow_submit

    base, app = live
    store = app.state.store
    bot = store.create_bot(Bot(name="workflow-amendment-studio", display_name="Amendment review fixture",
                               model="mock/demo", tools=[]))
    conversation, _ = store.create_conversation(
        bot.id, "Amend parked workflow", idem_key="workflow-amendment-conversation",
        request_hash="workflow-amendment-conversation")
    plan = {
        "name": "amendable-human-review",
        "envelope": {"tools": []},
        "budget": {"max_nodes": 8, "max_model_calls": 0},
        "nodes": [{"kind": "ask", "id": "review", "title": "Review findings",
                   "question": "Which findings should be included?", "options": ["All", "Only verified"],
                   "timeout_seconds": 600}],
    }
    saved = workflow_store.save_definition(store, name=plan["name"], plan=plan,
                                           source="operator", activate=False)
    submission = workflow_submit.submit_saved(
        store, bot=bot, definition=saved["definition_id"], inputs={}, origin="api",
        idem_key="workflow-amendment-start", request_hash="workflow-amendment-start",
        auto=False, conversation_id=conversation["id"])
    workflow_id = submission.workflow_run_id
    deadline = time.monotonic() + 20
    pending_questions = []
    while time.monotonic() < deadline:
        pending_questions = workflow_store.questions(store, workflow_id, status="pending")
        if pending_questions:
            break
        time.sleep(0.05)
    assert pending_questions, "the human-review workflow did not park on its question"

    artifact_override = os.environ.get("HUTCH_WORKFLOW_AMENDMENT_ARTIFACTS")
    artifacts = (Path(artifact_override) if artifact_override else
                 Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/workflow-studio/amendment")
    artifacts.mkdir(parents=True, exist_ok=True)
    page = browser.new_page(viewport={"width": 1440, "height": 960}, device_scale_factor=1)
    errors: list[str] = []
    failed_requests: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("requestfailed", lambda request: failed_requests.append(request.url))
    page.context.tracing.start(screenshots=True, snapshots=True, sources=False)
    viewports = []
    try:
        page.goto(f"{base}/#/chat/{bot.name}", wait_until="domcontentloaded")
        panel = page.locator("#workflow-panel")
        panel.get_by_role("button", name="Amend parked run").wait_for()
        old_question_id = pending_questions[0]["id"]
        panel.get_by_role("button", name="Amend parked run").click()
        dialog = page.locator('.modal-card[role="dialog"]')
        dialog.wait_for(state="visible")
        assert dialog.get_by_label("Candidate workflow plan").evaluate(
            "element => document.activeElement === element")
        candidate = {**plan, "nodes": [{**plan["nodes"][0],
                                         "question": "Which evidence-backed findings should remain?"}]}
        dialog.locator("#workflow-amendment-plan").fill(json.dumps(candidate, indent=2))
        with page.expect_response(lambda response: response.url.endswith(
                f"/api/v1/workflows/runs/{workflow_id}/amendments/preview")) as preview_info:
            dialog.get_by_role("button", name="Preview candidate").click()
        preview_response = preview_info.value
        assert preview_response.status == 200, preview_response.text()
        preview_quiescence = preview_response.json()["quiescence"]
        assert preview_quiescence["attempt_parked"] is True
        assert preview_quiescence["owned_work_quiet"] is True
        dialog.get_by_text("Pending questions that adoption would cancel:").wait_for()
        dialog.get_by_text(old_question_id, exact=True).wait_for()
        assert "Reusable completed results" in dialog.inner_text()
        assert "Which evidence-backed findings should remain?" in dialog.inner_text()
        assert dialog.get_by_role("button", name="Revise candidate").is_visible()
        assert dialog.get_by_role("button", name="Adopt amendment").is_visible()

        for label, width, height in (("desktop", 1440, 960), ("tablet", 768, 1024),
                                     ("phone", 360, 800), ("compact-phone", 320, 740)):
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(80)
            overflow = page.evaluate("Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - innerWidth")
            assert overflow <= 1, f"{label} has horizontal overflow: {overflow}px"
            bounds = dialog.bounding_box()
            assert bounds and bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= width + 1
            dialog.locator(".modal-body").evaluate("element => { element.scrollTop = 0; }")
            page.wait_for_timeout(40)
            page.screenshot(path=str(artifacts / f"editor-{label}.png"), full_page=True, animations="disabled")
            preview_panel = dialog.locator(".workflow-amendment-preview")
            preview_panel.scroll_into_view_if_needed()
            page.wait_for_timeout(40)
            page.screenshot(path=str(artifacts / f"preview-{label}.png"), full_page=True, animations="disabled")
            adopt_bounds = dialog.get_by_role("button", name="Adopt amendment").bounding_box()
            assert adopt_bounds and adopt_bounds["height"] >= 44, f"{label} adopt target is too small"
            viewports.append({"label": label, "size": [width, height], "dialog_bounds": bounds,
                              "horizontal_overflow_px": overflow,
                              "adopt_target_height": adopt_bounds["height"]})

        assert dialog.get_by_role("button", name="Adopt amendment").is_disabled()
        assert workflow_store.workflow_run(store, workflow_id)["revision_id"] == submission.revision_id
        dialog.get_by_label("I understand these questions will be canceled and archived").check()
        adopt_button = dialog.get_by_role("button", name="Adopt amendment")
        assert adopt_button.is_enabled()
        cancel_label = dialog.locator(".workflow-amendment-questions label")
        cancel_label.scroll_into_view_if_needed()
        label_bounds = cancel_label.bounding_box()
        footer_bounds = dialog.locator(".modal-footer").bounding_box()
        assert label_bounds and footer_bounds
        footer_clearance = footer_bounds["y"] - (label_bounds["y"] + label_bounds["height"])
        assert footer_clearance >= 8, (
            f"the cancellation choice needs breathing room above the fixed footer; got {footer_clearance:.1f}px"
        )
        page.screenshot(path=str(artifacts / "explicit-cancellation-compact-phone.png"),
                        full_page=True, animations="disabled")
        adopt_button.focus()
        with page.expect_response(lambda response: response.url.endswith(
                f"/api/v1/workflows/runs/{workflow_id}/amendments/adopt")) as response_info:
            page.keyboard.press("Enter")
        response = response_info.value
        assert response.status == 200, response.text()
        assert response.request.headers.get("idempotency-key")
        assert response.request.post_data_json["cancel_pending_questions"] is True
        dialog.wait_for(state="detached")

        deadline = time.monotonic() + 20
        new_questions = []
        while time.monotonic() < deadline:
            new_questions = workflow_store.questions(store, workflow_id, status="pending")
            if new_questions and new_questions[0]["id"] != old_question_id:
                break
            time.sleep(0.05)
        assert new_questions and new_questions[0]["id"] != old_question_id
        history = page.request.get(f"{base}/api/v1/workflows/runs/{workflow_id}/amendments")
        assert history.status == 200, history.text()
        history_id = history.json()["items"][0]["id"]
        archived = page.request.get(f"{base}/api/v1/workflows/runs/{workflow_id}/amendments/{history_id}")
        assert archived.status == 200, archived.text()
        assert any(question["id"] == old_question_id and question["status"] == "cancelled"
                   for question in archived.json()["questions"])
        await_focus = page.evaluate("document.activeElement?.dataset?.workflowAction || ''")
        assert await_focus == "", "focus should move to the composer while the amended run is active"
        assert page.locator("#chat-prompt").evaluate("element => document.activeElement === element")
        panel.get_by_role("button", name="Amend parked run").wait_for()
        page.locator("#workflow-panel").get_by_text("Waiting · saved workflow", exact=True).wait_for()
        page.screenshot(path=str(artifacts / "desktop-after-adoption.png"), full_page=True, animations="disabled")
        assert not errors, errors
        assert not failed_requests, failed_requests
        page.context.tracing.stop(path=str(artifacts / "trace.zip"))
        source_paths = ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                        "src/hutch/server/workflows_api.py", "src/hutch/workflow/amendments.py",
                        "src/hutch/workflow/persistence.py", "tests/e2e/test_browser.py")
        visual_artifacts = {file.name: hashlib.sha256(file.read_bytes()).hexdigest()
                            for file in artifacts.iterdir() if file.suffix in {".png", ".zip"}}
        (artifacts / "results.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_workflow_amendment_preview_adoption_is_explicit_and_responsive",
            "browser": browser.browser_type.name, "browser_version": browser.version,
            "playwright_version": package_version("playwright"), "viewports": viewports,
            "workflow_id": workflow_id, "old_question_id": old_question_id,
            "new_question_id": new_questions[0]["id"], "history_id": history_id,
            "interaction": "plan edited, field-level diff inspected, adoption stays disabled until explicit question cancellation is checked, adoption submitted with Enter; composer receives focus while continuation runs and the parked amend control returns",
            "cancellation_choice_bounds": label_bounds,
            "fixed_footer_bounds": footer_bounds,
            "page_errors": errors, "failed_requests": failed_requests, "provider_calls": 0,
            "source_sha256": {relative: hashlib.sha256((artifacts.parents[4] / relative).read_bytes()).hexdigest()
                              for relative in source_paths},
            "visual_artifact_sha256": visual_artifacts,
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        try:
            page.context.tracing.stop()
        except Exception:
            pass
        page.close()


def test_workflow_amendment_carry_preview_is_clear_and_responsive(browser, live, monkeypatch):
    import hutch.engine as engine_module
    from hutch.workflow import persistence as workflow_store
    from hutch.workflow import submit as workflow_submit

    entered = threading.Event()
    release = threading.Event()

    class ControlledRuntime:
        kind = "amendment-carry-visual-test"

        def execute(self, run, ctx, tools, stop):
            entered.set()
            assert release.wait(30), "the browser test did not release its controlled step"
            content = "carried worker result"
            ctx.emit(Event(run_id=run.id, type=EventType.message,
                           data={"role": "assistant", "content": content}))
            return content

    monkeypatch.setattr(engine_module, "get_runtime", lambda _bot: ControlledRuntime())
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-unused-by-controlled-runtime")
    base, app = live
    store = app.state.store
    bot = store.create_bot(Bot(name="workflow-amendment-carry-visual", display_name="Carry preview fixture",
                               model="openai/gpt-4o-mini", tools=[]))
    conversation, _ = store.create_conversation(
        bot.id, "Review a workflow amendment", idem_key="workflow-amendment-carry-conversation",
        request_hash="workflow-amendment-carry-conversation")
    plan = {
        "name": "amendment-carry-visual",
        "inputs": {"topic": {"type": "string", "default": "stable topic"}},
        "envelope": {"tools": [], "models": ["openai/gpt-4o-mini"]},
        "budget": {"max_nodes": 5, "max_model_calls": 2, "max_wall_seconds": 60},
        "nodes": [{"kind": "agent", "id": "work", "role": "worker", "model": "$bot",
                   "instruction": "Review {{topic}}.", "inputs": {"topic": {"ref": "input.topic"}},
                   "tools": []}],
    }
    saved = workflow_store.save_definition(store, name=plan["name"], plan=plan,
                                           source="operator", activate=False)
    submission = workflow_submit.submit_saved(
        store, bot=bot, definition=saved["definition_id"], inputs={}, origin="api",
        idem_key="workflow-amendment-carry-submit", request_hash="workflow-amendment-carry-submit",
        auto=False, conversation_id=conversation["id"])
    workflow_id = submission.workflow_run_id
    artifacts_override = os.environ.get("HUTCH_WORKFLOW_AMENDMENT_CARRY_ARTIFACTS")
    artifacts = (Path(artifacts_override) if artifacts_override else
                 Path(__file__).resolve().parents[2] /
                 "docs/realignment/artifacts/workflow-studio/amendment-carry-active-step-2026-10-11")
    artifacts.mkdir(parents=True, exist_ok=True)
    page = browser.new_page(viewport={"width": 1440, "height": 960}, device_scale_factor=1,
                            reduced_motion="reduce")
    page.set_default_timeout(5000)
    errors: list[str] = []
    failed_requests: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("requestfailed", lambda request: failed_requests.append(request.url))
    page.context.tracing.start(screenshots=True, snapshots=True, sources=False)
    viewports = []
    try:
        assert entered.wait(10), "the controlled worker did not start"
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            detail = workflow_store.workflow_run(store, workflow_id)
            attempt = store.get_run(str(detail["attempt_run_id"])) if detail else None
            if detail and detail["status"] == "waiting" and attempt and attempt.status.value == "waiting_workflow":
                break
            time.sleep(0.05)
        else:
            raise AssertionError("the workflow did not park with its worker child active")

        page.goto(f"{base}/#/chat/{bot.name}", wait_until="domcontentloaded")
        panel = page.locator("#workflow-panel")
        panel.get_by_role("button", name="Amend parked run").wait_for()
        panel.get_by_role("button", name="Amend parked run").click()
        dialog = page.locator('.modal-card[role="dialog"]')
        dialog.wait_for(state="visible")
        candidate = json.loads(json.dumps(plan))
        candidate["nodes"].append({"kind": "transform", "id": "after", "op": "constant",
                                   "args": {"value": "added after review"}})
        dialog.locator("#workflow-amendment-plan").fill(json.dumps(candidate, indent=2))
        with page.expect_response(lambda response: response.url.endswith(
                f"/api/v1/workflows/runs/{workflow_id}/amendments/preview")) as preview_info:
            dialog.get_by_role("button", name="Preview candidate").click()
        response = preview_info.value
        assert response.status == 200, response.text()
        quiescence = response.json()["quiescence"]
        assert quiescence["owned_work_quiet"] is False
        assert quiescence["owned_work_carryable"] is True
        assert [item["site_id"] for item in quiescence["carry_active_nodes"]] == ["work"]
        carried_node = quiescence["carry_active_nodes"][0]
        assert carried_node["model"] == "openai/gpt-4o-mini" and carried_node["role"] == "worker"
        dialog.locator(".workflow-amendment-preview").wait_for()
        dialog_text = dialog.inner_text()
        assert "original contract" in dialog_text and "new revision starts after it settles" in dialog_text, dialog_text
        assert "worker on openai/gpt-4o-mini" in dialog_text, dialog_text
        assert "Unchanged work to carry" in dialog_text, dialog_text
        adopt_button = dialog.get_by_role("button", name="Adopt amendment")
        assert adopt_button.is_enabled()

        for label, width, height in (("desktop", 1440, 960), ("tablet", 768, 1024),
                                     ("phone", 360, 800), ("compact-phone", 320, 740)):
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(80)
            overflow = page.evaluate(
                "Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - innerWidth")
            assert overflow <= 1, f"{label} has horizontal overflow: {overflow}px"
            bounds = dialog.bounding_box()
            assert bounds and bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= width + 1
            dialog.locator(".modal-body").evaluate("element => { element.scrollTop = 0; }")
            page.wait_for_timeout(40)
            page.screenshot(path=str(artifacts / f"carry-preview-{label}.png"),
                            full_page=True, animations="disabled")
            carry_summary = dialog.locator(".workflow-amendment-preview summary").filter(
                has_text="Unchanged work to carry")
            carry_summary.scroll_into_view_if_needed()
            carry_reason = dialog.locator(".workflow-amendment-preview li").filter(
                has_text="unchanged top-level tool-free worker contract")
            carry_reason.scroll_into_view_if_needed()
            reason_bounds = carry_reason.bounding_box()
            footer_bounds = dialog.locator(".modal-footer").bounding_box()
            assert reason_bounds and footer_bounds
            assert reason_bounds["y"] + reason_bounds["height"] <= footer_bounds["y"] + 1, (
                f"{label} carried-step explanation is obscured by the fixed footer")
            page.screenshot(path=str(artifacts / f"carry-review-{label}.png"),
                            full_page=True, animations="disabled")
            target = adopt_button.bounding_box()
            assert target and target["height"] >= 44, f"{label} adopt target is too small"
            viewports.append({"label": label, "size": [width, height], "dialog_bounds": bounds,
                              "horizontal_overflow_px": overflow,
                              "adopt_target_height": target["height"],
                              "carried_step_reason_bounds": reason_bounds,
                              "fixed_footer_bounds": footer_bounds})
        assert not errors, errors
        assert not failed_requests, failed_requests
        page.context.tracing.stop(path=str(artifacts / "trace.zip"))
        source_paths = ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                        "src/hutch/server/workflows_api.py", "src/hutch/workflow/amendments.py",
                        "src/hutch/workflow/persistence.py", "tests/e2e/test_browser.py")
        visual_artifacts = {file.name: hashlib.sha256(file.read_bytes()).hexdigest()
                            for file in artifacts.iterdir() if file.suffix in {".png", ".zip"}}
        (artifacts / "results.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_workflow_amendment_carry_preview_is_clear_and_responsive",
            "browser": browser.browser_type.name, "browser_version": browser.version,
            "playwright_version": package_version("playwright"), "viewports": viewports,
            "workflow_id": workflow_id,
            "carried_node": carried_node,
            "quiescence": {key: quiescence[key] for key in
                           ("attempt_parked", "owned_work_quiet", "owned_work_carryable")},
            "interaction": "live tool-free worker remained active while the owner inspected a later-node amendment; carry contract and adoption readiness were visible",
            "view_state": "owner-local amendment editor shows the read-only candidate diff and one live, unchanged, tool-free worker child; adoption is enabled while that exact child remains under its original run contract",
            "page_errors": errors, "failed_requests": failed_requests, "provider_calls": 0,
            "source_sha256": {relative: hashlib.sha256((artifacts.parents[4] / relative).read_bytes()).hexdigest()
                              for relative in source_paths},
            "visual_artifact_sha256": visual_artifacts,
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        release.set()
        try:
            page.context.tracing.stop()
        except Exception:
            pass
        page.close()



def test_workflow_amendment_drain_control_is_owner_reviewable_and_responsive(browser, live, monkeypatch):
    """Drive the real owner UI/API path while a tool-free child is active and paused."""
    import hutch.engine as engine_module
    from hutch.runtime.base import RunAborted
    from hutch.workflow import persistence as workflow_store
    from hutch.workflow import submit as workflow_submit

    entered = threading.Event()
    started_prompts: list[str] = []

    class ControlledRuntime:
        kind = "amendment-drain-visual-test"

        def execute(self, run, ctx, tools, stop):
            started_prompts.append(run.prompt)
            if "Original review" in run.prompt:
                entered.set()
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline and not stop():
                    time.sleep(0.01)
                assert stop(), "the owner UI did not stop the affected tool-free step"
                raise RunAborted("stopped", "affected tool-free step drained for amendment")
            content = "finished under the amended instruction"
            ctx.emit(Event(run_id=run.id, type=EventType.message,
                           data={"role": "assistant", "content": content}))
            return content

    monkeypatch.setattr(engine_module, "get_runtime", lambda _bot: ControlledRuntime())
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-unused-by-controlled-runtime")
    base, app = live
    store = app.state.store
    bot = store.create_bot(Bot(name="workflow-amendment-drain-visual", display_name="Drain preview fixture",
                               model="openai/gpt-4o-mini", tools=[]))
    conversation, _ = store.create_conversation(
        bot.id, "Review an affected workflow step", idem_key="workflow-amendment-drain-conversation",
        request_hash="workflow-amendment-drain-conversation")
    plan = {
        "name": "amendment-drain-visual",
        "inputs": {"topic": {"type": "string", "default": "stable topic"}},
        "envelope": {"tools": [], "models": ["openai/gpt-4o-mini"]},
        "budget": {"max_nodes": 5, "max_model_calls": 4, "max_wall_seconds": 60},
        "nodes": [{"kind": "agent", "id": "work", "role": "worker", "model": "$bot",
                   "instruction": "Original review of {{topic}}.",
                   "inputs": {"topic": {"ref": "input.topic"}}, "tools": []}],
    }
    saved = workflow_store.save_definition(store, name=plan["name"], plan=plan,
                                           source="operator", activate=False)
    submission = workflow_submit.submit_saved(
        store, bot=bot, definition=saved["definition_id"], inputs={}, origin="api",
        idem_key="workflow-amendment-drain-submit", request_hash="workflow-amendment-drain-submit",
        auto=False, conversation_id=conversation["id"])
    workflow_id = submission.workflow_run_id
    repo_root = Path(__file__).resolve().parents[2]
    artifacts_override = os.environ.get("HUTCH_WORKFLOW_AMENDMENT_DRAIN_ARTIFACTS")
    artifacts = Path(artifacts_override or "/tmp/hutch-workflow-amendment-drain-artifacts")
    artifacts.mkdir(parents=True, exist_ok=True)
    page = browser.new_page(viewport={"width": 1440, "height": 960}, device_scale_factor=1,
                            reduced_motion="reduce")
    page.set_default_timeout(5000)
    errors: list[str] = []
    failed_requests: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.on("requestfailed", lambda request: failed_requests.append(request.url))
    viewports = []
    try:
        assert entered.wait(10), "the controlled original worker did not start"
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            current = workflow_store.workflow_run(store, workflow_id)
            attempt = store.get_run(str(current["attempt_run_id"])) if current else None
            if current and current["status"] == "waiting" and attempt and attempt.status is RunStatus.waiting_workflow:
                break
            time.sleep(0.05)
        else:
            raise AssertionError("the workflow did not park with its child active")

        page.goto(f"{base}/#/chat/{bot.name}", wait_until="domcontentloaded")
        conversation_switcher = page.locator("#conversation-switcher")
        conversation_switcher.wait_for(state="visible")
        if conversation_switcher.input_value() != conversation["id"]:
            conversation_switcher.select_option(conversation["id"])
        panel = page.locator("#workflow-panel")
        panel.wait_for(state="visible")
        pause_button = panel.get_by_role("button", name=re.compile(r"Pause (?:workflow|after current work)"))
        pause_button.wait_for()
        with page.expect_response(lambda response: response.url.endswith(
                f"/api/v1/workflows/runs/{workflow_id}/pause")) as pause_info:
            pause_button.click()
        assert pause_info.value.status == 200, pause_info.value.text()
        panel.get_by_role("button", name="Amend parked run").click()
        dialog = page.locator('.modal-card[role="dialog"]')
        dialog.wait_for(state="visible")
        candidate = json.loads(json.dumps(plan))
        candidate["nodes"][0]["instruction"] = "Amended review of {{topic}}."
        candidate["nodes"].append({"kind": "transform", "id": "after", "op": "constant",
                                   "args": {"value": "after review"}})
        dialog.locator("#workflow-amendment-plan").fill(json.dumps(candidate, indent=2))
        with page.expect_response(lambda response: response.url.endswith(
                f"/api/v1/workflows/runs/{workflow_id}/amendments/preview")) as preview_info:
            dialog.get_by_role("button", name="Preview candidate").click()
        preview_response = preview_info.value
        assert preview_response.status == 200, preview_response.text()
        preview = preview_response.json()
        assert preview["quiescence"]["attempt_parked"] is True
        assert preview["quiescence"]["owned_work_quiet"] is False
        assert preview["quiescence"]["carry_active_nodes"] == []
        assert [item["site_id"] for item in preview["quiescence"]["drainable_active_nodes"]] == ["work"]
        assert dialog.get_by_role("button", name="Stop affected steps").is_visible()
        assert dialog.get_by_role("button", name="Adoption unavailable").is_disabled()
        assert "unfinished model response" in dialog.inner_text()
        assert "tool-free child with no owned descendants" in dialog.inner_text()

        stop_button = dialog.get_by_role("button", name="Stop affected steps")
        for label, width, height in (("desktop", 1440, 960), ("tablet", 768, 1024),
                                     ("phone", 360, 800), ("compact-phone", 320, 740)):
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(80)
            overflow = page.evaluate(
                "Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - innerWidth")
            assert overflow <= 1, f"{label} has horizontal overflow: {overflow}px"
            dialog_bounds = dialog.bounding_box()
            assert dialog_bounds and dialog_bounds["x"] >= 0 and dialog_bounds["x"] + dialog_bounds["width"] <= width + 1
            stop_button.scroll_into_view_if_needed()
            target = stop_button.bounding_box()
            assert target and target["height"] >= 44, f"{label} stop target is too small"
            page.screenshot(path=str(artifacts / f"drain-preview-{label}.png"),
                            full_page=True, animations="disabled")
            viewports.append({"label": label, "size": [width, height], "dialog_bounds": dialog_bounds,
                              "horizontal_overflow_px": overflow, "stop_target": target})

        stop_button.focus()
        with page.expect_response(lambda response: response.url.endswith(
                f"/api/v1/workflows/runs/{workflow_id}/amendments/drain")) as drain_info:
            page.keyboard.press("Enter")
        drain_response = drain_info.value
        assert drain_response.status == 200, drain_response.text()
        assert drain_response.request.headers.get("idempotency-key")
        drain_result = drain_response.json()
        assert [(item["site_id"], item["instance_key"]) for item in drain_result["requested"]] == [("work", "once")]
        dialog.get_by_text("Stopped affected steps · 1", exact=True).wait_for(timeout=7000)
        assert "owned processes have drained" in dialog.locator("#workflow-amendment-status").inner_text()
        assert dialog.get_by_role("button", name="Adopt amendment").is_enabled()
        page.set_viewport_size({"width": 320, "height": 740})
        stopped_summary = dialog.get_by_text("Stopped affected steps · 1", exact=True)
        stopped_summary.scroll_into_view_if_needed()
        page.screenshot(path=str(artifacts / "drain-complete-compact-phone.png"),
                        full_page=True, animations="disabled")
        adopt_button = dialog.get_by_role("button", name="Adopt amendment")
        adopt_button.focus()
        with page.expect_response(lambda response: response.url.endswith(
                f"/api/v1/workflows/runs/{workflow_id}/amendments/adopt")) as adopt_info:
            page.keyboard.press("Enter")
        adopt_response = adopt_info.value
        assert adopt_response.status == 200, adopt_response.text()
        history_id = adopt_response.json()["history_id"]
        dialog.wait_for(state="detached")

        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            current = workflow_store.workflow_run(store, workflow_id)
            if current and current["status"] in ("succeeded", "failed", "stopped", "outcome_unknown"):
                break
            time.sleep(0.05)
        assert current and current["status"] == "succeeded", current
        history = page.request.get(f"{base}/api/v1/workflows/runs/{workflow_id}/amendments/{history_id}")
        assert history.status == 200, history.text()
        archived = next(node for node in history.json()["nodes"] if node["site_id"] == "work")
        assert archived["status"] == "cancelled"
        assert len(started_prompts) == 2
        assert not errors, errors
        assert not failed_requests, failed_requests
        source_paths = ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                        "src/hutch/server/workflows_api.py", "src/hutch/workflow/amendments.py",
                        "src/hutch/workflow/persistence.py", "tests/e2e/test_browser.py")
        visual_artifacts = {file.name: hashlib.sha256(file.read_bytes()).hexdigest()
                            for file in artifacts.iterdir() if file.suffix == ".png"}
        (artifacts / "results.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_workflow_amendment_drain_control_is_owner_reviewable_and_responsive",
            "browser": browser.browser_type.name, "browser_version": browser.version,
            "playwright_version": package_version("playwright"), "viewports": viewports,
            "workflow_id": workflow_id, "drained_run_id": drain_result["requested"][0]["run_id"],
            "history_id": history_id, "final_status": current["status"],
            "interaction": "owner paused the live workflow, inspected the changed plan and drainability, keyboard-stopped the tool-free affected child, waited for cleanup, then adopted the revised plan with Enter",
            "provider_calls": 0, "page_errors": errors, "failed_requests": failed_requests,
            "source_sha256": {relative: hashlib.sha256((repo_root / relative).read_bytes()).hexdigest()
                              for relative in source_paths},
            "visual_artifact_sha256": visual_artifacts,
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        page.close()


def test_model_capability_observations_show_unknown_and_latest_evidence(browser, live):
    base, _app = live
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/model-capabilities"
    out.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    errors: list[str] = []
    external: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external.append(request.url)
            if urlsplit(request.url).hostname not in {"127.0.0.1", "localhost"} else None)
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    viewports = (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844),
                 ("compact-phone", 320, 740))
    capability_state = {"items": [], "error": False, "hold": True}
    pending_capability_routes = []
    def capability_response(route):
        if capability_state["hold"]:
            capability_state["hold"] = False
            pending_capability_routes.append(route)
            return
        if capability_state["error"]:
            route.fulfill(status=503, json={"detail": "Fixture history unavailable"})
            return
        route.fulfill(json={"items": capability_state["items"], "next_after_id": None})
    page.route("**/api/v1/model-capabilities**", capability_response)
    try:
        page.goto(base + "/#/connections")
        page.locator("#connection-management > summary").click()
        panel = page.get_by_role("region", name="Model tool-call observations")
        panel.wait_for()
        loading_state = panel.locator("#model-capability-results [role=status]")
        loading_state.wait_for()
        assert "Loading model tool-call observations" in loading_state.inner_text()
        panel.scroll_into_view_if_needed()
        page.screenshot(path=str(out / "loading-desktop.png"), animations="disabled")
        assert len(pending_capability_routes) == 1
        pending_capability_routes.pop().fulfill(json={"items": [], "next_after_id": None})
        empty_state = panel.locator("#model-capability-results [role=status]")
        empty_state.wait_for()
        assert "unknown, not passed or failed" in empty_state.inner_text()
        for label, width, height in viewports:
            page.set_viewport_size({"width": width, "height": height})
            panel.scroll_into_view_if_needed()
            page.screenshot(path=str(out / f"empty-{label}.png"), animations="disabled")
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1, label

        capability_state["error"] = True
        page.reload()
        page.locator("#connection-management > summary").click()
        panel = page.get_by_role("region", name="Model tool-call observations")
        error_state = panel.locator("#model-capability-results [role=alert]")
        error_state.wait_for()
        assert "history could not be loaded" in error_state.inner_text()
        for label, width, height in (("desktop", 1440, 960), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            panel.scroll_into_view_if_needed()
            page.screenshot(path=str(out / f"error-{label}.png"), animations="disabled")
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1, label

        capability_state["error"] = False
        capability_state["items"] = [{"id": 2, "run_id": "run_fixture", "provider": "fixture-route",
            "account_id": "fixture-account", "model": "fixture-model", "route_revision": "a" * 64,
            "capability": "function_tool_calls", "source_tool": "list_files",
            "observed_at": datetime.now(timezone.utc).isoformat(), "status": "observed",
            "scope": "exact connection, account, model, and route revision"}]
        page.reload()
        page.locator("#connection-management > summary").click()
        panel = page.get_by_role("region", name="Model tool-call observations")
        panel.get_by_text("fixture-route · fixture-model", exact=True).wait_for()
        panel.get_by_text("list_files", exact=True).wait_for()
        panel.get_by_text("route revision aaaaaaaaaaaa", exact=False).wait_for()
        assert "fixture-account" not in panel.inner_text()
        for label, width, height in viewports:
            page.set_viewport_size({"width": width, "height": height})
            panel.scroll_into_view_if_needed()
            page.screenshot(path=str(out / f"observed-{label}.png"), animations="disabled")
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1, label
            nested_overflow = panel.evaluate("el => el.scrollWidth - el.clientWidth")
            assert nested_overflow <= 1, (label, nested_overflow)
        assert not errors, errors
        assert not external, external
        (out / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_model_capability_observations_show_unknown_and_latest_evidence",
            "command": "uv run pytest -q tests/e2e/test_browser.py::test_model_capability_observations_show_unknown_and_latest_evidence",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(), "hutch_version": package_version("hutch"),
            "browser": browser.version,
            "viewports": [{"name": label, "width": width, "height": height} for label, width, height in viewports],
            "states": ["loading", "empty_unknown", "history_unavailable", "observed"],
            "inspected_screenshots": ["loading-desktop.png", "empty-phone.png", "error-phone.png",
                                      "observed-desktop.png", "observed-tablet.png", "observed-phone.png",
                                      "observed-compact-phone.png"],
            "external_requests": external, "provider_credentials_used": False,
            "capability_call_live": False, "fixture_evidence": True,
        }, indent=2) + "\n")
    finally:
        try:
            context.tracing.stop(path=str(out / "model-capabilities-trace.zip"))
        except Exception:
            pass
        context.close()


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
        def account_can_create_events(account):
            return (account.get("event_creation_opted_in") is True and
                    "https://www.googleapis.com/auth/calendar.events.owned" in account.get("scopes", []))

        @staticmethod
        def can_create_events(account_id):
            return False

        @staticmethod
        def list_calendars(account_id):
            return [{"id": "primary", "name": "Personal Calendar", "primary": True, "access_role": "owner"},
                    {"id": "team@example.test", "name": "Team Calendar", "primary": False, "access_role": "reader"}]

        @staticmethod
        def start(label, callback, *, allow_event_creation=False):
            from hutch.google_calendar import OAuthStart
            return OAuthStart("https://accounts.google.com/o/oauth2/v2/auth?state=fixture", "fixture")

        @staticmethod
        def callback_uri(request):
            port = request.scope["server"][1]
            return f"http://127.0.0.1:{port}/api/v1/connections/google-calendar/callback"

    monkeypatch.setattr("hutch.google_calendar.GoogleCalendarBook", FixtureGoogleCalendarBook)
    bot = Bot(name="calendar-assistant", display_name="Calendar Assistant", model="mock/demo", tools=[])
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
        page.get_by_role("heading", name="Apps & AI").wait_for()
        page.locator("#connection-management > summary").click()
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
        account_card = page.locator('[data-google-calendar-account="gcal_0123456789abcdef01234567"]')
        bot_selector = account_card.locator("[data-google-calendar-bot]")
        assert bot_selector.locator("option:checked").inner_text() == "Calendar Assistant"
        grant_summary = account_card.locator(".google-calendar-grants .device-row")
        assert "Calendar Assistant" in grant_summary.inner_text()
        assert "calendar-assistant" not in grant_summary.inner_text()
        assert page.get_by_text("retained in this Bot's run history", exact=False).is_visible()
        assert page.get_by_text("Google's OAuth grant is account-level read-only", exact=False).is_visible()
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
        page.get_by_text("Finish Google read-only sign-in in the new browser tab", exact=False).wait_for()
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


def test_google_calendar_event_creation_scope_is_explicit_and_owner_only(browser, live, monkeypatch):
    from hutch.google_calendar import OAuthStart

    base, app = live
    monkeypatch.setenv("HUTCH_GOOGLE_OAUTH_CLIENT_ID", "fixture-client.apps.googleusercontent.com")
    write_account_id = "gcal_1123456789abcdef01234567"
    write_scope = "https://www.googleapis.com/auth/calendar.events.owned"

    class FixtureGoogleCalendarBook:
        accounts_rows = [{"id": write_account_id, "label": "Work calendar",
                          "created_at": "2026-10-09T00:00:00+00:00", "scopes": [
                              "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
                              "https://www.googleapis.com/auth/calendar.events.readonly", write_scope],
                          "event_creation_opted_in": True,
                          "status": "connected"}]
        sign_in_calls = []

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
        def account_can_create_events(account):
            return (account.get("event_creation_opted_in") is True and
                    write_scope in account.get("scopes", []))

        @staticmethod
        def can_create_events(account_id):
            return account_id == write_account_id

        @staticmethod
        def list_calendars(account_id):
            return [{"id": "primary", "name": "Personal Calendar", "primary": True, "access_role": "owner"},
                    {"id": "team@example.test", "name": "Shared Team Calendar", "primary": False,
                     "access_role": "writer"}]

        @classmethod
        def start(cls, label, callback, *, allow_event_creation=False):
            cls.sign_in_calls.append((label, allow_event_creation))
            scopes = "calendar.calendarlist.readonly calendar.events.readonly"
            if allow_event_creation:
                scopes += " " + write_scope
            url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({"state": "fixture", "scope": scopes})
            return OAuthStart(url, "fixture")

        @staticmethod
        def callback_uri(request):
            port = request.scope["server"][1]
            return f"http://127.0.0.1:{port}/api/v1/connections/google-calendar/callback"

    monkeypatch.setattr("hutch.google_calendar.GoogleCalendarBook", FixtureGoogleCalendarBook)
    bot = Bot(name="calendar-owner", display_name="Calendar Owner", model="mock/demo", tools=[])
    app.state.store.create_bot(bot)
    browser_context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    browser_context.tracing.start(screenshots=True, snapshots=True, sources=True)
    page = browser_context.new_page()
    page.add_init_script("""
      window.__calendarOAuth = { target: null, url: null, opener: 'not-set' };
      window.open = (_url, target) => {
        window.__calendarOAuth.target = target;
        return {
          set opener(value) { window.__calendarOAuth.opener = value; },
          location: { replace(value) { window.__calendarOAuth.url = value; } },
          close() {}
        };
      };
    """)
    errors, external = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external.append(request.url)
            if not request.url.startswith(base) else None)
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/google-calendar-event-creation"
    out.mkdir(parents=True, exist_ok=True)
    captures = []
    try:
        page.goto(base + "/#/connections")
        page.get_by_role("heading", name="Apps & AI").wait_for()
        page.locator("#connection-management > summary").click()
        account = page.locator(f'[data-google-calendar-account="{write_account_id}"]')
        create_access = account.locator("[data-google-calendar-create-access]")
        assert create_access.is_disabled()
        page.get_by_role("button", name="Load calendars").click()
        calendar = account.locator("[data-google-calendar-calendar]")
        calendar.wait_for(state="visible")
        calendar.select_option("team@example.test")
        assert "read only here" in calendar.locator("option:checked").inner_text()
        assert create_access.is_disabled(), "shared writer calendars must not receive this owned-calendar scope"
        calendar.select_option("primary")
        assert create_access.is_enabled()
        create_access.check()
        calendar.select_option("team@example.test")
        assert create_access.is_disabled() and not create_access.is_checked()
        assert "This selection will stay read-only" in account.locator("[data-google-calendar-status]").inner_text()
        calendar.select_option("primary")
        assert create_access.is_enabled()
        create_access.check()
        grant_button = account.get_by_role("button", name="Grant read and create access")
        assert grant_button.is_enabled()
        grant_button.click()
        approval = page.get_by_role("dialog", name="Grant event creation")
        assert "Personal Calendar" in approval.inner_text() and "primary" not in approval.inner_text()
        approval.get_by_text("Google’s account-level scope also permits changing and deleting events on calendars you own", exact=False).wait_for()
        for label, width, height in (("desktop", 1440, 960), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            page.screenshot(path=str(out / f"permission-review-{label}.png"), animations="disabled")
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1, label
            if width <= 390:
                assert approval.get_by_role("button", name="Grant after review").bounding_box()["height"] >= 44
        page.set_viewport_size({"width": 1440, "height": 960})
        approval.get_by_role("button", name="Grant after review").click()
        page.get_by_text("Can read and create events on Personal Calendar", exact=False).wait_for()
        grant = app.state.store.google_calendar_grant(bot.id)
        assert grant and grant["allow_event_creation"] is True and grant["calendar_id"] == "primary"
        grant_summary = account.locator(".google-calendar-grants .device-row")
        grant_summary.wait_for(state="visible")
        assert "every creation needs approval" in grant_summary.inner_text()
        page.get_by_role("button", name="Dismiss notification").click()

        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024),
                                     ("phone", 390, 844), ("compact-phone", 320, 740)):
            page.set_viewport_size({"width": width, "height": height})
            account.scroll_into_view_if_needed()
            page.screenshot(path=str(out / f"owner-grant-{label}.png"), animations="disabled")
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, overflow)
            if width <= 390:
                assert account.get_by_role("button", name="Revoke Bot access").bounding_box()["height"] >= 44
            captures.append({"size": label, "viewport": [width, height], "scene": "owned calendar event-creation grant",
                             "horizontal_overflow": overflow})

        assert page.locator("#google-calendar-event-creation").is_enabled()
        page.locator("#google-calendar-label").fill("Write-enabled account")
        page.locator("#google-calendar-event-creation").check()
        page.get_by_role("button", name="Connect Google Calendar").click()
        page.get_by_text("Finish Google sign-in for event creation", exact=False).wait_for()
        oauth = page.evaluate("window.__calendarOAuth")
        assert oauth["target"] == "_blank" and oauth["opener"] is None
        query = parse_qs(urlsplit(oauth["url"]).query)
        assert write_scope in query["scope"][0].split()
        assert FixtureGoogleCalendarBook.sign_in_calls[-1] == ("Write-enabled account", True)
        assert not errors, errors
        assert not external, external
        (out / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_google_calendar_event_creation_scope_is_explicit_and_owner_only",
            "command": ("PLAYWRIGHT_BROWSERS_PATH=/home/kevina/.cache/ms-playwright .venv/bin/pytest -q "
                        "-W error::pytest.PytestUnhandledThreadExceptionWarning -W error::SyntaxWarning "
                        "tests/e2e/test_browser.py::test_google_calendar_event_creation_scope_is_explicit_and_owner_only"),
            "captured_at": datetime.now(timezone.utc).isoformat(), "browser": browser.version,
            "provider_credentials_used": False, "provider_calls": 0,
            "scenario": "Fixture-only account consent metadata, owner calendar selection, disabled shared-writer grant, exact user review, local persistence and explicit OAuth scope choice",
            "external_requests": external, "page_errors": errors, "captures": captures,
            "source_sha256": {path: hashlib.sha256((out.parents[3] / path).read_bytes()).hexdigest()
                              for path in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                           "src/hutch/server/app.py", "src/hutch/store.py",
                                           "src/hutch/google_calendar.py", "src/hutch/tools/google_calendar.py")},
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        try:
            browser_context.tracing.stop(path=str(out / "google-calendar-write-trace.zip"))
        except Exception:
            pass
        browser_context.close()


def test_gmail_preview_discloses_restricted_scope_and_requires_local_setup(browser, live):
    from pathlib import Path

    base, _ = live
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/google-mail"
    out.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    errors, external = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external.append(request.url)
            if not request.url.startswith(base) else None)
    try:
        page.goto(base + "/#/connections")
        page.get_by_role("heading", name="Apps & AI").wait_for()
        page.locator("#connection-management > summary").click()
        card = page.locator('[aria-labelledby="google-mail-title"]')
        card.wait_for()
        text = card.inner_text().lower()
        assert "experimental" in text and "local inference only" in text
        assert "gmail.readonly" in text and "restricted" in text
        assert "verification" in text and "security assessment" in text
        assert "account-wide" in text and "cannot send" in text
        assert card.get_by_role("button").count() == 0
        page.locator("#google-mail-access summary").click()
        page.locator("#google-oauth-setup > summary").click()
        assert "add a valid google desktop oauth client id" in card.inner_text().lower()
        setup = page.locator("#google-oauth-setup")
        setup.wait_for()
        assert setup.get_by_label("Google Desktop OAuth client ID").is_visible()
        save_button = setup.get_by_role("button", name="Save client ID")
        assert save_button.is_enabled()
        assert "never paste a client secret" in setup.inner_text().lower()
        assert "one client id is shared by calendar" in setup.inner_text().lower()
        card.get_by_role("button", name="Open Google setup").click()
        assert page.url.endswith("#/connections")
        assert page.locator("#google-oauth-client-id").evaluate("element => document.activeElement === element")
        assert card.get_by_role("link", name="Review Google's Gmail scope requirements").count() == 1
        captures = []
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024),
                                     ("phone", 390, 844), ("compact-phone", 320, 740)):
            page.set_viewport_size({"width": width, "height": height})
            setup.scroll_into_view_if_needed()
            if width <= 640:
                save_box = save_button.bounding_box()
                assert save_box["y"] >= 76 and save_box["y"] + save_box["height"] <= height
                assert save_box["height"] >= 44
                if width <= 360:
                    assert save_box["height"] == 44
            page.screenshot(path=str(out / f"client-setup-{label}.png"), animations="disabled")
            card.scroll_into_view_if_needed()
            page.screenshot(path=str(out / f"unconfigured-{label}.png"), animations="disabled")
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, overflow)
            captures.append({"size": label, "viewport": [width, height],
                             "scenes": ["Google client setup", "unconfigured Gmail"],
                             "horizontal_overflow": overflow})
        assert not errors, errors
        assert not external, external
        (out / "unconfigured-validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_gmail_preview_discloses_restricted_scope_and_requires_local_setup",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "command": ".venv/bin/pytest -q tests/e2e/test_browser.py::test_gmail_preview_discloses_restricted_scope_and_requires_local_setup",
            "browser": browser.version, "playwright_version": package_version("playwright"),
            "provider_credentials_used": False, "provider_calls": 0,
            "scenario": "Private-preview Gmail is labelled experimental; Connections explains restricted gmail.readonly account consent, verification/security assessment and Local-inference-only boundaries; shared Google Desktop client setup is actionable and no Gmail connect control appears until configured",
            "external_requests": external, "page_errors": errors, "captures": captures,
            "inspected_screenshots": [f"{scene}-{size}.png" for size in ("desktop", "tablet", "phone", "compact-phone")
                                      for scene in ("client-setup", "unconfigured")],
            "source_sha256": {path: hashlib.sha256((out.parents[3] / path).read_bytes()).hexdigest()
                              for path in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                           "src/hutch/server/app.py", "src/hutch/google_oauth_config.py",
                                           "src/hutch/google_calendar.py", "docs/connections.md", "docs/requirements.md")},
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        context.close()


def test_google_oauth_environment_override_is_readonly_in_connections(browser, live, monkeypatch):
    from pathlib import Path

    base, _ = live
    monkeypatch.setenv("HUTCH_GOOGLE_OAUTH_CLIENT_ID", "operator-preview.apps.googleusercontent.com")
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/google-mail"
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    errors, external = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external.append(request.url)
            if not request.url.startswith(base) else None)
    try:
        page.goto(base + "/#/connections")
        page.get_by_role("heading", name="Apps & AI").wait_for()
        page.locator("#connection-management > summary").click()
        setup = page.locator("#google-oauth-setup")
        setup.locator("summary").click()
        field = setup.get_by_label("Google Desktop OAuth client ID")
        assert field.input_value() == "operator-preview.apps.googleusercontent.com"
        assert field.get_attribute("readonly") is not None
        assert setup.get_by_role("button", name="Save client ID").is_disabled()
        assert setup.get_by_role("button", name="Clear").is_disabled()
        assert "managed by the hutch operator" in setup.inner_text().lower()
        captures = []
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024),
                                     ("phone", 390, 844), ("compact-phone", 320, 740)):
            page.set_viewport_size({"width": width, "height": height})
            setup.scroll_into_view_if_needed()
            if width <= 640:
                assert field.bounding_box()["y"] >= 76
            page.screenshot(path=str(out / f"operator-managed-{label}.png"), animations="disabled")
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, overflow)
            captures.append({"size": label, "viewport": [width, height], "horizontal_overflow": overflow})
        assert not errors, errors
        assert not external, external
        (out / "google-oauth-env-validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_google_oauth_environment_override_is_readonly_in_connections",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "command": ".venv/bin/pytest -q tests/e2e/test_browser.py::test_google_oauth_environment_override_is_readonly_in_connections",
            "browser": browser.version, "playwright_version": package_version("playwright"),
            "provider_credentials_used": False, "provider_calls": 0,
            "scenario": "Synthetic operator-managed public Google client ID; field is read-only and cannot be cleared in Hutch; no provider request",
            "external_requests": external, "page_errors": errors, "captures": captures,
            "inspected_screenshots": [f"operator-managed-{size}.png"
                                      for size in ("desktop", "tablet", "phone", "compact-phone")],
            "source_sha256": {path: hashlib.sha256((out.parents[3] / path).read_bytes()).hexdigest()
                              for path in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                           "src/hutch/server/app.py", "src/hutch/google_oauth_config.py")},
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        context.close()


def test_gmail_local_grant_and_oauth_flow_at_desktop_tablet_and_phone(browser, live, monkeypatch):
    from pathlib import Path

    from hutch.google_calendar import OAuthStart
    from hutch.google_mail import GOOGLE_MAIL_SCOPE
    from hutch.models import InferenceMode

    base, app = live
    account_id = "gmail_0123456789abcdef01234567"
    constructed_client_ids = []

    class FixtureGoogleMailBook:
        accounts_rows = [{"id": account_id, "label": "Personal Gmail", "created_at": "2026-10-09T00:00:00+00:00",
                          "scopes": [GOOGLE_MAIL_SCOPE], "status": "connected"}]

        class Secrets:
            @staticmethod
            def available():
                return True

        def __init__(self, state_dir, client_id):
            self.secrets = self.Secrets()
            constructed_client_ids.append(client_id)

        def accounts(self):
            return list(self.accounts_rows)

        @staticmethod
        def callback_uri(request):
            port = request.scope["server"][1]
            return f"http://127.0.0.1:{port}/api/v1/connections/google-mail/callback"

        @classmethod
        def start(cls, label, callback):
            return OAuthStart("https://accounts.google.com/o/oauth2/v2/auth?state=fixture", "fixture")

        @classmethod
        def _account(cls, reference):
            from hutch.google_calendar import GoogleCalendarError
            account = next((row for row in cls.accounts_rows if row["id"] == reference), None)
            if not account:
                raise GoogleCalendarError("Gmail account is not connected")
            return account

    monkeypatch.setattr("hutch.google_mail.GoogleMailBook", FixtureGoogleMailBook)
    local = app.state.store.create_bot(Bot(name="gmail-local", display_name="Mailbox Analyst", model="ollama/qwen3:4b",
                                           inference_mode=InferenceMode.local, tools=[]))
    hybrid = app.state.store.create_bot(Bot(name="gmail-hybrid", display_name="Hosted Assistant", model="openai/gpt-4o-mini",
                                            inference_mode=InferenceMode.hybrid, tools=[]))
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    page.add_init_script("""
      window.__gmailOAuth = { target: null, url: null, opener: 'not-set', closed: false };
      window.open = (_url, target) => {
        window.__gmailOAuth.target = target;
        return {
          set opener(value) { window.__gmailOAuth.opener = value; },
          location: { replace(value) { window.__gmailOAuth.url = value; } },
          close() { window.__gmailOAuth.closed = true; }
        };
      };
    """)
    errors, external = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external.append(request.url) if not request.url.startswith(base) else None)
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/google-mail"
    out.mkdir(parents=True, exist_ok=True)
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        page.goto(base + "/#/connections")
        page.locator("#connection-management > summary").click()
        card = page.locator('[aria-labelledby="google-mail-title"]')
        card.wait_for()
        page.locator("#google-mail-access summary").click()
        page.locator("#google-oauth-setup > summary").click()
        page.locator("#google-oauth-client-id").fill("fixture-client.apps.googleusercontent.com")
        page.locator("#google-oauth-client-save").click()
        client_change_review = page.locator(".modal-card[role='dialog']")
        client_change_review.wait_for()
        client_review_sizes = []
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024),
                                     ("phone", 390, 844), ("compact-phone", 320, 740)):
            page.set_viewport_size({"width": width, "height": height})
            page.screenshot(path=str(out / f"client-change-review-{label}.png"), animations="disabled")
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
            if width <= 640:
                assert page.get_by_role("button", name="Save new ID").bounding_box()["height"] >= 44
            client_review_sizes.append({"size": label, "viewport": [width, height]})
        page.set_viewport_size({"width": 1440, "height": 960})
        page.get_by_role("button", name="Save new ID").click()
        page.get_by_text("Ready for Google sign-in.", exact=True).wait_for()
        page.locator("#google-mail-connect").wait_for(state="visible")
        assert app.state.store.kv_get("connections:google_oauth_client_id") == \
            "fixture-client.apps.googleusercontent.com"
        page.get_by_role("button", name="Dismiss notification").first.click()
        page.get_by_role("button", name="Connect Gmail").wait_for()
        page.locator("#google-mail-label").fill("Work")
        page.get_by_role("button", name="Connect Gmail").click()
        page.get_by_text("Finish Google sign-in in the new browser tab", exact=False).wait_for()
        oauth = page.evaluate("window.__gmailOAuth")
        assert oauth["target"] == "_blank" and oauth["opener"] is None
        destination = urlsplit(oauth["url"])
        assert destination.scheme == "https" and destination.hostname == "accounts.google.com"
        assert destination.path == "/o/oauth2/v2/auth" and parse_qs(destination.query)["state"] == ["fixture"]
        assert "fixture-client.apps.googleusercontent.com" in constructed_client_ids
        page.get_by_role("button", name="Dismiss notification").click()

        account = page.locator(f'[data-google-mail-account="{account_id}"]')
        account.wait_for()
        bot_selector = account.locator("[data-google-mail-bot]")
        options = bot_selector.locator("option").all_inner_texts()
        assert options == ["Mailbox Analyst"] and "Hosted Assistant" not in options
        account.get_by_role("button", name="Grant search access").click()
        page.get_by_text("Can search sender, subject, date and short previews", exact=False).wait_for()
        grant = app.state.store.google_mail_grant(local.id)
        assert grant and grant["account_id"] == account_id
        assert app.state.store.google_mail_grant(hybrid.id) is None
        assert "loopback endpoint" in page.locator("[data-google-mail-account]").inner_text()
        page.get_by_role("button", name="Dismiss notification").click()

        captures = []
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            card.scroll_into_view_if_needed()
            page.screenshot(path=str(out / f"gmail-overview-{label}.png"), animations="disabled")
            account.scroll_into_view_if_needed()
            page.screenshot(path=str(out / f"gmail-granted-{label}.png"), animations="disabled")
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, overflow)
            captures.append({"size": label, "viewport": [width, height], "horizontal_overflow": overflow,
                             "screens": [f"gmail-overview-{label}.png", f"gmail-granted-{label}.png"]})
        assert not errors, errors
        assert not external, external
        (out / "grant-validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_gmail_local_grant_and_oauth_flow_at_desktop_tablet_and_phone",
            "command": "PLAYWRIGHT_BROWSERS_PATH=/home/kevina/.cache/ms-playwright .venv/bin/pytest -q tests/e2e/test_browser.py::test_gmail_local_grant_and_oauth_flow_at_desktop_tablet_and_phone",
            "captured_at": datetime.now(timezone.utc).isoformat(), "browser": browser.version,
            "provider_credentials_used": False, "provider_calls": 0,
            "scenario": "Synthetic connected Gmail account; local grant is persisted only for a loopback Local-inference Bot; hybrid Bot is absent; fixed Google OAuth destination is opened with no opener; no external network requests",
            "external_requests": external, "page_errors": errors, "captures": captures,
            "client_change_review": client_review_sizes,
            "source_sha256": {path: hashlib.sha256((out.parents[3] / path).read_bytes()).hexdigest()
                              for path in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                           "src/hutch/server/app.py", "src/hutch/server/security.py", "src/hutch/store.py",
                                           "src/hutch/google_calendar.py", "src/hutch/google_mail.py",
                                           "src/hutch/google_oauth_config.py", "src/hutch/tools/google_calendar.py",
                                           "src/hutch/tools/google_mail.py")},
            "inspected_screenshots": [f"gmail-overview-{size}.png" for size in ("desktop", "tablet", "phone")]
                                      + [f"gmail-granted-{size}.png" for size in ("desktop", "tablet", "phone")]
                                      + [f"client-change-review-{size}.png" for size in
                                         ("desktop", "tablet", "phone", "compact-phone")],
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        try:
            context.tracing.stop(path=str(out / "grant-trace.zip"))
        finally:
            context.close()


def test_browser_pauses_when_a_human_challenge_appears_during_wait(browser, live, tmp_path):
    from types import SimpleNamespace

    from hutch.tools.browser import BrowserTool
    from tests.test_tools import make_ctx

    _base, app = live
    bot = app.state.store.create_bot(Bot(name="late-human-checkpoint", model="openai/gpt-4o-mini",
                                         tools=["browser"], local_browser_handoff=True))
    ctx = make_ctx(app.state.store, app.state.config, tmp_path, bot=bot)
    ctx.headless = False
    page = browser.new_page()
    page.set_content("<main id='page'>Account overview</main>")
    page.evaluate("window.hutchSessionMarker = 'same-live-page'")
    page.evaluate("setTimeout(() => { document.querySelector('#page').textContent = 'Human verification is required.'; }, 30)")
    tool = BrowserTool()
    tool._ensure = lambda _ctx: SimpleNamespace(pages=[page])
    handoffs = []

    def resume_human(reason, url, **kwargs):
        handoffs.append((reason, url, kwargs))
        assert page.evaluate("window.hutchSessionMarker") == "same-live-page"
        if len(handoffs) == 2:
            page.locator("#page").evaluate("el => { el.textContent = 'Account overview'; }")

    ctx.gate.wait_for_human = resume_human
    try:
        result = tool.run({"action": "wait", "seconds": 0.1}, ctx)
        assert len(handoffs) == 2, "the page must stay paused when the challenge remains after a resume"
        assert "Human verification is needed" in handoffs[0][0]
        assert "same window" in handoffs[0][2]["handoff"]
        assert result.ok and "waited 0.1s" in result.output
        assert page.evaluate("window.hutchSessionMarker") == "same-live-page"
        read = tool.run({"action": "read"}, ctx)
        assert read.ok and "Account overview" in read.output
        assert "Human verification" not in read.output
    finally:
        page.close()


def test_browser_hands_off_when_a_click_reveals_a_sensitive_field(browser, live, tmp_path):
    from types import SimpleNamespace

    from hutch.tools.browser import BrowserTool
    from tests.test_tools import make_ctx

    _base, app = live
    bot = app.state.store.create_bot(Bot(name="late-sensitive-field", model="openai/gpt-4o-mini",
                                         tools=["browser"], local_browser_handoff=True))
    ctx = make_ctx(app.state.store, app.state.config, tmp_path, bot=bot)
    ctx.headless = False
    page = browser.new_page()
    url = "https://account.example.test/start"
    page.route(url, lambda route: route.fulfill(
        status=200, content_type="text/html", body="""<!doctype html><button id="continue">Continue</button>
          <main id="form"></main><script>window.hutchMarker='same-live-page';
          document.querySelector('#continue').addEventListener('click', () => {
            document.querySelector('#form').innerHTML='<label>Password <input id="password" type="password"></label>';
          });</script>"""))
    page.goto(url)
    tool = BrowserTool()
    tool._ensure = lambda _ctx: SimpleNamespace(pages=[page])
    ctx.gate.decide = lambda *_args, **_kwargs: None
    handoffs = []
    tool_fills = []
    page_fill = page.fill
    page.fill = lambda selector, value, **kwargs: (tool_fills.append((selector, value)),
                                                   page_fill(selector, value, **kwargs))[1]

    def resume_human(reason, resume_url, **kwargs):
        handoffs.append((reason, resume_url, kwargs))
        assert page.evaluate("window.hutchMarker") == "same-live-page"
        if len(handoffs) == 1:
            page.locator("#password").fill("human-only-secret")

    ctx.gate.wait_for_human = resume_human
    try:
        result = tool.run({"action": "click", "selector": "#continue"}, ctx)
        assert len(handoffs) == 1
        assert "password" in handoffs[0][0].lower()
        assert "visible Hutch browser window" in handoffs[0][2]["handoff"]
        assert not result.ok and result.data["action_completed"]
        assert "click already happened" in result.output
        assert "human-only-secret" not in result.output

        attempted = tool.run({"action": "type", "selector": "#password", "text": "agent-secret"}, ctx)
        assert not attempted.ok
        assert len(handoffs) == 2
        assert tool_fills == [], "the agent must never fill a sensitive field"
        assert "agent-secret" not in attempted.output and "human-only-secret" not in attempted.output
    finally:
        page.close()


def test_browser_hands_off_when_a_wait_reveals_a_sensitive_field(browser, live, tmp_path):
    from types import SimpleNamespace

    from hutch.tools.browser import BrowserTool
    from tests.test_tools import make_ctx

    _base, app = live
    bot = app.state.store.create_bot(Bot(name="delayed-sensitive-field", model="openai/gpt-4o-mini",
                                         tools=["browser"], local_browser_handoff=True))
    ctx = make_ctx(app.state.store, app.state.config, tmp_path, bot=bot)
    ctx.headless = False
    page = browser.new_page()
    url = "https://account.example.test/delayed"
    page.route(url, lambda route: route.fulfill(
        status=200, content_type="text/html", body="""<!doctype html><main id="form">Loading</main>
          <script>window.hutchMarker='same-live-page'; setTimeout(() => {
          document.querySelector('#form').innerHTML='<label>Password <input type="password" name="account-secret"></label>';
          }, 40);</script>"""))
    page.goto(url)
    tool = BrowserTool()
    tool._ensure = lambda _ctx: SimpleNamespace(pages=[page])
    handoffs = []

    def resume_human(reason, resume_url, **kwargs):
        handoffs.append((reason, resume_url, kwargs))
        assert page.evaluate("window.hutchMarker") == "same-live-page"
        page.locator("input[name=account-secret]").fill("human-only-secret")

    ctx.gate.wait_for_human = resume_human
    try:
        result = tool.run({"action": "wait", "seconds": 0.1}, ctx)
        assert len(handoffs) == 1
        assert "sensitive field" in handoffs[0][0].lower()
        assert not result.ok and result.data["sensitive_field_revealed"]
        assert result.data["action_completed"]
        assert "human-only-secret" not in result.output
    finally:
        page.close()


def test_browser_hands_off_when_text_entry_reveals_a_sensitive_field(browser, live, tmp_path):
    from types import SimpleNamespace

    from hutch.tools.browser import BrowserTool
    from tests.test_tools import make_ctx

    _base, app = live
    bot = app.state.store.create_bot(Bot(name="progressive-sensitive-form", model="openai/gpt-4o-mini",
                                         tools=["browser"], local_browser_handoff=True))
    ctx = make_ctx(app.state.store, app.state.config, tmp_path, bot=bot)
    ctx.headless = False
    page = browser.new_page()
    url = "https://account.example.test/progressive"
    page.route(url, lambda route: route.fulfill(
        status=200, content_type="text/html", body="""<!doctype html><label>Account name
          <input id="account" autocomplete="username"></label><main id="form"></main>
          <script>window.hutchMarker='same-live-page';
          document.querySelector('#account').addEventListener('input', () => {
            document.querySelector('#form').innerHTML='<label>Password <input id="password" type="password"></label>';
          });</script>"""))
    page.goto(url)
    tool = BrowserTool()
    tool._ensure = lambda _ctx: SimpleNamespace(pages=[page])
    ctx.gate.decide = lambda *_args, **_kwargs: None
    handoffs = []

    def resume_human(reason, resume_url, **kwargs):
        handoffs.append((reason, resume_url, kwargs))
        assert page.evaluate("window.hutchMarker") == "same-live-page"
        page.locator("#password").fill("human-only-secret")

    ctx.gate.wait_for_human = resume_human
    try:
        result = tool.run({"action": "type", "selector": "#account", "text": "demo-account"}, ctx)
        assert len(handoffs) == 1
        assert "password" in handoffs[0][0].lower()
        assert not result.ok and result.data["sensitive_field_revealed"]
        assert result.data["action_completed"]
        assert "text entry already happened" in result.output
        assert "demo-account" not in result.output and "human-only-secret" not in result.output
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
        page.get_by_role("heading", name="Apps & AI").wait_for()
        page.locator("#connection-management > summary").click()
        card = page.locator('[aria-labelledby="outlook-calendar-title"]')
        assert "Calendars.ReadBasic" in card.inner_text()
        assert "Microsoft consent applies to the signed-in account" in card.inner_text()
        assert "event bodies, attachments and extensions are not available" in card.inner_text()
        page.locator("#outlook-calendar-access > summary").click()
        assert "common" in card.inner_text()
        assert "cannot expand that choice" in card.inner_text()
        calendar_signin = page.locator("#outlook-calendar-connect")
        assert calendar_signin.is_enabled()
        assert calendar_signin.get_attribute("aria-label") == "Sign in with Microsoft"
        assert calendar_signin.locator("img").evaluate("img => img.complete && img.naturalWidth === 215")
        page.locator("#outlook-calendar-label").fill("Work")
        calendar_signin.click()
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
        calendar_details = card.locator("#outlook-calendar-access")
        if not calendar_details.evaluate("element => element.open"):
            calendar_details.locator("summary").click()
        card.get_by_text("Can read Work Calendar", exact=False).wait_for(state="visible")
        account_card = page.locator('[data-outlook-calendar-account="mscal_0123456789abcdef01234567"]')
        bot_selector = account_card.locator("[data-outlook-calendar-bot]")
        assert bot_selector.locator("option:checked").inner_text() == "Meeting Planner"
        grant_summary = account_card.locator(".google-calendar-grants .device-row")
        assert "Meeting Planner" in grant_summary.inner_text()
        assert "calendar-planner" not in grant_summary.inner_text()
        assert page.get_by_text("Calendars.ReadBasic account consent", exact=False).is_visible()
        while page.locator(".toast").count():
            page.locator(".toast-close").first.click()

        captures = []
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            card = page.locator('[aria-labelledby="outlook-calendar-title"]')
            access_details = card.locator("#outlook-calendar-access")
            if not access_details.evaluate("element => element.open"):
                access_details.locator("summary").click()
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


def test_outlook_calendar_event_creation_is_separate_approved_and_responsive(browser, live, monkeypatch):
    from pathlib import Path

    base, app = live
    monkeypatch.setenv("HUTCH_OUTLOOK_OAUTH_CLIENT_ID", "fixture-public-client")

    class FixtureOutlookCalendarWriteBook:
        accounts_rows = [{"id": "mscalw_0123456789abcdef01234567", "label": "Work events",
                          "created_at": "2026-10-10T00:00:00+00:00", "scopes": ["Calendars.ReadWrite"],
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
            assert account_id == "mscalw_0123456789abcdef01234567"
            return [{"id": "work", "name": "Work Calendar", "primary": True}]

        @staticmethod
        def callback_uri(request):
            port = request.scope["server"][1]
            return f"http://localhost:{port}/api/v1/connections/outlook-calendar-write/callback"

        @staticmethod
        def start(label, callback):
            from hutch.google_calendar import OAuthStart
            return OAuthStart("https://login.microsoftonline.com/common/oauth2/v2.0/authorize?scope=Calendars.ReadWrite&state=fixture",
                              "fixture")

    monkeypatch.setattr("hutch.outlook_calendar_write.OutlookCalendarWriteBook", FixtureOutlookCalendarWriteBook)
    bot = Bot(name="outlook-event-reviewer", display_name="Calendar Assistant", model="mock/demo", tools=[])
    app.state.store.create_bot(bot)
    page = browser.new_page(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page.add_init_script("""
      window.__outlookWriteOAuth = { target: null, url: null, opener: 'not-set' };
      window.open = (_url, target) => {
        window.__outlookWriteOAuth.target = target;
        return {
          set opener(value) { window.__outlookWriteOAuth.opener = value; },
          location: { replace(value) { window.__outlookWriteOAuth.url = value; } },
          close() {}
        };
      };
    """)
    errors, external = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external.append(request.url)
            if not request.url.startswith(base) else None)
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/outlook-calendar-write"
    out.mkdir(parents=True, exist_ok=True)
    try:
        page.goto(base + "/#/connections")
        page.get_by_role("heading", name="Apps & AI").wait_for()
        page.locator("#connection-management > summary").click()
        card = page.locator('[aria-labelledby="outlook-calendar-title"]')
        card.locator("#outlook-calendar-access > summary").click()
        card.get_by_text("Add event creation (optional)").click()
        assert "Calendars.ReadWrite" in card.inner_text()
        assert "create, read, change and delete" in card.inner_text()
        assert "Hutch does not expose event editing or deletion" in card.inner_text()
        assert "Every event needs your exact approval" in card.inner_text()

        permission_captures = []
        approval_notice_captures = []
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            page.locator("#outlook-calendar-write-access > summary").evaluate("""el => {
              const scroller = el.closest('.page-scroll');
              const box = el.getBoundingClientRect();
              const frame = scroller?.getBoundingClientRect();
              if (scroller && frame) scroller.scrollTop += box.top - frame.top - 18;
            }""")
            page.screenshot(path=str(out / f"permission-{label}.png"), animations="disabled")
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, overflow)
            permission_captures.append({"size": label, "viewport": [width, height],
                                        "scene": "separate scope and exact-approval disclosure",
                                        "horizontal_overflow": overflow})
            notice = page.locator("#outlook-calendar-write-access .outlook-mail-send-safety")
            notice.scroll_into_view_if_needed()
            notice.screenshot(path=str(out / f"approval-{label}.png"), animations="disabled")
            approval_notice_captures.append({"size": label, "viewport": [width, height],
                                             "scene": "exact event approval and uncertain-result boundary"})

        page.set_viewport_size({"width": 1440, "height": 960})

        page.locator("#outlook-calendar-write-label").fill("Work events")
        signin = page.locator("#outlook-calendar-write-connect")
        assert signin.is_enabled()
        assert signin.get_attribute("aria-label") == "Sign in with Microsoft for event creation"
        signin.click()
        page.get_by_text("Finish Microsoft sign-in in the new browser tab", exact=False).wait_for()
        oauth = page.evaluate("window.__outlookWriteOAuth")
        assert oauth["target"] == "_blank" and oauth["opener"] is None
        authorization_url = urlsplit(oauth["url"])
        assert authorization_url.scheme == "https" and authorization_url.hostname == "login.microsoftonline.com"
        assert parse_qs(authorization_url.query)["scope"] == ["Calendars.ReadWrite"]

        page.get_by_role("button", name="Load calendars").click()
        calendar = page.locator("[data-outlook-calendar-write-calendar]")
        calendar.wait_for(state="visible")
        calendar.select_option("work")
        grant_button = page.get_by_role("button", name="Allow approved event creation")
        assert grant_button.is_enabled()
        grant_button.click()
        card.get_by_text("Can create approved events on Work Calendar", exact=False).wait_for()
        account_card = page.locator('[data-outlook-calendar-write-account="mscalw_0123456789abcdef01234567"]')
        assert "Calendar Assistant" in account_card.inner_text()
        assert app.state.store.outlook_calendar_write_grant(bot.id)["calendar_name"] == "Work Calendar"
        while page.locator(".toast").count():
            page.locator(".toast-close").first.click()

        captures = []
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            if not page.locator("#connection-management").evaluate("element => element.open"):
                page.locator("#connection-management > summary").click()
            card = page.locator('[aria-labelledby="outlook-calendar-title"]')
            if not card.locator("#outlook-calendar-access").evaluate("element => element.open"):
                card.locator("#outlook-calendar-access > summary").click()
            if not card.locator("#outlook-calendar-write-access").evaluate("element => element.open"):
                card.locator("#outlook-calendar-write-access > summary").click()
            page.locator("[data-outlook-calendar-write-account]").scroll_into_view_if_needed()
            page.screenshot(path=str(out / f"granted-{label}.png"), animations="disabled")
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, overflow)
            captures.append({"size": label, "viewport": [width, height], "scene": "separate event-creation account and selected-calendar Bot grant",
                             "horizontal_overflow": overflow})
        assert page.get_by_role("button", name="Revoke event access").bounding_box()["height"] >= 44
        assert not errors, errors
        assert not external, external
        (out / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_outlook_calendar_event_creation_is_separate_approved_and_responsive",
            "captured_at": datetime.now(timezone.utc).isoformat(), "browser": browser.version,
            "provider_credentials_used": False, "provider_calls": 0,
            "scenario": "Synthetic Microsoft sign-in and calendar list, real local connection API and per-Bot grant; no event was sent",
            "external_requests": external, "page_errors": errors,
            "permission_review_captures": permission_captures,
            "approval_notice_captures": approval_notice_captures, "grant_captures": captures,
            "source_sha256": {path: hashlib.sha256((out.parents[3] / path).read_bytes()).hexdigest()
                              for path in ("src/hutch/server/static/app.js", "src/hutch/server/app.py",
                                           "src/hutch/server/security.py", "src/hutch/store.py",
                                           "src/hutch/outlook_calendar_write.py", "src/hutch/tools/outlook_calendar_write.py")},
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        page.close()


def test_outlook_mail_grant_and_consent_boundary_fit_all_viewports(browser, live, monkeypatch):
    base, app = live
    monkeypatch.setenv("HUTCH_OUTLOOK_OAUTH_CLIENT_ID", "fixture-public-client")

    class FixtureOutlookMailBook:
        accounts_rows = [{"id": "msmail_0123456789abcdef01234567", "label": "Work",
                          "created_at": "2026-10-09T00:00:00+00:00", "scopes": ["Mail.Read"],
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

        @classmethod
        def _account(cls, account_id):
            assert account_id == "msmail_0123456789abcdef01234567"
            return cls.accounts_rows[0]

        @staticmethod
        def callback_uri(request):
            port = request.scope["server"][1]
            return f"http://localhost:{port}/api/v1/connections/outlook-mail/callback"

        @staticmethod
        def start(label, callback):
            from hutch.outlook_calendar import OAuthStart
            return OAuthStart("https://login.microsoftonline.com/common/oauth2/v2.0/authorize?state=fixture", "fixture")

    monkeypatch.setattr("hutch.outlook_mail.OutlookMailBook", FixtureOutlookMailBook)
    bot = Bot(name="mail-assistant", display_name="Mail Assistant", model="mock/demo", tools=[])
    app.state.store.create_bot(bot)
    output = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/outlook-mail"
    output.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    page.add_init_script("""
      window.__outlookMailOAuth = { target: null, url: null, opener: 'not-set', closed: false };
      window.open = (_url, target) => {
        window.__outlookMailOAuth.target = target;
        return {
          set opener(value) { window.__outlookMailOAuth.opener = value; },
          location: { replace(value) { window.__outlookMailOAuth.url = value; } },
          close() { window.__outlookMailOAuth.closed = true; }
        };
      };
    """)
    errors, external = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external.append(request.url)
            if not request.url.startswith(base) else None)
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        page.goto(base + "/#/connections")
        page.get_by_role("heading", name="Apps & AI").wait_for()
        page.locator("#connection-management > summary").click()
        card = page.locator(".outlook-mail-card")
        card.wait_for()
        assert "Mail.Read" in card.inner_text()
        assert "Reading and sending use separate account sign-ins and separate Bot grants" in card.inner_text()
        assert "provider consent must be revoked separately" in card.inner_text()
        assert "including Deleted Items and Clutter" in card.inner_text()
        page.locator("#outlook-mail-access > summary").click()
        mail_signin = page.locator("#outlook-mail-connect")
        assert mail_signin.is_enabled()
        assert mail_signin.get_attribute("aria-label") == "Sign in with Microsoft"
        assert mail_signin.locator("img").evaluate("img => img.complete && img.naturalWidth === 215")
        page.locator("#outlook-mail-label").fill("Work")
        mail_signin.click()
        page.get_by_text("Finish Microsoft sign-in in the new browser tab", exact=False).wait_for()
        oauth = page.evaluate("window.__outlookMailOAuth")
        assert oauth["target"] == "_blank" and oauth["opener"] is None
        authorization_url = urlsplit(oauth["url"])
        assert authorization_url.scheme == "https" and authorization_url.hostname == "login.microsoftonline.com"
        assert authorization_url.path == "/common/oauth2/v2.0/authorize"
        assert parse_qs(authorization_url.query)["state"] == ["fixture"]

        grant = card.get_by_role("button", name="Grant read access")
        assert grant.is_enabled()
        grant.click()
        page.locator(".toast-msg").last.wait_for()
        grant_notice = page.locator(".toast-msg").last.inner_text()
        assert "in Work" in grant_notice
        assert "msmail_0123456789abcdef01234567" not in grant_notice
        mail_details = page.locator("#outlook-mail-access")
        if not mail_details.evaluate("element => element.open"):
            mail_details.locator("summary").click()
        card.get_by_text("Can search message previews", exact=False).wait_for(state="visible")
        account_card = page.locator('[data-outlook-mail-account="msmail_0123456789abcdef01234567"]')
        bot_selector = account_card.locator("[data-outlook-mail-bot]")
        assert bot_selector.locator("option:checked").inner_text() == "Mail Assistant"
        grant_summary = account_card.locator(".google-calendar-grants .device-row")
        assert "Mail Assistant" in grant_summary.inner_text()
        assert "mail-assistant" not in grant_summary.inner_text()
        account_card.locator("[data-outlook-mail-disconnect]").click()
        disconnect_dialog = page.get_by_role("dialog", name="Disconnect Outlook Mail")
        assert "Mail Assistant" in disconnect_dialog.inner_text()
        assert "mail-assistant" not in disconnect_dialog.inner_text()
        disconnect_dialog.get_by_role("button", name="Cancel").click()
        page.get_by_text("Mail previews are sent to that Bot's selected model", exact=False).wait_for()
        while page.locator(".toast").count():
            page.locator(".toast-close").first.click()

        captures = []
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            card = page.locator(".outlook-mail-card")
            mail_access = page.locator("#outlook-mail-access")
            if not mail_access.evaluate("element => element.open"):
                mail_access.locator("summary").click()
            scroll = page.locator(".page-scroll")
            scroll.evaluate("element => { element.scrollTop = 0; }")
            card.evaluate("element => { const scroller = document.querySelector('.page-scroll'); "
                          "if (scroller) scroller.scrollTop += element.getBoundingClientRect().top - 96; }")
            page.screenshot(path=str(output / f"overview-{label}.png"), animations="disabled")
            account = page.locator("[data-outlook-mail-account]")
            account.evaluate("element => { const scroller = document.querySelector('.page-scroll'); "
                             "if (scroller) scroller.scrollTop += element.getBoundingClientRect().top - 140; }")
            page.screenshot(path=str(output / f"granted-{label}.png"), animations="disabled")
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, overflow)
            captures.append({"size": label, "viewport": [width, height], "scenes": ["permission disclosure", "granted account"],
                             "horizontal_overflow": overflow})
        assert page.get_by_role("button", name="Revoke Bot access").bounding_box()["height"] >= 44
        assert not errors, errors
        assert not external, external
        (output / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_outlook_mail_grant_and_consent_boundary_fit_all_viewports",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "browser": browser.version, "playwright_version": package_version("playwright"),
            "provider_credentials_used": False, "provider_calls": 0,
            "scenario": "Fixture account metadata and consent redirect; actual local API persists one Bot grant; no mail content or Microsoft call",
            "external_requests": external, "page_errors": errors, "captures": captures,
            "source_sha256": {path: hashlib.sha256((output.parents[3] / path).read_bytes()).hexdigest()
                              for path in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                           "src/hutch/server/app.py", "src/hutch/server/security.py",
                                           "src/hutch/store.py", "src/hutch/outlook_mail.py",
                                           "src/hutch/tools/outlook_mail.py")},
        }, indent=2) + "\n", encoding="utf-8")
        context.tracing.stop(path=str(output / "trace.zip"))
    finally:
        if context.tracing:
            try:
                context.tracing.stop()
            except Exception:
                pass
        context.close()


def test_outlook_mail_send_access_is_separate_and_responsive(browser, live, monkeypatch):
    monkeypatch.setenv("HUTCH_OUTLOOK_OAUTH_CLIENT_ID", "fixture-public-client")
    base, app = live

    class FixtureOutlookMailSendBook:
        account_id = "mssend_0123456789abcdef01234567"
        accounts_rows = [{"id": account_id, "label": "Work sender",
                          "created_at": "2026-10-09T00:00:00+00:00",
                          "scopes": ["Mail.Send", "offline_access"], "status": "connected"}]

        class Secrets:
            @staticmethod
            def available():
                return True

        def __init__(self, state_dir, client_id):
            self.secrets = self.Secrets()

        def accounts(self):
            return list(self.accounts_rows)

        @classmethod
        def callback_uri(cls, request):
            return f"http://localhost:{request.scope['server'][1]}/api/v1/connections/outlook-mail-send/callback"

        @staticmethod
        def start(label, callback):
            assert label == "Second sender"
            from hutch.outlook_calendar import OAuthStart
            return OAuthStart("https://login.microsoftonline.com/common/oauth2/v2.0/authorize?state=send-fixture",
                              "send-fixture")

        def _account(self, account_id):
            return next(account for account in self.accounts_rows if account["id"] == account_id)

        @classmethod
        def disconnect(cls, account_id):
            assert account_id == cls.account_id
            cls.accounts_rows = [account for account in cls.accounts_rows if account["id"] != account_id]
            return {"removed": True, "provider_revocation": "unavailable"}

    monkeypatch.setattr("hutch.outlook_mail.OutlookMailSendBook", FixtureOutlookMailSendBook)
    bot = Bot(name="mail-assistant", display_name="Mail Assistant", model="mock/demo", tools=[])
    app.state.store.create_bot(bot)
    output = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/outlook-mail-send"
    output.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    page.add_init_script("""
      window.__outlookMailSendOAuth = { url: null, opener: 'not-set', closed: false };
      window.open = () => ({
        set opener(value) { window.__outlookMailSendOAuth.opener = value; },
        location: { replace(value) { window.__outlookMailSendOAuth.url = value; } },
        close() { window.__outlookMailSendOAuth.closed = true; }
      });
    """)
    errors, external = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external.append(request.url)
            if not request.url.startswith(base) else None)
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        page.goto(base + "/#/connections")
        page.get_by_role("heading", name="Apps & AI").wait_for()
        page.locator("#connection-management > summary").click()
        card = page.locator(".outlook-mail-card")
        page.locator("#outlook-mail-access > summary").click()
        send_access = page.locator("#outlook-mail-send-access")
        send_access.locator("summary").click()
        assert "Mail.Send" in send_access.inner_text()
        assert "Every send requires your exact approval" in send_access.inner_text()
        send_signin = page.locator("#outlook-mail-send-connect")
        assert send_signin.get_attribute("aria-label") == "Sign in with Microsoft"
        assert send_signin.is_enabled()
        assert send_signin.locator("img").evaluate("img => img.complete && img.naturalWidth === 215")
        page.locator("#outlook-mail-send-label").fill("Second sender")
        send_signin.click()
        wait_for_page(page, "window.__outlookMailSendOAuth.url !== null")
        oauth = page.evaluate("window.__outlookMailSendOAuth")
        authorization_url = urlsplit(oauth["url"])
        assert oauth["opener"] is None
        assert authorization_url.scheme == "https" and authorization_url.hostname == "login.microsoftonline.com"
        assert authorization_url.path == "/common/oauth2/v2.0/authorize"
        assert parse_qs(authorization_url.query)["state"] == ["send-fixture"]

        account = page.locator('[data-outlook-mail-send-account="mssend_0123456789abcdef01234567"]')
        assert "Mail.Send" in account.inner_text()
        assert "Mail.Read" not in account.inner_text()
        selector = account.locator("[data-outlook-mail-send-bot]")
        assert selector.locator("option:checked").inner_text() == "Mail Assistant"
        account.get_by_role("button", name="Grant send access").click()
        page.get_by_text("may prepare one new plain-text email", exact=False).wait_for()
        grant_row = account.locator(".outlook-mail-send-grants .device-row")
        grant_row.wait_for()
        assert "Mail Assistant" in grant_row.inner_text()
        assert "outlook-mail-send" not in grant_row.inner_text()

        captures = []
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024),
                                     ("phone", 390, 844), ("compact-phone", 320, 740)):
            page.set_viewport_size({"width": width, "height": height})
            while page.locator(".toast-close").count():
                page.locator(".toast-close").first.click()
            send_access.locator("summary").evaluate("el => el.scrollIntoView({block: 'start'})")
            page.screenshot(path=str(output / f"send-access-{label}.png"), animations="disabled")
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, overflow)
            captures.append({"size": label, "viewport": [width, height], "horizontal_overflow": overflow})
        assert account.get_by_role("button", name="Revoke send access").bounding_box()["height"] >= 44

        account.get_by_role("button", name="Revoke send access").click()
        page.get_by_role("dialog", name="Revoke Outlook Mail sending access").get_by_role(
            "button", name="Revoke access").click()
        page.get_by_text("No Bot can prepare email from this account.").wait_for()
        account.get_by_role("button", name="Disconnect sending account").click()
        dialog = page.get_by_role("dialog", name="Disconnect Outlook Mail sending")
        assert "Microsoft consent is not revoked by Hutch" in dialog.inner_text()
        dialog.get_by_role("button", name="Disconnect").click()
        page.get_by_text("No Outlook Mail sending accounts connected.").wait_for()
        assert app.state.store.list_outlook_mail_send_grants() == []
        assert not errors, errors
        assert not external, external
        (output / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_outlook_mail_send_access_is_separate_and_responsive",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "browser": browser.version, "playwright_version": package_version("playwright"),
            "provider_credentials_used": False, "provider_calls": 0,
            "scenario": "Local fixture account; separate Mail.Send consent, explicit Bot grant/revoke and local disconnect",
            "external_requests": external, "page_errors": errors, "captures": captures,
            "source_sha256": {path: hashlib.sha256((output.parents[3] / path).read_bytes()).hexdigest()
                              for path in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                           "src/hutch/server/static/brands/openai-white-monoblossom.svg",
                                           "src/hutch/server/static/brands/ms-symbollockup_signin_dark.svg",
                                           "src/hutch/server/app.py", "src/hutch/outlook_mail.py",
                                           "src/hutch/tools/outlook_mail_send.py", "tests/e2e/test_browser.py")},
        }, indent=2) + "\n", encoding="utf-8")
        context.tracing.stop(path=str(output / "trace.zip"))
    finally:
        if context.tracing:
            try:
                context.tracing.stop()
            except Exception:
                pass
        context.close()


def test_google_mail_send_access_is_send_only_and_responsive(browser, live, monkeypatch):
    from urllib.parse import parse_qs, urlsplit

    monkeypatch.setenv("HUTCH_GOOGLE_OAUTH_CLIENT_ID", "fixture-desktop-client.apps.googleusercontent.com")
    base, app = live
    scope = "https://www.googleapis.com/auth/gmail.send"

    class FixtureGoogleMailSendBook:
        account_id = "gmail_send_0123456789abcdef01234567"
        accounts_rows = [{"id": account_id, "label": "Work sender", "from_address": "owner@example.test",
                          "created_at": "2026-10-10T00:00:00+00:00", "scopes": [scope], "status": "connected"}]

        class Secrets:
            @staticmethod
            def available():
                return True

        def __init__(self, state_dir, client_id):
            self.secrets = self.Secrets()

        def accounts(self):
            return list(self.accounts_rows)

        @classmethod
        def callback_uri(cls, request):
            return f"http://127.0.0.1:{request.scope['server'][1]}/api/v1/connections/google-mail-send/callback"

        @staticmethod
        def start(label, callback, from_address):
            assert label == "Second sender" and from_address == "owner@example.test"
            from hutch.google_calendar import OAuthStart
            return OAuthStart("https://accounts.google.com/o/oauth2/v2/auth?" +
                              urlencode({"state": "send-fixture", "scope": scope}), "send-fixture")

        def _account(self, account_id):
            return next(account for account in self.accounts_rows if account["id"] == account_id)

        @classmethod
        def disconnect(cls, account_id):
            assert account_id == cls.account_id
            cls.accounts_rows = [account for account in cls.accounts_rows if account["id"] != account_id]
            return {"removed": True, "provider_revocation": "confirmed"}

    monkeypatch.setattr("hutch.google_mail_send.GoogleMailSendBook", FixtureGoogleMailSendBook)
    app.state.store.create_bot(Bot(name="gmail-assistant", display_name="Mail Assistant", model="mock/demo", tools=[]))
    output = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/google-mail-send"
    output.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    page.add_init_script("""
      window.__googleMailSendOAuth = { url: null, opener: 'not-set', closed: false };
      window.open = () => ({
        set opener(value) { window.__googleMailSendOAuth.opener = value; },
        location: { replace(value) { window.__googleMailSendOAuth.url = value; } },
        close() { window.__googleMailSendOAuth.closed = true; }
      });
    """)
    errors, external = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external.append(request.url)
            if not request.url.startswith(base) else None)
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        page.goto(base + "/#/connections")
        page.get_by_role("heading", name="Apps & AI").wait_for()
        page.locator("#connection-management > summary").click()
        page.locator("#google-mail-access > summary").click()
        send_access = page.locator("#google-mail-send-access")
        send_access.locator("summary").click()
        assert "gmail.send" in send_access.inner_text()
        assert "sensitive" in send_access.inner_text()
        assert "cannot read or search your mailbox" in send_access.inner_text()

        page.locator("#google-mail-send-label").fill("Second sender")
        page.locator("#google-mail-send-from").fill("owner@example.test")
        page.locator("#google-mail-send-connect").click()
        wait_for_page(page, "window.__googleMailSendOAuth.url !== null")
        oauth = page.evaluate("window.__googleMailSendOAuth")
        authorization_url = urlsplit(oauth["url"])
        assert oauth["opener"] is None
        assert authorization_url.scheme == "https" and authorization_url.hostname == "accounts.google.com"
        assert authorization_url.path == "/o/oauth2/v2/auth"
        assert parse_qs(authorization_url.query)["scope"] == [scope]

        account = page.locator('[data-google-mail-send-account="gmail_send_0123456789abcdef01234567"]')
        assert "owner@example.test" in account.inner_text()
        assert "send only" in account.inner_text()
        assert "gmail.readonly" not in account.inner_text()
        selector = account.locator("[data-google-mail-send-bot]")
        assert selector.locator("option:checked").inner_text() == "Mail Assistant"
        account.get_by_role("button", name="Allow approved sending").click()
        page.get_by_text("may prepare one plain-text email", exact=False).wait_for()
        grant_row = account.locator(".google-calendar-grants .device-row")
        grant_row.wait_for()
        assert "Mail Assistant" in grant_row.inner_text()
        assert "gmail_send_" not in grant_row.inner_text()

        captures = []
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024),
                                     ("phone", 390, 844), ("compact-phone", 320, 740)):
            page.set_viewport_size({"width": width, "height": height})
            while page.locator(".toast-close").count():
                page.locator(".toast-close").first.click()
            send_access.locator("summary").evaluate("el => el.scrollIntoView({block: 'start'})")
            page.screenshot(path=str(output / f"send-only-{label}.png"), animations="disabled")
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, overflow)
            captures.append({"size": label, "viewport": [width, height], "horizontal_overflow": overflow})
        assert account.get_by_role("button", name="Revoke send access").bounding_box()["height"] >= 44

        account.get_by_role("button", name="Revoke send access").click()
        page.get_by_role("dialog", name="Revoke Gmail sending access").get_by_role(
            "button", name="Revoke access").click()
        page.get_by_text("No assistant has send access to this account.").wait_for()
        account.get_by_role("button", name="Disconnect").click()
        dialog = page.get_by_role("dialog", name="Disconnect send-only Gmail")
        assert "does not affect a separate Gmail search connection" in dialog.inner_text()
        dialog.get_by_role("button", name="Disconnect").click()
        page.get_by_text("No send-only Gmail accounts connected.").wait_for()
        assert app.state.store.list_google_mail_send_grants() == []
        assert not errors, errors
        assert not external, external
        (output / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_google_mail_send_access_is_send_only_and_responsive",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "browser": browser.version, "playwright_version": package_version("playwright"),
            "provider_credentials_used": False, "provider_calls": 0,
            "scenario": "Fixture send-only Gmail account; separate gmail.send OAuth, explicit assistant grant/revoke, and local disconnect",
            "external_requests": external, "page_errors": errors, "captures": captures,
            "source_sha256": {path: hashlib.sha256((output.parents[3] / path).read_bytes()).hexdigest()
                              for path in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                           "src/hutch/server/app.py", "src/hutch/google_mail_send.py",
                                           "src/hutch/tools/google_mail_send.py", "src/hutch/store.py",
                                           "tests/e2e/test_browser.py")},
        }, indent=2) + "\n", encoding="utf-8")
        context.tracing.stop(path=str(output / "trace.zip"))
    finally:
        if context.tracing:
            try:
                context.tracing.stop()
            except Exception:
                pass
        context.close()


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
        page.locator("#connection-management > summary").click()
        button = page.get_by_role("button", name="Continue with ChatGPT")
        button.wait_for(state="visible")
        page.get_by_role("heading", name="Apps & AI").wait_for()
        assert button.is_enabled()
        assert page.get_by_text("Availability depends on OpenAI eligibility and your account", exact=False).is_visible()
        # Wait for the first app paint before taking the full-page desktop capture. The button can
        # become visible one frame before the view is composited, which produced a blank proof image.
        wait_for_page(page, "document.fonts.status === 'loaded'")
        page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
        page.wait_for_timeout(250)
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            button.scroll_into_view_if_needed()
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


def wait_for_page(page, expression, *, arg=None, timeout=30000):
    """Poll a page predicate without Playwright's CSP-blocked wait_for_function eval."""
    return wait_for(lambda: page.evaluate(expression, arg), timeout=timeout / 1000)


def wait_for(fn, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.05)
    raise AssertionError("timed out")


def open_assistant_customization(page):
    details = page.locator("#assistant-more-settings")
    details.wait_for(state="attached")
    if not details.evaluate("element => element.open"):
        details.locator(":scope > summary").click()
    assert details.evaluate("element => element.open")


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
            wait_for_page(page, "el => el.textContent.includes('Shared with')", arg=share_status.element_handle())
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
                wait_for_page(page,
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
            wait_for_page(page, "() => document.querySelector('#conversation-files-status')?.textContent?.includes('no longer has access')")
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
        wait_for_page(page, "() => document.querySelector('#conversation-files-status')?.textContent === '50 items'")
        assert dialog.locator(".conversation-file").count() == 50
        dialog.get_by_role("button", name="Load more").click()
        wait_for_page(page, "() => document.querySelector('#conversation-files-status')?.textContent === '51 items'")
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
    try:
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

        page.locator("#studio-conversation-options").click()
        page.locator("#studio-conversation-more > summary").click()
        page.locator("#studio-archive-conversation").click()
        wait_for(lambda: page.locator("#conversation-switcher").input_value() != conversation_id)
        archived = app.state.store.get_conversation(conversation_id)
        assert archived["archived"] == 1
        assert len(app.state.store.list_conversation_messages(conversation_id)) >= 4
        assert not errors, errors
    finally:
        context.close()


def test_conversation_options_are_compact_persistent_and_recoverable(browser, live, tmp_path, request):
    base, app = live
    store = app.state.store
    bot = store.create_bot(Bot(name="conversation-options", model="mock/demo", tools=[]))
    first, _ = store.create_conversation(bot.id, "A research thread", idem_key="options-first",
                                         request_hash="options-first")
    second, _ = store.create_conversation(bot.id, "A follow-up", idem_key="options-second",
                                          request_hash="options-second")
    page = browser.new_page(viewport={"width": 1440, "height": 960})
    request.addfinalizer(page.close)
    page.set_default_timeout(8000)
    errors = []
    external_requests = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda req: external_requests.append(req.url)
            if urlsplit(req.url).netloc not in {urlsplit(base).netloc, ""} else None)
    page.context.tracing.start(screenshots=True, snapshots=True, sources=False)
    seeded = page.request.post(f"{base}/api/v1/conversations/{first['id']}/messages",
        data={"prompt": "Help me prepare a launch review."}, headers={"Idempotency-Key": "options-seed-message"})
    assert seeded.status == 201, seeded.text()
    seeded_run = seeded.json()["id"]
    wait_for(lambda: store.get_run(seeded_run).terminal)
    assert store.get_conversation(first["id"])["unread"] == 1
    page.goto(base + "/#/chat/conversation-options")
    page.locator("#conversation-switcher").wait_for()
    page.locator("#conversation-switcher").select_option(first["id"])
    page.locator("#chat-stream").get_by_text("Help me prepare a launch review.", exact=True).wait_for()

    artifacts = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/conversation-options"
    artifacts.mkdir(parents=True, exist_ok=True)
    viewports = [("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844),
                 ("compact-phone", 320, 844)]
    inspected = []
    for label, width, height in viewports:
        page.set_viewport_size({"width": width, "height": height})
        page.locator("#studio-conversation-options").click()
        menu = page.locator("#studio-conversation-actions[open]")
        menu.wait_for()
        page.get_by_role("button", name="Pin conversation").wait_for()
        overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        assert overflow == 0, f"{label} conversation header overflowed by {overflow}px"
        menu_box = menu.bounding_box()
        assert menu_box["x"] >= 0 and menu_box["x"] + menu_box["width"] <= width
        page.locator("#studio-conversation-more > summary").wait_for()
        page.screenshot(path=str(artifacts / f"menu-{label}.png"))
        inspected.append({"name": label, "viewport": [width, height], "horizontal_overflow_px": overflow,
                          "menu_bounds": {key: round(value, 2) for key, value in menu_box.items()}})
        if label in {"phone", "compact-phone"}:
            page.locator("#studio-conversation-more > summary").click()
            assert page.get_by_role("button", name="Save reusable request").is_visible()
            assert page.get_by_role("button", name="Download task template").is_visible()
            more_bounds = page.locator("#studio-conversation-more-panel").bounding_box()
            assert more_bounds["x"] >= 0 and more_bounds["x"] + more_bounds["width"] <= width
            assert more_bounds["y"] + more_bounds["height"] <= height
            page.screenshot(path=str(artifacts / f"more-{label}.png"))
            page.keyboard.press("Escape")
            assert page.locator("#studio-conversation-actions[open]").count() == 1
        if label == "desktop":
            page.keyboard.press("Escape")
            assert menu.is_hidden()
            assert page.locator("#studio-conversation-options").evaluate("el => el === document.activeElement")
        else:
            page.locator("#studio-conversation-options").click()

    page.locator("#studio-conversation-options").click()
    page.get_by_role("button", name="Pin conversation").click()
    wait_for(lambda: store.get_conversation(first["id"])["pinned"] == 1)
    page.locator("#studio-conversation-options").click()
    page.get_by_role("button", name="Mark unread").click()
    wait_for(lambda: store.get_conversation(first["id"])["unread"] == 1)
    page.locator("#conversation-switcher").select_option(second["id"])
    wait_for_page(page, "id => document.querySelector('#conversation-switcher')?.value === id", arg=second["id"])
    assert store.get_conversation(first["id"])["unread"] == 1
    page.locator("#conversation-switcher").select_option(first["id"])
    wait_for_page(page, "id => document.querySelector('#conversation-switcher')?.value === id", arg=first["id"])
    wait_for(lambda: store.get_conversation(first["id"])["unread"] == 0)

    page.locator("#studio-conversation-options").click()
    page.get_by_role("button", name="New section").click()
    page.locator("#conversation-section-name").fill("Client work")
    page.locator("#modal-confirm").click()
    wait_for(lambda: store.get_conversation(first["id"])["section"] == "Client work")

    page.locator("#studio-conversation-options").click()
    more_actions = page.locator("#studio-conversation-more > summary")
    more_actions.click()
    assert more_actions.get_attribute("aria-expanded") == "true"
    assert page.get_by_role("button", name="Save reusable request").is_visible()
    assert page.get_by_role("button", name="Download task template").is_visible()
    page.keyboard.press("Escape")
    assert page.locator("#studio-conversation-actions").is_visible()
    assert more_actions.get_attribute("aria-expanded") == "false"
    assert more_actions.evaluate("el => el === document.activeElement")
    page.keyboard.press("Escape")
    assert page.locator("#studio-conversation-actions[open]").count() == 0
    assert page.locator("#studio-conversation-options").evaluate("el => el === document.activeElement")

    page.locator("#studio-conversation-options").click()
    more_actions = page.locator("#studio-conversation-more > summary")
    more_actions.click()
    page.get_by_role("button", name="Download task template").click()
    page.get_by_role("heading", name="Download task template").wait_for()
    assert page.locator("#task-template-prompt").input_value() == "Help me prepare a launch review."
    assert "first request only" in page.locator("#modal-root").inner_text().lower()
    template_review_sizes = []
    for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
        page.set_viewport_size({"width": width, "height": height})
        dialog = page.locator("#modal-root .modal-card")
        box = dialog.bounding_box()
        overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        confirm = page.locator("#modal-confirm").bounding_box()
        assert overflow == 0, f"{label} task template review overflowed by {overflow}px"
        assert box["x"] >= 0 and box["x"] + box["width"] <= width
        assert confirm["y"] + confirm["height"] <= height
        assert page.locator("#task-template-name").is_visible() and page.locator("#task-template-prompt").is_visible()
        page.screenshot(path=str(artifacts / f"task-template-review-{label}.png"))
        template_review_sizes.append({"name": label, "viewport": [width, height], "overflow_px": overflow,
                                      "dialog_bounds": {key: round(value, 2) for key, value in box.items()}})
    with page.expect_download() as template_download_info:
        page.locator("#modal-confirm").click()
    template_download = template_download_info.value
    template_path = tmp_path / template_download.suggested_filename
    template_download.save_as(template_path)
    task_template = json.loads(template_path.read_text(encoding="utf-8"))
    assert task_template == {
        "kind": "hutch-task-template", "version": 1,
        "name": "A research thread", "prompt": "Help me prepare a launch review.",
    }
    runs_before_template_import = [run.id for run in store.list_runs()]
    page.locator("#composer-menu-btn").click()
    page.get_by_role("button", name="Import task-template file").click()
    page.locator("#task-template-file").set_input_files(template_path)
    assert page.locator("#chat-prompt").input_value() == "Help me prepare a launch review."
    assert [run.id for run in store.list_runs()] == runs_before_template_import
    wait_for_page(page, "document.querySelector('#live-status')?.textContent.includes('Nothing was sent')")

    page.locator("#studio-conversation-options").click()
    page.locator("#studio-conversation-more > summary").click()
    page.get_by_role("button", name="Export conversation").click()
    page.get_by_role("heading", name="Export conversation").wait_for()
    with page.expect_download() as download_info:
        page.locator("#modal-confirm").click()
    download = download_info.value
    assert download.suggested_filename.endswith(".json")
    download_path = tmp_path / download.suggested_filename
    download.save_as(download_path)
    exported = json.loads(download_path.read_text(encoding="utf-8"))
    assert exported["conversation"]["id"] == first["id"]
    assert exported["scope"]["excluded"]

    page.locator("#studio-conversation-options").click()
    page.get_by_role("button", name="Rename conversation").click()
    page.get_by_role("heading", name="Rename conversation").wait_for()
    page.locator("#conversation-title-input").fill("Launch review notes")
    page.get_by_role("button", name="Save name").click()
    wait_for(lambda: store.get_conversation(first["id"])["title"] == "Launch review notes")
    wait_for_page(page, "document.querySelector('#conversation-switcher')?.innerText.includes('Launch review notes')")
    assert "Launch review notes" in page.locator("#conversation-switcher").inner_text()
    page.reload()
    page.locator("#conversation-switcher").wait_for()
    assert "Launch review notes" in page.locator("#conversation-switcher").inner_text()

    page.locator("#studio-conversation-options").click()
    page.locator("#studio-conversation-more > summary").click()
    page.get_by_role("button", name="Archive conversation").click()
    wait_for(lambda: store.get_conversation(first["id"])["archived"] == 1)
    assert page.locator(f"#conversation-switcher option[value='{first['id']}']").count() == 1
    page.locator("#conversation-switcher").select_option(first["id"])
    wait_for_page(page, "id => document.querySelector('#conversation-switcher')?.value === id", arg=first["id"])
    page.locator("#studio-conversation-options").click()
    page.locator("#studio-conversation-more > summary").click()
    page.get_by_role("button", name="Restore conversation").click()
    wait_for(lambda: store.get_conversation(first["id"])["archived"] == 0)
    assert not errors, errors
    assert not external_requests, external_requests
    repo = Path(__file__).resolve().parents[2]
    (artifacts / "validation.json").write_text(json.dumps({
        "test": "tests/e2e/test_browser.py::test_conversation_options_are_compact_persistent_and_recoverable",
        "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_conversation_options_are_compact_persistent_and_recoverable",
        "browser": browser.browser_type.name, "browser_version": browser.version,
        "playwright_version": package_version("playwright"), "viewports": inspected,
        "task_template_review_viewports": template_review_sizes,
        "fixture_only": True, "provider_calls": 0, "external_requests": external_requests,
        "page_errors": errors,
        "verified": ["pin and unread state survive client navigation", "reopening clears unread",
                     "chat section persists", "rename persists after reload", "first user request can be reviewed and downloaded as a local task template",
                     "task template import only fills the composer draft", "export reviewed before local download",
                     "nested More menu groups less frequent actions and supports Escape focus return",
                     "archived chat can be restored", "Escape returns focus", "all menu sizes fit their viewport"],
        "source_sha256": {name: hashlib.sha256((repo / name).read_bytes()).hexdigest()
                          for name in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                       "src/hutch/server/app.py", "src/hutch/store.py", "tests/e2e/test_browser.py")},
        "trace": "trace.zip",
            }, indent=2) + "\n", encoding="utf-8")
    page.context.tracing.stop(path=str(artifacts / "trace.zip"))
    page.close()


def test_bot_menu_downloads_a_reviewable_local_setup_template(browser, live, tmp_path, request):
    base, app = live
    bot = Bot(name="template-export", model="mock/demo", tools=["memory", "files"],
              description="A reusable project reviewer.", instructions="Review project risks and cite source files.",
              base_url="https://private-provider.example/v1", workspace_mode="folder",
              workdir=str(tmp_path / "private-project"))
    app.state.store.create_bot(bot)
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    request.addfinalizer(page.close)
    page.set_default_timeout(8000)
    page.context.tracing.start(screenshots=True, snapshots=True, sources=False)
    page.goto(base + "/#/chat/template-export")
    page.locator("#conversation-switcher").wait_for()
    page.locator('[data-bot-options="template-export"]').click()
    page.get_by_role("menuitem", name="Share as template").click()
    page.get_by_role("heading", name="Share as template").wait_for()
    assert "Nothing is uploaded" in page.locator("#modal-root").inner_text()
    yaml_text = page.locator("#bot-template-preview").inner_text()
    assert "Review project risks" in yaml_text
    assert "private-provider.example" not in yaml_text
    assert str(tmp_path / "private-project") not in yaml_text
    artifacts = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/conversation-options"
    artifacts.mkdir(parents=True, exist_ok=True)
    inspected = []
    for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
        page.set_viewport_size({"width": width, "height": height})
        preview = page.locator("#bot-template-preview")
        confirm = page.locator("#modal-confirm")
        overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        preview_box, confirm_box = preview.bounding_box(), confirm.bounding_box()
        assert overflow == 0, f"{label} template review overflowed by {overflow}px"
        assert preview.is_visible() and confirm.is_visible()
        assert confirm_box["y"] + confirm_box["height"] <= height
        page.screenshot(path=str(artifacts / f"template-review-{label}.png"))
        inspected.append({"label": label, "viewport": [width, height], "overflow_px": overflow,
                          "preview_visible": preview.is_visible(), "confirm_visible": confirm.is_visible()})
    with page.expect_download() as download_info:
        page.locator("#modal-confirm").click()
    download = download_info.value
    path = tmp_path / download.suggested_filename
    download.save_as(path)
    import yaml
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert document["kind"] == "BotConfig"
    assert document["spec"]["instructions"] == "Review project risks and cite source files."
    assert "base_url" not in document["spec"] and "workdir" not in document["spec"]
    assert len(app.state.store.list_bots()) == 1, "creating a local template file must not add a Bot"
    (artifacts / "template-review-validation.json").write_text(json.dumps({
        "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_bot_menu_downloads_a_reviewable_local_setup_template",
        "browser": browser.browser_type.name, "browser_version": browser.version,
        "playwright_version": package_version("playwright"), "viewports": inspected,
        "effect": "download-only local YAML; no public share, no Bot creation, no provider calls",
        "trace": "template-review-trace.zip",
        "excluded_fixture_values": ["provider endpoint URL", "local workspace path"],
        "source_sha256": {name: hashlib.sha256((Path(__file__).resolve().parents[2] / name).read_bytes()).hexdigest()
                          for name in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                       "src/hutch/server/app.py", "src/hutch/store.py")},
    }, indent=2) + "\n")
    page.context.tracing.stop(path=str(artifacts / "template-review-trace.zip"))
    page.close()


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
        page.locator("#run-technical-details > summary").click()
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


def test_passkey_pair_and_unlock_pages_explain_the_phone_flow(browser, live):
    """The browser surface requests a passkey without exposing a bearer-token workflow."""
    base, _app = live
    page = browser.new_page(viewport={"width": 390, "height": 844})
    try:
        page.goto(f"{base}/pair")
        page.get_by_role("heading", name="Pair this device").wait_for()
        assert "save a passkey on this device" in page.locator("#pair-instructions").inner_text()
        assert page.locator("[autocomplete=one-time-code]").count() == 1
        assert page.locator("script[src='/static/pair.js']").count() == 1
        assert "bearer" not in page.locator("body").inner_text().lower()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

        page.goto(f"{base}/login")
        assert page.get_by_role("button", name="Unlock with passkey").is_visible()
        assert page.locator("script[src='/static/passkey-login.js']").count() == 1
        assert "local owner token" in page.locator("body").inner_text().lower()
    finally:
        page.close()


def test_virtual_passkey_pairs_locks_and_unlocks_over_https(browser, tmp_path, monkeypatch):
    """Exercise the browser's real WebAuthn ceremony against Hutch over local HTTPS."""
    if browser.browser_type.name != "chromium":
        pytest.skip("the WebAuthn virtual authenticator requires Chromium's DevTools protocol")

    import socket
    import ssl
    import uvicorn
    from datetime import timedelta
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    from hutch.approvals import action_fingerprint
    from hutch.models import ApprovalRequest, iso, utcnow

    rp_id = "hutch.example"
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "1")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", rp_id)
    monkeypatch.setenv("HUTCH_WEBAUTHN_RP_ID", rp_id)
    monkeypatch.delenv("HUTCH_AUTH_TOKEN", raising=False)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, rp_id)])
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(rp_id)]), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    cert_path, key_path = tmp_path / "hutch.test.crt", tmp_path / "hutch.test.key"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                           serialization.NoEncryption()))
    cert_path.chmod(0o600)
    key_path.chmod(0o600)

    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    monkeypatch.setenv("HUTCH_WEBAUTHN_ORIGIN", f"https://{rp_id}:{port}")
    app = create_app()
    monkeypatch.setattr(app.state.engine, "tick", lambda: None)
    bot = app.state.store.create_bot(Bot(name="phone-start", model="mock/demo", tools=[], paused=True,
                                         remote_start_enabled=True))
    approval_run = app.state.store.create_run(Run(bot_id=bot.id, prompt="Review a file write over HTTPS",
                                                  status=RunStatus.waiting_approval))
    approval_detail = {"path": "status.txt", "content": "HTTPS approval fixture"}
    approval = app.state.store.create_approval(ApprovalRequest(
        run_id=approval_run.id, bot_id=bot.id, tool="files", action="Write status.txt", detail=approval_detail,
        action_hash=action_fingerprint("files", approval_detail),
        expires_at=iso(utcnow() + timedelta(minutes=10))))
    resume_bot = app.state.store.create_bot(Bot(name="phone-resume", model="mock/demo", tools=[]))
    human_run = app.state.store.create_run(Run(bot_id=resume_bot.id, prompt="Resume the local sign-in step"))
    claimed = app.state.store.claim_run(human_run.id, "https-resume-fixture", lease_seconds=60)
    assert claimed is not None
    app.state.store.transition_run(human_run.id, RunStatus.running, fence=claimed.fence)
    app.state.store.transition_run(human_run.id, RunStatus.waiting_human, fence=claimed.fence)
    app.state.store.append_event(Event(run_id=human_run.id, type=EventType.human_needed,
                                       data={"reason": "Complete the local sign-in step"}))
    app.state.store.flush_events()
    human_event_seq = app.state.store.last_seq(human_run.id)
    code = app.state.store.create_pairing_code(allow_start=True)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                           ssl_certfile=str(cert_path), ssl_keyfile=str(key_path),
                                           proxy_headers=False, access_log=False, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    chromium = browser.browser_type.launch(args=["--host-resolver-rules=MAP hutch.example 127.0.0.1"])
    context = chromium.new_context(viewport={"width": 390, "height": 844}, ignore_https_errors=True)
    page = context.new_page()
    page.set_default_timeout(10_000)
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server.started

        authenticator = context.new_cdp_session(page)
        authenticator.send("WebAuthn.enable")
        virtual_authenticator = authenticator.send("WebAuthn.addVirtualAuthenticator", {"options": {
            "protocol": "ctap2", "transport": "internal", "hasResidentKey": True,
            "hasUserVerification": True, "isUserVerified": True,
            "automaticPresenceSimulation": True,
        }})

        base = f"https://{rp_id}:{port}"
        page.goto(base + "/pair")
        page.locator('[name="label"]').fill("Chromium virtual phone")
        page.locator('[name="code"]').fill(code)
        page.get_by_role("button", name="Pair device").click()
        page.get_by_role("heading", name="Passkey saved").wait_for()
        page.get_by_role("link", name="Open Hutch").click()
        page.locator("#phone-root .phone-brand").wait_for()
        assert page.get_by_text("Chromium virtual phone").count() == 0  # the phone surface does not expose device administration

        page.get_by_role("button", name="Lock").click()
        page.get_by_role("heading", name="Hutch is locked").wait_for()
        page.get_by_role("link", name="Sign in with your passkey").click()
        page.get_by_role("button", name="Unlock with passkey").click()
        page.locator("#phone-root .phone-brand").wait_for()
        status = page.evaluate("""async () => {
          const response = await fetch('/api/v1/session', { cache: 'no-store' });
          return { status: response.status, body: await response.json() };
        }""")
        assert status["status"] == 200 and status["body"]["principal"] == "paired"
        assert "start" in status["body"]["capabilities"]

        page.locator('[data-phone-tab="review"]').click()
        card = page.locator(f'.approval-card [data-phone-approve="{approval.id}"]').locator("..").locator("..")
        allow = card.get_by_role("button", name="Allow once")
        allow.wait_for()
        assert allow.get_attribute("data-action-hash") == approval.action_hash
        with page.expect_response(lambda response: response.url.endswith(
                f"/api/v1/actions/approvals/{approval.id}/approve")) as decision:
            allow.click()
        decision_response = decision.value
        assert decision_response.status == 200, decision_response.text()
        assert decision_response.request.headers.get("x-hutch-csrf")
        assert decision_response.request.headers.get("idempotency-key")
        assert decision_response.request.post_data_json == {"always": False, "action_hash": approval.action_hash}
        assert app.state.store.get_approval(approval.id).status.value == "approved"

        page.get_by_role("button", name="Status").click()
        page.locator("#phone-start-form").wait_for()
        assert "Scheduled tasks are paused" in page.locator("#phone-root").inner_text()
        assert "scheduled tasks paused" in page.locator('#phone-start-form [name="bot"]').inner_text()
        assert "pausing a Bot only pauses its scheduled tasks" in page.locator("#phone-start-form").inner_text()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.locator('#phone-start-form [name="prompt"]').fill("Check the local project status")
        with page.expect_response(lambda response: response.request.method == "POST" and
                                 response.url.endswith("/api/v1/tasks/runs")) as start_response:
            page.get_by_role("button", name="Start work").click()
        started = start_response.value
        assert started.status == 201, started.text()
        run_id = started.json()["id"]
        page.locator(".phone-run-detail").wait_for()
        assert page.locator(".phone-run-detail h1").inner_text() == "Check the local project status"
        run = app.state.store.get_run(run_id)
        assert run.bot_id == bot.id
        assert run.origin == f"remote:{status['body']['credential_id']}"
        assert run.model_override == ""

        with page.expect_response(lambda response: response.url.endswith(
                f"/api/v1/tasks/runs/{run_id}/stop")) as stopped:
            page.get_by_role("button", name="Stop run").click()
        stop_response = stopped.value
        assert stop_response.status == 200, stop_response.text()
        assert stop_response.request.headers.get("x-hutch-csrf")
        assert stop_response.request.headers.get("idempotency-key")
        assert stop_response.request.post_data_json == {}
        assert app.state.store.get_run(run_id).status is RunStatus.stopped

        page.get_by_role("button", name="All runs").click()
        page.locator(f'[data-phone-run="{human_run.id}"]').click()
        page.locator(".phone-run-detail").wait_for()
        resume = page.get_by_role("button", name="Resume after completing the requested step")
        assert resume.get_attribute("data-human-seq") == str(human_event_seq)
        with page.expect_response(lambda response: response.url.endswith(
                f"/api/v1/tasks/runs/{human_run.id}/resume")) as resumed:
            resume.click()
        resume_response = resumed.value
        assert resume_response.status == 200, resume_response.text()
        assert resume_response.request.headers.get("x-hutch-csrf")
        assert resume_response.request.headers.get("idempotency-key")
        assert resume_response.request.post_data_json == {"human_event_seq": human_event_seq}
        assert resume_response.json() == {"resumed": human_run.id, "human_event_seq": human_event_seq,
                                          "replayed": False}
        assert app.state.store.kv_get(f"resume:{human_run.id}") == "1"
        assert app.state.store.get_run(human_run.id).status is RunStatus.waiting_human
        credentials = authenticator.send("WebAuthn.getCredentials", {
            "authenticatorId": virtual_authenticator["authenticatorId"]})
        assert len(credentials["credentials"]) == 1
    finally:
        context.close()
        chromium.close()
        server.should_exit = True
        thread.join(timeout=10)
    assert not thread.is_alive()


def test_chromium_trusts_a_private_https_certificate_chain(browser, tmp_path):
    """Verify a private CA and hostname without Playwright's certificate-error bypass."""
    import os
    import shutil
    import ssl
    import subprocess
    from datetime import timedelta
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    certutil = shutil.which("certutil")
    if not certutil:
        pytest.skip("NSS certutil is required to add an isolated test CA to Chromium's temporary trust store")

    rp_id = "hutch.example"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Hutch Local Test CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
          .not_valid_after(now + timedelta(days=2))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False,
                                       data_encipherment=False, key_agreement=False, key_cert_sign=True,
                                       crl_sign=True, encipher_only=None, decipher_only=None), critical=True)
          .sign(ca_key, hashes.SHA256()))
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, rp_id)])
    server_cert = (x509.CertificateBuilder().subject_name(server_name).issuer_name(ca_name)
                   .public_key(server_key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
                   .add_extension(x509.SubjectAlternativeName([x509.DNSName(rp_id)]), critical=False)
                   .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                   .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False,
                                                key_encipherment=True, data_encipherment=False,
                                                key_agreement=False, key_cert_sign=False, crl_sign=False,
                                                encipher_only=None, decipher_only=None), critical=True)
                   .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                   .sign(ca_key, hashes.SHA256()))

    ca_path, cert_path, key_path = tmp_path / "test-ca.pem", tmp_path / "server.pem", tmp_path / "server.key"
    ca_path.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    cert_path.write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(server_key.private_bytes(serialization.Encoding.PEM,
                                                   serialization.PrivateFormat.TraditionalOpenSSL,
                                                   serialization.NoEncryption()))
    browser_home = tmp_path / "browser-home"
    nss_db = browser_home / ".pki" / "nssdb"
    nss_db.mkdir(parents=True)
    subprocess.run([certutil, "-N", "--empty-password", "-d", f"sql:{nss_db}"],
                   check=True, capture_output=True, text=True)
    subprocess.run([certutil, "-A", "-d", f"sql:{nss_db}", "-n", "Hutch Local Test CA", "-t", "C,,",
                    "-i", str(ca_path)], check=True, capture_output=True, text=True)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"trusted private HTTPS")

        def log_message(self, *_args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(cert_path, key_path)
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    chromium = browser.browser_type.launch(
        env={**os.environ, "HOME": str(browser_home)},
        args=["--host-resolver-rules=MAP hutch.example 127.0.0.1"],
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        page = chromium.new_page(viewport={"width": 390, "height": 844})
        response = page.goto(f"https://{rp_id}:{server.server_port}/", wait_until="domcontentloaded")
        assert response and response.status == 200
        assert page.locator("body").inner_text() == "trusted private HTTPS"
        assert page.evaluate("location.protocol + '//' + location.hostname") == "https://hutch.example"
    finally:
        server.shutdown()
        thread.join(timeout=10)
        server.server_close()
        chromium.close()
    assert not thread.is_alive()


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


def test_bot_usage_limits_are_optional_clear_and_use_everyday_time_units(browser, live):
    base, app = live
    store = app.state.store
    store.create_bot(Bot(name="limit-bot", model="mock/demo", approval_mode=ApprovalMode.auto))
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/assistant-usage-details-2026-10-10"
    out.mkdir(parents=True, exist_ok=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = ctx.new_page()
    errors = []
    external_requests = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external_requests.append(request.url) if not request.url.startswith(base) else None)
    ctx.tracing.start(screenshots=True, snapshots=True, sources=False)
    viewports = {"desktop": (1440, 960), "tablet": (900, 1024), "phone": (390, 844), "compact_phone": (320, 740)}
    try:
        page.goto(f"{base}/#/bot/limit-bot")
        disclosure = page.locator("#assistant-usage-limits")
        disclosure.wait_for(state="attached")
        initially_open = disclosure.evaluate("element => ({open: element.open, html: element.outerHTML.slice(0, 150)})")
        assert not initially_open["open"], f"usage settings should start collapsed: {initially_open}"
        open_assistant_customization(page)
        expected_steps, expected_duration = "24 work steps", "15 min per task"
        expected_timeout_minutes = "15"
        for label, (width, height) in viewports.items():
            page.set_viewport_size({"width": width, "height": height})
            summary = disclosure.locator(":scope > summary")
            assert not disclosure.evaluate("element => element.open"), f"usage details should be closed at {label}"
            assert expected_steps in summary.inner_text()
            assert expected_duration in summary.inner_text()
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
            disclosure.scroll_into_view_if_needed()
            page.screenshot(path=str(out / f"{label}-limits-collapsed.png"))

            if label == "phone":
                summary.focus()
                summary.press("Space")
            else:
                summary.click()
            assert disclosure.evaluate("element => element.open")
            form = page.locator("#form-limits")
            form.wait_for(state="visible")
            assert page.locator('label:has([name="max_steps"])').inner_text().startswith("Maximum work steps")
            assert page.locator('label:has([name="timeout_minutes"])').inner_text().startswith("Time per task (minutes)")
            assert page.locator('#form-limits [name="timeout_minutes"]').input_value() == expected_timeout_minutes
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
            disclosure.scroll_into_view_if_needed()
            page.screenshot(path=str(out / f"{label}-limits-open.png"))

            if label == "phone":
                page.locator('#form-limits [name="max_steps"]').fill("11")
                page.locator('#form-limits [name="timeout_minutes"]').fill("2.5")
                page.locator('#form-limits [name="daily_token_cap"]').fill("7500")
                page.locator('#form-limits [name="max_cost_usd"]').fill("0.65")
                page.locator('#form-limits button[type="submit"]').click()
                wait_for(lambda: store.get_bot("limit-bot").limits.timeout_seconds == 150)
                page.locator("#toast-root .toast-msg").filter(has_text="Limits saved.").wait_for(state="visible")
                limits = store.get_bot("limit-bot").limits
                assert limits.max_steps == 11 and limits.timeout_seconds == 150
                assert limits.daily_token_cap == 7500 and limits.max_cost_usd == 0.65
                page.locator("#toast-root").evaluate("root => root.replaceChildren()")
                expected_steps, expected_duration = "11 work steps", "2.5 min per task"
                expected_timeout_minutes = "2.5"
                wait_for_page(page, "document.querySelector('#assistant-usage-limits small')?.textContent.includes('2.5 min per task')")
                assert not disclosure.evaluate("element => element.open")
                disclosure.locator(":scope > summary").focus()
                disclosure.locator(":scope > summary").press("Space")
                assert disclosure.evaluate("element => element.open")
                disclosure.locator(":scope > summary").press("Space")
                assert not disclosure.evaluate("element => element.open")
            else:
                summary.click()
                assert not disclosure.evaluate("element => element.open")

        assert not errors, errors
        assert not external_requests, external_requests
        (out / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_bot_usage_limits_are_optional_clear_and_use_everyday_time_units",
            "viewports": {name: {"width": size[0], "height": size[1]} for name, size in viewports.items()},
            "verified": ["settings stay collapsed until requested", "summary reports existing work and time limits",
                         "keyboard opens the details on phone", "900 seconds displays as 15 minutes",
                         "2.5 minutes saves as 150 seconds", "no horizontal overflow at 320px or larger widths",
                         "no external requests"],
            "browser": {"name": page.evaluate("navigator.userAgent")},
            "source_sha256": {"app.js": hashlib.sha256((Path(__file__).resolve().parents[2] / "src/hutch/server/static/app.js").read_bytes()).hexdigest(),
                              "style.css": hashlib.sha256((Path(__file__).resolve().parents[2] / "src/hutch/server/static/style.css").read_bytes()).hexdigest()},
        }, indent=2) + "\n")
    finally:
        ctx.tracing.stop(path=str(out / "trace.zip"))
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
        open_assistant_customization(page)
        page.locator("#form-tools").wait_for()
        delegate = page.locator('#form-tools input[name="tools"][value="delegate_task"]')
        assert not delegate.is_checked()
        assert page.get_by_text("Each request asks for approval and uses another run slot", exact=False).is_visible()

        for label, (width, height) in sizes.items():
            page.set_viewport_size({"width": width, "height": height})
            panel = page.locator('section[aria-labelledby="tool-settings-title"]')
            position = position_panel("start")
            page.wait_for_timeout(80)
            delete_button = page.get_by_role("button", name="Delete assistant")
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
        open_assistant_customization(page)
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


def test_quick_bot_creation_uses_the_workspace_default_without_starting_work(browser, live, monkeypatch):
    base, app = live
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key-never-sent-to-a-provider")
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    page.set_default_timeout(8000)
    errors: list[str] = []
    outside_requests: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: outside_requests.append(request.url)
            if urlsplit(request.url).netloc not in {urlsplit(base).netloc, ""} else None)
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/quick-setup-language-2026-10-10"
    out.mkdir(parents=True, exist_ok=True)
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        configured = page.request.put(f"{base}/api/v1/preferences/model-defaults", data={
            "model": "openai/gpt-4o-mini", "inference_mode": "hybrid",
        })
        assert configured.status == 200, configured.text()
        page.goto(f"{base}/#/chat")
        page.locator("#topbar-new-bot").click()
        page.get_by_role("heading", name="Set up your assistant").wait_for()
        purpose = "Prepare a weekly project update from notes I share."
        page.get_by_label("What would you like this assistant to handle?").fill(purpose)
        name_input = page.get_by_label("Assistant name")
        assert name_input.is_visible() and name_input.is_enabled()
        assert re.fullmatch(r"[A-Z][a-z]+ [A-Z][a-z]+", name_input.input_value())
        page.locator(".setup-identity summary").click()
        assert page.locator("#setup-description").input_value() == "Project Reporter"
        page.locator(".setup-identity summary").click()
        name_style = name_input.evaluate("""el => {
          const style = getComputedStyle(el);
          return {height: el.getBoundingClientRect().height, borderStyle: style.borderStyle,
                  borderWidth: style.borderTopWidth, background: style.backgroundColor};
        }""")
        assert name_style["height"] >= 44, name_style
        assert name_style["borderStyle"] == "solid" and name_style["borderWidth"] == "1px", name_style
        assert name_style["background"] != "rgba(0, 0, 0, 0)", name_style
        assert page.locator(".setup-quick-summary").is_visible()
        quick_summary = page.locator(".setup-quick-summary").inner_text()
        assert "Uses your saved AI choice" in quick_summary
        assert "no apps connected or recurring work" in quick_summary
        assert "checks with you before important actions" in quick_summary
        assert "openai/gpt-4o-mini" not in quick_summary
        assert "hybrid" not in quick_summary.lower()
        assert page.locator("#modal-confirm").inner_text() == "Create bot"
        assert page.locator("#setup-customize").is_visible()
        assert app.state.store.list_bots() == [] and app.state.store.list_runs() == []
        captures = []
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            metrics = page.evaluate("""() => ({width:document.documentElement.scrollWidth-innerWidth,
              dialog:document.querySelector('[role=dialog]').getBoundingClientRect().toJSON(),
              footer:document.querySelector('.modal-footer').getBoundingClientRect(),
              summary:document.querySelector('.setup-quick-summary').getBoundingClientRect(),
              name:document.querySelector('#setup-display_name').getBoundingClientRect()})""")
            assert metrics["width"] <= 1, (label, metrics)
            assert metrics["footer"]["bottom"] <= height + 1, (label, metrics)
            assert metrics["summary"]["bottom"] <= metrics["footer"]["top"] + 1, (label, metrics)
            assert metrics["name"]["bottom"] <= metrics["footer"]["top"] + 1, (label, metrics)
            assert metrics["dialog"]["left"] >= -1 and metrics["dialog"]["right"] <= width + 1, (label, metrics)
            page.screenshot(path=str(out / f"quick-{label}.png"), animations="disabled")
            captures.append({"viewport": [width, height], "horizontal_overflow": metrics["width"],
                             "footer_visible": True, "summary_visible_above_footer": True,
                             "name_visible_above_footer": True})
        page.set_viewport_size({"width": 1440, "height": 960})
        page.locator("#setup-customize").click()
        page.get_by_role("heading", name="Choose what powers it").wait_for()
        assert page.get_by_label("Model route").input_value() == "openai/gpt-4o-mini"
        assert page.locator("#setup-inference_mode").input_value() == "hybrid"
        page.locator("#modal-cancel").click()
        page.locator("#topbar-new-bot").click()
        page.get_by_label("What would you like this assistant to handle?").fill(purpose)
        with page.expect_response(lambda response: response.url.endswith("/api/v1/bots")
                                 and response.request.method == "POST") as created:
            page.locator("#modal-confirm").click()
        assert created.value.status == 201, created.value.text()
        bot = app.state.store.list_bots()[0]
        assert bot is not None and bot.instructions == purpose
        assert bot.model == "openai/gpt-4o-mini" and bot.inference_mode.value == "hybrid"
        assert bot.tools == [] and bot.schedule is None and bot.approval_mode is ApprovalMode.ask
        assert bot.workspace_mode == "managed"
        assert app.state.store.list_runs() == [], "quick creation must save a Bot without starting work"
        assert not errors and not outside_requests, (errors, outside_requests)
        (out / "validation.json").write_text(json.dumps({
            "command": "uv run pytest -q tests/e2e/test_browser.py::test_quick_bot_creation_uses_the_workspace_default_without_starting_work",
            "browser": browser.browser_type.name, "browser_version": browser.version,
            "playwright_version": package_version("playwright"), "provider_calls": 0,
            "external_requests": outside_requests, "page_errors": errors, "captures": captures,
            "verified": ["purpose-first one-screen setup", "editable suggested name visible", "plain-language saved AI choice summary", "model route and inference mode remain in fine-tuning",
                         "no tools or recurring task enabled", "approval remains ask-first", "creation starts no run"],
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
        page.get_by_role("heading", name="Set up your assistant").wait_for()
        page.get_by_label("What would you like this assistant to handle?").fill(
            "Review release notes and prepare a short summary of changes that affect our project.")
        suggested_name = page.get_by_label("Assistant name").input_value()
        assert re.fullmatch(r"[A-Z][a-z]+ [A-Z][a-z]+", suggested_name)
        page.locator(".setup-identity summary").click()
        assert page.locator("#setup-description").input_value() == "Release Notes Reviewer"
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
        page.locator("#setup-display_name").fill("Release Notes Reviewer")
        page.locator("#setup-name").fill("guided-release-reviewer")
        page.get_by_label("Short note").fill("Summarize project release notes")
        page.locator("#modal-confirm").click()
        page.get_by_role("heading", name="Choose what powers it").wait_for()
        page.locator("#setup-back").click()
        assert "Review release notes" in page.locator("#setup-purpose").input_value()
        page.locator("#modal-confirm").click()
        page.get_by_role("heading", name="Choose what powers it").wait_for()
        page.get_by_label("Model route").fill("openai/gpt-4o-mini")
        page.locator("#modal-confirm").click()
        page.get_by_role("heading", name="Choose its apps").wait_for()
        assert page.locator("#setup-tools input:checked").count() == 0
        page.get_by_text("Task focus (optional)").click()
        page.locator("#setup-preset").select_option("research")
        assert "never chooses a model or provider" in page.locator(".setup-task-focus").inner_text()
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
        page.get_by_role("heading", name="Review and create").wait_for()
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
        assert page.locator(".setup-review-list").get_by_text("Research", exact=True).is_visible()
        assert app.state.store.list_runs() == []
        assert app.state.store.get_bot("guided-release-reviewer") is None
        page.locator("#setup-yaml-details > summary").click()
        yaml_build = page.get_by_role("button", name="Build YAML preview")
        with page.expect_response(lambda response: response.url.endswith("/api/v1/bot-configs/preview")
                                 and response.request.method == "POST") as yaml_preview:
            yaml_build.focus()
            yaml_build.press("Enter")
        preview_response = yaml_preview.value
        assert preview_response.status == 200, preview_response.text()
        preview_payload = preview_response.json()
        yaml_text = preview_payload["yaml"]
        assert "kind: BotConfig" in yaml_text and "guided-release-reviewer" in yaml_text
        assert "preset: research" in yaml_text
        assert "Review release notes and prepare a short summary" in yaml_text
        assert preview_payload["saved"] is False
        assert "provider endpoint URL" in preview_payload["omitted_fields"]
        assert page.locator("#setup-yaml-download").is_enabled()
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            page.locator("#setup-yaml-preview").scroll_into_view_if_needed()
            page.screenshot(path=str(out / f"yaml-preview-{label}.png"), animations="disabled")
            metrics = page.evaluate("""() => ({viewport:[innerWidth,innerHeight], documentWidth:document.documentElement.scrollWidth,
              bodyOverflow:document.querySelector('.modal-body').scrollWidth-document.querySelector('.modal-body').clientWidth,
              previewVisible:(() => {const r=document.querySelector('#setup-yaml-preview').getBoundingClientRect();
                const body=document.querySelector('.modal-body').getBoundingClientRect();
                const footer=document.querySelector('.modal-footer').getBoundingClientRect();
                return r.height>0 && r.top>=body.top-1 && r.bottom<=footer.top+1;})(),
              footerVisible:document.querySelector('.modal-footer').getBoundingClientRect().bottom<=innerHeight})""")
            assert metrics["documentWidth"] - width <= 1 and metrics["bodyOverflow"] <= 1, (label, metrics)
            assert metrics["previewVisible"] and metrics["footerVisible"], (label, metrics)
        yaml_download_button = page.get_by_role("button", name="Download YAML")
        yaml_download_button.focus()
        with page.expect_download() as yaml_download:
            yaml_download_button.press("Enter")
        download = yaml_download.value
        assert download.suggested_filename == "hutch-guided-release-reviewer.yaml"
        download.save_as(str(out / download.suggested_filename))
        assert (out / download.suggested_filename).read_text(encoding="utf-8") == yaml_text
        assert app.state.store.get_bot("guided-release-reviewer") is None
        assert app.state.store.list_runs() == []
        with page.expect_response(lambda response: response.url.endswith("/api/v1/bots")
                                 and response.request.method == "POST") as created:
            page.locator("#modal-confirm").click()
        assert created.value.status == 201, created.value.text()
        wait_for(lambda: app.state.store.get_bot("guided-release-reviewer") is not None)
        bot = app.state.store.get_bot("guided-release-reviewer")
        assert bot.instructions == "Review release notes and prepare a short summary of changes that affect our project."
        assert bot.description == "Summarize project release notes"
        assert bot.preset == "research"
        assert bot.tools == ["read_file"] and bot.approval_mode is ApprovalMode.ask
        assert bot.local_browser_handoff is handoff_enabled
        assert bot.schedule and bot.schedule.prompt == "Review release notes and report important changes."
        assert app.state.store.list_runs() == [], "bot creation must not submit a run"
        assert not errors, errors
        (out / "validation.json").write_text(json.dumps({
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_guided_bot_creation_reviews_configuration_at_desktop_tablet_and_phone",
            "browser": browser.browser_type.name, "browser_version": browser.version,
            "playwright_version": package_version("playwright"),
            "scenario": "guided setup selects a task focus without changing the explicit provider route, uses a test-only dummy key and makes no model call; Enter builds a non-persisting YAML preview and downloads the same sanitized text before the separate Create bot confirmation; checked review configuration at desktop, tablet and phone widths",
            "viewports": {"desktop": [1440, 960], "tablet": [900, 1024], "phone": [390, 844]},
            "inspected_screenshots": ["purpose-desktop.png", "purpose-tablet.png", "purpose-phone.png",
                                      "options-desktop.png", "options-tablet.png", "options-phone.png",
                                      "configuration-desktop.png", "configuration-tablet.png", "configuration-phone.png",
                                      "configuration-handoff-phone.png", "review-desktop.png", "review-tablet.png",
                                      "review-phone.png", "review-details-end-desktop.png", "review-details-end-tablet.png",
                                      "review-details-end-phone.png", "yaml-preview-desktop.png", "yaml-preview-tablet.png",
                                      "yaml-preview-phone.png"],
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


def test_bot_setup_yaml_import_fills_reviewed_draft_without_saving_until_confirmation(browser, live, monkeypatch):
    import hashlib
    from pathlib import Path

    base, app = live
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key-never-sent-to-a-provider")
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    page.set_default_timeout(10_000)
    errors: list[str] = []
    requests: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: requests.append(request.url))
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/bot-setup-import"
    out.mkdir(parents=True, exist_ok=True)
    yaml_text = """apiVersion: hutch.ai/v1
kind: BotConfig
spec:
  name: imported-release-reviewer
  display_name: Jordan Reed · Release Notes Reviewer
  template: null
  description: Summarize project release notes
  instructions: Review release notes and prepare a short summary for the project team.
  model: openai/gpt-4o-mini
  inference_mode: hybrid
  tools:
  - read_file
  memory_enabled: false
  cron: 0 9 * * 1
  timezone: America/Vancouver
  catch_up: skip
  schedule_prompt: Review release notes and report important changes.
  approval_mode: ask
  risk_tier: supervised
  command_rules: []
  workspace_mode: managed
  local_browser_handoff: false
  limits:
    max_steps: 11
    timeout_seconds: 240
    daily_token_cap: 4000
    max_turn_tokens: 800
    max_cost_usd: 0.1
    daily_cost_cap_usd: 0.9
"""
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        page.goto(base + "/#/chat")
        page.locator("#topbar-new-bot").click()
        page.get_by_role("heading", name="Set up your assistant").wait_for()
        page.locator("#setup-customize").click()
        page.get_by_role("heading", name="Choose what powers it").wait_for()
        page.locator("#setup-back").click()
        page.locator("#setup-yaml-import-details > summary").click()
        choose = page.get_by_role("button", name="Choose YAML file")
        with page.expect_file_chooser() as chooser:
            choose.focus()
            choose.press("Enter")
        chooser.value.set_files({"name": "project-reviewer.yaml", "mimeType": "application/yaml",
                                "buffer": yaml_text.encode("utf-8")})
        page.get_by_role("status").filter(has_text="YAML validated and copied into this unsaved draft").wait_for()
        import_requests = [url for url in requests if "/api/v1/bot-configs/import" in url]
        assert len(import_requests) == 1
        page.locator("#setup-yaml-import-button").click()
        page.locator("#setup-yaml-file").set_input_files({"name": "too-large.yaml", "mimeType": "application/yaml",
                                                            "buffer": b"x" * 65_537})
        page.get_by_role("status").filter(has_text="no larger than 64 KiB").wait_for()
        assert len([url for url in requests if "/api/v1/bot-configs/import" in url]) == 1
        assert app.state.store.get_bot("imported-release-reviewer") is None
        with page.expect_file_chooser() as chooser:
            page.locator("#setup-yaml-import-button").press("Enter")
        chooser.value.set_files({"name": "project-reviewer.yaml", "mimeType": "application/yaml",
                                "buffer": yaml_text.encode("utf-8")})
        page.get_by_role("status").filter(has_text="YAML validated and copied into this unsaved draft").wait_for()
        assert page.get_by_label("What would you like this assistant to handle?").input_value().startswith("Review release notes")
        assert page.locator("#setup-display_name").input_value() == "Jordan Reed · Release Notes Reviewer"
        assert app.state.store.get_bot("imported-release-reviewer") is None
        assert app.state.store.list_runs() == []
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            metrics = page.evaluate("""() => ({viewport:[innerWidth,innerHeight], documentWidth:document.documentElement.scrollWidth,
              bodyOverflow:document.querySelector('.modal-body').scrollWidth-document.querySelector('.modal-body').clientWidth,
              footerVisible:document.querySelector('.modal-footer').getBoundingClientRect().bottom<=innerHeight,
              chooseHeight:document.querySelector('#setup-yaml-import-button').getBoundingClientRect().height})""")
            assert metrics["documentWidth"] - width <= 1 and metrics["bodyOverflow"] <= 1, (label, metrics)
            assert metrics["footerVisible"] and metrics["chooseHeight"] >= 44, (label, metrics)
            page.screenshot(path=str(out / f"import-draft-{label}.png"), animations="disabled")

        page.set_viewport_size({"width": 390, "height": 844})
        page.locator("#modal-confirm").click()
        page.get_by_role("heading", name="Choose what powers it").wait_for()
        assert page.get_by_label("Model route").input_value() == "openai/gpt-4o-mini"
        assert page.get_by_label("Inference mode").input_value() == "hybrid"
        page.locator("#modal-confirm").click()
        page.get_by_role("heading", name="Choose its apps").wait_for()
        assert page.locator('input[name="setup-tool"][value="read_file"]').is_checked()
        page.get_by_text("Add a recurring task (optional)").click()
        assert page.get_by_label("Cron schedule", exact=True).input_value() == "0 9 * * 1"
        assert page.get_by_label("Time zone").input_value() == "America/Vancouver"
        assert page.get_by_label("Missed schedule windows").input_value() == "skip"
        page.locator("#modal-confirm").click()
        page.get_by_role("heading", name="Review and create").wait_for()
        assert "America/Vancouver" in page.locator(".setup-review").inner_text()
        assert "missed windows: skip" in page.locator(".setup-review").inner_text()
        assert "Memory" in page.locator(".setup-review").inner_text()
        assert app.state.store.get_bot("imported-release-reviewer") is None
        assert app.state.store.list_runs() == []
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            page.locator(".setup-review-list").scroll_into_view_if_needed()
            metrics = page.evaluate("""() => ({viewport:[innerWidth,innerHeight], documentWidth:document.documentElement.scrollWidth,
              bodyOverflow:document.querySelector('.modal-body').scrollWidth-document.querySelector('.modal-body').clientWidth,
              footerVisible:document.querySelector('.modal-footer').getBoundingClientRect().bottom<=innerHeight})""")
            assert metrics["documentWidth"] - width <= 1 and metrics["bodyOverflow"] <= 1, (label, metrics)
            assert metrics["footerVisible"], (label, metrics)
            page.screenshot(path=str(out / f"review-import-{label}.png"), animations="disabled")
        with page.expect_response(lambda response: response.url.endswith("/api/v1/bots")
                                 and response.request.method == "POST") as created:
            page.locator("#modal-confirm").click()
        assert created.value.status == 201, created.value.text()
        bot = app.state.store.get_bot("imported-release-reviewer")
        assert bot is not None and bot.display_name == "Jordan Reed · Release Notes Reviewer"
        assert bot.instructions == "Review release notes and prepare a short summary for the project team."
        assert bot.model == "openai/gpt-4o-mini" and bot.tools == ["read_file"]
        assert bot.schedule and bot.schedule.timezone == "America/Vancouver" and bot.schedule.catch_up.value == "skip"
        assert bot.limits.max_steps == 11 and bot.workspace_mode == "managed"
        assert app.state.store.list_runs() == [], "import must not start a Bot run"
        assert not errors, errors
        assert all(url.startswith(base) for url in requests), requests
        (out / "reviewed-import.yaml").write_text(yaml_text, encoding="utf-8")
        (out / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_bot_setup_yaml_import_fills_reviewed_draft_without_saving_until_confirmation",
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_bot_setup_yaml_import_fills_reviewed_draft_without_saving_until_confirmation",
            "browser": browser.browser_type.name, "browser_version": browser.version,
            "playwright_version": package_version("playwright"),
            "viewports": {"desktop": [1440, 960], "tablet": [900, 1024], "phone": [390, 844]},
            "scenario": "keyboard chooses a versioned YAML file, server validation copies it into a draft, every saved setting is reviewed, and only explicit final confirmation creates the Bot; no run or model call",
            "page_errors": errors, "request_hosts": sorted({url.split('/')[2] for url in requests}),
            "source_sha256": {relative: hashlib.sha256((Path(__file__).resolve().parents[2] / relative).read_bytes()).hexdigest()
                              for relative in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                               "src/hutch/server/app.py", "tests/e2e/test_browser.py")},
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        try:
            context.tracing.stop(path=str(out / "trace.zip"))
        finally:
            context.close()


def test_named_workspace_coordinator_is_first_class_direct_chat_at_responsive_sizes(browser, live):
    base, app = live
    coordinator = Bot(name="workspace-coordinator", display_name="Workspace Coordinator",
                     model="mock/demo", tools=[])
    specialist = Bot(name="release-notes-reviewer", display_name="Release Notes Reviewer",
                     model="mock/demo", tools=[])
    app.state.store.create_bot(coordinator)
    app.state.store.create_bot(specialist)
    helper_names = [f"release-helper-{index}" for index in range(9)]
    for index, helper_name in enumerate(helper_names):
        app.state.store.create_bot(Bot(name=helper_name, display_name=f"Release Helper {index}",
                                       model="mock/demo", tools=[]))
    app.state.store.set_workspace_coordinator(coordinator.id)

    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/workspace-coordinator"
    out.mkdir(parents=True, exist_ok=True)
    roster_output = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/workspace-specialists"
    roster_output.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    page.set_default_timeout(8000)
    errors: list[str] = []
    requests: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: requests.append(request.url))
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        page.goto(f"{base}/#/bot/{coordinator.name}")
        open_assistant_customization(page)
        page.get_by_role("heading", name="About this assistant", exact=True).wait_for()
        roster_panel = page.locator("#workspace-specialist-roster")
        roster_details = page.locator("#workspace-specialist-settings")
        roster_summary = roster_details.locator("summary")
        assert roster_panel.is_visible()
        assert roster_details.get_attribute("open") is None
        assert page.locator("#workspace-specialist-roster-count").inner_text() == "0 approved"
        roster_summary.focus()
        page.keyboard.press("Enter")
        assert roster_details.get_attribute("open") is not None
        roster_filter = page.get_by_label("Filter specialist Bots")
        assert roster_filter.is_visible()
        roster_filter.fill("Release Notes")
        visible_choices = page.locator("[data-workspace-specialist-choice]:visible")
        assert visible_choices.count() == 1
        assert "Release Notes Reviewer" in visible_choices.inner_text()
        allowed_specialist = page.locator(f'[data-workspace-specialist="{specialist.id}"]')
        assert allowed_specialist.count() == 1 and not allowed_specialist.is_checked()
        allowed_specialist.focus()
        page.keyboard.press("Space")
        assert allowed_specialist.is_checked()
        page.get_by_role("button", name="Save specialist roster").click()
        assert app.state.store.workspace_specialists()["specialist_bot_ids"] == [specialist.id]
        assert page.locator("#workspace-specialist-roster-count").inner_text() == "1 approved"
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024),
                                     ("phone", 390, 844), ("compact-phone", 320, 844)):
            page.set_viewport_size({"width": width, "height": height})
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1, label
            assert roster_panel.is_visible()
            page.evaluate("document.activeElement?.blur()")
            page.screenshot(path=str(roster_output / f"roster-expanded-{label}.png"), animations="disabled")
            roster_summary.focus()
            page.keyboard.press("Enter")
            assert roster_details.get_attribute("open") is None
            page.evaluate("document.activeElement?.blur()")
            page.screenshot(path=str(roster_output / f"roster-collapsed-{label}.png"), animations="disabled")
            roster_summary.focus()
            page.keyboard.press("Enter")
            assert roster_details.get_attribute("open") is not None
        assert "does not stop existing work" in roster_panel.inner_text()

        for helper_name in helper_names:
            assert app.state.store.delete_bot(helper_name)
        page.set_viewport_size({"width": 1440, "height": 960})
        page.goto(f"{base}/#/chat")
        page.locator(".ctx-id h1").wait_for()
        assert page.locator("#workspace-coordinator-pill").inner_text() == "Workspace coordinator"
        rows = page.locator("#roster-list [data-switch-bot]")
        assert rows.first.get_attribute("data-switch-bot") == coordinator.name
        assert rows.first.locator(".roster-sub").inner_text().startswith("Coordinator · ")

        # A coordinator is an ordinary, directly addressable Bot conversation too.
        conversation_id = page.locator("#conversation-switcher").input_value()
        coordinator_chat = app.state.store.get_conversation(conversation_id)
        assert coordinator_chat["bot_id"] == coordinator.id
        page.locator("#bot-search").fill("Release Notes")
        specialist_options = page.locator("[data-bot-options='release-notes-reviewer']")
        specialist_options.wait_for(state="visible")
        specialist_options.click()
        page.get_by_role("menuitem", name="Assistant settings").click()
        open_assistant_customization(page)
        page.get_by_role("button", name="Make this the main assistant").click()
        page.get_by_role("heading", name="Make this your main assistant?").wait_for()
        page.locator("#modal-confirm").click()
        page.get_by_role("heading", name="About this assistant", exact=True).wait_for()
        assert app.state.store.workspace_coordinator_id() == specialist.id
        assert app.state.store.workspace_specialists()["specialist_bot_ids"] == []
        chat_link = page.locator(f"#app-top-context .ctx-actions a[href='#/chat/{specialist.name}']")
        assert chat_link.count() == 1, page.locator("#app-top-context").inner_html()
        chat_link.click()
        page.locator("#chat-stream").get_by_role("heading", name="Release Notes Reviewer").wait_for()
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
        outside_requests = [url for url in requests if urlsplit(url).netloc not in {urlsplit(base).netloc, ""}]
        assert not outside_requests, outside_requests
        (out / "validation.json").write_text(json.dumps({
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_named_workspace_coordinator_is_first_class_direct_chat_at_responsive_sizes",
            "browser": browser.browser_type.name, "browser_version": browser.version,
            "playwright_version": package_version("playwright"),
            "viewports": {"desktop": [1440, 960], "tablet": [900, 1024], "phone": [390, 844],
                          "compact_phone": [320, 844]},
            "scenario": "the selected workspace coordinator opens as the default direct chat, is labelled in the roster and composer, the owner can maintain an explicit specialist allowlist from settings, and promoting a specialist removes it without adding the former coordinator",
            "page_errors": errors,
            "source_sha256": {relative: hashlib.sha256((Path(__file__).resolve().parents[2] / relative).read_bytes()).hexdigest()
                              for relative in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                               "src/hutch/server/app.py", "tests/e2e/test_browser.py")},
        }, indent=2) + "\n", encoding="utf-8")
        (roster_output / "validation.json").write_text(json.dumps({
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_named_workspace_coordinator_is_first_class_direct_chat_at_responsive_sizes",
            "browser": browser.browser_type.name, "browser_version": browser.version,
            "playwright_version": package_version("playwright"),
            "viewports": {"desktop": [1440, 960], "tablet": [900, 1024], "phone": [390, 844],
                          "compact_phone": [320, 844]},
            "keyboard": "Enter expands/collapses the focused roster summary; Space toggles the focused specialist checkbox; Save persists the selection.",
            "scenario": "the specialist roster stays compact by default, shows the approved count, expands on demand for search and editing, and remains usable at desktop, tablet, phone and compact-phone widths; promotion does not approve the former coordinator",
            "trace": "trace.zip",
            "page_errors": errors, "external_requests": len(outside_requests), "provider_calls": 0,
            "source_sha256": {relative: hashlib.sha256((Path(__file__).resolve().parents[2] / relative).read_bytes()).hexdigest()
                              for relative in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                               "src/hutch/server/app.py", "src/hutch/store.py", "tests/e2e/test_browser.py")},
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        try:
            context.tracing.stop(path=str(roster_output / "trace.zip"))
        except Exception:
            pass
        context.close()


def test_bot_roster_pins_persist_and_simple_mascots_stay_distinct(browser, live):
    """Pin frequent Bots in the one roster; preserve direct access and lightweight identity."""
    base, app = live
    store = app.state.store
    bots = [
        Bot(name="workspace-coordinator", display_name="Workspace Coordinator", model="mock/demo", tools=[]),
        Bot(name="agenda-assistant", display_name="Agenda Assistant", model="mock/demo", tools=[]),
        Bot(name="operations-review", display_name="Operations Reviewer", model="mock/demo", tools=[]),
        Bot(name="research-helper", display_name="Research Companion for Long-Term Vendor Strategy and Operations", model="mock/demo", tools=[]),
        Bot(name="website-auditor", display_name="Website Auditor", model="mock/demo", tools=[]),
    ]
    for bot in bots:
        store.create_bot(bot)
    store.set_workspace_coordinator("workspace-coordinator")

    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/pinned-roster"
    out.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    page.set_default_timeout(8000)
    errors: list[str] = []
    requests: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: requests.append(request.url))
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    viewports = (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844))
    try:
        page.goto(f"{base}/#/chat")
        page.locator(".ctx-id h1").wait_for()
        # This scenario validates readable names in the expanded sidebar,
        # independent of a remembered user's compact-rail preference.
        name_labels = page.locator("#roster-list .roster-name")
        if not name_labels.first.is_visible():
            expand_sidebar = page.get_by_role("button", name="Expand sidebar")
            if expand_sidebar.is_visible():
                expand_sidebar.click()
            else:
                page.locator("#nav-toggle").click()
        name_labels.first.wait_for(state="visible")
        wait_for_page(page, """() => {
          const name = document.querySelector('#roster-list .roster-name');
          if (!name) return false;
          const style = getComputedStyle(name);
          return style.whiteSpace === 'nowrap' && style.textOverflow === 'ellipsis' && style.lineHeight !== 'normal';
        }""")
        assert page.locator("#roster-list .avatar").count() == len(bots)
        assert page.locator("#roster-list .roster-entry").evaluate_all(
            "rows => rows.every(row => row.querySelectorAll('[data-bot-options]').length === 1 && !row.querySelector('[data-pin-bot], .roster-pin, .roster-settings'))")
        long_name = "Research Companion for Long-Term Vendor Strategy and Operations"
        long_name_row = page.locator("[data-switch-bot='research-helper']")
        long_name_row.evaluate("button => { for (let parent = button.parentElement; parent && parent.id !== 'roster-list'; parent = parent.parentElement) if (parent instanceof HTMLDetailsElement) parent.open = true; }")
        name_label = long_name_row.locator(".roster-name")
        name_label.wait_for(state="visible")
        wait_for_page(page, """() => {
          const el = document.querySelector("[data-switch-bot='research-helper'] .roster-name");
          if (!el) return false;
          const style = getComputedStyle(el);
          return style.whiteSpace === 'nowrap' && style.textOverflow === 'ellipsis' && el.scrollWidth > el.clientWidth;
        }""")
        name_metrics = name_label.evaluate(
            "el => ({text:el.textContent.trim(), fullName:el.closest('[data-switch-bot]').title})")
        assert "monospace" not in page.locator("[data-switch-bot='research-helper'] .roster-sub").evaluate(
            "el => getComputedStyle(el).fontFamily")
        assert name_metrics["text"] == long_name
        assert name_metrics["fullName"].startswith(long_name)
        assert page.locator(".roster-name").evaluate_all(
            "els => els.every(el => getComputedStyle(el).whiteSpace === 'nowrap' && getComputedStyle(el).textOverflow === 'ellipsis')")
        ellipsis = name_label.evaluate("""el => ({
          computed: getComputedStyle(el).getPropertyValue('text-overflow'),
          inline: el.getAttribute('style'),
          stylesheets: [...document.styleSheets].map(sheet => sheet.href),
          rule: [...document.styleSheets].flatMap(sheet => [...(sheet.cssRules || [])])
            .filter(rule => rule.selectorText === '.roster-name').map(rule => rule.cssText)
        })""")
        assert ellipsis["computed"] == "ellipsis", ellipsis
        assert name_label.evaluate("el => el.scrollWidth > el.clientWidth"), (
            "long sidebar names should visibly truncate on one line"
        )
        selected_row = page.locator("#roster-list .roster-entry.is-current")
        selected_row_metrics = selected_row.evaluate("""row => {
          const box = row.getBoundingClientRect();
          const menu = row.querySelector('.roster-options').getBoundingClientRect();
          return {width:box.width, background:getComputedStyle(row).backgroundColor,
                  menuRightGap:Math.abs(box.right-menu.right)};
        }""")
        assert selected_row_metrics["width"] > 220 and selected_row_metrics["menuRightGap"] <= 1, selected_row_metrics
        assert selected_row_metrics["background"] not in {"transparent", "rgba(0, 0, 0, 0)"}, selected_row_metrics
        typical_name_metrics = page.locator("#roster-list .roster-name").evaluate_all(
            "els => els.filter(el => el.textContent.trim() !== 'Research Companion for Long-Term Vendor Strategy and Operations')"
            ".map(el => ({name:el.textContent.trim(), width:el.clientWidth, textWidth:el.scrollWidth}))"
        )
        assert all(item["textWidth"] <= item["width"] + 1 for item in typical_name_metrics), typical_name_metrics

        page.locator("[data-switch-bot='research-helper']").hover()
        page.get_by_role("button", name=f"Options for {long_name}").click()
        menu = page.get_by_role("menu")
        assert menu.get_by_role("menuitem", name="Assistant settings").is_visible()
        menu.get_by_role("menuitem", name="Pin to sidebar").click()
        assert store.get_bot("research-helper").pinned is True
        page.locator("[data-switch-bot='website-auditor']").hover()
        page.locator("[data-bot-options='website-auditor']").click()
        page.get_by_role("menuitem", name="Pin to sidebar").click()
        wait_for_page(page, """() => {
          const names = [...document.querySelectorAll('#roster-list [data-switch-bot]')].map(el => el.dataset.switchBot);
          return names.indexOf('website-auditor') < names.indexOf('agenda-assistant');
        }""")
        assert page.locator("#roster-list [data-switch-bot]").evaluate_all(
            "els => els.map(el => el.dataset.switchBot)") == [
                "workspace-coordinator", "research-helper", "website-auditor", "agenda-assistant", "operations-review"]
        page.locator("[data-switch-bot='workspace-coordinator']").hover()
        page.set_viewport_size({"width": 1440, "height": 960})
        coordinator_options = page.locator("[data-bot-options='workspace-coordinator']")
        coordinator_options.evaluate("el => el.scrollIntoView({block:'nearest'})")
        coordinator_options.click()
        coordinator_menu = page.get_by_role("menu")
        assert coordinator_menu.get_by_role("menuitem", name="Assistant settings").is_visible()
        assert coordinator_menu.get_by_role("menuitem", name="Pin to sidebar").count() == 0
        page.evaluate("renderRoster()")
        assert page.get_by_role("menu").get_by_role("menuitem", name="Assistant settings").is_visible()
        page.keyboard.press("Escape")
        assert page.locator("[data-bot-options='workspace-coordinator']").evaluate("el => el === document.activeElement")

        page.reload()
        page.locator(".ctx-id h1").wait_for()
        if page.locator(".app-shell").evaluate("el => el.classList.contains('collapsed')"):
            page.get_by_role("button", name="Expand sidebar").click()
            page.locator(".roster-name").first.wait_for(state="visible")
        assert store.get_bot("research-helper").pinned is True
        assert store.get_bot("website-auditor").pinned is True
        assert page.locator("#roster-list [data-switch-bot]").evaluate_all(
            "els => els.map(el => el.dataset.switchBot)")[0] == "workspace-coordinator"

        page.locator("#bot-search").fill("Website")
        assert page.locator("#roster-list [data-switch-bot]").evaluate_all(
            "els => els.map(el => el.dataset.switchBot)") == ["website-auditor"]
        page.locator("#bot-search").fill("")

        page.locator("[data-switch-bot='research-helper']").hover()
        page.locator("[data-bot-options='research-helper']").click()
        page.get_by_role("menuitem", name="Remove from pinned").focus()
        page.keyboard.press("Enter")
        wait_for_page(page, "document.activeElement?.dataset?.botOptions === 'research-helper'")
        assert store.get_bot("research-helper").pinned is False

        identity = page.locator("#roster-list .avatar svg").evaluate_all("""svgs => {
          const ids = svgs.flatMap(svg => [...svg.querySelectorAll('[id]')].map(node => node.id));
          return {count: ids.length, shapes: svgs.map(svg => svg.querySelector(':scope > path')?.getAttribute('d')),
                  fills: svgs.map(svg => svg.querySelector('path')?.getAttribute('fill')),
                  eyes: svgs.map(svg => [...svg.querySelectorAll('[data-sigil-eye]')].map(eye => ({
                    shape:eye.getAttribute('data-sigil-eye'),tag:eye.tagName.toLowerCase(),
                    fill:eye.getAttribute('fill') || eye.closest('g')?.getAttribute('fill'),
                    stroke:eye.getAttribute('stroke'),
                    cx:eye.dataset.cx,cy:eye.dataset.cy,rx:eye.dataset.rx,ry:eye.dataset.ry,
                    width:eye.getBBox().width,height:eye.getBBox().height,
                    angle:eye.dataset.angle})))};
        }""")
        assert identity["count"] == 0, "flat app avatars need no shared SVG definition IDs"
        assert len(set(identity["shapes"])) == 5, "name-derived avatars should remain distinguishable"
        assert len(set(identity["fills"])) > 1 and all(len(eyes) == 2 for eyes in identity["eyes"])
        assert all(eye["fill"] == "#0b1511" and eye["stroke"] is None and eye["tag"] == "path"
                   for eyes in identity["eyes"] for eye in eyes)
        assert page.locator("#roster-list .avatar svg [data-sigil-glint]").count() == 0
        assert all(1.0 <= float(eye["height"]) / float(eye["width"]) <= 1.35
                   and -12 <= float(eye.get("angle", 0)) <= 12
                   for eyes in identity["eyes"] for eye in eyes)
        assert all(abs(float(eyes[0].get("angle", 0)) + float(eyes[1].get("angle", 0))) <= 4
                   for eyes in identity["eyes"]), "paired eyes should have a gentle mirrored tilt"
        assert all(abs(float(eyes[0]["cx"]) - float(eyes[1]["cx"])) <= 16
                   for eyes in identity["eyes"]), "paired eyes should read as one compact face"
        assert page.locator("#roster-list .avatar svg [data-sigil-outline]").count() == 0
        assert {eye["shape"] for eyes in identity["eyes"] for eye in eyes} == {"left", "right"}
        assert all(len({(eye["cx"], eye["cy"]) for eye in eyes}) == 2 for eyes in identity["eyes"])

        snapshots = []
        for label, width, height in viewports:
            page.set_viewport_size({"width": width, "height": height})
            mobile_roster_capture = None
            menu_capture = None
            if width > 900 and page.locator(".app-shell").evaluate("el => el.classList.contains('collapsed')"):
                page.get_by_role("button", name="Expand sidebar").click()
                page.locator(".roster-name").first.wait_for(state="visible")
            if width <= 900:
                if not page.locator("#workspace").evaluate("el => el.classList.contains('open')"):
                    page.locator("#nav-toggle").click()
                assert page.locator("#ws-close").is_visible(), "the open mobile roster needs a visible close control"
                page.locator(".roster-name").first.wait_for(state="visible")
                mobile_roster_capture = out / f"{label}-roster.png"
                page.screenshot(path=str(mobile_roster_capture), animations="disabled")
                if width <= 640:
                    assert page.locator("#roster-list [data-switch-bot]").count() == len(bots)
            selected_row = page.locator("[data-switch-bot='research-helper']")
            selected_row.evaluate("button => { for (let parent = button.parentElement; parent; parent = parent.parentElement) if (parent instanceof HTMLDetailsElement) parent.open = true; }")
            selected_row.wait_for(state="visible")
            selected_row.click()
            page.wait_for_url("**/#/chat/research-helper")
            wait_for_page(page, """() => location.hash === '#/chat/research-helper'
              && document.querySelector('.ctx-id h1')?.textContent.includes('Research Companion')""")
            wait_for_page(page, "document.querySelector('[data-switch-bot=\\\"research-helper\\\"]')?.getAttribute('aria-current') === 'true'")
            wait_for_page(page, """() => {
              const button = document.querySelector('#roster-list [data-switch-bot="research-helper"]');
              const entry = button?.closest('.roster-entry');
              const row = entry?.getBoundingClientRect();
              const options = entry?.querySelector('[data-bot-options]')?.getBoundingClientRect();
              const name = button?.querySelector('.roster-name');
              const nameStyle = name && getComputedStyle(name);
              return entry?.isConnected && row?.width > 0 && row.height > 0 && options?.width > 0
                && name?.isConnected && name.getBoundingClientRect().height > 0
                && nameStyle.whiteSpace === 'nowrap' && nameStyle.textOverflow === 'ellipsis';
            }""")
            # Route changes rebuild the roster DOM; re-resolve this button
            # after the destination chat has rendered before reading geometry.
            selected_row = page.locator("#roster-list [data-switch-bot='research-helper']")
            row_evidence = page.evaluate("""() => {
              const button = document.querySelector('#roster-list [data-switch-bot="research-helper"]');
              const entry = button?.closest('.roster-entry');
              const options = entry?.querySelector('[data-bot-options]');
              const name = button?.querySelector('.roster-name');
              const nameStyle = name && getComputedStyle(name);
              const row = button?.getBoundingClientRect();
              const option = options?.getBoundingClientRect();
              const wrapper = entry?.getBoundingClientRect();
              return {
                name: {height:name?.clientHeight, lineHeight:parseFloat(nameStyle?.lineHeight),
                       overflow:nameStyle?.textOverflow, clipped:name?.scrollWidth > name?.clientWidth},
                selection: {current:button?.getAttribute('aria-current'),
                  background:entry && getComputedStyle(entry).backgroundColor,
                  rowRight:row?.right, optionsRight:option?.right, wrapperRight:wrapper?.right,
                  optionsVisible:options && getComputedStyle(options).display !== 'none'}
              };
            }""")
            name_geometry = row_evidence["name"]
            selection_geometry = row_evidence["selection"]
            assert name_geometry["height"] <= name_geometry["lineHeight"] + 1, (label, name_geometry)
            assert name_geometry["overflow"] == "ellipsis", (label, name_geometry)
            assert name_geometry["clipped"], (label, name_geometry)
            assert selection_geometry["current"] == "true", (label, selection_geometry)
            assert selection_geometry["background"] != "rgba(0, 0, 0, 0)", (label, selection_geometry)
            assert selection_geometry["optionsVisible"], (label, selection_geometry)
            assert abs(selection_geometry["wrapperRight"] - selection_geometry["optionsRight"]) <= 3, (
                label, selection_geometry
            )
            assert selection_geometry["rowRight"] < selection_geometry["optionsRight"], (
                label, selection_geometry
            )
            selected_capture = out / f"{label}-selected-row.png"
            page.screenshot(path=str(selected_capture), animations="disabled")
            page.locator("[data-switch-bot='research-helper']").hover()
            page.locator("[data-bot-options='research-helper']").click()
            assert page.get_by_role("menu").get_by_role("menuitem", name="Assistant settings").is_visible()
            menu_capture = out / f"{label}-menu.png"
            page.screenshot(path=str(menu_capture), animations="disabled")
            page.keyboard.press("Escape")
            if width <= 900 and page.locator("#workspace").evaluate("el => el.classList.contains('open')"):
                page.locator("#ws-close").click()
            if width <= 900:
                assert not page.locator("#workspace").evaluate("el => el.classList.contains('open')")
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") == 0, label
            if width <= 640:
                target = page.locator("#roster-list [data-bot-options]").first
                assert target.bounding_box()["height"] >= 44
            page.screenshot(path=str(out / f"{label}.png"), animations="disabled")
            snapshots.append({"size": label, "viewport": [width, height], "horizontal_overflow": 0,
                              "long_name": name_geometry,
                              "selected_row_geometry": selection_geometry,
                              "selected_row_capture": selected_capture.name,
                              "roster_capture": mobile_roster_capture.name if mobile_roster_capture else None,
                              "options_menu_capture": menu_capture.name})

        assert not errors, errors
        outside_requests = [url for url in requests if urlsplit(url).netloc not in {urlsplit(base).netloc, ""}]
        assert not outside_requests, outside_requests
        (out / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_bot_roster_pins_persist_and_simple_mascots_stay_distinct",
            "command": ".venv/bin/pytest -q tests/e2e/test_browser.py::test_bot_roster_pins_persist_and_simple_mascots_stay_distinct",
            "browser": browser.version, "playwright": package_version("playwright"),
            "fixture_only": True, "provider_calls": 0, "external_requests": len(outside_requests), "page_errors": errors,
            "typical_names": typical_name_metrics,
            "viewports": snapshots,
            "verified": ["one options button per Bot; pin and settings actions share its menu", "pin persists after reload", "coordinator stays first and cannot be pinned",
                         "search includes pinned bots", "keyboard activation and Escape restore focus", "long names truncate with an ellipsis on one line while full names remain available in the title",
                         "mobile roster has a visible close control", "phone roster reopens with all Bots visible", "phone menu target is at least 44px",
                         "flat 2D identities use distinct silhouettes, colors, and balanced shape-fitted ink eyes"],
            "avatar_svg_ids": identity["count"], "source_sha256": {
                relative: hashlib.sha256((Path(__file__).resolve().parents[2] / relative).read_bytes()).hexdigest()
                for relative in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                 "src/hutch/server/app.py", "tests/e2e/test_browser.py")},
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        try:
            context.tracing.stop(path=str(out / "trace.zip"))
        except Exception:
            pass
        context.close()


def test_large_idle_roster_stays_compact_and_remains_searchable_and_keyboard_accessible(browser, live):
    base, app = live
    store = app.state.store
    bots = [Bot(name="workspace-coordinator", display_name="Workspace Coordinator", model="mock/demo", tools=[])]
    bots.extend(Bot(name=f"release-helper-{index}", display_name=f"Release Helper {index}", model="mock/demo", tools=[])
                for index in range(9))
    for bot in bots:
        store.create_bot(bot)
    store.set_workspace_coordinator("workspace-coordinator")
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/compact-roster"
    out.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    page.set_default_timeout(8000)
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        page.goto(f"{base}/#/chat/workspace-coordinator")
        page.locator(".ctx-id h1").wait_for()
        detail = page.locator("#roster-idle-details")
        summary = detail.locator(":scope > summary")
        assert not detail.evaluate("el => el.open")
        assert "9" in summary.inner_text()
        assert page.locator("#roster-list [data-switch-bot]:visible").count() == 1
        page.screenshot(path=str(out / "collapsed-desktop.png"), animations="disabled")

        summary.focus()
        page.keyboard.press("Enter")
        wait_for_page(page, "document.querySelector('#roster-idle-details')?.open === true")
        assert page.locator("#roster-list [data-switch-bot]:visible").count() == 10
        page.keyboard.press("Enter")
        wait_for_page(page, "document.querySelector('#roster-idle-details')?.open === false")
        page.locator("#bot-search").fill("Release Helper 7")
        assert page.locator("#roster-list [data-switch-bot]").evaluate_all("els => els.map(el => el.dataset.switchBot)") == ["release-helper-7"]
        page.locator("#bot-search").fill("")
        assert not detail.evaluate("el => el.open"), "search should not silently expand the saved roster"

        screenshots = []
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            if width <= 900:
                page.locator("#nav-toggle").click()
                assert page.locator("#workspace").evaluate("el => el.classList.contains('open')")
            assert page.locator("#roster-idle-details").is_visible()
            assert not detail.evaluate("el => el.open")
            assert page.evaluate("document.documentElement.scrollWidth-innerWidth") <= 1
            page.screenshot(path=str(out / f"collapsed-{label}.png"), animations="disabled")
            screenshots.append({"size": label, "viewport": [width, height], "idle_list_collapsed": True,
                                "horizontal_overflow": 0})
            if width <= 900:
                page.locator("#ws-close").click()

        if browser.browser_type.name == "chromium":
            page.set_viewport_size({"width": 1440, "height": 960})
            page.locator("#workspace").evaluate("el => el.classList.remove('open')")
            page.reload()
            page.locator("#conversation-switcher").wait_for()
            page.locator("#roster-idle-details").evaluate("el => el.open = true")
            action = page.locator("[data-bot-options='release-helper-0']")
            assert page.evaluate("matchMedia('(hover:hover) and (pointer:fine)').matches")
            assert action.evaluate("el => getComputedStyle(el).opacity") == "0.62"
            action.click()
            menu = page.locator("#roster-action-menu")
            assert menu.is_visible()
            assert menu.get_by_role("menuitem", name="Pin to sidebar").is_visible()
            page.keyboard.press("Escape")
            assert not menu.is_visible()
            assert action.evaluate("el => el === document.activeElement")
            page.locator("[data-switch-bot='release-helper-0']").hover()
            assert action.evaluate("el => getComputedStyle(el).opacity") == "1"

        assert not errors, errors
        (out / "validation.json").write_text(json.dumps({
            "command": "uv run pytest -q tests/e2e/test_browser.py::test_large_idle_roster_stays_compact_and_remains_searchable_and_keyboard_accessible",
            "browser": browser.browser_type.name, "browser_version": browser.version,
            "playwright_version": package_version("playwright"), "viewports": screenshots,
            "bots": 10, "initial_visible_bots": 1, "all_bots_keyboard_expansion": True,
            "search_keeps_full_roster_reachable": True,
            "desktop_options_control_visible_at_rest_and_emphasized_on_hover": browser.browser_type.name == "chromium",
            "page_errors": errors, "provider_calls": 0,
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        try:
            context.tracing.stop(path=str(out / "trace.zip"))
        except Exception:
            pass
        context.close()


def test_bot_sidebar_menu_supports_recoverable_hide_and_named_sections(browser, live):
    """Rare roster organization stays in one menu, and hidden Bots remain findable and recoverable."""
    base, app = live
    store = app.state.store
    bots = [
        Bot(name="workspace-coordinator", display_name="Workspace Coordinator", model="mock/demo", tools=[]),
        Bot(name="client-research", display_name="Client Research", model="mock/demo", tools=[]),
        Bot(name="release-reviewer", display_name="Release Reviewer", model="mock/demo", tools=[]),
    ]
    for bot in bots:
        store.create_bot(bot)
    store.set_workspace_coordinator("workspace-coordinator")

    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/bot-chat-options"
    out.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    page.set_default_timeout(8000)
    errors: list[str] = []
    external: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external.append(request.url)
            if urlsplit(request.url).netloc not in {urlsplit(base).netloc, ""} else None)
    try:
        page.goto(f"{base}/#/chat")
        page.locator(".ctx-id h1").wait_for()
        page.locator("[data-bot-options='client-research']").click()
        menu = page.get_by_role("menu")
        menu.get_by_role("menuitem", name="New section").click()
        dialog = page.get_by_role("dialog", name="New section")
        dialog.get_by_label("Section name").fill("Client work")
        dialog.get_by_role("button", name="Save section").click()
        page.locator("[data-roster-section='Client work'] summary").wait_for()
        assert store.get_bot("client-research").roster_section == "Client work"
        page.screenshot(path=str(out / "section-desktop.png"), animations="disabled")
        page.locator("[data-roster-section='Client work'] summary").click()

        page.locator("[data-bot-options='client-research']").click()
        page.get_by_role("menuitem", name="Hide from sidebar").click()
        page.locator("#roster-hidden-details summary").wait_for()
        assert store.get_bot("client-research").sidebar_hidden is True
        hidden = page.locator("#roster-list #roster-hidden-details")
        hidden.locator("summary").click()
        assert page.locator("#roster-list [data-switch-bot='client-research']").is_visible()
        assert "schedules continue" in hidden.inner_text().lower()
        page.screenshot(path=str(out / "hidden-desktop.png"), animations="disabled")

        page.locator("[data-bot-options='client-research']").click()
        page.get_by_role("menuitem", name="Show in sidebar").click()
        page.locator("[data-roster-section='Client work'] summary").wait_for()
        assert store.get_bot("client-research").sidebar_hidden is False
        section = page.locator("[data-roster-section='Client work']")
        if not section.evaluate("el => el.open"):
            section.locator("summary").click()
        assert section.locator("[data-switch-bot='client-research']").is_visible()
        assert store.get_bot("client-research").roster_section == "Client work"

        page.reload()
        page.locator(".ctx-id h1").wait_for()
        section = page.locator("[data-roster-section='Client work']")
        if not section.evaluate("el => el.open"):
            section.locator("summary").click()
        assert page.locator("[data-roster-section='Client work'] [data-switch-bot='client-research']").is_visible()

        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            if width <= 900 and page.locator("#ws-close").is_hidden():
                page.locator("#nav-toggle").click()
            page.locator("[data-bot-options='client-research']").click()
            assert page.get_by_role("menu").get_by_role("menuitem", name="Hide from sidebar").is_visible()
            page.screenshot(path=str(out / f"menu-{label}.png"), animations="disabled")
            page.keyboard.press("Escape")
            if width <= 900 and page.locator("#ws-close").is_visible():
                page.locator("#ws-close").click()
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") == 0, label

        page.set_viewport_size({"width": 1440, "height": 960})
        coordinator_options = page.locator("[data-bot-options='workspace-coordinator']")
        coordinator_options.evaluate("el => el.scrollIntoView({block:'nearest'})")
        coordinator_options.click()
        coordinator_menu = page.get_by_role("menu")
        assert coordinator_menu.get_by_role("menuitem", name="Hide from sidebar").count() == 0
        assert coordinator_menu.get_by_role("menuitem", name="New section").count() == 0
        page.keyboard.press("Escape")
        assert store.get_bot("workspace-coordinator").sidebar_hidden is False
        assert not errors, errors
        assert not external, external
        (out / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_bot_sidebar_menu_supports_recoverable_hide_and_named_sections",
            "command": ".venv/bin/pytest -q tests/e2e/test_browser.py::test_bot_sidebar_menu_supports_recoverable_hide_and_named_sections",
            "browser": browser.version, "playwright": package_version("playwright"),
            "fixture_only": True, "provider_calls": 0, "external_requests": external, "page_errors": errors,
            "viewports": [[1440, 960], [900, 1024], [390, 844]],
            "verified": ["one Bot options menu includes pin/settings/organization actions", "section assignment persists across reload",
                         "hidden Bots remain recoverable and section assignment is retained", "hiding does not pause execution or schedules",
                         "workspace coordinator remains visible and cannot be grouped", "phone and tablet menus fit without horizontal overflow"],
            "source_sha256": {relative: hashlib.sha256((Path(__file__).resolve().parents[2] / relative).read_bytes()).hexdigest()
                              for relative in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                               "src/hutch/server/app.py", "src/hutch/models.py")},
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        context.close()


def test_duplicate_bot_starts_from_safe_editable_setup_without_copying_authority(browser, live, monkeypatch):
    """A Bot can seed a new setup draft without copying tools, schedules, memory, or its workspace."""
    base, app = live
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key-never-sent-to-a-provider")
    source = Bot(name="release-reviewer", display_name="Release Notes Reviewer", model="openai/gpt-4o-mini",
                 tools=["read_file", "write_file", "remember"], memory_enabled=True,
                 instructions="Review release notes and prepare a short project summary.",
                 description="Review and summarize project releases.", workspace_mode="folder",
                 workdir="/private/source/project", base_url="https://private-provider.example/v1",
                 local_browser_handoff=True,
                 schedule=Schedule(cron="0 9 * * 1", timezone="America/Vancouver",
                                   prompt="Review the latest release notes."))
    app.state.store.create_bot(source)
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/bot-chat-options"
    out.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    page.set_default_timeout(8000)
    errors: list[str] = []
    requests: list[str] = []
    create_payloads: list[dict] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: requests.append(request.url))
    page.on("request", lambda request: create_payloads.append(request.post_data_json)
            if request.url.endswith("/api/v1/bots") and request.method == "POST" else None)
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        page.goto(f"{base}/#/chat/{source.name}")
        page.locator("[data-bot-options='release-reviewer']").click()
        page.get_by_role("menuitem", name="Duplicate bot").click()
        page.get_by_role("heading", name="Set up your assistant").wait_for()
        assert page.get_by_label("Assistant name").input_value() == "Release Notes Reviewer copy"
        name_input = page.get_by_label("Assistant name")
        name_style = name_input.evaluate("el => ({borderStyle:getComputedStyle(el).borderStyle, borderWidth:getComputedStyle(el).borderWidth, background:getComputedStyle(el).backgroundColor})")
        assert name_style["borderStyle"] == "solid" and name_style["borderWidth"] == "1px", name_style
        assert name_style["background"] != "rgba(0, 0, 0, 0)", name_style
        assert "Review release notes and prepare a short project summary." in page.locator("#setup-purpose").input_value()
        note = page.locator(".setup-duplicate-note")
        note.wait_for()
        assert "not copied" in note.inner_text()
        assert app.state.store.get_bot("release-reviewer-copy") is None

        captures = []
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            page.screenshot(path=str(out / f"duplicate-setup-{label}.png"), animations="disabled")
            metrics = page.evaluate("""() => ({viewport:[innerWidth,innerHeight], overflow:document.documentElement.scrollWidth-innerWidth,
                footer:document.querySelector('.modal-footer').getBoundingClientRect().bottom,
                dialog:document.querySelector('[role=dialog]').getBoundingClientRect().toJSON()})""")
            assert metrics["overflow"] <= 1 and metrics["footer"] <= height + 1, (label, metrics)
            assert metrics["dialog"]["left"] >= -1 and metrics["dialog"]["right"] <= width + 1, (label, metrics)
            captures.append({"viewport": [width, height], "overflow_px": metrics["overflow"], "footer_visible": True})

        page.set_viewport_size({"width": 390, "height": 844})
        page.locator("#modal-confirm").click()
        page.get_by_role("heading", name="Choose what powers it").wait_for()
        assert page.get_by_label("Model route").input_value() == source.model
        assert page.locator("#setup-workspace_mode").input_value() == "managed"
        page.locator("#modal-confirm").click()
        page.get_by_role("heading", name="Choose its apps").wait_for()
        assert page.locator("#setup-tools input:checked").count() == 0
        page.locator("#modal-confirm").click()
        page.get_by_role("heading", name="Review and create").wait_for()
        review = page.locator(".setup-review").inner_text()
        assert "managed" in review.lower() and "no tools enabled" in review.lower()
        assert "Recurring task\nNone" in review and "Memory\nDisabled" in review
        assert app.state.store.get_bot("release-reviewer-copy") is None
        assert app.state.store.list_runs() == []
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            page.locator(".setup-review-list").scroll_into_view_if_needed()
            page.screenshot(path=str(out / f"duplicate-review-{label}.png"), animations="disabled")
            metrics = page.evaluate("""() => ({overflow:document.documentElement.scrollWidth-innerWidth,
                bodyOverflow:document.querySelector('.modal-body').scrollWidth-document.querySelector('.modal-body').clientWidth,
                footer:document.querySelector('.modal-footer').getBoundingClientRect().bottom})""")
            assert metrics["overflow"] <= 1 and metrics["bodyOverflow"] <= 1 and metrics["footer"] <= height + 1, (label, metrics)
        with page.expect_response(lambda response: response.url.endswith("/api/v1/bots")
                                 and response.request.method == "POST") as created:
            page.locator("#modal-confirm").click()
        assert created.value.status == 201, created.value.text()
        duplicate = app.state.store.get_bot(created.value.json()["name"])
        assert duplicate is not None
        assert duplicate.instructions == source.instructions and duplicate.model == source.model
        assert duplicate.workspace_mode == "managed" and duplicate.workdir is None and duplicate.base_url is None
        assert duplicate.tools == [] and not duplicate.memory_enabled and duplicate.schedule is None
        assert not duplicate.local_browser_handoff and app.state.store.list_runs() == []
        assert create_payloads and "base_url" not in create_payloads[-1] and "workdir" not in create_payloads[-1]
        assert not errors and all(url.startswith(base) for url in requests), (errors, requests)
        (out / "duplicate-validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_duplicate_bot_starts_from_safe_editable_setup_without_copying_authority",
            "command": ".venv/bin/pytest -q tests/e2e/test_browser.py::test_duplicate_bot_starts_from_safe_editable_setup_without_copying_authority",
            "browser": browser.version, "playwright_version": package_version("playwright"),
            "viewports": captures, "fixture_only": True, "provider_calls": 0, "external_requests": 0,
            "copied": ["standing instructions", "model route", "inference mode", "execution limits", "editable name"],
            "not_copied": ["enabled tools", "connected accounts", "custom provider URL", "local folder", "schedule", "memory values", "chat history", "browser handoff"],
            "page_errors": errors,
            "source_sha256": {name: hashlib.sha256((Path(__file__).resolve().parents[2] / name).read_bytes()).hexdigest()
                              for name in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                           "src/hutch/server/app.py", "src/hutch/store.py")},
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        try:
            context.tracing.stop(path=str(out / "duplicate-trace.zip"))
        except Exception:
            pass
        context.close()


def test_purpose_derived_bot_name_is_editable_and_reviewed_at_responsive_sizes(browser, live, monkeypatch):
    base, app = live
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key-never-sent-to-a-provider")
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/bot-naming-quality"
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
        first_request = "Track the launch checklist and notify me when a blocker needs attention."
        occupied_name = page.evaluate("purpose => suggestBotDisplayName(purpose, [])", first_request)
        occupied_name = occupied_name.split(" · ", 1)[0]
        expected_role = "Launch Checklist Monitor"
        app.state.store.create_bot(Bot(name="occupied-name", display_name=occupied_name,
                                       description=expected_role, model="mock/demo", tools=[]))
        page.reload()
        page.locator("#roster-list [data-switch-bot]").wait_for()
        expected_person = occupied_name
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            page.locator(".ctx-subtitle").wait_for(state="visible")
            assert page.locator(".ctx-id h1").inner_text() == expected_person
            assert page.locator(".ctx-subtitle").inner_text() == f"AI assistant · {expected_role}"
            roster_name = page.locator('#roster-list [data-switch-bot="occupied-name"] .roster-name')
            assert roster_name.inner_text() == expected_person
            assert page.locator('#roster-list [data-switch-bot="occupied-name"] .roster-sub').inner_text() == expected_role
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1, label
            page.screenshot(path=str(out / f"chat-identity-{label}.png"), animations="disabled")
        page.goto(f"{base}/#/bot/occupied-name")
        page.locator(".ctx-id h1").wait_for()
        assert page.locator(".ctx-id h1").inner_text() == expected_person
        assert page.locator(".ctx-subtitle").inner_text() == "Assistant settings · Launch Checklist Monitor"
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1, label
            page.screenshot(path=str(out / f"settings-identity-{label}.png"), animations="disabled")
        page.goto(f"{base}/#/chat/occupied-name")
        page.locator(".ctx-id h1").wait_for()
        page.set_viewport_size({"width": 1440, "height": 960})
        page.locator("#topbar-new-bot").click()
        display_name = page.locator("#setup-display_name")
        display_name.wait_for(state="visible")
        assert page.get_by_text("Suggested from your request", exact=False).is_visible()
        purpose = page.locator("#setup-purpose")
        if not purpose.is_visible():
            page.locator("#setup-use-source").uncheck()
        assert purpose.is_visible()
        purpose.fill(first_request)
        address = page.locator("#setup-name")
        page.locator(".setup-identity summary").click()
        description = page.locator("#setup-description")
        page.locator(".setup-identity summary").click()

        def assert_identity(role: str, local_address: str) -> str:
            identity = display_name.input_value()
            assert re.fullmatch(r"[A-Z][a-z]+ [A-Z][a-z]+", identity)
            assert " · " not in identity
            assert description.input_value() == role
            assert address.input_value() == local_address
            return identity

        first_identity = assert_identity("Launch Checklist Monitor", "launch-checklist-monitor")
        assert first_identity != occupied_name
        purpose.fill("Track my follow-up tasks from each meeting and remind me when anything is overdue.")
        assert_identity("Follow-up Task Monitor", "follow-up-task-monitor")
        purpose.fill("Organize my receipts into monthly folders and tell me when one is missing.")
        assert_identity("Receipt Organizer", "receipt-organizer")
        purpose.fill("Remind me to renew my passport next month.")
        assert_identity("Passport Renewal Reminder", "passport-renewal-reminder")
        purpose.fill("Alert me when an invoice is overdue.")
        assert_identity("Invoice Reminder", "invoice-reminder")
        purpose.fill("File my monthly expense receipts into folders every Friday.")
        assert_identity("Expense Receipt Organizer", "expense-receipt-organizer")
        purpose.fill("Coordinate work across my bots and keep me updated.")
        assert_identity("Workspace Coordinator", "workspace-coordinator")
        purpose.fill("Create a weekly project status update for leadership.")
        assert_identity("Project Status Reporter", "project-status-reporter")
        purpose.fill("I need a bot that prepares weekly project status updates for my leadership team.")
        assert_identity("Project Status Reporter", "project-status-reporter")
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            page.screenshot(path=str(out / f"automatic-name-{label}.png"), animations="disabled")
            metrics = page.evaluate("""() => ({viewport:[innerWidth,innerHeight],
              documentWidth:document.documentElement.scrollWidth,
              bodyOverflow:document.querySelector('.modal-body').scrollWidth-document.querySelector('.modal-body').clientWidth})""")
            assert metrics["documentWidth"] - width <= 1 and metrics["bodyOverflow"] <= 1, (label, metrics)
        page.set_viewport_size({"width": 1440, "height": 960})
        purpose.fill("Review release notes for changes affecting our project.")
        assert_identity("Release Notes Reviewer", "release-notes-reviewer")

        page.locator(".setup-identity summary").click()
        description.fill("A note I wrote myself")
        purpose.fill("Review monthly security alerts for my team.")
        assert display_name.input_value() != ""
        assert description.input_value() == "A note I wrote myself"
        assert address.input_value() == "security-alerts-reviewer"

        display_name.fill("Launch Readiness Analyst")
        assert address.input_value() == "security-alerts-reviewer"
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

        page.locator("#setup-name").scroll_into_view_if_needed()
        address_visibility = page.evaluate("""() => {
          const address = document.querySelector('#setup-name').getBoundingClientRect();
          const footer = document.querySelector('.modal-footer').getBoundingClientRect();
          return {addressTop:address.top,addressBottom:address.bottom,footerTop:footer.top,
            viewport:[innerWidth,innerHeight]};
        }""")
        assert address_visibility["addressBottom"] <= address_visibility["footerTop"] + 1, address_visibility
        page.screenshot(path=str(out / "identity-phone-address-visible.png"), animations="disabled")

        page.locator("#modal-confirm").click()
        page.get_by_label("Model route").fill("openai/gpt-4o-mini")
        page.locator("#modal-confirm").click()
        page.locator("#modal-confirm").click()
        page.get_by_role("heading", name="Review and create").wait_for()
        review = page.locator(".setup-review-list").inner_text()
        assert "Launch Readiness Analyst" in review and "A note I wrote myself" in review and "launch-ops" in review
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
        assert bot.description == "A note I wrote myself"
        assert bot.instructions == "Review monthly security alerts for my team."
        assert app.state.store.list_runs() == []
        assert not any("/chat/completions" in url or "/responses" in url for url in requests)
        page.locator(".ctx-id h1").wait_for()
        assert page.locator(".ctx-id h1").inner_text() == "Launch Readiness Analyst"
        assert page.locator(".ctx-subtitle").inner_text() == "AI assistant · A note I wrote myself"
        if page.locator(".toast-close").count():
            page.locator(".toast-close").last.click()
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            page.screenshot(path=str(out / f"chat-{label}.png"), animations="disabled")
            metrics = page.evaluate("""() => ({viewport:[innerWidth,innerHeight],
              documentWidth:document.documentElement.scrollWidth, headingVisible:!!document.querySelector('.ctx-id h1')})""")
            assert metrics["documentWidth"] - width <= 1 and metrics["headingVisible"], (label, metrics)
        for index in range(8):
            app.state.store.create_bot(Bot(
                name=f"roster-helper-{index}",
                display_name="Quarterly Cross-functional Project Research and Reporting Assistant " + str(index),
                description="Supports a shared team workflow.", model="mock/demo", tools=[]))
        page.goto(f"{base}/#/bots")
        page.get_by_role("heading", name="Manage assistants").wait_for()
        card = page.locator('[data-fleet-bot="occupied-name"]')
        assert card.locator(".bot-name").inner_text() == expected_person
        assert card.locator(".bot-desc").inner_text() == expected_role
        long_name = page.locator('[data-fleet-bot="roster-helper-0"] .bot-name')
        assert long_name.evaluate("element => getComputedStyle(element).whiteSpace") == "nowrap"
        assert long_name.evaluate("element => getComputedStyle(element).textOverflow") == "ellipsis"
        assert long_name.get_attribute("title").startswith("Quarterly Cross-functional")
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1, label
            page.screenshot(path=str(out / f"fleet-identity-{label}.png"), animations="disabled")
        assert not errors, errors
        (out / "validation.json").write_text(json.dumps({
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_purpose_derived_bot_name_is_editable_and_reviewed_at_responsive_sizes",
            "browser": browser.browser_type.name, "browser_version": browser.version,
            "playwright_version": package_version("playwright"),
            "viewports": {"desktop": [1440, 960], "tablet": [900, 1024], "phone": [390, 844]},
            "scenario": "purpose-derived short teammate names keep inferred task roles in descriptions and headers; role names preserve follow-up compounds, trim secondary/time/status clauses, normalize reminder actions and receipt nouns, and identify the workspace coordinator; local addresses follow roles independently of custom display names; the owner can edit either value; chat, settings, roster, and ten-assistant management views keep names on one line with long-name ellipses; no provider request occurs",
            "inspected_screenshots": [f"chat-identity-{size}.png" for size in ("desktop", "tablet", "phone")]
                                     + [f"automatic-name-{size}.png" for size in ("desktop", "tablet", "phone")]
                                     + [f"settings-identity-{size}.png" for size in ("desktop", "tablet", "phone")]
                                     + [f"fleet-identity-{size}.png" for size in ("desktop", "tablet", "phone")]
                                     + [f"identity-{size}.png" for size in ("desktop", "tablet", "phone")]
                                     + ["identity-phone-address-visible.png"]
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


def test_bot_creation_reuses_only_the_selected_chat_messages_and_keeps_provenance(browser, live, monkeypatch):
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
        context_request = "Use public-facing launch notes only; do not contact stakeholders."
        store._insert_conversation_message(db, message_id="chat-context-prior-constraint", conversation_id=conversation["id"],
            seq=3, run_id="", role="user", content=context_request, created_at=conversation["created_at"])
        store._insert_conversation_message(db, message_id="chat-context-current-request", conversation_id=conversation["id"],
            seq=4, run_id="", role="user", content=source_request, created_at=conversation["created_at"])

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
        page.get_by_role("heading", name="Create from this request").wait_for()
        source_toggle = page.locator("#setup-use-source")
        assert source_toggle.is_checked()
        purpose = page.locator("#setup-purpose")
        assert purpose.input_value() == source_request
        assert not purpose.is_visible()
        page.locator("#setup-purpose-editor > summary").click()
        assert purpose.is_visible()
        assert "private payroll" not in purpose.input_value().lower()
        source_toggle.uncheck()
        assert purpose.input_value() == ""
        source_toggle.check()
        assert not purpose.is_visible()
        page.locator("#setup-purpose-editor > summary").click()
        purpose.fill("Track the launch checklist; notify me when a blocker needs attention.")
        assert re.fullmatch(r"[A-Z][a-z]+ [A-Z][a-z]+", page.locator("#setup-display_name").input_value())
        page.locator(".setup-identity summary").click()
        assert page.locator("#setup-description").input_value() == "Launch Checklist Monitor"
        page.set_viewport_size({"width": 390, "height": 844})
        page.locator("#setup-display_name").fill("Launch Checklist Monitor")
        page.locator("#setup-name").fill("launch-checklist")
        page.locator("#setup-customize").click()
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

        page.locator("#setup-back").click()
        page.get_by_role("heading", name="Set up your assistant").wait_for()
        context_picker = page.locator("#setup-context-picker")
        assert context_picker.is_visible()
        context_picker.locator(":scope > summary").click()
        prior_constraint = page.locator('[data-setup-context-message="chat-context-prior-constraint"]')
        private_context = page.locator('[data-setup-context-message="chat-context-private-old"]')
        assert prior_constraint.is_visible() and not prior_constraint.is_checked()
        assert private_context.is_visible() and not private_context.is_checked()
        assert "public-facing launch notes" in context_picker.inner_text().lower()
        prior_constraint.check()
        assert "1 message selected" in page.locator("#setup-context-count").inner_text().lower()

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
            page.screenshot(path=str(out / f"chat-source-context-{label}.png"), animations="disabled")

        page.locator("#modal-confirm").click()
        page.get_by_role("heading", name="Choose what powers it").wait_for()
        page.set_viewport_size({"width": 390, "height": 844})
        page.locator("#modal-confirm").click()
        page.get_by_role("heading", name="Choose its apps").wait_for()
        page.locator("#modal-confirm").click()
        page.get_by_role("heading", name="Review and create").wait_for()
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            page.locator(".setup-source-details").first.locator(":scope > summary").click()
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
            if label != "phone": page.locator(".setup-source-details").first.locator(":scope > summary").click()

        assert "chat-context-source · Launch planning · message 4" in page.locator(".setup-review-list").inner_text()
        context_review = page.locator(".setup-review-list > div").filter(has_text="Earlier chat context")
        context_review.locator("details summary").click()
        assert page.get_by_text(context_request, exact=True).is_visible()
        assert "saved bot instructions" in page.locator(".setup-review-list").inner_text().lower()
        page.set_viewport_size({"width": 390, "height": 844})
        context_review.scroll_into_view_if_needed()
        context_box = context_review.bounding_box()
        footer_box = page.locator(".modal-footer").bounding_box()
        assert context_box["y"] + context_box["height"] <= footer_box["y"]
        page.screenshot(path=str(out / "chat-source-review-context-phone.png"), animations="disabled")
        assert "will not start a run" in page.locator(".modal-body").inner_text().lower()
        assert store.list_runs() == []
        with page.expect_response(lambda response: response.url.endswith("/api/v1/bots")
                                 and response.request.method == "POST") as created:
            page.locator("#modal-confirm").click()
        assert created.value.status == 201, created.value.text()
        bot = store.get_bot("launch-checklist")
        assert bot and bot.instructions.startswith("Track the launch checklist; notify me when a blocker needs attention.")
        assert "Use public-facing launch notes only; do not contact stakeholders." in bot.instructions
        assert bot.creation_context_sources[0].message_id == "chat-context-prior-constraint"
        assert bot.creation_source and bot.creation_source.model_dump() == {
            "conversation_id": conversation["id"], "message_id": "chat-context-current-request",
            "source_bot_id": source_bot.id, "sequence": 4, "created_at": conversation["created_at"],
            "original_request": source_request,
        }
        assert store.list_runs() == []
        assert not errors, errors
        (out / "validation.json").write_text(json.dumps({
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_bot_creation_reuses_only_the_selected_chat_messages_and_keeps_provenance",
            "browser": browser.browser_type.name, "browser_version": browser.version,
            "playwright_version": package_version("playwright"),
            "scenario": "latest user message seeds an editable Bot draft; only explicitly selected earlier same-chat user messages are included as saved background; assistant/private unrelated turns are excluded; provenance persists; creation starts no run; no model call",
            "viewports": {"desktop": [1440, 960], "tablet": [900, 1024], "phone": [390, 844]},
            "screenshots": [f"chat-source-{state}-{size}.png" for state in ("purpose", "context", "model", "review")
                            for size in ("desktop", "tablet", "phone")] + ["chat-source-review-context-phone.png"],
            "page_errors": errors,
            "source_sha256": {relative: hashlib.sha256((Path(__file__).resolve().parents[2] / relative).read_bytes()).hexdigest()
                              for relative in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                               "src/hutch/server/app.py", "src/hutch/models.py", "src/hutch/estimate.py",
                                               "src/hutch/store.py", "tests/test_api.py", "tests/e2e/test_browser.py")},
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        try: context.tracing.stop(path=str(out / "trace.zip"))
        except Exception: pass
        context.close()


def test_user_can_start_bot_setup_from_the_exact_chat_request(browser, live, monkeypatch):
    """A selected request becomes Bot instructions; the user creates it without retyping or starting a run."""
    import hashlib
    from pathlib import Path

    base, app = live
    monkeypatch.setattr(app.state.engine, "tick", lambda: None)
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key-never-sent-to-a-provider")
    store = app.state.store
    bot = store.create_bot(Bot(name="request-source", display_name="Project Partner", model="mock/demo", tools=[]))
    conversation, _ = store.create_conversation(bot.id, "Project planning", idem_key="request-source-conversation",
                                                request_hash="request-source-conversation")
    selected_request = "Review the supplier proposals and recommend the strongest fit for our rollout."
    later_request = "Separately, remind me to book a dentist appointment next month."
    first_run = Run(bot_id=bot.id, prompt=selected_request, conversation_id=conversation["id"], status=RunStatus.succeeded)
    store.create_run(first_run)
    with store._tx() as db:
        db.execute("INSERT INTO conversation_runs (conversation_id, run_id, attached_at) VALUES (?, ?, ?)",
                   (conversation["id"], first_run.id, first_run.created_at))
        store._insert_conversation_message(db, message_id="selected-request-message", conversation_id=conversation["id"],
            seq=1, run_id=first_run.id, role="user", content=selected_request, created_at=first_run.created_at)
    store.append_event(Event(run_id=first_run.id, type=EventType.message,
        data={"role": "assistant", "content": "I compared the supplier proposals."}))
    store.flush_events()
    second_run = Run(bot_id=bot.id, prompt=later_request, conversation_id=conversation["id"], status=RunStatus.succeeded)
    store.create_run(second_run)
    with store._tx() as db:
        db.execute("INSERT INTO conversation_runs (conversation_id, run_id, attached_at) VALUES (?, ?, ?)",
                   (conversation["id"], second_run.id, second_run.created_at))
        store._insert_conversation_message(db, message_id="later-request-message", conversation_id=conversation["id"],
            seq=3, run_id=second_run.id, role="user", content=later_request, created_at=second_run.created_at)
    store.append_event(Event(run_id=second_run.id, type=EventType.message,
        data={"role": "assistant", "content": "I can help with that separately."}))
    store.flush_events()
    bot_count_before = len(store.list_bots())
    run_count_before = len(store.list_runs(limit=100))
    configured = store.kv_get("workspace:model-defaults")
    assert configured is None

    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/bot-from-message"
    out.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    page.set_default_timeout(8000)
    errors, external = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external.append(request.url) if not request.url.startswith(base) else None)
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    touch_context = None
    try:
        response = page.request.put(f"{base}/api/v1/preferences/model-defaults", data={
            "model": "openai/gpt-4o-mini", "inference_mode": "hybrid",
        })
        assert response.status == 200, response.text()
        page.goto(f"{base}/#/chat/{bot.name}")
        action = page.locator('[data-create-bot-from-request="selected-request-message"]')
        action.wait_for(state="visible")
        assert action.get_attribute("aria-label") == "Create a bot from this request"
        action.focus()
        page.keyboard.press("Enter")
        page.get_by_role("heading", name="Create from this request").wait_for(state="visible")
        assert page.locator("#setup-use-source").is_checked()
        assert page.locator("#setup-purpose").input_value() == selected_request
        assert not page.locator("#setup-purpose").is_visible(), "the selected request is already the instruction; editing stays optional"
        assert "Use this request as the Bot’s instructions" in page.locator(".setup-context-source").inner_text()
        assert "no need to enter it again" in page.locator(".bot-setup").inner_text().lower()
        assert page.locator("#setup-display_name").input_value()
        assert page.locator(".setup-quick-summary").is_visible()
        assert page.locator("#modal-confirm").inner_text() == "Create bot"
        assert page.locator('[data-setup-context-message="later-request-message"]').count() == 0
        assert later_request not in page.locator(".bot-setup").inner_text()
        assert "message 1" in page.locator(".bot-setup").inner_text()
        action_target = action.bounding_box()
        assert action_target and action_target["height"] >= 32
        captures = []
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            metrics = page.evaluate("""() => ({width:document.documentElement.scrollWidth, viewport:innerWidth,
              dialog:document.querySelector('[role=dialog]').getBoundingClientRect().toJSON(),
              footer:document.querySelector('.modal-footer').getBoundingClientRect().toJSON(),
              name:document.querySelector('#setup-display_name').getBoundingClientRect().toJSON(),
              summary:document.querySelector('.setup-quick-summary').getBoundingClientRect().toJSON()})""")
            assert metrics["width"] - width <= 1, (label, metrics)
            assert metrics["dialog"]["left"] >= -1 and metrics["dialog"]["right"] <= width + 1, (label, metrics)
            assert metrics["footer"]["bottom"] <= height + 1, (label, metrics)
            assert metrics["name"]["bottom"] <= metrics["footer"]["top"] + 1, (label, metrics)
            assert metrics["summary"]["bottom"] <= metrics["footer"]["top"] + 1, (label, metrics)
            page.screenshot(path=str(out / f"selected-request-{label}.png"), animations="disabled")
            captures.append({"size": label, "viewport": [width, height], "horizontal_overflow": metrics["width"] - width,
                             "name_visible": True, "defaults_visible": True, "selected_message": "selected-request-message"})
        assert len(store.list_bots()) == bot_count_before and len(store.list_runs(limit=100)) == run_count_before
        suggested_name = page.locator("#setup-display_name").input_value()
        assert re.fullmatch(r"[A-Z][a-z]+ [A-Z][a-z]+", suggested_name), (
            "the selected request should produce a short professional name")
        page.locator(".setup-identity summary").click()
        assert page.locator("#setup-description").input_value() == "Supplier Proposals Reviewer"
        page.locator(".setup-identity summary").click()
        custom_name = "Taylor Reed"
        page.locator("#setup-display_name").fill(custom_name)
        with page.expect_response(lambda response: response.url.endswith("/api/v1/bots")
                                 and response.request.method == "POST") as created:
            page.locator("#modal-confirm").click()
        assert created.value.status == 201, created.value.text()
        created_bot = next(item for item in store.list_bots() if item.id != bot.id)
        assert created_bot.instructions == selected_request
        assert created_bot.display_name == custom_name, "the owner must be able to replace the suggested name"
        assert created_bot.creation_source and created_bot.creation_source.message_id == "selected-request-message"
        assert created_bot.creation_source.original_request == selected_request
        assert created_bot.model == "openai/gpt-4o-mini"
        assert len(store.list_runs(limit=100)) == run_count_before, "creating from a message must not run the task"
        page.locator("#modal-root").wait_for(state="hidden")
        touch_context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True,
                                            has_touch=True, reduced_motion="reduce")
        touch_page = touch_context.new_page()
        touch_page.set_default_timeout(8000)
        touch_page.on("pageerror", lambda error: errors.append(str(error)))
        touch_page.on("request", lambda request: external.append(request.url) if not request.url.startswith(base) else None)
        touch_page.goto(f"{base}/#/chat/{bot.name}")
        touch_action = touch_page.locator('[data-create-bot-from-request="selected-request-message"]')
        touch_action.wait_for(state="visible")
        assert touch_page.evaluate("matchMedia('(pointer: coarse)').matches")
        touch_box = touch_action.bounding_box()
        assert touch_box and touch_box["height"] >= 44, touch_box
        touch_action.tap()
        touch_page.get_by_role("heading", name="Create from this request").wait_for(state="visible")
        assert not touch_page.locator("#setup-purpose").is_visible()
        touch_metrics = touch_page.evaluate("""() => ({width:document.documentElement.scrollWidth, viewport:innerWidth,
          dialog:document.querySelector('[role=dialog]').getBoundingClientRect().toJSON(),
          footer:document.querySelector('.modal-footer').getBoundingClientRect().toJSON()})""")
        assert touch_metrics["width"] - 390 <= 1, touch_metrics
        assert touch_metrics["dialog"]["left"] >= -1 and touch_metrics["dialog"]["right"] <= 391, touch_metrics
        assert touch_metrics["footer"]["bottom"] <= 845, touch_metrics
        touch_page.screenshot(path=str(out / "selected-request-phone.png"), animations="disabled")
        captures.append({"size": "phone-touch", "viewport": [390, 844], "pointer": "coarse",
                         "touch_target_height": touch_box["height"],
                         "horizontal_overflow": touch_metrics["width"] - 390,
                         "selected_message": "selected-request-message"})
        assert not errors, errors
        assert not external, external
        assert len(store.list_bots()) == bot_count_before + 1
        assert len(store.list_runs(limit=100)) == run_count_before
        (out / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_user_can_start_bot_setup_from_the_exact_chat_request",
            "command": ".venv/bin/pytest -q tests/e2e/test_browser.py::test_user_can_start_bot_setup_from_the_exact_chat_request --no-header",
            "browser": browser.version, "playwright_version": package_version("playwright"),
            "provider_calls": 0, "external_requests": external, "page_errors": errors,
            "scenario": "Keyboard-activate a message action in a multi-request conversation; exact request is used without retyping; only the chosen message is saved as Bot instructions; unrelated later text is excluded; create starts no run; phone path keeps the same no-retype default",
            "captures": captures,
            "source_sha256": {name: hashlib.sha256((out.parents[3] / name).read_bytes()).hexdigest()
                              for name in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                           "tests/e2e/test_browser.py")},
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        try:
            context.tracing.stop(path=str(out / "trace.zip"))
        finally:
            if touch_context is not None:
                touch_context.close()
            context.close()


def test_coordinator_can_refine_a_bot_purpose_without_changing_its_source_or_authority(browser, live, monkeypatch):
    """The opt-in draft is tool-free, reviewable, responsive, and restricted to selected messages."""
    import hashlib
    import json
    from pathlib import Path

    base, app = live
    monkeypatch.setattr(app.state.engine, "tick", lambda: None)
    store = app.state.store
    coordinator = store.create_bot(Bot(name="purpose-coordinator", display_name="Mara",
        model="openai/gpt-4o-mini", tools=["files", "memory"]))
    store.set_workspace_coordinator(coordinator.id)
    conversation, _ = store.create_conversation(coordinator.id, "Bot planning",
        idem_key="purpose-coordinator-chat", request_hash="purpose-coordinator-chat")
    for seq, message_id, role, content in (
        (1, "purpose-context-earlier", "user", "Use British spelling and keep the report to one page."),
        (2, "purpose-source-message", "user", "Prepare a weekly project status report for leadership."),
        (3, "purpose-source-answer", "assistant", "I can help you define a reporting Bot."),
        (4, "purpose-later-message", "user", "Do not use this unrelated private follow-up."),
    ):
        message_run = Run(bot_id=coordinator.id, prompt=content, status=RunStatus.succeeded,
                          conversation_id=conversation["id"])
        store.create_run(message_run)
        with store._tx() as db:
            db.execute("INSERT INTO conversation_runs (conversation_id, run_id, attached_at) VALUES (?, ?, ?)",
                       (conversation["id"], message_run.id, message_run.created_at))
            store._insert_conversation_message(db, message_id=message_id, conversation_id=conversation["id"],
                seq=seq, run_id=message_run.id, role=role, content=content, created_at=message_run.created_at)
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/bot-purpose-refinement"
    out.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    errors: list[str] = []
    calls: list[dict] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/api/v1/conversations/*/bot-purpose-drafts", lambda route: (
        calls.append(json.loads(route.request.post_data or "{}")),
        route.fulfill(status=201, json={"id": "fixture-purpose-draft-run"})
    ) if route.request.method == "POST" else route.continue_())
    page.route("**/api/v1/tasks/runs/fixture-purpose-draft-run**", lambda route: route.fulfill(
        status=200, json={"id": "fixture-purpose-draft-run", "terminal": True, "status": "succeeded",
                         "status_label": "Succeeded", "events": [{"type": "message", "data": {
                             "role": "assistant", "content": json.dumps({"kind": "draft", "instructions": "Prepare a weekly leadership report from the project information the owner provides.\n\nSeparate confirmed facts from assumptions, highlight material changes, and list unanswered questions. Keep the report to one page, use British spelling, and do not contact anyone.", "assumptions": []})}}]}
    ))
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        page.goto(f"{base}/#/chat/{coordinator.name}")
        page.locator("#conversation-switcher").wait_for()
        page.locator('[data-create-bot-from-request="purpose-source-message"]').click()
        original = "Prepare a weekly project status report for leadership."
        purpose = page.locator("#setup-purpose")
        assert purpose.input_value() == original
        assert not purpose.is_visible()
        assert "Make a bot" in page.locator("[data-create-bot-from-request='purpose-source-message']").inner_text()
        page.locator("#setup-purpose-editor > summary").click()
        assert purpose.is_visible()
        page.locator("#setup-customize").click()
        page.get_by_role("heading", name="Choose what powers it").wait_for()
        page.locator("#setup-back").click()
        page.locator("#setup-context-picker > summary").click()
        selected_context = page.locator('[data-setup-context-message="purpose-context-earlier"]')
        selected_context.check()
        page.locator("#setup-refine-details > summary").click()
        refine = page.get_by_role("button", name="Check for missing details")
        assert refine.evaluate("el => el.getBoundingClientRect().height") >= 44
        refine.click()
        suggestion_text = "Prepare a weekly leadership report from the project information the owner provides.\n\nSeparate confirmed facts from assumptions, highlight material changes, and list unanswered questions. Keep the report to one page, use British spelling, and do not contact anyone."
        page.locator("#setup-purpose-draft-text").wait_for()
        assert purpose.input_value() == original, "the suggestion must not overwrite the user's purpose automatically"
        assert page.locator("#setup-purpose-draft-text").input_value() == suggestion_text
        assert len(calls) == 1
        assert calls[0] == {"source_message_id": "purpose-source-message", "purpose": original,
                            "context_message_ids": ["purpose-context-earlier"], "clarification_history": []}
        assert "Do not use this unrelated private follow-up." not in json.dumps(calls)
        assert "I can help you define a reporting Bot." not in json.dumps(calls)
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            page.locator("#setup-purpose-draft-text").evaluate("el => el.scrollIntoView({block:'center',inline:'nearest'})")
            metrics = page.evaluate("""() => ({viewport:[innerWidth,innerHeight],
              documentWidth:document.documentElement.scrollWidth,
              modalWidth:document.querySelector('.modal-card').scrollWidth-document.querySelector('.modal-card').clientWidth,
              footerVisible:document.querySelector('.modal-footer').getBoundingClientRect().bottom<=innerHeight,
              actionHeight:document.querySelector('#setup-purpose-draft-use').getBoundingClientRect().height,
              textareaVisible:(() => {const field=document.querySelector('#setup-purpose-draft-text').getBoundingClientRect();
                const body=document.querySelector('.modal-body').getBoundingClientRect();
                const footer=document.querySelector('.modal-footer').getBoundingClientRect();
                return {ok:field.top>=body.top-1 && field.bottom<=footer.top+1,
                  field:[field.top,field.bottom],body:[body.top,body.bottom],footerTop:footer.top,
                  scrollTop:document.querySelector('.modal-body').scrollTop,
                  scrollHeight:document.querySelector('.modal-body').scrollHeight,
                  clientHeight:document.querySelector('.modal-body').clientHeight};})()})""")
            assert metrics["documentWidth"] - width <= 1 and metrics["modalWidth"] <= 1, (label, metrics)
            assert metrics["footerVisible"] and metrics["actionHeight"] >= 44 and metrics["textareaVisible"]["ok"], (label, metrics)
            page.screenshot(path=str(out / f"review-draft-{label}.png"), animations="disabled")
        page.get_by_role("button", name="Use this draft").click()
        assert purpose.input_value() == suggestion_text
        assert page.locator("#setup-display_name").input_value(), "the professional name suggestion remains visible for review"
        purpose.evaluate("el => el.scrollIntoView({block:'center',inline:'nearest'})")
        assert "Draft applied to the purpose field" in page.locator("#setup-purpose-draft-status").inner_text()
        page.screenshot(path=str(out / "purpose-applied-phone.png"), animations="disabled")
        assert not errors, errors
        (out / "validation.json").write_text(json.dumps({
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_coordinator_can_refine_a_bot_purpose_without_changing_its_source_or_authority",
            "browser": browser.browser_type.name, "browser_version": browser.version,
            "playwright_version": package_version("playwright"),
            "viewports": {"desktop": [1440, 960], "tablet": [900, 1024], "phone": [390, 844]},
            "scenario": "owner explicitly requests one review-only coordinator response using the exact source, editable purpose and only selected earlier user messages; assistant replies and later user messages stay excluded; suggestion does not overwrite purpose or authority until accepted; fixture response, no provider call",
            "screenshots": [f"review-draft-{size}.png" for size in ("desktop", "tablet", "phone")]
                           + ["purpose-applied-phone.png"],
            "draft_request_count": len(calls), "page_errors": errors,
            "source_sha256": {relative: hashlib.sha256((Path(__file__).resolve().parents[2] / relative).read_bytes()).hexdigest()
                              for relative in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                               "src/hutch/server/app.py", "src/hutch/models.py", "src/hutch/store.py",
                                               "tests/test_conversations.py", "tests/e2e/test_browser.py")},
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        try:
            context.tracing.stop(path=str(out / "trace.zip"))
        except Exception:
            pass
        context.close()


def test_chat_sourced_bot_setup_clarifies_multiple_details_and_restores_after_reload(browser, live, monkeypatch):
    """A coordinator preserves multiple clarification turns and returns a review-only draft."""
    import hashlib
    import json
    from pathlib import Path

    base, app = live
    monkeypatch.setattr(app.state.engine, "tick", lambda: None)
    store = app.state.store
    coordinator = store.create_bot(Bot(name="guided-setup-coordinator", display_name="Mara",
        model="openai/gpt-4o-mini", tools=["files", "memory"]))
    store.set_workspace_coordinator(coordinator.id)
    conversation, _ = store.create_conversation(coordinator.id, "Bot planning",
        idem_key="guided-setup-chat", request_hash="guided-setup-chat")
    for seq, message_id, role, content in (
        (1, "guided-setup-source", "user", "Prepare a weekly project status report for leadership."),
        (2, "guided-setup-answer", "assistant", "I can help set up a reporting Bot."),
        (3, "guided-setup-later", "user", "Do not include this unrelated later request."),
    ):
        message_run = Run(bot_id=coordinator.id, prompt=content, status=RunStatus.succeeded,
                          conversation_id=conversation["id"])
        store.create_run(message_run)
        with store._tx() as db:
            db.execute("INSERT INTO conversation_runs (conversation_id, run_id, attached_at) VALUES (?, ?, ?)",
                       (conversation["id"], message_run.id, message_run.created_at))
            store._insert_conversation_message(db, message_id=message_id, conversation_id=conversation["id"],
                seq=seq, run_id=message_run.id, role=role, content=content, created_at=message_run.created_at)

    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/bot-setup-multi-round"
    out.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    errors: list[str] = []
    calls: list[dict] = []
    responses = {
        "guided-setup-question-run": '{"kind":"question","question":"What should leadership receive?",'
            '"options":["A concise written summary","A table of status, owner and next step"]}',
        "guided-setup-followup-run": '{"kind":"question","question":"What should the Bot do when an update is missing?",'
            '"options":["Ask me before the report","Label the gap as not provided"]}',
        "guided-setup-draft-run": '{"kind":"draft","instructions":"Prepare a weekly leadership status report. '
            'Use a concise three-bullet summary with confirmed facts, blockers and next steps. Label missing updates '
            'as not provided and never guess. Do not send it.",'
            '"assumptions":["The owner will provide project updates in the conversation."]}',
    }
    page.on("pageerror", lambda error: errors.append(str(error)))

    def submit_draft(route):
        calls.append(json.loads(route.request.post_data or "{}"))
        run_id = ("guided-setup-question-run" if len(calls) == 1
                  else "guided-setup-followup-run" if len(calls) == 2
                  else "guided-setup-draft-run")
        route.fulfill(status=201, json={"id": run_id})

    def read_draft_run(route):
        run_id = route.request.url.split("/tasks/runs/")[1].split("?")[0]
        route.fulfill(status=200, json={"id": run_id, "terminal": True, "status": "succeeded",
            "status_label": "Succeeded", "events": [{"type": "message", "data": {
                "role": "assistant", "content": responses[run_id]}}]})

    page.route("**/api/v1/conversations/*/bot-purpose-drafts", submit_draft)
    page.route("**/api/v1/tasks/runs/guided-setup-*-run**", read_draft_run)
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        page.goto(f"{base}/#/chat/{coordinator.name}")
        page.locator("#conversation-switcher").wait_for()
        bot_count = len(store.list_bots())
        run_count = len(store.list_runs(limit=100))
        page.locator('[data-create-bot-from-request="guided-setup-source"]').click()
        assert page.locator("#setup-purpose").input_value() == "Prepare a weekly project status report for leadership."
        assert not page.locator("#setup-purpose").is_visible()
        page.locator("#setup-refine-details > summary").click()
        page.get_by_role("button", name="Check for missing details").click()
        question = page.locator("#setup-clarification-question")
        question.wait_for()
        assert "What should leadership receive?" in question.inner_text()
        assert page.get_by_role("radio", name="A concise written summary").is_visible()
        assert len(calls) == 1
        assert calls[0] == {"source_message_id": "guided-setup-source",
                            "purpose": "Prepare a weekly project status report for leadership.",
                            "context_message_ids": [], "clarification_history": []}
        assert "Do not include this unrelated later request." not in json.dumps(calls)
        page.screenshot(path=str(out / "question-desktop.png"), animations="disabled")
        page.get_by_role("radio", name="A concise written summary").check()
        page.locator("#setup-clarification-answer").fill("A three-bullet note in chat, please.")

        # Reopening the setup restores the selected request and unsent answer from this browser only.
        page.reload()
        page.locator("#conversation-switcher").wait_for()
        page.locator('[data-create-bot-from-request="guided-setup-source"]').click()
        question = page.locator("#setup-clarification-question")
        question.wait_for()
        assert page.get_by_role("radio", name="A concise written summary").is_checked()
        assert page.locator("#setup-clarification-answer").input_value() == "A three-bullet note in chat, please."
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(out / "question-phone-restored.png"), animations="disabled")
        page.get_by_role("button", name="Continue with this answer").click()
        question = page.locator("#setup-clarification-question")
        question.wait_for()
        assert len(calls) == 2
        assert "What should the Bot do when an update is missing?" in question.inner_text()
        assert calls[1]["clarification_history"] == [{
            "question": "What should leadership receive?",
            "answer": "A concise written summary — A three-bullet note in chat, please."}]
        assert calls[1]["source_message_id"] == "guided-setup-source"
        assert calls[1]["context_message_ids"] == []
        assert "Do not include this unrelated later request." not in json.dumps(calls[1])

        page.set_viewport_size({"width": 1440, "height": 960})
        assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
        page.screenshot(path=str(out / "followup-question-desktop.png"), animations="disabled")
        page.get_by_role("radio", name="Label the gap as not provided").check()
        page.locator("#setup-clarification-answer").fill("Never fill gaps with guesses.")

        # The second question and the first answer both survive another reload.
        page.reload()
        page.locator("#conversation-switcher").wait_for()
        page.locator('[data-create-bot-from-request="guided-setup-source"]').click()
        question = page.locator("#setup-clarification-question")
        question.wait_for()
        assert page.get_by_role("radio", name="Label the gap as not provided").is_checked()
        assert page.locator("#setup-clarification-answer").input_value() == "Never fill gaps with guesses."
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
        page.screenshot(path=str(out / "followup-question-phone-restored.png"), animations="disabled")
        page.get_by_role("button", name="Continue with this answer").click()

        page.locator("#setup-purpose-draft-text").wait_for()
        assert len(calls) == 3
        assert calls[2]["clarification_history"] == [
            {
                "question": "What should leadership receive?",
                "answer": "A concise written summary — A three-bullet note in chat, please.",
            },
            {
                "question": "What should the Bot do when an update is missing?",
                "answer": "Label the gap as not provided — Never fill gaps with guesses.",
            },
        ]
        assert calls[2]["source_message_id"] == "guided-setup-source"
        assert calls[2]["context_message_ids"] == []
        assert "Do not include this unrelated later request." not in json.dumps(calls[2])
        assert page.locator("#setup-purpose-draft-text").input_value().startswith("Prepare a weekly leadership")
        assert "The owner will provide project updates" in page.locator("#setup-purpose-draft-assumptions").inner_text()

        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            metrics = page.evaluate("""() => ({width:document.documentElement.scrollWidth, viewport:innerWidth,
              modalWidth:document.querySelector('.modal-card').scrollWidth-document.querySelector('.modal-card').clientWidth,
              footerBottom:document.querySelector('.modal-footer').getBoundingClientRect().bottom,
              textarea:document.querySelector('#setup-purpose-draft-text').getBoundingClientRect().toJSON(),
              body:document.querySelector('.modal-body').getBoundingClientRect().toJSON(),
              footer:document.querySelector('.modal-footer').getBoundingClientRect().toJSON()})""")
            assert metrics["width"] - width <= 1 and metrics["modalWidth"] <= 1, (label, metrics)
            assert metrics["footerBottom"] <= height and metrics["textarea"]["top"] >= metrics["body"]["top"] - 1
            assert metrics["textarea"]["bottom"] <= metrics["footer"]["top"] + 1
            page.screenshot(path=str(out / f"review-draft-{label}.png"), animations="disabled")
        page.get_by_role("button", name="Use this draft").click()
        assert page.locator("#setup-purpose").input_value().startswith("Prepare a weekly leadership")
        assert len(store.list_bots()) == bot_count, "clarification must not create a Bot before explicit confirmation"
        assert len(store.list_runs(limit=100)) == run_count, "fixtures must not create or run provider work"
        assert not errors, errors
        (out / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_chat_sourced_bot_setup_clarifies_multiple_details_and_restores_after_reload",
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_chat_sourced_bot_setup_clarifies_multiple_details_and_restores_after_reload",
            "browser": browser.browser_type.name, "browser_version": browser.version,
            "playwright_version": package_version("playwright"),
            "viewports": {"desktop": [1440, 960], "tablet": [900, 1024], "phone": [390, 844]},
            "provider_calls": 0, "external_requests": 0,
            "scenario": "chat-derived Bot setup preserves its exact request, asks two bounded choice questions one at a time, restores each question and unsent answer after reload, carries both answers into a review-only draft, and creates no Bot or run",
            "screenshots": ["question-desktop.png", "question-phone-restored.png",
                            "followup-question-desktop.png", "followup-question-phone-restored.png"]
                + [f"review-draft-{size}.png" for size in ("desktop", "tablet", "phone")],
            "clarification_request_count": len(calls), "page_errors": errors,
            "source_sha256": {relative: hashlib.sha256((Path(__file__).resolve().parents[2] / relative).read_bytes()).hexdigest()
                              for relative in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                               "src/hutch/server/app.py", "tests/test_conversations.py",
                                               "tests/e2e/test_browser.py")},
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        try:
            context.tracing.stop(path=str(out / "trace.zip"))
        except Exception:
            pass
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
        page.get_by_role("heading", name="Set up your assistant").wait_for()
        page.locator("#setup-purpose").fill("Prepare a weekly project summary.")
        page.locator("#setup-display_name").fill("Project Summary Assistant")
        page.locator(".setup-identity summary").click()
        page.locator("#setup-name").fill("workspace-default-child")
        page.locator("#setup-customize").click()
        page.get_by_role("heading", name="Choose what powers it").wait_for()
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
        open_assistant_customization(page)
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
        wait_for_page(page, "form => !form.isConnected", arg=stale_secondary_form)
        wait_for_page(page, "() => [...document.querySelectorAll('[data-schedule-form] [name=name]')].some(input => input.value === 'Monthly release review')")

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
        wait_for_page(page, "form => !form.isConnected", arg=stale_primary_form)
        page.locator("#form-schedule").wait_for(state="visible")
        assert page.locator('#form-schedule [name="schedule_prompt"]').input_value() \
            == "Check the weekly security feed and list actionable changes."
        page.reload()
        open_assistant_customization(page)
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
            # These editors are vertically scrollable forms; assert viewport reflow,
            # while the workflow-link journey separately checks that the action is reachable.
            for index, entry in enumerate(page.locator("details.schedule-entry").all()):
                entry.scroll_into_view_if_needed()
                box = entry.bounding_box()
                assert box and 0 < box["width"] <= width, (label, index, box)
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


def test_routine_editor_links_an_activated_workflow_accessibly_across_viewports(browser, live):
    base, app = live
    from hutch.workflow import persistence as workflow_store

    bot = Bot(name="routine-workflow-visual", display_name="Routine workflow visual fixture",
              model="mock/demo", tools=[], instructions="A visual fixture with no provider access.",
              schedules=[Schedule(id="schedule_visual_workflow", name="Weekly evidence report",
                                  cron="0 9 * * 1", timezone="UTC", enabled=False)])
    app.state.store.create_bot(bot)
    plan = {
        "name": "visual-workflow-verification-method",
        "budget": {"max_nodes": 3, "max_model_calls": 0},
        "nodes": [{"kind": "transform", "id": "value", "op": "constant",
                   "args": {"value": "verified fixture"}}],
        "outputs": ["value"],
    }
    saved = workflow_store.save_definition(app.state.store,
        name="Weekly evidence report with a deliberately long saved workflow title", plan=plan,
        activate=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/scheduled-workflow-link-2026-10-11"
    out.mkdir(parents=True, exist_ok=True)
    page.context.tracing.start(screenshots=True, snapshots=True, sources=False)
    trace_stopped = False
    captures = []
    try:
        page.goto(f"{base}/#/bot/{bot.name}")
        open_assistant_customization(page)
        form = page.locator("#form-schedule")
        form.wait_for()
        selector = form.locator("[data-schedule-workflow-definition]")
        selector.wait_for()
        assert selector.locator(f'option[value="{saved["definition_id"]}"]').count() == 1

        # Link by keyboard to verify the selection, exact revision, and input editor work without a mouse.
        selector.focus()
        page.keyboard.press("ArrowDown")
        assert selector.input_value() == saved["definition_id"]
        assert form.locator('[name="workflow_revision_id"]').input_value() == saved["revision_id"]
        assert form.locator("[data-workflow-inputs-field]").is_visible()
        assert saved["revision_id"] in form.locator("[data-workflow-revision-summary]").inner_text()
        form.locator('[name="name"]').fill("Weekly evidence report")
        with page.expect_response(lambda response: response.url.endswith(
                f"/api/v1/bots/{bot.id}/schedules/{bot.schedule.id}")
                and response.request.method == "PUT") as linked_response:
            form.get_by_role("button", name="Save task").focus()
            page.keyboard.press("Enter")
        assert linked_response.value.status == 200, linked_response.value.text()
        resource = linked_response.value.json()
        assert resource["workflow_definition_id"] == saved["definition_id"]
        assert resource["workflow_revision_id"] == saved["revision_id"]
        assert resource["enabled"] is False
        wait_for(lambda: app.state.store.get_bot(bot.id).schedule.workflow_revision_id == saved["revision_id"])
        page.get_by_role("button", name="Dismiss notification").click()

        sizes = {"desktop-1440": (1440, 1000), "tablet-768": (768, 980),
                 "phone-360": (360, 844), "reflow-320": (320, 800)}
        for label, (width, height) in sizes.items():
            page.set_viewport_size({"width": width, "height": height})
            entry = page.locator("details.schedule-entry").first
            entry.evaluate("el => el.open = true")
            entry.evaluate("el => el.scrollIntoView({block: 'start'})")
            page.wait_for_timeout(80)
            metrics = page.evaluate("""() => ({
                viewport: [innerWidth, innerHeight],
                document: [document.documentElement.scrollWidth, document.documentElement.scrollHeight],
                body: [document.body.scrollWidth, document.body.scrollHeight],
                selected: document.querySelector('[data-schedule-workflow-definition]').value,
                revision: document.querySelector('[name=workflow_revision_id]').value,
                saveTarget: (() => { const b = document.querySelector('[data-schedule-form] button[type=submit]');
                  const r = b.getBoundingClientRect(); return [r.width, r.height]; })()
            })""")
            assert metrics["document"][0] - width <= 1, (label, metrics)
            assert metrics["body"][0] - width <= 1, (label, metrics)
            assert metrics["selected"] == saved["definition_id"] and metrics["revision"] == saved["revision_id"]
            assert min(metrics["saveTarget"]) >= 44, (label, metrics)
            page.screenshot(path=str(out / f"routine-link-{label}.png"),
                            animations="disabled")
            entry.screenshot(path=str(out / f"routine-link-{label}-editor.png"), animations="disabled")
            revision_summary = form.locator("[data-workflow-revision-summary]")
            revision_summary.scroll_into_view_if_needed()
            assert revision_summary.is_visible()
            assert saved["revision_id"] in revision_summary.inner_text()
            assert "deliberately long saved workflow title" in revision_summary.inner_text()
            page.screenshot(path=str(out / f"routine-link-{label}-pinned-revision.png"),
                            animations="disabled")
            save_button = form.get_by_role("button", name="Save task")
            save_button.evaluate("el => el.scrollIntoView({block: 'center'})")
            action_target = save_button.evaluate("el => { const r = el.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; }")
            assert action_target[1] >= 0 and action_target[1] + action_target[3] <= height, (label, action_target)
            assert action_target[2] >= 44 and action_target[3] >= 44, (label, action_target)
            page.screenshot(path=str(out / f"routine-link-{label}-actions.png"), animations="disabled")
            captures.append({"size": label, **metrics, "save_action": action_target})

        page.context.tracing.stop(path=str(out / "routine-link-trace.zip"))
        trace_stopped = True
        assert not errors, errors
        source_root = Path(__file__).resolve().parents[2]
        (out / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_routine_editor_links_an_activated_workflow_accessibly_across_viewports",
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_routine_editor_links_an_activated_workflow_accessibly_across_viewports",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(),
            "hutch_version": package_version("hutch"),
            "browser": browser.browser_type.name,
            "browser_version": browser.version,
            "playwright_version": package_version("playwright"),
            "scenario": "owner links an activated saved revision to a disabled routine using keyboard selection; no provider call",
            "captures": captures,
            "page_errors": errors,
            "source_sha256": {
                name: hashlib.sha256((source_root / path).read_bytes()).hexdigest()
                for name, path in {"app.js": "src/hutch/server/static/app.js",
                                   "style.css": "src/hutch/server/static/style.css",
                                   "app.py": "src/hutch/server/app.py",
                                   "models.py": "src/hutch/models.py"}.items()
            },
        }, indent=2) + "\n", encoding="utf-8")
        (out / "visual-review.md").write_text(
            "# Routine-to-workflow visual review\n\n"
            "The schedule editor keeps the routine title and saved-workflow selector readable at desktop, tablet, "
            "phone, and 320 CSS-pixel reflow widths. Linking remains a visible owner action, the workflow input "
            "editor appears after selection, and the disabled routine keeps its draft state. The submit target stays "
            "at least 44 CSS pixels in both dimensions. Screenshots are retained beside this review; no browser "
            "console errors were observed.\n", encoding="utf-8")
    finally:
        if not trace_stopped:
            try:
                page.context.tracing.stop(path=str(out / "routine-link-trace.zip"))
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
    open_assistant_customization(page)
    mode = page.locator('#form-model select[name="inference_mode"]')
    task_focus = page.locator('#form-model select[name="preset"]')
    mode.wait_for()
    task_focus.wait_for()
    assert mode.input_value() == "hybrid"
    assert task_focus.input_value() == ""
    assert task_focus.locator('option[value="coding"]').count() == 1
    assert "never selects a model, provider, or paid route" in page.locator("#task-focus-help").inner_text()
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
        captures.append({"size": size, **metrics, "taskFocusControlVisible": task_focus.is_visible(),
                         "strictOfflineDisabled": disabled_state["disabled"],
                         "capabilityStatus": offline_capability["status"]})

    page.set_viewport_size({"width": 390, "height": 844})
    mode.scroll_into_view_if_needed()
    assert mode.is_visible() and page.locator("#inference-mode-help").is_visible()
    page.screenshot(path=str(capture_dir / "settings-phone-routing.png"), animations="disabled")
    ctx.tracing.stop(path=str(capture_dir / "settings-trace.zip"))
    captures.append({"size": "phone-routing", "viewport": [390, 844], "routingVisible": mode.is_visible(),
                     "taskFocusVisible": task_focus.is_visible(),
                     "helpVisible": page.locator("#inference-mode-help").is_visible()})

    mode.select_option("local")
    task_focus.select_option("coding")
    with page.expect_response(lambda response: response.url.endswith("/api/bots/route-bot")
                              and response.request.method == "PATCH") as saved:
        page.locator('#form-model button[type="submit"]').click()
    assert saved.value.status == 200, saved.value.text()
    assert saved.value.json()["preset"] == "coding"
    wait_for(lambda: store.get_bot("route-bot").inference_mode.value == "local"
             and store.get_bot("route-bot").preset == "coding")
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
        "scenario": "synthetic bot settings; changed routing mode and per-Bot local task focus together; no provider or model call",
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
    wait_for_page(page, "document.querySelectorAll('.ms-menu .ms-item[role=menuitemradio]').length >= 2")
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
    page.locator("#studio-conversation-options").click()
    page.locator("#studio-new-conversation").click()
    wait_for_page(page, "old => document.querySelector('#conversation-switcher').value !== old", arg=first_conversation)
    assert "tiny:1b" in page.locator(".ms-btn").get_attribute("aria-label")
    assert "is-custom" not in page.locator(".ms-btn").get_attribute("class")
    page.locator("#conversation-switcher").select_option(first_conversation)
    wait_for_page(page, "() => document.querySelector('.ms-btn')?.getAttribute('aria-label')?.includes('small:2b')")

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


def test_openrouter_models_are_searchable_from_the_chat_picker(browser, switcher_env, request):
    from tests.fakes import FakeOpenAI

    base, app, _fake = switcher_env
    router = FakeOpenAI()
    router.require_key = "router-e2e-secret"
    router.models = [
        {"id": "anthropic/claude-sonnet-4", "name": "Claude Sonnet 4",
         "pricing": {"prompt": "0.000003", "completion": "0.000015"},
         "supported_parameters": ["tools"]},
        {"id": "deepseek/deepseek-chat-v3", "name": "DeepSeek Chat V3",
         "pricing": {"prompt": "0.0000002", "completion": "0.0000008"},
         "supported_parameters": ["temperature"]},
    ]
    request.addfinalizer(router.close)
    book = ConnectionBook(app.state.config.state_dir)
    book.add("openrouter", base_url=router.url + "/v1")
    book.set_key("openrouter", "router-e2e-secret")
    from hutch.modelchoices import reset_cache
    reset_cache()

    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/openrouter-model-search"
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
        assert router.requests == [], "opening a chat must not refresh provider catalogs"
        button.click()
        page.locator('.ms-menu [data-spec="openrouter/anthropic/claude-sonnet-4"]').wait_for()
        catalog = page.request.get(f"{base}/api/bots/chatty/models?discover=1").json()
        assert any(row["spec"] == "openrouter/anthropic/claude-sonnet-4" for row in catalog["models"]), catalog
        with page.expect_response(lambda response: "/api/bots/chatty/models?discover=1" in response.url) as all_models_response:
            page.locator(".ms-more").click()
        all_models = all_models_response.value.json()
        assert any(row["spec"] == "openrouter/anthropic/claude-sonnet-4" for row in all_models["models"]), all_models
        dialog = page.locator(".modal-card")
        dialog.wait_for()
        # The catalog is below the initial viewport in the scrollable model list;
        # text_content verifies it is present before exercising visible search.
        assert "OpenRouter" in page.locator(".ms-groups").text_content()
        assert "catalog price" in page.locator(".ms-groups").text_content()

        page.locator(".ms-search").fill("deepseek")
        wait_for(lambda: any("q=deepseek" in row["path"] for row in router.requests))
        result = page.locator('.ms-row[data-text*="deepseek"]:visible')
        result.wait_for()
        assert "DeepSeek Chat V3" in result.inner_text()

        captures = []
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            box = page.locator(".modal-card").bounding_box()
            assert box and box["x"] >= 0 and box["x"] + box["width"] <= width + 1, (label, box)
            assert page.evaluate("document.documentElement.scrollWidth") <= width + 1, label
            page.screenshot(path=str(out / f"search-{label}.png"), animations="disabled")
            captures.append({"viewport": [width, height], "modal": box})

        page.locator('input[name="ms-pick"][value="openrouter/deepseek/deepseek-chat-v3"]').check()
        page.locator("#modal-confirm").click()
        assert "is-custom" in button.get_attribute("class")
        assert app.state.store.get_bot("chatty").model == "ollama/tiny:1b"
        assert not any(row["method"] == "POST" for row in router.requests), "search and selection must not call a model"
        assert not errors, errors
        (out / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_browser.py::test_openrouter_models_are_searchable_from_the_chat_picker",
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_openrouter_models_are_searchable_from_the_chat_picker",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(), "browser": browser.version,
            "playwright_version": package_version("playwright"), "captures": captures,
            "page_errors": errors,
            "provider_requests": [{"method": row["method"], "path": row["path"]} for row in router.requests],
            "inference_requests": sum(row["method"] == "POST" for row in router.requests),
            "source_sha256": {relative: hashlib.sha256((Path(__file__).resolve().parents[2] / relative).read_bytes()).hexdigest()
                              for relative in ("src/hutch/server/static/model-switcher.js",
                                               "src/hutch/server/static/model-switcher.css", "src/hutch/modelchoices.py",
                                               "tests/e2e/test_browser.py")},
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        try:
            context.tracing.stop(path=str(out / "trace.zip"))
        except Exception:
            pass
        context.close()


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
        open_assistant_customization(page)
        page.locator("#runtime-recovery").wait_for()
        assert page.get_by_text("OpenCode execution is unavailable in Hutch.").is_visible()
        assert "Hutch never imports private sign-in files or credentials" in page.locator("#runtime-recovery").inner_text()
        isolation_help = page.locator("#inference-mode-help").inner_text()
        offline_capability = next(item for item in page.request.get(f"{base}/api/v1/capabilities").json()
                                  if item["id"] == "strict_offline")
        if offline_capability["status"] == "unavailable":
            assert "Hutch could not verify worker network isolation on this host" in isolation_help
            assert "Strict Offline stays unavailable" in isolation_help
        else:
            assert "Hutch verified that the isolated worker" in isolation_help
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


def test_small_workspace_has_one_roster_and_legacy_routes_do_not_trap_back(browser, live, request):
    base, app = live
    app.state.store.create_bot(Bot(name="one-bot", model="mock/demo", tools=[]))
    page = browser.new_page(viewport={"width": 1200, "height": 800})
    request.addfinalizer(page.close)
    page.goto(base + "/#/chat/one-bot")
    page.locator("#conversation-switcher").wait_for()
    assert not page.locator("#fleet-nav").is_visible()
    assert not page.locator("#monitor-nav").get_attribute("open")
    assert page.get_by_text("Manage all bots", exact=True).count() == 0
    assert page.get_by_role("button", name="Context", exact=True).count() == 0
    page.locator("[data-bot-options='one-bot']").click()
    page.get_by_role("menuitem", name="Assistant settings").click()
    open_assistant_customization(page)
    page.get_by_role("heading", name="About this assistant", exact=True).wait_for()
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
        open_assistant_customization(page)
        page.get_by_role("heading", name="About this assistant", exact=True).wait_for()
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
        wait_for_page(page, "form => !form.isConnected", arg=old_form)
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
        wait_for_page(page, "form => !form.isConnected", arg=old_form)
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
        open_assistant_customization(page)
        page.get_by_role("heading", name="About this assistant", exact=True).wait_for()
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
        wait_for_page(page, "form => !form.isConnected", arg=old_form)
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
    page.get_by_role("link", name="Manage assistants", exact=True).click()
    page.locator("#fleet-search").wait_for()
    assert page.locator("#fleet-count").inner_text() == "10 of 10 assistants"
    page.locator("#fleet-state").select_option("paused")
    assert page.locator("#fleet-count").inner_text() == "1 of 10 assistants"
    page.locator("#fleet-search").fill("fleet-9")
    assert page.locator("#fleet-count").inner_text() == "0 of 10 assistants"
    page.locator("#fleet-state").select_option("all")
    assert page.locator("#fleet-count").inner_text() == "1 of 10 assistants"
    card = page.locator('[data-fleet-bot="fleet-9"]')
    card.locator("[data-fleet-options]").click()
    menu = card.locator(".fleet-card-menu-panel")
    assert menu.get_by_role("button", name="Pause assistant").is_visible()
    with page.expect_response(lambda response: response.url.endswith("/api/bots/fleet-9")
                             and response.request.method == "PATCH") as paused:
        menu.get_by_role("button", name="Pause assistant").click()
    assert paused.value.status == 200
    wait_for(lambda: app.state.store.get_bot("fleet-9").paused)
    card = page.locator('[data-fleet-bot="fleet-9"]')
    card.locator("[data-fleet-options]").click()
    menu = card.locator(".fleet-card-menu-panel")
    assert menu.get_by_role("button", name="Resume assistant").is_visible()
    with page.expect_response(lambda response: response.url.endswith("/api/bots/fleet-9")
                             and response.request.method == "PATCH") as resumed:
        menu.get_by_role("button", name="Resume assistant").click()
    assert resumed.value.status == 200
    wait_for(lambda: not app.state.store.get_bot("fleet-9").paused)
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
    page.wait_for_url("**/#/chat/draft-b")
    page.locator("#conversation-switcher").wait_for(state="visible")
    assert page.locator("#chat-prompt").input_value() == ""
    page.locator('[data-switch-bot="draft-a"]').click()
    page.wait_for_url("**/#/chat/draft-a")
    page.locator("#conversation-switcher").wait_for(state="visible")
    wait_for_page(page, "id => document.querySelector('#conversation-switcher')?.value === id", arg=first)
    assert page.locator("#chat-prompt").input_value() == "Private draft for A"
    page.locator("#studio-conversation-options").click()
    page.locator("#studio-new-conversation").click()
    wait_for_page(page, "id => document.querySelector('#conversation-switcher')?.value !== id", arg=first)
    assert page.locator("#chat-prompt").input_value() == ""
    page.locator("#conversation-switcher").select_option(first)
    wait_for_page(page, "document.querySelector('#chat-prompt')?.value === 'Private draft for A'")
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
    assert card.get_by_text(approval_id, exact=True).is_visible()
    assert card.get_attribute("data-action-hash")
    for selector, name in (("[data-approve=\"1\"]", "Allow once"),
                           ("[data-approve=\"0\"]", "Deny")):
        button = card.locator(selector)
        description_ids = button.get_attribute("aria-describedby").split()
        description = " ".join(page.locator(f'[id="{element_id}"]').inner_text()
                               for element_id in description_ids)
        assert approval_id in description and "write report" in description
        assert card.get_by_role(
            "button", name=name, description=re.compile(r"write report.*" + re.escape(approval_id)),
        ).is_visible()
    thread = card.locator("xpath=ancestor::article[@data-run-id]")
    assert thread.locator(".msg.you").count() == 1
    assert thread.locator(".msg.you").bounding_box()["y"] < thread.locator(".msg.agent").bounding_box()["y"]
    assert not thread.locator(".answer").count(), "a waiting run must not echo the user's prompt as an assistant answer"
    card.get_by_text("Review details", exact=True).click()
    assert "Changing a file needs your okay." in card.inner_text()
    assert "ask:file-write" not in card.inner_text()
    assert not card.locator(".approval-detail").is_visible()
    card.locator(".approval-raw summary").click()
    assert card.locator(".approval-detail").is_visible()
    card.locator('[data-approve="1"]').focus()
    time.sleep(3.3)  # transcript poll keeps the review expanded and the decision focused
    assert card.locator(".approval-detail").is_visible()
    assert card.locator('[data-approve="1"]').evaluate("e => e === document.activeElement")
    assert page.locator("#studio-stop-run").is_visible()
    assert page.locator("#studio-review-run").is_visible()
    page.locator("#studio-conversation-options").click()
    settings = page.locator('.conversation-actions-panel [data-conversation-action="settings"]')
    assert settings.is_visible() and settings.inner_text().strip() == "Assistant settings"
    assert settings.get_attribute("href") == "#/bot/chat-approval"
    page.locator("#studio-conversation-options").click()
    header = page.locator(".app-top").bounding_box()
    for control in ("#conversation-switcher", "#studio-search-messages", "#studio-conversation-options",
                    "#studio-review-run", "#studio-stop-run"):
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


def test_chat_header_uses_available_title_space_and_groups_assistant_settings(browser, live):
    base, app = live
    app.state.store.create_bot(Bot(name="header-space", display_name="Design Partner", model="mock/demo", tools=[]))
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/chat-header-options"
    out.mkdir(parents=True, exist_ok=True)
    page = browser.new_page(viewport={"width": 1440, "height": 960})
    page_errors = []
    external_requests = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.on("request", lambda request: external_requests.append(request.url)
            if urlsplit(request.url).hostname not in {"127.0.0.1", "localhost"} else None)
    page.goto(base + "/#/chat/header-space")
    title = page.locator(".ctx-heading h1")
    title.wait_for()
    assert title.inner_text() == "Design Partner"
    assert title.evaluate("e => e.scrollWidth <= e.clientWidth + 1"), "the title should use available header space"
    assert page.locator(".ctx-actions > a").count() == 0, "assistant settings should not consume permanent toolbar space"
    page.screenshot(path=str(out / "desktop.png"), full_page=True)
    page.locator("#studio-conversation-options").click()
    settings = page.locator('.conversation-actions-panel [data-conversation-action="settings"]')
    assert settings.is_visible() and settings.inner_text().strip() == "Assistant settings"
    assert settings.get_attribute("href") == "#/bot/header-space"
    assert not page.locator("#studio-stop-run").is_visible()
    page.screenshot(path=str(out / "desktop-options.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(50)
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
    header = page.locator(".app-top").bounding_box()
    for control in ("#conversation-switcher", "#studio-search-messages", "#studio-conversation-options"):
        box = page.locator(control).bounding_box()
        assert box["y"] >= header["y"] and box["y"] + box["height"] <= header["y"] + header["height"] + 1
    page.screenshot(path=str(out / "phone-options.png"), full_page=True)
    (out / "validation.json").write_text(json.dumps({
        "test": "tests/e2e/test_browser.py::test_chat_header_uses_available_title_space_and_groups_assistant_settings",
        "browser": f"{browser.browser_type.name.title()} {browser.version}",
        "playwright": package_version("playwright"),
        "viewports": {"desktop": [1440, 960], "phone": [390, 844]},
        "verified": ["title uses available toolbar width", "assistant settings are grouped in the chat options menu",
                     "phone toolbar has no horizontal overflow", "primary chat controls stay within the toolbar"],
        "page_errors": page_errors, "external_requests": external_requests, "provider_calls": 0,
        "source_sha256": {source: hashlib.sha256((out.parents[3] / source).read_bytes()).hexdigest()
                          for source in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                         "tests/e2e/test_browser.py")},
    }, indent=2) + "\n", encoding="utf-8")
    assert not page_errors
    assert not external_requests
    page.close()


@pytest.mark.parametrize("scenario", ["stable", "changed", "tampered_page_crypto", "selected_file", "insecure_page"])
def test_browser_form_submit_rechecks_the_reviewed_payload_in_chromium(
    browser, store, config, tmp_path, monkeypatch, scenario
):
    """A real DOM-backed form cannot submit a payload changed during approval wait."""
    from hutch.approvals import ApprovalGate, resolve_approval_ex
    from hutch.models import Bot
    from hutch.safety import PolicyEngine
    from hutch.tools.base import ToolContext
    from hutch.tools.browser import BrowserTool

    bot = store.create_bot(Bot(name=f"form-review-{scenario}", tools=["browser"]))
    run = Run(bot_id=bot.id, prompt="Review this message", status=RunStatus.running)
    store.create_run(run)
    page = browser.new_page()
    page_url = "http://example.test/form" if scenario == "insecure_page" else "https://example.test/form"
    form_fields = "<input id='attachment' name='attachment' type='file'>" if scenario == "selected_file" else ""
    page.route(page_url, lambda route: route.fulfill(status=200, content_type="text/html", body=f"""<!doctype html><form action='/messages/send' method='post'>
      <label>Recipient <input id='recipient' name='recipient' type='email' value='person@example.test'></label>
      <label>Password <input id='password' name='password' type='password' value='must-not-leak-this-secret'></label>
      {form_fields}
      <button type='submit'>Send message</button>
      <output id='sent'></output></form>
      <script>document.querySelector('form').addEventListener('submit', e => {{
        e.preventDefault(); document.querySelector('#sent').textContent = 'submitted';
      }});</script>"""))
    page.goto(page_url)
    assert page.evaluate("window.isSecureContext") is (scenario != "insecure_page")
    if scenario == "tampered_page_crypto":
        page.evaluate("crypto.subtle.digest = async () => new Uint8Array(32).buffer")
        assert "new Uint8Array" in page.evaluate("crypto.subtle.digest.toString()")
    if scenario == "selected_file":
        attachment = tmp_path / "fixture-upload.txt"
        attachment.write_text("fixture file data")
        page.locator("#attachment").set_input_files(str(attachment))
    gate = ApprovalGate(store, bot, run, PolicyEngine(), store.append_event, poll_seconds=0.01)
    ctx = ToolContext(bot=bot, run=run, store=store, policy=gate.policy, gate=gate, config=config,
                      workspace=tmp_path / "workspace")
    ctx.workspace.mkdir()

    def decide_in_test(req, _action, **_kwargs):
        if scenario in {"changed", "tampered_page_crypto"}:
            page.locator("#recipient").fill("attacker@example.test")
        assert resolve_approval_ex(store, req.id, True, expected_hash=req.action_hash).won

    monkeypatch.setattr(gate, "_wait", decide_in_test)
    tool = BrowserTool()
    monkeypatch.setattr(tool, "_ensure", lambda _ctx: type("Context", (), {"pages": [page]})())
    result = tool.run({"action": "click", "selector": "button[type=submit]"}, ctx)
    request = store.pending_approvals()
    assert not request
    submitted = page.locator("#sent").inner_text()
    if scenario in {"changed", "tampered_page_crypto"}:
        assert not result.ok and "changed after review" in result.output
        assert submitted == ""
    elif scenario in {"selected_file", "insecure_page"}:
        assert not result.ok
        assert "cannot submit an attached file" in result.output if scenario == "selected_file" else \
               "secure browser form review is unavailable" in result.output
        assert submitted == ""
        assert not store.pending_approvals()
        assert gate.last_authorization is None
        page.close()
        return
    else:
        assert result.ok and submitted == "submitted"
    assert "must-not-leak-this-secret" not in repr(gate.last_authorization)
    detail = gate.last_authorization["detail"]
    assert detail["target_kind"] == "form_submit"
    assert detail["target"]["fields"] == [
        {"label": "Recipient", "type": "email"},
        {"label": "Password", "type": "password", "sensitive": True, "present": True},
    ]
    assert "person@example.test" not in repr(detail)
    assert "attacker@example.test" not in repr(detail)
    assert "must-not-leak-this-secret" not in repr(detail)
    page.close()


def test_form_submission_approval_explains_destination_and_fields_at_all_viewports(browser, live, monkeypatch):
    from hutch.approvals import ApprovalGate
    from hutch.models import ApprovalMode
    from hutch.safety import PolicyEngine

    base, app = live
    store = app.state.store
    bot = store.create_bot(Bot(name="form-approval-review", model="mock/demo", tools=[], approval_mode=ApprovalMode.ask))
    conversation, _ = store.create_conversation(bot.id, "Form review", idem_key="form-review", request_hash="form-review")
    run = Run(bot_id=bot.id, prompt="Send the reviewed message", status=RunStatus.pending,
              conversation_id=conversation["id"])
    store.submit_conversation_message(conversation["id"], run.prompt, run,
        Task(bot_id=bot.id, prompt=run.prompt), idem_key="form-review-turn", request_hash="form-review-turn")
    run = store.get_run(run.id)
    assert run and store.set_status(run, RunStatus.running)
    gate = ApprovalGate(store, bot, run, PolicyEngine(), store.append_event)
    monkeypatch.setattr(gate, "_wait", lambda *_args, **_kwargs: None)
    detail = {
        "action": "click", "selector": "button[type=submit]", "label": "", "url": "https://mail.example.test/compose",
        "profile_bot_id": bot.id, "target_kind": "form_submit",
        "target": {"kind": "form_submit", "label": "Send message", "tag": "button", "type": "submit",
                   "method": "post", "destination": "https://mail.example.test",
                   "fields": [{"label": "Recipient", "type": "email"},
                              {"label": "Password", "type": "password", "sensitive": True, "present": True}]},
        "target_fingerprint": "a" * 64,
    }
    gate.decide("browser", "Submit form to https://mail.example.test (POST) with Send message", detail, outward=True)
    page = browser.new_page(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(base + "/#/chat/form-approval-review")
    card = page.locator("#chat-stream [data-approval-card]").first
    card.wait_for()
    card.locator("summary").click()
    assert "Submit form to https://mail.example.test (POST)" in card.inner_text()
    review = card.locator(".form-review-rows")
    assert "Destination" in card.inner_text() and "Request method" in card.inner_text()
    assert "Recipient" in review.inner_text() and "Password · sensitive value hidden" in review.inner_text()
    assert "person@example.test" not in card.inner_text() and "must-not-leak-this-secret" not in card.inner_text()
    assert not card.locator(".approval-detail").count(), "field values and internal fingerprints stay out of raw review JSON"
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/browser-form-review"
    out.mkdir(parents=True, exist_ok=True)
    captures = []
    phone_decision = None
    for name, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844)):
        page.set_viewport_size({"width": width, "height": height})
        page.screenshot(path=str(out / f"{name}.png"), full_page=True, animations="disabled")
        overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
        assert overflow <= 1
        captures.append({"viewport": name, "size": [width, height], "horizontal_overflow_px": overflow,
                         "screenshot_sha256": hashlib.sha256((out / f"{name}.png").read_bytes()).hexdigest()})
        if name == "phone":
            decision = card.locator('[data-approve="1"]')
            decision.scroll_into_view_if_needed()
            button_box = decision.bounding_box()
            composer_box = page.locator("#composer-box").bounding_box()
            chat_box = page.locator("#chat-scroll").bounding_box()
            assert button_box and composer_box and chat_box
            assert button_box["y"] >= chat_box["y"] - 1
            assert button_box["y"] + button_box["height"] <= composer_box["y"] + 1
            page.screenshot(path=str(out / "phone-decision.png"), animations="disabled")
            phone_decision = {"decision_visible_above_composer": True,
                              "screenshot_sha256": hashlib.sha256((out / "phone-decision.png").read_bytes()).hexdigest()}
    assert not errors, errors
    (out / "results.json").write_text(json.dumps({
        "browser": browser.browser_type.name, "browser_version": browser.version,
        "provider_calls": 0, "human_review_fixture": "local SQLite approval; no external page or provider",
        "sensitive_values_in_review": False, "page_errors": errors, "captures": captures,
        "phone_decision": phone_decision,
        "source_sha256": {name: hashlib.sha256((Path(__file__).resolve().parents[2] / name).read_bytes()).hexdigest()
                          for name in ("src/hutch/tools/browser.py", "src/hutch/server/static/app.js",
                                       "src/hutch/server/static/style.css")},
    }, indent=2) + "\n")
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
    alerts = page.locator("#browser-alerts-disclosure")
    assert alerts.evaluate("el => !el.open"), "notification settings should stay out of the decision queue by default"
    assert page.locator("#browser-alerts-status").is_hidden()
    assert page.locator("#browser-alerts-summary-state").inner_text() == "Off"
    alerts.locator("summary").click()
    page.locator("#browser-alerts-status").get_by_text("Optional alerts", exact=False).wait_for()
    page.locator("#browser-alerts-toggle").click()
    page.locator("#browser-alerts-status").get_by_text("On while Hutch is open", exact=False).wait_for()
    assert page.locator("#browser-alerts-summary-state").inner_text() == "On"
    assert page.evaluate("Notification.permission") == "granted"
    page.screenshot(path=str(out / "notifications-open-desktop.png"), full_page=True, animations="disabled")
    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(path=str(out / "notifications-open-phone.png"), full_page=True, animations="disabled")
    page.set_viewport_size({"width": 1440, "height": 1000})
    alerts.locator("summary").click()
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
    alerts.locator("summary").click()
    page.locator("#browser-alerts-toggle").click()
    page.locator("#browser-alerts-status").get_by_text("Optional alerts", exact=False).wait_for()
    assert page.locator("#browser-alerts-summary-state").inner_text() == "Off"
    assert page.evaluate("JSON.parse(localStorage.getItem('hutch:browser-alerts'))") is False
    page.evaluate("Notification.permission = 'denied'; updateBrowserAlertsUi()")
    assert page.locator("#browser-alerts-summary-state").inner_text() == "Blocked"
    assert page.locator("#browser-alerts-toggle").is_disabled()
    page.evaluate("delete window.Notification; updateBrowserAlertsUi()")
    assert page.locator("#browser-alerts-summary-state").inner_text() == "Unavailable"
    assert page.locator("#browser-alerts-toggle").is_disabled()
    (out / "results.json").write_text(json.dumps({
        "browser": browser.browser_type.name, "browser_version": browser.version,
        "playwright": package_version("playwright"), "provider_calls": 0,
        "notification_api": "test stub; no operating-system permission or notification used",
        "private_action_text_in_notice": False, "duplicate_notices": False,
        "notification_click_opens_review_queue": True,
        "notification_settings_collapsed_by_default": True,
        "notification_settings_captures": ["notifications-open-desktop.png", "notifications-open-phone.png"],
        "page_errors": errors, "captures": records,
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
    card.locator("details.approval-review > summary").click()
    allow = card.locator('[data-approve="1"]')
    allow.focus()
    time.sleep(5.3)  # unchanged queue poll must preserve review and decision focus
    assert card.locator("details.approval-review").get_attribute("open") is not None
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
    wait_for_page(page, "document.querySelectorAll('#chat-stream [data-run-id]').length === 2")
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
    wait_for_page(page, "resourceStream && resourceStream.readyState === EventSource.OPEN")
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
    wait_for_page(page, "feedMode === 'run'")
    page.evaluate("location.hash = '#/bot/resource-replay'")
    open_assistant_customization(page)
    settings = page.locator('#form-instructions textarea[name="instructions"]')
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
    page.get_by_role("heading", name="About this assistant", exact=True).wait_for()
    open_assistant_customization(page)
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
    assert page.locator("#fleet-count").inner_text() == "2 of 10 assistants"
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


@pytest.mark.parametrize("width,height,size", [
    (1440, 960, "desktop"), (768, 960, "tablet"), (360, 844, "phone"), (320, 800, "compact-phone"),
])
def test_chat_discloses_unsupported_image_input_and_preserves_pasted_image_draft(browser, live, width, height, size):
    import hashlib
    import json
    from pathlib import Path
    base, app = live
    app.state.store.create_bot(Bot(name=f"image-input-{size}", model="mock/demo", tools=[]))
    context = browser.new_context(viewport={"width": width, "height": height}, reduced_motion="reduce")
    page = context.new_page()
    page_errors = []
    console_errors = []
    message_posts = []
    external_requests = []
    failed_responses = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
    page.on("request", lambda request: message_posts.append(request.url)
            if request.method == "POST" and request.url.endswith("/messages") else None)
    page.on("request", lambda request: external_requests.append(request.url)
            if urlsplit(request.url).hostname not in {"127.0.0.1", "localhost"} else None)
    page.on("response", lambda response: failed_responses.append({"url": response.url, "status": response.status})
            if response.status >= 400 else None)
    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/persona-image-input-unsupported"
    out.mkdir(parents=True, exist_ok=True)
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    trace_active = True
    try:
        page.goto(base + f"/#/chat/image-input-{size}")
        page.locator("#conversation-switcher").wait_for()
        page.locator("#composer-menu-btn").click()
        menu = page.locator("#composer-menu")
        menu.wait_for(state="visible")
        note = menu.locator(".cmenu-image-note")
        assert note.get_attribute("role") == "note"
        assert note.inner_text() == "Image attachments aren’t available in chat yet. Describe an image in text instead."
        box = menu.bounding_box()
        assert box and box["x"] >= 0 and box["x"] + box["width"] <= width + 1
        assert box["y"] >= 0 and box["y"] + box["height"] <= height + 1
        assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
        page.screenshot(path=str(out / f"options-{size}.png"), full_page=True, animations="disabled")

        prompt = page.locator("#chat-prompt")
        draft = "Keep this description while an image cannot be attached"
        prompt.fill(draft)
        paste_prevented = prompt.evaluate("""el => {
          const transfer = new DataTransfer();
          transfer.items.add(new File(["fixture"], "fixture.png", {type: "image/png"}));
          const event = new ClipboardEvent("paste", {clipboardData: transfer, bubbles: true, cancelable: true});
          el.dispatchEvent(event);
          return event.defaultPrevented;
        }""")
        assert paste_prevented and prompt.input_value() == draft
        assert "Image attachments aren’t available" in page.locator("#toast-root").inner_text()
        assert message_posts == [], "an unsupported image must not be submitted or trigger model inference"
        assert not page_errors and not console_errors and not external_requests and not failed_responses
        context.tracing.stop(path=str(out / f"trace-{size}.zip"))
        trace_active = False
        (out / f"validation-{size}.json").write_text(json.dumps({
            "test": "test_chat_discloses_unsupported_image_input_and_preserves_pasted_image_draft",
            "browser": f"{browser.browser_type.name.title()} {browser.version}",
            "viewport": [width, height], "horizontal_overflow_px": page.evaluate("document.documentElement.scrollWidth - innerWidth"),
            "dom_note": note.inner_text(), "paste_prevented": paste_prevented,
            "draft_preserved": prompt.input_value() == draft, "message_posts": message_posts,
            "page_errors": page_errors, "console_errors": console_errors,
            "external_requests": external_requests, "failed_responses": failed_responses,
            "source_sha256": {relative: hashlib.sha256((out.parents[3] / relative).read_bytes()).hexdigest()
                for relative in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                 "src/hutch/data/presets.json", "tests/e2e/test_browser.py")},
        }, indent=2) + "\n")
    finally:
        if trace_active:
            try:
                context.tracing.stop(path=str(out / f"trace-{size}-failed.zip"))
            except Exception:
                pass
        context.close()


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
        wait_for_page(page, "document.activeElement?.dataset.receiptReview !== undefined")
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


def test_workflow_owned_uncertain_effect_is_reviewable_without_rewriting_workflow(browser, live, monkeypatch):
    """A workflow receipt reaches the owner review UI without granting another action."""
    import hashlib
    import json
    from pathlib import Path

    from hutch.workflow import persistence as wstore
    from hutch.workflow import submit as workflow_submit
    from hutch.workflow.runtime import _settle as settle_workflow

    base, app = live
    store = app.state.store
    monkeypatch.setattr(app.state.engine, "tick", lambda: None)
    bot = store.create_bot(Bot(name="workflow-effect-review", model="mock/demo", tools=["shell"]))
    conversation, _ = store.create_conversation(
        bot.id, "Workflow effect review", idem_key="workflow-review-conversation",
        request_hash="workflow-review-conversation-v1")
    plan = {
        "name": "uncertain-report-publish",
        "envelope": {"tools": ["shell"]},
        "budget": {"max_nodes": 4, "max_model_calls": 0},
        "nodes": [{"kind": "tool", "id": "publish", "tool": "shell",
                   "args": {"command": "publish report"}}],
    }
    submitted = workflow_submit.submit_workflow(
        store, bot=bot, plan=plan, definition_name=plan["name"],
        conversation_id=conversation["id"])
    attempt = store.claim_run(submitted.attempt_run_id, "workflow-review-fixture", 60)
    assert attempt is not None
    attempt = store.transition_run(attempt.id, RunStatus.running, fence=attempt.fence)
    workflow = wstore.workflow_run(store, submitted.workflow_run_id)
    assert workflow is not None
    assert wstore.claim_workflow_attempt(
        store, workflow["id"], attempt_run_id=attempt.id,
        owner_fence=attempt.fence, revision_id=workflow["revision_id"])
    wstore.open_node(
        store, workflow["id"], owner_run_id=attempt.id, owner_fence=attempt.fence,
        revision_id=workflow["revision_id"], site_id="publish", instance_key="once",
        kind="tool", input_value={"command": "publish report"}, input_hash="c" * 64)
    action_id = store.begin_action(
        attempt.id, "shell", "workflow-effect-before-response", "process", "Publish the checked report",
        fence=attempt.fence, arguments={"command": "publish report"},
        authority={"source": "fixture", "detail": {"reviewed": True}},
        scope={"workspace": "isolated-review-fixture"},
        workflow_identity={"workflow_run_id": workflow["id"], "revision_id": workflow["revision_id"],
                           "site_id": "publish", "instance_key": "once", "slot": "tool"})
    # This browser fixture creates the durable uncertain state directly. Process-crash
    # behavior and duplicate-effect prevention are independently tested with a real sink.
    settle_workflow(store, workflow["id"], attempt, revision_id=workflow["revision_id"],
                    status="outcome_unknown", reason="the effect response was not recorded",
                    output_sites=["publish"])
    attempt = store.transition_run(
        attempt.id, RunStatus.outcome_unknown, fence=attempt.fence,
        exit_reason="outcome_unknown", error="the effect response was not recorded")
    assert store.get_action(action_id)["status"] == "unknown"
    assert wstore.workflow_run(store, workflow["id"])["status"] == "outcome_unknown"
    sealed_chain = store.verify_chain(attempt.id)

    artifacts = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/workflow-effect-review-20261012"
    artifacts.mkdir(parents=True, exist_ok=True)
    errors, failed_requests = [], []
    context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
    page = context.new_page()
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.on("requestfailed", lambda request: failed_requests.append({"url": request.url,
                                                                       "failure": request.failure}))
    try:
        page.goto(f"{base}/#/run/{attempt.id}")
        run_card = page.locator(f'[data-run-id="{attempt.id}"]')
        receipt = run_card.locator(f'[data-receipt-card="{action_id}"]')
        receipt.wait_for()
        assert "Action outcome needs review" in receipt.inner_text()
        assert "may already have happened" in receipt.inner_text()
        page.screenshot(path=str(artifacts / "desktop-unresolved.png"), full_page=True)

        page.reload()
        receipt.wait_for()
        page.locator("#needs-you-open").click()
        queued_receipt = page.locator(f'#needs-you [data-receipt-card="{action_id}"]')
        queued_receipt.wait_for()
        assert "Publish the checked report" in queued_receipt.inner_text()
        page.screenshot(path=str(artifacts / "desktop-needs-you.png"), full_page=True)
        review_button = queued_receipt.get_by_role("button", name="Review action outcome", exact=True)
        review_button.focus()
        page.keyboard.press("Enter")
        page.locator("#receipt-outcome").wait_for()
        page.locator(".modal-card details summary").first.click()
        saved_details = page.locator(".receipt-json").inner_text()
        assert workflow["id"] in saved_details and '"site_id": "publish"' in saved_details
        assert "Check the file, account or service involved" in page.locator(".modal-card").inner_text()
        page.screenshot(path=str(artifacts / "desktop-review-dialog.png"), full_page=True)
        page.locator("#receipt-outcome").select_option("not_applied")
        page.locator("#receipt-evidence").fill(
            "Checked the isolated effect sink after the run ended; no publish record exists.")
        page.locator("#modal-confirm").click()
        page.locator(".modal-card").wait_for(state="detached")
        page.get_by_role("button", name="View recorded outcome", exact=True).wait_for()

        report = store.get_action(action_id)
        assert report["status"] == "unknown"
        assert report["reconciliation"]["outcome"] == "not_applied"
        assert store.get_run(attempt.id).status is RunStatus.outcome_unknown
        assert wstore.workflow_run(store, workflow["id"])["status"] == "outcome_unknown"
        assert store.verify_chain(attempt.id) == sealed_chain
        reviewed_receipt = run_card.locator(f'[data-receipt-card="{action_id}"]')
        assert "No effect found · human report" in reviewed_receipt.inner_text()

        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(120)
        phone_metrics = page.evaluate("() => ({client: document.documentElement.clientWidth, "
                                       "scroll: document.documentElement.scrollWidth})")
        assert phone_metrics["scroll"] <= phone_metrics["client"] + 1, phone_metrics
        page.screenshot(path=str(artifacts / "phone-reviewed.png"), full_page=True)
    finally:
        context.tracing.stop(path=str(artifacts / "trace.zip"))
        context.close()

    root = Path(__file__).resolve().parents[2]
    source_paths = [root / path for path in (
        "tests/e2e/test_browser.py", "src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
        "src/hutch/server/app.py", "src/hutch/store.py", "src/hutch/workflow/runtime.py",
        "src/hutch/workflow/persistence.py")]
    artifact_paths = [artifacts / name for name in (
        "desktop-unresolved.png", "desktop-needs-you.png", "desktop-review-dialog.png",
        "phone-reviewed.png", "trace.zip")]
    validation = {
        "test": "tests/e2e/test_browser.py::test_workflow_owned_uncertain_effect_is_reviewable_without_rewriting_workflow",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "browser": {"name": browser.browser_type.name, "version": browser.version},
        "fixture": {"workflow_run_id": workflow["id"], "revision_id": workflow["revision_id"],
                    "attempt_run_id": attempt.id, "attempt_status": attempt.status.value,
                    "node": "publish", "action_id": action_id, "external_effect_calls": 0},
        "human_review": {"outcome": report["reconciliation"]["outcome"],
                         "workflow_status_unchanged": True, "run_status_unchanged": True,
                         "transcript_chain_unchanged": True},
        "phone_view": {"viewport": [390, 844], "client_width": phone_metrics["client"],
                       "document_width": phone_metrics["scroll"]},
        "console_errors": errors,
        "failed_requests": failed_requests,
        "source_sha256": {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in source_paths},
        "artifact_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in artifact_paths},
    }
    (artifacts / "validation.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    assert errors == []
    assert failed_requests == []


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


def test_explicit_cross_bot_fact_share_is_reviewable_revocable_and_responsive(browser, live):
    from pathlib import Path
    from hutch.store import Store
    base, application = live
    store = application.state.store
    source = store.create_bot(Bot(name='research-partner', display_name='Research Partner', tools=['memory']))
    target = store.create_bot(Bot(name='brief-writer', display_name='Brief Writer', tools=['memory']))
    source_conversation, _ = store.create_conversation(source.id, 'Research notes', idem_key='share-source-chat',
                                                        request_hash='source')
    target_conversation, _ = store.create_conversation(target.id, 'Draft brief', idem_key='share-target-chat',
                                                        request_hash='target')
    run = store.create_run(Run(bot_id=source.id, conversation_id=source_conversation['id'],
                               prompt='synthetic reviewed fact', status=RunStatus.running))
    fact = store.remember(source.id, 'Preferred reference', 'Use the vendor security guide.',
                          run_id=run.id, expected_fence=0)
    store.transition_run(run.id, RunStatus.succeeded, fence=0)
    store.review_fact(source.id, fact.id, content_hash=fact.content_hash, action='approve', actor='fixture')
    out = Path(__file__).resolve().parents[2] / 'docs/realignment/artifacts/fact-sharing'
    out.mkdir(parents=True, exist_ok=True)
    sizes = {'desktop': (1440, 960), 'tablet': (900, 1024), 'phone': (390, 844)}
    context = browser.new_context(viewport={'width': 1440, 'height': 960}, reduced_motion='reduce')
    page = context.new_page()
    errors, external, trace = [], [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda request: external.append(request.url) if not request.url.startswith(base) else None)
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    trace_stopped = False
    try:
        page.goto(f'{base}/#/chat/{source.name}')
        page.locator('#conversation-switcher').select_option(source_conversation['id'])
        page.locator('.fact-panel details summary').first.click()
        trigger = page.locator(f'[data-fact-share-create="{fact.id}"]')
        trigger.wait_for()
        trigger.focus(); page.keyboard.press('Enter')
        dialog = page.get_by_role('dialog', name='Share this reference with a Bot')
        dialog.wait_for()
        assert 'Use the vendor security guide.' in dialog.inner_text()
        assert 'untrusted reference data' in dialog.inner_text()
        assert 'grants no tool permission' in dialog.inner_text()
        assert dialog.locator('#fact-share-target').locator('option').all_inner_texts() == ['Brief Writer']
        for label, (width, height) in sizes.items():
            page.set_viewport_size({'width': width, 'height': height})
            assert page.evaluate('document.documentElement.scrollWidth - innerWidth') <= 1, label
            page.screenshot(path=str(out / f'share-review-{label}.png'), full_page=True, animations='disabled')
            trace.append({'viewport': label, 'size': [width, height], 'state': 'share_review',
                          'horizontal_overflow': page.evaluate('document.documentElement.scrollWidth - innerWidth')})
        page.keyboard.press('Escape')
        wait_for_page(page, 'document.activeElement?.dataset.factShareCreate !== undefined')
        trigger = page.locator(f'[data-fact-share-create="{fact.id}"]')
        trigger.click()
        page.get_by_role('dialog', name='Share this reference with a Bot').locator('#fact-share-target').select_option(label='Brief Writer')
        with page.expect_response(lambda response: response.request.method == 'POST' and response.url.endswith('/shares')) as created:
            page.locator('#modal-confirm').click()
        assert created.value.status == 201, created.value.text()
        share = created.value.json()
        assert share['state'] == 'active' and share['fact_revision'] == fact.revision
        page.locator('.fact-share-list summary').wait_for()
        page.locator('.fact-share-list summary').click()
        outgoing = page.locator(f'[data-fact-share-card="{share["id"]}"]')
        outgoing.wait_for()
        assert 'Shared with Brief Writer' in outgoing.inner_text()
        for label, (width, height) in sizes.items():
            page.set_viewport_size({'width': width, 'height': height})
            outgoing.scroll_into_view_if_needed()
            overflow = page.evaluate('document.documentElement.scrollWidth - innerWidth')
            assert overflow <= 1, label
            page.screenshot(path=str(out / f'source-{label}.png'), full_page=True, animations='disabled')
            trace.append({'viewport': label, 'size': [width, height], 'state': 'outgoing_share',
                          'horizontal_overflow': overflow})

        persisted = Store(application.state.config)
        try:
            target_recall = persisted.recall_fact_page(target.id, conversation_id=target_conversation['id'],
                                                       query='vendor', limit=20)
            assert target_recall[0]['share_id'] == share['id']
            assert target_recall[0]['shared_from'] == 'Research Partner'
        finally:
            persisted.close()

        page.goto(f'{base}/#/chat/{target.name}')
        page.locator('#conversation-switcher').select_option(target_conversation['id'])
        page.locator('.fact-share-list summary').wait_for()
        page.locator('.fact-share-list summary').click()
        incoming = page.locator(f'[data-fact-share-card="{share["id"]}"]')
        incoming.wait_for()
        assert 'Shared by Research Partner' in incoming.inner_text()
        assert 'untrusted data' in incoming.inner_text()
        recall = store.recall_fact_page(target.id, conversation_id=target_conversation['id'], query='vendor', limit=20)
        assert recall[0]['share_id'] == share['id']
        for label, (width, height) in sizes.items():
            page.set_viewport_size({'width': width, 'height': height})
            incoming.scroll_into_view_if_needed()
            overflow = page.evaluate('document.documentElement.scrollWidth - innerWidth')
            assert overflow <= 1, label
            page.screenshot(path=str(out / f'recipient-{label}.png'), full_page=True, animations='disabled')
            trace.append({'viewport': label, 'size': [width, height], 'state': 'incoming_share',
                          'horizontal_overflow': overflow})
        incoming.get_by_role('button', name='Remove shared fact').click()
        page.get_by_role('dialog', name='Remove shared reference?').wait_for()
        with page.expect_response(lambda response: response.request.method == 'DELETE' and '/fact-shares/' in response.url) as revoked:
            page.locator('#modal-confirm').click()
        assert revoked.value.status == 200, revoked.value.text()
        assert store.recall_fact_page(target.id, conversation_id=target_conversation['id'], query='vendor', limit=20) == []
        assert not errors and not external
        context.tracing.stop(path=str(out / 'trace.zip'))
        trace_stopped = True
        (out / 'results.json').write_text(json.dumps({
            'test': 'tests/e2e/test_browser.py::test_explicit_cross_bot_fact_share_is_reviewable_revocable_and_responsive',
            'command': 'uv run pytest -q tests/e2e/test_browser.py::test_explicit_cross_bot_fact_share_is_reviewable_revocable_and_responsive',
            'browser': browser.browser_type.name, 'browser_version': browser.version,
            'playwright_version': package_version('playwright'), 'viewports': trace,
            'page_errors': errors, 'external_requests': external, 'provider_calls': 0,
            'scenario': 'Locally seeded reviewed fact is explicitly granted to a named Bot; exact snapshot and provenance survive a fresh Store connection; recipient can revoke; retrieval stops immediately.',
            'captures': [f'{screen}-{size}.png' for screen in ('share-review', 'source', 'recipient') for size in sizes],
            'source_sha256': {name: hashlib.sha256((out.parents[3] / name).read_bytes()).hexdigest() for name in (
                'src/hutch/store.py', 'src/hutch/fact_memory.py', 'src/hutch/tools/memory.py',
                'src/hutch/server/app.py', 'src/hutch/server/static/app.js', 'src/hutch/server/static/style.css')},
        }, indent=2) + '\n', encoding='utf-8')
    finally:
        if not trace_stopped:
            try:
                context.tracing.stop(path=str(out / 'trace.zip'))
            except Exception:
                pass
        context.close()


@pytest.mark.parametrize('label,width,height', [('desktop',1440,960),('tablet',900,1024),('phone',390,844)])
def test_bot_memory_export_explains_scope_and_downloads_complete_json(browser, live, tmp_path, label, width, height):
    import hashlib
    import json
    from pathlib import Path

    base, application = live
    store = application.state.store
    bot = store.create_bot(Bot(name=f'memory-export-{label}', display_name='Memory Export', tools=['memory']))
    current = store.remember(bot.id, 'report_style', 'Use concise headings and short bullets.')
    archived = store.remember(bot.id, 'old_project', 'Keep the historical project reference.')
    store.review_fact(bot.id, archived.id, content_hash=archived.content_hash, action='archive', actor='operator')

    page = browser.new_page(viewport={'width':width,'height':height}, reduced_motion='reduce')
    page.set_default_timeout(8000)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.context.tracing.start(screenshots=True, snapshots=True, sources=False)
    trace_stopped = False
    try:
        page.goto(f'{base}/#/bot/{bot.name}')
        open_assistant_customization(page)
        download_button = page.get_by_role('button', name='Download memory JSON')
        download_button.wait_for()
        page.locator('#memory-toggle').wait_for()
        download_button.click()
        dialog = page.get_by_role('dialog', name='Export Bot memory')
        dialog.get_by_text('unencrypted plaintext', exact=False).wait_for()
        dialog.get_by_text('Archived fact versions and review history', exact=False).wait_for()
        dialog.get_by_text('conversation transcripts, credentials, action receipts, and workspace files', exact=False).wait_for()
        metrics = page.evaluate("""() => ({
          viewport:[innerWidth,innerHeight], document:[document.documentElement.scrollWidth,document.documentElement.scrollHeight],
          button:document.querySelector('#memory-export')?.getBoundingClientRect().toJSON(),
          confirm:document.querySelector('#modal-confirm')?.getBoundingClientRect().toJSON(),
          modal:document.querySelector('.modal-card')?.getBoundingClientRect().toJSON(),
          body: {scroll:document.querySelector('.modal-body')?.scrollHeight, client:document.querySelector('.modal-body')?.clientHeight}
        })""")
        assert metrics['document'][0] - metrics['viewport'][0] <= 1, (label, metrics)
        assert 0 <= metrics['confirm']['top'] and metrics['confirm']['bottom'] <= metrics['viewport'][1], (label, metrics)
        if width <= 640:
            assert metrics['button']['height'] >= 44 and metrics['confirm']['height'] >= 44, metrics

        out = Path(__file__).resolve().parents[2] / 'docs/realignment/artifacts/bot-memory-export'
        out.mkdir(parents=True, exist_ok=True)
        screenshot = out / f'{label}.png'
        trace = out / f'{label}-trace.zip'
        page.screenshot(path=str(screenshot), animations='disabled')
        with page.expect_download() as download_info:
            dialog.get_by_role('button', name='Download JSON').click()
        download = download_info.value
        assert download.suggested_filename == f'hutch-memory-{bot.name}.json'
        saved = tmp_path / download.suggested_filename
        download.save_as(str(saved))
        payload = json.loads(saved.read_text(encoding='utf-8'))
        assert payload['bot']['id'] == bot.id
        assert {fact['id'] for fact in payload['facts']} == {current.id, archived.id}
        assert next(fact for fact in payload['facts'] if fact['id'] == archived.id)['status'] == 'archived'
        assert any(review['fact_id'] == archived.id and review['action'] == 'archive'
                   for review in payload['reviews'])
        assert page.evaluate('document.activeElement?.id') == 'memory-export'
        assert not errors, errors

        page.context.tracing.stop(path=str(trace))
        trace_stopped = True
        repo = Path(__file__).resolve().parents[2]
        (out / f'{label}.json').write_text(json.dumps({
            'test':'tests/e2e/test_browser.py::test_bot_memory_export_explains_scope_and_downloads_complete_json',
            'browser':browser.browser_type.name, 'browser_version':browser.version,
            'viewport':[width,height], 'page_errors':errors, 'horizontal_overflow_px':metrics['document'][0]-width,
            'facts_exported':len(payload['facts']), 'reviews_exported':len(payload['reviews']),
            'provider_calls':0, 'screenshot':screenshot.name, 'trace':trace.name,
            'source_sha256':{name:hashlib.sha256((repo/name).read_bytes()).hexdigest() for name in (
                'src/hutch/server/app.py','src/hutch/store.py','src/hutch/server/static/app.js',
                'src/hutch/server/static/style.css')},
        },indent=2)+'\n',encoding='utf-8')
    finally:
        if not trace_stopped:
            page.context.tracing.stop()
        page.context.close()


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
        wait_for_page(page, "document.querySelectorAll('#receipts-pending [data-receipt-card]').length === 2")
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
    bot = store.create_bot(Bot(name="reply-fixture", display_name="Project Delivery Partner",
                               model="mock/demo", tools=[]))
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

    out = Path(__file__).resolve().parents[2] / "docs/realignment/artifacts/reply-quote-polish-2026-10-10"
    out.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": width, "height": height}, reduced_motion="reduce",
                                  has_touch=(size == "phone"))
    page = context.new_page()
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"{base}/#/chat/{bot.name}")
    details_link = page.get_by_role("link", name="View work details")
    details_link.wait_for(state="visible")
    assert details_link.get_attribute("href") == f"#/run/{run.id}"
    assert run.id not in page.locator(f".thread[data-run-id='{run.id}']").inner_text()
    if size == "phone":
        details_bounds = details_link.bounding_box()
        assert details_bounds["width"] >= 44 and details_bounds["height"] >= 44
    reply = page.get_by_role("button", name=f"Reply to {bot_label} message")
    reply.wait_for(state="visible")
    reply.focus()
    page.keyboard.press("Enter")
    preview = page.locator("#reply-composer")
    preview.wait_for(state="visible")
    assert "migration finished successfully" in page.locator("#reply-composer-preview").inner_text()
    assert f"Replying to {bot_label}" in page.locator("#reply-composer-preview").inner_text()
    assert "reply-fixture" not in page.locator("#reply-composer-preview").inner_text()
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
    wait_for_page(page, """async ({conversationId, sourceId}) => {
      const r = await fetch(`/api/v1/conversations/${conversationId}?after=0&limit=100`);
      if (!r.ok) return false;
      const page = await r.json();
      return page.messages.some(message => message.role === 'user'
        && message.content === 'Can you explain that result?'
        && message.reply_to_message_id === sourceId);
    }""", arg={"conversationId": conversation["id"], "sourceId": "reply-fixture-answer"})
    assert page.locator("#toast-root .toast").count() == 0, "The sent message itself confirms ordinary send success."
    assert preview.is_hidden()
    anchored = page.locator(".reply-reference-quote")
    anchored.wait_for(state="visible")
    assert "The migration finished successfully" in anchored.inner_text()
    quote_height = anchored.bounding_box()["height"]
    assert quote_height <= 140, f"A short reply reference should stay compact; rendered at {quote_height:.1f}px"
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
        answer_run = response.json()
        answer_card = page.locator(f'#chat-stream [data-run-id="{answer_run["id"]}"]')
        answer_bubble = answer_card.locator(".msg.you .bubble")
        answer_bubble.wait_for(state="visible")
        wait_for_page(page, """() => {
          const scroll = document.querySelector('#chat-scroll');
          const bubble = [...document.querySelectorAll('#chat-stream .thread')].at(-1)?.querySelector('.msg.you .bubble');
          const composer = document.querySelector('.composer');
          if (!scroll || !bubble || !composer) return false;
          const bubbleRect = bubble.getBoundingClientRect();
          const composerRect = composer.getBoundingClientRect();
          return scroll.scrollTop + scroll.clientHeight >= scroll.scrollHeight - 2
            && bubbleRect.bottom <= composerRect.top + 1;
        }""")
        answer_scroll = page.evaluate("""() => {
          const scroll = document.querySelector('#chat-scroll');
          const bubble = [...document.querySelectorAll('#chat-stream .thread')].at(-1)?.querySelector('.msg.you .bubble');
          const composer = document.querySelector('.composer');
          return {
            at_latest: scroll.scrollTop + scroll.clientHeight >= scroll.scrollHeight - 2,
            answer_above_composer: bubble.getBoundingClientRect().bottom <= composer.getBoundingClientRect().top + 1,
          };
        }""")
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
                          "selected_labels": ["Risks", "Timeline"], "horizontal_overflow": overflow,
                          "answer_scroll": answer_scroll})

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
