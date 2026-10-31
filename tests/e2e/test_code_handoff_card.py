"""The coding task card must show an owner verification receipt, not just readiness.

Uses the real server, store and Git worktree. The coding CLI is not launched here;
the handoff is completed through the same store states the CLI writes after a
verified process exit, then one explicit check command runs in the worktree.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
from playwright.sync_api import Error as PlaywrightError, expect

from hutch import code_handoff
from hutch.code_review import verify_handoff
from hutch.models import Bot

from tests.e2e.test_design_system import app_server, browser  # noqa: F401
from tests.support.artifacts import artifact_path


def _git(directory, *args):
    return subprocess.run(["git", "-C", str(directory), *args], check=True, capture_output=True, text=True)


def test_code_handoff_card_shows_owner_verification(browser, app_server, tmp_path):
    base, app = app_server
    store = app.state.store
    state_dir = Path(os.environ["HUTCH_STATE_DIR"])
    project = tmp_path / "handoff-card-project"
    project.mkdir()
    _git(project, "init", "-q")
    _git(project, "config", "user.email", "hutch-test@example.invalid")
    _git(project, "config", "user.name", "Hutch Test")
    (project / "README.md").write_text("A tiny fixture for the coding card.\n")
    _git(project, "add", "README.md")
    _git(project, "commit", "-qm", "base")

    bot = store.create_bot(Bot(name="coding-card", display_name="Coding Partner", model="mock/demo",
                               tools=[], workspace_mode="folder", workdir=str(project)))
    client = httpx.Client(base_url=base, timeout=20)
    conversation = client.post("/api/v1/conversations", json={"bot": bot.id},
                               headers={"Idempotency-Key": uuid.uuid4().hex}).json()
    sent = client.post(f"/api/v1/conversations/{conversation['id']}/messages",
                       json={"prompt": "Add a contributor setup note to this README."},
                       headers={"Idempotency-Key": uuid.uuid4().hex})
    assert sent.status_code == 201, sent.text
    run_id = sent.json()["id"]
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        run = client.get(f"/api/v1/tasks/runs/{run_id}").json()
        if run["terminal"]:
            break
        time.sleep(0.05)
    assert run["status"] == "succeeded", run
    messages = client.get(f"/api/v1/conversations/{conversation['id']}").json()["messages"]
    user_message = next(row for row in messages if row["run_id"] == run_id and row["role"] == "user")
    assistant_message = next(row for row in messages if row["run_id"] == run_id and row["role"] == "assistant")
    inspected = code_handoff.inspect_project(str(project))
    handoff_id, _ = store.create_code_handoff(
        conversation_id=conversation["id"], source_run_id=run_id,
        source_user_message_id=user_message["id"], source_assistant_message_id=assistant_message["id"],
        task_brief="Add one concise contributor setup note.", project_root=inspected["project_root"],
        project_name=project.name, project_device=inspected["project_device"],
        project_inode=inspected["project_inode"], git_common_dir=inspected["git_common_dir"],
        base_commit=inspected["base_commit"], idem_key=uuid.uuid4().hex,
        request_hash=uuid.uuid4().hex,
    )
    worktree, branch = code_handoff.create_task_worktree(store.code_handoff(handoff_id), state_dir)
    (worktree / "README.md").write_text("A tiny fixture for the coding card.\nContributor setup: install dependencies.\n")
    store.claim_code_handoff(handoff_id)
    store.start_code_handoff(handoff_id, worktree_path=str(worktree), branch_name=branch,
                             opencode_version="2.0.24", runner_pid=999999, runner_starttime=1,
                             runner_boot_id="fixture", runner_session=1)
    store.finish_code_handoff(handoff_id, status="changes_ready", changed_files=1,
                              summary="1 changed file in the isolated worktree.", exit_code=0)
    verify_handoff(store, handoff_id, [sys.executable, "-c", "print('README check passed')"],
                   state_dir=state_dir)

    context = browser.new_context(reduced_motion="reduce")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
    page.on("console", lambda msg: errors.append(f"console: {msg.text}") if msg.type == "error" else None)
    out = artifact_path("code-handoff")
    out.mkdir(parents=True, exist_ok=True)
    try:
        for width, height in ((1440, 960), (834, 1112), (390, 844), (320, 740)):
            page.set_viewport_size({"width": width, "height": height})
            page.goto(f"{base}/#/conversation/{conversation['id']}")
            card = page.locator(".code-handoff-card")
            expect(card).to_be_visible()
            expect(card).to_contain_text("Owner check passed")
            expect(card).to_contain_text("exit 0")
            assert page.evaluate("Math.max(0, document.documentElement.scrollWidth - window.innerWidth)") <= 1
            for attempt in range(3):
                try:
                    card.screenshot(path=str(out / f"code-handoff-verified-{width}.png"),
                                    animations="disabled")
                    break
                except PlaywrightError:
                    if attempt == 2:
                        raise
                    page.wait_for_timeout(300)  # an SSE refresh can replace the feed node mid-capture
        assert not errors, errors
    finally:
        context.close()
        client.close()
