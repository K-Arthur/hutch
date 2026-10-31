from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from hutch import code_handoff, code_review, procguard
from hutch.code_prune import prune_handoff
from hutch.code_review import CodeReviewError, verify_handoff
from hutch.server.app import create_app


def _git(directory, *args):
    return subprocess.run(["git", "-C", str(directory), *args], check=True, capture_output=True, text=True)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def _prepare(client, tmp_path, *, key_prefix: str, complete: bool = True):
    project = tmp_path / "project"
    project.mkdir()
    _git(project, "init", "-q")
    _git(project, "config", "user.email", "hutch-test@example.invalid")
    _git(project, "config", "user.name", "Hutch Test")
    readme = project / "README.md"
    readme.write_text("A tiny coding fixture.\n")
    _git(project, "add", "README.md")
    _git(project, "commit", "-qm", "base")

    bot = client.post("/api/bots", json={
        "name": "code-helper", "model": "mock/demo", "tools": [],
        "workspace_mode": "folder", "workdir": str(project),
    })
    assert bot.status_code == 201, bot.text
    conversation = client.post("/api/v1/conversations", json={"bot": bot.json()["id"]},
                               headers={"Idempotency-Key": f"{key_prefix}-conversation"}).json()
    sent = client.post(f"/api/v1/conversations/{conversation['id']}/messages",
                       json={"prompt": "Improve this README for new contributors."},
                       headers={"Idempotency-Key": f"{key_prefix}-source"})
    assert sent.status_code == 201, sent.text
    run_id = sent.json()["id"]
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        state = client.get(f"/api/v1/tasks/runs/{run_id}").json()
        if state["terminal"]:
            break
        time.sleep(0.05)
    assert state["status"] == "succeeded"
    messages = client.get(f"/api/v1/conversations/{conversation['id']}").json()["messages"]
    source_user = next(row for row in messages if row["run_id"] == run_id and row["role"] == "user")
    source_answer = next(row for row in messages if row["run_id"] == run_id and row["role"] == "assistant")
    created = client.post("/api/v1/code-handoffs", json={
        "conversation_id": conversation["id"], "source_run_id": run_id,
        "source_user_message_id": source_user["id"],
        "source_assistant_message_id": source_answer["id"],
        "task_brief": "Add one concise contributor setup note to README.md.",
    }, headers={"Idempotency-Key": f"{key_prefix}-handoff"})
    assert created.status_code == 201, created.text
    handoff_id = created.json()["id"]
    if not complete:
        return handoff_id, None, None, readme
    store = client.app.state.store
    record = store.code_handoff(handoff_id)
    worktree, branch = code_handoff.create_task_worktree(record, Path(os.environ["HUTCH_STATE_DIR"]))
    (worktree / "README.md").write_text("A tiny coding fixture.\nContributor setup: install dependencies.\n")
    store.claim_code_handoff(handoff_id)
    store.start_code_handoff(handoff_id, worktree_path=str(worktree), branch_name=branch,
                             opencode_version="2.0.24", runner_pid=999999, runner_starttime=1,
                             runner_boot_id="fixture", runner_session=1)
    store.finish_code_handoff(handoff_id, status="changes_ready", changed_files=1,
                              summary="1 changed file in the isolated worktree.", exit_code=0)
    return handoff_id, worktree, branch, readme


def _receipts(client, handoff_id):
    with client.app.state.store._lock:
        rows = client.app.state.store._db.execute(
            "SELECT * FROM code_handoff_receipts WHERE handoff_id = ? ORDER BY rowid", (handoff_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def test_verify_records_a_content_free_receipt_and_reuses_an_identical_pass(client, tmp_path):
    handoff_id, worktree, _branch, _readme = _prepare(client, tmp_path, key_prefix="verify")
    state_dir = Path(os.environ["HUTCH_STATE_DIR"])
    command = [sys.executable, "-c", "print('check ok')"]

    result = verify_handoff(client.app.state.store, handoff_id, command, state_dir=state_dir)
    assert result["exit_code"] == 0 and result["reused"] is False
    assert code_review.verification_state(result) == "verified"
    assert len(result["argv_digest"]) == 64 and len(result["worktree_digest"]) == 64
    assert result["changed_files"] == 1
    receipts = _receipts(client, handoff_id)
    assert len(receipts) == 1
    assert set(receipts[0]) == {"id", "handoff_id", "kind", "argv_digest", "exit_code", "duration_ms",
                                "changed_files", "worktree_digest", "timed_out", "output_truncated",
                                "detail", "created_at"}
    assert "check ok" not in str(receipts[0])

    reused = verify_handoff(client.app.state.store, handoff_id, command, state_dir=state_dir)
    assert reused["reused"] is True and reused["id"] == result["id"]
    assert len(_receipts(client, handoff_id)) == 1

    (worktree / "README.md").write_text("A tiny coding fixture.\nContributor setup: use the lockfile.\n")
    rerun = verify_handoff(client.app.state.store, handoff_id, command, state_dir=state_dir)
    assert rerun["reused"] is False and rerun["id"] != result["id"]
    assert len(_receipts(client, handoff_id)) == 2


def test_failed_check_is_verification_failed_and_blocks_prune_until_discarded(client, tmp_path):
    handoff_id, worktree, branch, readme = _prepare(client, tmp_path, key_prefix="failed")
    state_dir = Path(os.environ["HUTCH_STATE_DIR"])
    store = client.app.state.store

    failed = verify_handoff(store, handoff_id, [sys.executable, "-c", "raise SystemExit(3)"],
                            state_dir=state_dir)
    assert failed["exit_code"] == 3
    assert code_review.verification_state(failed) == "verification_failed"
    failed_again = verify_handoff(store, handoff_id, [sys.executable, "-c", "raise SystemExit(3)"],
                                  state_dir=state_dir)
    assert failed_again["reused"] is False and failed_again["id"] != failed["id"]

    with pytest.raises(CodeReviewError, match="verification failed"):
        prune_handoff(store, handoff_id, state_dir=state_dir, confirmed=True)
    assert worktree.is_dir()

    pruned = prune_handoff(store, handoff_id, state_dir=state_dir, confirmed=True, discard=True)
    assert pruned["kind"] == "prune" and pruned["worktree_removed"] is True
    assert pruned["branch_removed"] is True
    assert not worktree.exists()
    assert readme.read_text() == "A tiny coding fixture.\n"
    branches = _git(Path(store.code_handoff(handoff_id)["project_root"]), "branch", "--list", branch)
    assert branches.stdout.strip() == ""
    with pytest.raises(CodeReviewError, match="already pruned"):
        prune_handoff(store, handoff_id, state_dir=state_dir, confirmed=True, discard=True)


def test_verify_requires_confirmation_and_a_prior_check_for_prune(client, tmp_path):
    handoff_id, worktree, _branch, _readme = _prepare(client, tmp_path, key_prefix="gate")
    state_dir = Path(os.environ["HUTCH_STATE_DIR"])
    store = client.app.state.store

    with pytest.raises(CodeReviewError, match="confirm explicitly"):
        prune_handoff(store, handoff_id, state_dir=state_dir, confirmed=False)
    with pytest.raises(CodeReviewError, match="code verify"):
        prune_handoff(store, handoff_id, state_dir=state_dir, confirmed=True)
    assert worktree.is_dir()

    verify_handoff(store, handoff_id, [sys.executable, "-c", "pass"], state_dir=state_dir)
    pruned = prune_handoff(store, handoff_id, state_dir=state_dir, confirmed=True)
    assert pruned["branch_removed"] is True
    assert not worktree.exists()


def test_verify_bounds_output_and_stops_a_timeout_in_its_own_group(client, tmp_path):
    handoff_id, _worktree, _branch, _readme = _prepare(client, tmp_path, key_prefix="bounds")
    state_dir = Path(os.environ["HUTCH_STATE_DIR"])
    store = client.app.state.store
    noisy = [sys.executable, "-c", "import sys; sys.stdout.write('x' * 300000)"]
    result = verify_handoff(store, handoff_id, noisy, state_dir=state_dir)
    assert result["exit_code"] == 0
    assert result["output_truncated"] == 1
    assert len(result["output"]) == code_review.MAX_CAPTURED_BYTES
    assert len(_receipts(client, handoff_id)[0]["detail"]) < 500

    slow = verify_handoff(store, handoff_id, [sys.executable, "-c", "import time; time.sleep(30)"],
                          state_dir=state_dir, timeout_seconds=1, rerun=True)
    assert slow["timed_out"] == 1
    assert code_review.verification_state(slow) == "verification_failed"
    assert slow["duration_ms"] >= 900


def test_verify_and_prune_refuse_while_the_recorded_runner_group_is_alive(client, tmp_path):
    handoff_id, _worktree, _branch, _readme = _prepare(client, tmp_path, key_prefix="live", complete=False)
    store = client.app.state.store
    identity = None
    worker = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
    try:
        identity = procguard.identity(worker.pid)
        assert identity is not None
        store.claim_code_handoff(handoff_id)
        store.start_code_handoff(handoff_id, worktree_path="fixture", branch_name="hutch/code/fixture",
                                 opencode_version="2.0.24", runner_pid=worker.pid,
                                 runner_starttime=identity.starttime, runner_boot_id=procguard.boot_id(),
                                 runner_session=identity.session)
        with pytest.raises(CodeReviewError, match="process group is still present"):
            verify_handoff(store, handoff_id, [sys.executable, "-c", "pass"],
                           state_dir=Path(os.environ["HUTCH_STATE_DIR"]))
        with pytest.raises(CodeReviewError, match="process group is still present"):
            prune_handoff(store, handoff_id, state_dir=Path(os.environ["HUTCH_STATE_DIR"]),
                          confirmed=True, discard=True)
    finally:
        if identity is not None:
            procguard.end_recorded([{"pid": worker.pid, "pgid": worker.pid, "starttime": identity.starttime,
                                     "boot_id": procguard.boot_id()}], term_grace=0.5, kill_grace=1)
        worker.wait(timeout=3)


def test_receipts_are_append_only_and_the_api_reports_verification(client, tmp_path):
    handoff_id, _worktree, _branch, _readme = _prepare(client, tmp_path, key_prefix="api")
    conversation_id = client.app.state.store.code_handoff(handoff_id)["conversation_id"]
    listing = client.get(f"/api/v1/code-handoffs?conversation_id={conversation_id}").json()
    resource = next(row for row in listing if row["id"] == handoff_id)
    assert resource["verification"] is None
    assert resource["verify_command"] == f"hutch code verify {handoff_id} -- <command>"
    assert resource["prune_command"] == f"hutch code prune {handoff_id}"
    assert resource["pruned_at"] is None

    verify_handoff(client.app.state.store, handoff_id, [sys.executable, "-c", "pass"],
                   state_dir=Path(os.environ["HUTCH_STATE_DIR"]))
    resource = next(row for row in client.get(
        f"/api/v1/code-handoffs?conversation_id={conversation_id}").json() if row["id"] == handoff_id)
    assert resource["verification"]["state"] == "verified"
    assert resource["verification"]["exit_code"] == 0
    assert len(resource["verification"]["argv_digest"]) == 64

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with client.app.state.store._tx() as db:
            db.execute("UPDATE code_handoff_receipts SET exit_code = 1 WHERE handoff_id = ?", (handoff_id,))
    with pytest.raises(sqlite3.IntegrityError, match="retained history"):
        with client.app.state.store._tx() as db:
            db.execute("DELETE FROM code_handoff_receipts WHERE handoff_id = ?", (handoff_id,))


def test_cli_verify_and_prune_use_the_real_database(client, tmp_path):
    from hutch.cli import app as cli_app

    handoff_id, worktree, _branch, _readme = _prepare(client, tmp_path, key_prefix="cli")
    runner = CliRunner()
    verified = runner.invoke(cli_app, ["code", "verify", handoff_id, "--",
                                       sys.executable, "-c", "print('cli check ok')"])
    assert verified.exit_code == 0, verified.output
    assert "verified" in verified.output.lower()
    assert worktree.is_dir()

    refused = runner.invoke(cli_app, ["code", "prune", handoff_id])
    assert refused.exit_code == 2
    assert "without confirmation" in refused.output

    pruned = runner.invoke(cli_app, ["code", "prune", handoff_id, "--yes"])
    assert pruned.exit_code == 0, pruned.output
    assert "Removed the retained worktree" in pruned.output
    assert not worktree.exists()
