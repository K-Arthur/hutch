"""The Studio transcript in the real browser: the thread, its steps, its gates and its bubbles.

Fixtures are clearly synthetic runs written straight into the store (no model is contacted), the same
pattern as tests/e2e/test_experience_surfaces.py. Contracts pinned here are the ones the redesign made:

* answers render safe Markdown (inert HTML, working Copy) -- unit coverage in tests/test_studio_markdown.py;
* every tool call is a step card with a plain-language title, a state word, an exit code and a measured
  duration, and expands to the exact request and the full output;
* a permission request shows the exact content up front and keeps its Allow once / Deny semantics;
* the header states each fact once (no status chip, no repeated needs-you count);
* long requests clamp, and every control's accessible name contains its visible text (WCAG 2.5.3).
"""

from __future__ import annotations

from datetime import timedelta

import pytest

pw = pytest.importorskip("playwright.sync_api")
expect = pw.expect

from hutch.approvals import action_fingerprint  # noqa: E402
from hutch.models import (ApprovalRequest, Event, EventType, Run, RunStatus, Task, iso, utcnow)  # noqa: E402
from tests.e2e.test_design_system import app_server, browser  # noqa: E402,F401

BOT = "design-system-review"


def _seed(app, key, prompt, steps=(), *, answer=None, status=RunStatus.succeeded, approval=None, started_s_ago=120):
    """steps: (tool, args, output|None, ok, seconds). Returns (conversation_id, run)."""
    store = app.state.store
    app.state.engine.tick = lambda: None            # seeded runs keep the state they are given
    bot = store.get_bot(BOT)
    conv, _ = store.create_conversation(bot.id, key, idem_key=f"c-{key}", request_hash=f"c-{key}")
    run = Run(bot_id=bot.id, prompt=prompt)
    store.submit_conversation_message(conv["id"], prompt, run, Task(bot_id=bot.id, kind="conversation", prompt=prompt),
                                      idem_key=f"t-{key}", request_hash=f"t-{key}")
    store.transition_run(run.id, RunStatus.running)
    at = utcnow() - timedelta(seconds=started_s_ago)
    for tool, args, output, ok, seconds in steps:
        store.append_event(Event(run_id=run.id, type=EventType.tool_call, ts=iso(at), data={"tool": tool, "args": args}))
        if output is not None:
            at += timedelta(seconds=seconds)
            store.append_event(Event(run_id=run.id, type=EventType.tool_result, ts=iso(at),
                                     data={"tool": tool, "ok": ok, "output": output}))
        at += timedelta(milliseconds=200)
    if approval:
        detail = approval["detail"]
        store.create_approval(ApprovalRequest(
            run_id=run.id, bot_id=bot.id, tool=approval["tool"], action=approval["action"], detail=detail,
            rule=approval.get("rule", ""), risk=approval.get("risk", "medium"), sticky_key=approval.get("sticky_key", ""),
            outward=approval.get("outward", False), expires_at=iso(utcnow() + timedelta(minutes=8)),
            action_hash=action_fingerprint(approval["tool"], detail, approval.get("sticky_key", ""), approval.get("outward", False)),
        ), begin_wait=True)
    elif answer:
        store.append_event(Event(run_id=run.id, type=EventType.message, ts=iso(at), data={"role": "assistant", "content": answer}))
    if not approval:
        store.transition_run(run.id, status, exit_reason="completed" if status is RunStatus.succeeded else "failed",
                             **({"error": "The run stopped."} if status is RunStatus.failed else {}))
    store.flush_events()
    return conv["id"], run


@pytest.fixture()
def context(browser, app_server):   # depends on app_server so the page closes before the server stops
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, reduced_motion="reduce")
    ctx.grant_permissions(["clipboard-read", "clipboard-write"])
    yield ctx
    ctx.close()


def _open(context, base, conversation_id):
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.add_init_script("window.__hutchXss = 0")
    page.goto(f"{base}/#/conversation/{conversation_id}", wait_until="domcontentloaded")
    page.locator("#chat-stream [data-run-id]").first.wait_for(timeout=20_000)
    return page, errors


ANSWER = """## Findings

You have **3 focus blocks** and one clash. See [the notes](https://example.org/week) or [bad](javascript:window.__hutchXss=1).

1. Move the Thursday sync.
2. Block Monday morning.

| Day | Hours |
|:--|--:|
| Mon | 2 |

```bash
git log --oneline | head -3
```

<img src=x onerror="window.__hutchXss=2"> and <script>window.__hutchXss=3</script>"""


def test_answer_renders_markdown_inertly_and_code_can_be_copied(context, app_server):
    base, app = app_server
    conversation, _ = _seed(app, "markdown", "Plan my week", answer=ANSWER)
    page, errors = _open(context, base, conversation)
    answer = page.locator("#chat-stream .answer").first
    expect(answer.locator("h2")).to_have_text("Findings")
    assert answer.locator("strong").inner_text() == "3 focus blocks"
    assert answer.locator("ol li").count() == 2
    assert answer.locator(".md-table th").count() == 2
    link = answer.locator('a[href="https://example.org/week"]')
    assert link.get_attribute("rel") == "noopener noreferrer" and link.get_attribute("target") == "_blank"
    # untrusted markup stays text: no unsafe link, no elements, nothing executed
    assert answer.locator('a[href^="javascript:"]').count() == 0
    assert answer.locator("img, script, iframe").count() == 0
    assert "<script>" in answer.inner_text()
    page.wait_for_timeout(150)
    assert page.evaluate("window.__hutchXss") == 0
    # the fenced block is labelled and its Copy control copies exactly the code
    block = answer.locator("[data-md-code]").first
    assert block.locator(".md-code-lang").inner_text() == "bash"
    block.get_by_role("button", name="Copy bash code").click()
    expect(block.locator("[data-md-copy]")).to_have_text("Copied")
    assert page.evaluate("navigator.clipboard.readText()") == "git log --oneline | head -3"
    assert not errors, errors


def test_tool_calls_are_step_cards_with_exact_request_result_and_measured_time(context, app_server):
    base, app = app_server
    conversation, run = _seed(app, "steps", "Run the parser tests", [
        ("list_files", {"path": "src"}, "src/parser.py\nsrc/lexer.py", True, 0.2),
        ("shell", {"command": "pytest -q tests/test_parser.py"}, "exit=1\nF\n1 failed in 0.31s", False, 3.2),
    ], answer="The nested-group test fails.")
    page, errors = _open(context, base, conversation)
    summary = page.locator("details.tool-stream > summary")
    expect(summary).to_contain_text("2 steps")
    rows = page.locator(".tool-line[data-tool-line]")
    expect(rows).to_have_count(2)
    ok_row, failed_row = rows.nth(0), rows.nth(1)
    assert ok_row.get_attribute("class").split()[1] == "success"
    assert failed_row.locator(".tool-name").inner_text() == "Ran a command"
    assert failed_row.locator(".tool-args-text").inner_text() == "pytest -q tests/test_parser.py"
    assert failed_row.locator(".tool-exit").inner_text() == "exit 1"
    assert failed_row.locator(".tool-fail").inner_text() == "Failed"          # a word, not only a colour
    assert failed_row.locator(".tool-time").inner_text() == "3.2s"            # measured from the two events
    # collapsed by default; expanding shows the exact request and the full output
    assert page.locator(".tool-line-body").first.is_hidden()
    failed_row.locator(".tool-line-head").click()
    body = failed_row.locator(".tool-line-body")
    expect(body).to_be_visible()
    assert body.locator(".tcmd").inner_text().strip() == "pytest -q tests/test_parser.py"
    output = body.locator(".tool-res")
    assert "1 failed in 0.31s" in output.inner_text()
    output.get_by_role("button", name="Copy output").click()
    assert page.evaluate("navigator.clipboard.readText()") == "exit=1\nF\n1 failed in 0.31s"
    # raw input is one toggle away
    body.get_by_role("button", name="Raw").click()
    assert '"command": "pytest -q tests/test_parser.py"' in body.locator(".traw").inner_text()
    assert not errors, errors


def test_gate_shows_exact_content_up_front_and_keeps_decision_semantics(context, app_server):
    base, app = app_server
    content = "# Q3 brief\n\n- one\n- two\n"
    conversation, run = _seed(app, "gate", "Save the brief", [
        ("list_files", {"path": "."}, "(empty)", True, 0.1),
    ], approval=dict(tool="files", action="write q3-brief.md (24 chars)", rule="ask:file-write", risk="medium",
                     sticky_key="files:write", detail={"path": "q3-brief.md", "content": content, "revision": {"exists": False}}))
    page, errors = _open(context, base, conversation)
    card = page.locator("#chat-stream [data-approval-card]").first
    card.locator('[data-approve="1"]').wait_for()
    assert card.get_attribute("role") == "group"
    # the exact content and whether it is new are visible without opening anything
    preview = card.locator(".gate-preview")
    expect(preview).to_be_visible()
    assert preview.locator(".gate-path").inner_text() == "q3-brief.md"
    assert "New file" in preview.inner_text()
    assert "- one" in preview.locator("code").inner_text()
    assert "Changing a file needs your okay." in card.inner_text()
    assert card.locator(".gate-tags").get_by_text("stays on this computer").count() == 1
    # the three decisions, by name, each tied to the action
    for name in ("Allow once", "Always allow for this bot", "Deny"):
        assert card.get_by_role("button", name=name).is_visible(), name
    # the header repeats nothing: no status chip, and the thread's own status carries the state
    assert page.locator(".app-top .ctx-meta .status").count() == 0
    assert "Waiting for you" in page.locator("#chat-stream .mhead .status").first.inner_text()
    expect(page.locator(".app-top .ctx-id > .avatar")).to_have_attribute("data-state", "waiting")
    # denying records the decision and flattens the gate into a ledger row
    card.locator('[data-approve="0"]').click()
    ledger = page.locator("#chat-stream .approval-card-chat.resolved")
    ledger.wait_for(timeout=15_000)
    assert "Denied" in ledger.first.inner_text()
    assert app.state.store.get_approval(card.get_attribute("data-approval-card")).status.value == "denied"
    assert not errors, errors


def test_long_request_clamps_and_expands_and_controls_name_their_visible_text(context, app_server):
    base, app = app_server
    long_prompt = "Please compare the vendors.\n" + "\n".join(f"Point {i}: keep it short and sourced." for i in range(1, 14))
    conversation, _ = _seed(app, "long", long_prompt, answer="Done.")
    page, errors = _open(context, base, conversation)
    bubble = page.locator("#chat-stream .bubble.is-long")
    expect(bubble).to_have_count(1)
    clamped = bubble.bounding_box()["height"]
    toggle = page.locator("#chat-stream [data-bubble-toggle]")
    expect(toggle).to_have_attribute("aria-expanded", "false")
    toggle.click()
    expect(toggle).to_have_attribute("aria-expanded", "true")
    expect(toggle).to_have_text("Show less")
    assert bubble.bounding_box()["height"] > clamped + 40
    # the full text was never removed from the page
    assert "Point 13: keep it short and sourced." in bubble.text_content()
    # WCAG 2.5.3: a control's accessible name must contain its visible text
    mismatches = page.evaluate("""() => [...document.querySelectorAll('#chat-stream button, #chat-stream a[href]')]
      .filter(e => e.getAttribute('aria-label') && e.textContent.trim())
      .filter(e => !e.getAttribute('aria-label').toLowerCase().includes(e.textContent.trim().toLowerCase()))
      .map(e => `${e.textContent.trim()} -> ${e.getAttribute('aria-label')}`)""")
    assert not mismatches, mismatches
    assert not errors, errors


def test_header_states_each_fact_once(context, app_server):
    base, app = app_server
    conversation, _ = _seed(app, "header", "Sync", [("shell", {"command": "date"}, None, True, 0)], status=RunStatus.running,
                            started_s_ago=5)
    page, errors = _open(context, base, conversation)
    # running: the face and the turn's status word carry it; the header has no chip and no repeated counts
    expect(page.locator(".app-top .ctx-id > .avatar")).to_have_attribute("data-state", "running")
    assert page.locator(".app-top .status").count() == 0
    assert page.locator(".workflow .w.waiting, .workflow .w.queued, .workflow .w.needs").count() == 0
    expect(page.locator("#studio-stop-run")).to_be_visible()
    header = page.locator(".app-top").bounding_box()
    box = page.locator("#conversation-switcher").bounding_box()
    assert header["y"] <= box["y"] and box["y"] + box["height"] <= header["y"] + header["height"] + 1
    # the picker truncates instead of overflowing, even with a very long title
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
    assert not errors, errors


def test_expanded_bubble_step_and_output_survive_live_updates(context, app_server):
    """The feed replaces its HTML on every event batch; what the person opened must stay open."""
    base, app = app_server
    long_prompt = "Audit the repository.\n" + "\n".join(f"Check {i}: report anything surprising." for i in range(1, 14))
    output = "\n".join(f"src/module_{i}.py:{i}: TODO" for i in range(1, 60))
    conversation, run = _seed(app, "live", long_prompt, [("shell", {"command": "rg -n TODO src"}, output, True, 0.5)],
                              status=RunStatus.running, started_s_ago=30)
    page, errors = _open(context, base, conversation)
    page.locator("#chat-stream [data-bubble-toggle]").click()
    stream = page.locator("details.tool-stream").first
    if not stream.evaluate("el => el.open"):
        stream.locator("summary").click()
    page.locator(".tool-line-head").first.click()
    out = page.locator(".tool-line .tool-out").first
    expect(out).to_have_attribute("data-clipped", "true")
    out.locator("[data-show-more]").click()
    expect(out).to_have_attribute("data-clipped", "false")
    page.locator('.tool-line [data-raw-toggle]').first.click()
    # a new step arrives: the whole feed re-renders
    app.state.store.append_event(Event(run_id=run.id, type=EventType.tool_call, ts=iso(utcnow()),
                                       data={"tool": "list_files", "args": {"path": "."}}))
    app.state.store.flush_events()
    expect(page.locator(".tool-line[data-tool-line]")).to_have_count(2, timeout=20_000)
    expect(page.locator("#chat-stream [data-bubble-toggle]")).to_have_attribute("aria-expanded", "true")
    expect(page.locator(".tool-line-head").first).to_have_attribute("aria-expanded", "true")
    expect(page.locator(".tool-line .tool-out").first).to_have_attribute("data-clipped", "false")
    expect(page.locator(".tool-line [data-raw-toggle]").first).to_have_attribute("aria-pressed", "true")
    assert not errors, errors
