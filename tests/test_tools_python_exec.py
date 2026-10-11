"""run_python / reset_workspace: the tool-layer contract.

The policy sequence mirrors tools/shell.py (policy check -> approval gate ->
begin_effect -> run -> receipt): ask-by-default with sticky keys, tier
translation, fail-closed containment refusals, and receipts that match the
typed output-block contract (parse_blocks-clean, hash-bound to the EXACT
submitted code). The manager is faked; the containment gate is exercised
with the real checks (HUTCH_SANDBOX=off, sandbox.status()).
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any

import pytest

from hutch.approvals import ApprovalGate, resolve_approval, resolve_approval_ex
from hutch.models import ApprovalMode, Bot, Event, Run, RunStatus
from hutch.outputblocks import parse_blocks
from hutch.safety import PolicyEngine
from hutch.tools.base import ToolContext
from hutch.tools.python_exec import OUTPUT_TEXT_LIMIT, ResetWorkspaceTool, RunPythonTool, TOOLS
from hutch.workspace import protocol

CONVERSATION_ID = "conv-py-tools"


class FakeManager:
    """Records execute/restart calls and replays scripted responses."""

    def __init__(self, tmp_path, response: dict | None = None, restart_result: dict | None = None):
        self.calls: list[tuple[str, str, int]] = []
        self.restarts: list[str] = []
        self._dir = tmp_path / "ws"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._response = response
        self._restart_result = restart_result or {
            "ok": True, "generation": 8, "reason": "reset_workspace tool", "survivors": 0,
            "stale": {"state": "stale", "generation_ended": 7, "generation_started": 8},
        }

    @property
    def workspace_dir(self):
        return self._dir

    def session_info(self) -> dict[str, Any]:
        return {"conversation_id": CONVERSATION_ID, "status": "ready", "generation": 7,
                "ordinal": len(self.calls), "workspace_dir": str(self._dir),
                "child_alive": True, "last_error": "", "store": None}

    def execute(self, code: str, timeout_ms: int, *, procs: Any = None) -> dict:
        self.calls.append((code, timeout_ms, threading.get_ident()))
        return self._response or ok_response(code)

    def restart(self, *, reason: str = "") -> dict:
        self.restarts.append(reason)
        return self._restart_result


def ok_response(code: str, **overrides) -> dict:
    response = {
        "op": "exec", "id": "wx_fake", "status": "ok",
        "receipt": {
            "ordinal": 3, "environment_generation": 7,
            "started_at": "2026-10-11T00:00:00+00:00",
            "finished_at": "2026-10-11T00:00:01+00:00",
            "source_sha256": protocol.sha256_of_source(code),
            "status": "ok", "stdout_chars_total": 5, "stderr_chars_total": 0,
        },
        "stdout_tail": "hello\n", "stderr_tail": "", "result_repr": "42",
        "blocks": [{"kind": "text", "payload": {"content": "emitted from the cell"},
                    "text_fallback": "emitted from the cell"}],
        "produced_files": [{"name": "out.txt", "sha256": "a" * 64, "bytes": 3}],
    }
    response.update(overrides)
    return response


def make_ctx(store, config, tmp_path, *, tier: str = "supervised",
             approval_mode: ApprovalMode = ApprovalMode.ask, conversation_id: str = CONVERSATION_ID):
    bot = Bot(name="py-bot", model="mock/demo", tools=[], approval_mode=approval_mode)
    store.create_bot(bot)
    run = Run(bot_id=bot.id, prompt="run python", status=RunStatus.running,
              conversation_id=conversation_id)
    store.create_run(run)
    ws = tmp_path / "run-ws"
    ws.mkdir(exist_ok=True)
    gate = ApprovalGate(store, bot, run, PolicyEngine(tier=tier), lambda ev: store.append_event(ev),
                        poll_seconds=0.01)
    ctx = ToolContext(bot=bot, run=run, store=store, policy=gate.policy, gate=gate,
                      config=config, workspace=ws, emit=lambda ev: store.append_event(ev))
    return bot, run, ctx


def wait_for_approval(store, timeout: float = 5.0):
    end = time.time() + timeout
    while time.time() < end and not store.pending_approvals():
        time.sleep(0.01)
    pending = store.pending_approvals()
    assert pending, "the tool never asked for approval"
    return pending[0]


@pytest.fixture
def strict_containment(monkeypatch):
    """The suite default is HUTCH_SANDBOX=off (conftest); tests that exercise
    the gate and receipts turn strict containment on with a passing probe so
    they stay hermetic (no bwrap needed)."""
    from hutch import sandbox as sandbox_module
    monkeypatch.setenv("HUTCH_SANDBOX", "strict")
    monkeypatch.setattr(sandbox_module, "status",
                        lambda refresh=False: sandbox_module.Status(True, version="0.13.0-test"))


def run_in_thread(tool, ctx, args) -> tuple[dict, threading.Thread]:
    result: dict = {}

    def invoke():
        result["value"] = tool.run(args, ctx)

    worker = threading.Thread(target=invoke, daemon=True)
    worker.start()
    return result, worker


# ------------------------------------------------------------------------- basics


def test_tools_export():
    assert [tool.name for tool in TOOLS] == ["run_python", "reset_workspace"]


def test_effect_is_process_only_with_code(store, config, tmp_path):
    _, _, ctx = make_ctx(store, config, tmp_path)
    tool = RunPythonTool(manager_factory=lambda c, conv: FakeManager(tmp_path))
    assert tool.effect({"code": "1"}, ctx) == "process"
    assert tool.effect({"code": ""}, ctx) == ""
    assert tool.effect({}, ctx) == ""
    assert ResetWorkspaceTool(manager_factory=lambda c, conv: FakeManager(tmp_path)).effect({}, ctx) == "process"


def test_missing_and_oversized_code_refused(store, config, tmp_path):
    _, _, ctx = make_ctx(store, config, tmp_path)
    fake = FakeManager(tmp_path)
    tool = RunPythonTool(manager_factory=lambda c, conv: fake)
    assert tool.run({}, ctx).ok is False
    assert tool.run({"code": "   "}, ctx).ok is False
    result = tool.run({"code": "x = 1\n" * 60_000}, ctx)   # > 100k chars
    assert result.ok is False and "100,000" in result.output or "100000" in result.output
    assert fake.calls == []                                 # nothing reached the manager


def test_requires_a_conversation_scoped_run(store, config, tmp_path):
    _, _, ctx = make_ctx(store, config, tmp_path, conversation_id="")
    fake = FakeManager(tmp_path)
    result = RunPythonTool(manager_factory=lambda c, conv: fake).run({"code": "1"}, ctx)
    assert result.ok is False and "conversation" in result.output
    assert fake.calls == []


# --------------------------------------------------------------- rehearse + containment


def test_rehearse_mode_never_executes(store, config, tmp_path, strict_containment):
    _, _, ctx = make_ctx(store, config, tmp_path)
    ctx.dry_run = True
    fake = FakeManager(tmp_path)
    result = RunPythonTool(manager_factory=lambda c, conv: fake).run({"code": "1"}, ctx)
    assert result.ok is True and result.data.get("simulated") is True
    assert fake.calls == []
    reset_result = ResetWorkspaceTool(manager_factory=lambda c, conv: fake).run({}, ctx)
    assert reset_result.data.get("simulated") is True
    assert fake.restarts == []


def test_containment_off_refuses_fail_closed(store, config, tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_SANDBOX", "off")      # the conftest default, made explicit
    _, _, ctx = make_ctx(store, config, tmp_path)
    fake = FakeManager(tmp_path)
    result = RunPythonTool(manager_factory=lambda c, conv: fake).run({"code": "1"}, ctx)
    assert result.ok is False
    assert "containment" in result.output and "Nothing was run" in result.output
    assert result.data["sandbox"] == "off"
    assert fake.calls == []
    reset_result = ResetWorkspaceTool(manager_factory=lambda c, conv: fake).run({}, ctx)
    assert reset_result.ok is False and reset_result.data["sandbox"] == "off"


def test_unavailable_strict_sandbox_refuses_fail_closed(store, config, tmp_path, monkeypatch):
    from hutch import sandbox as sandbox_module
    monkeypatch.setenv("HUTCH_SANDBOX", "strict")
    monkeypatch.setattr(sandbox_module, "status",
                        lambda refresh=False: sandbox_module.Status(False, reason="no bubblewrap on this host"))
    # the availability refusal comes AFTER the gate (shell.py's order), so an
    # auto bot reaches it without a human; the ask-mode path is covered above
    _, _, ctx = make_ctx(store, config, tmp_path, approval_mode=ApprovalMode.auto)
    fake = FakeManager(tmp_path)
    result = RunPythonTool(manager_factory=lambda c, conv: fake).run({"code": "1"}, ctx)
    assert result.ok is False
    assert "no bubblewrap on this host" in result.output
    assert "Nothing was run" in result.output
    assert result.data["sandbox"] == "unavailable"
    assert fake.calls == []


# ---------------------------------------------------------------------- approvals


def test_ask_by_default_creates_approval_with_sticky_key(store, config, tmp_path, strict_containment):
    _, run, ctx = make_ctx(store, config, tmp_path)
    fake = FakeManager(tmp_path)
    tool = RunPythonTool(manager_factory=lambda c, conv: fake)
    result, worker = run_in_thread(tool, ctx, {"code": "total = 40 + 2\nprint(total)", "timeout_seconds": 30})
    approval = wait_for_approval(store)
    assert approval.tool == "run_python"
    assert approval.sticky_key == "python:exec"
    assert approval.detail["timeout_seconds"] == 30
    assert approval.detail["code"] == "total = 40 + 2\nprint(total)"
    assert fake.calls == []                              # nothing runs before a human answers
    resolve_approval(store, approval.id, approve=True, by="human")
    worker.join(10)
    assert len(fake.calls) == 1
    assert result["value"].ok is True
    assert result["value"].data["exec_status"] == "ok"


def test_sticky_allow_covers_later_calls(store, config, tmp_path, strict_containment):
    _, run, ctx = make_ctx(store, config, tmp_path)
    fake = FakeManager(tmp_path)
    tool = RunPythonTool(manager_factory=lambda c, conv: fake)
    result, worker = run_in_thread(tool, ctx, {"code": "1"})
    approval = wait_for_approval(store)
    resolve_approval_ex(store, approval.id, approve=True, by="human", sticky=True)
    worker.join(10)
    assert result["value"].ok is True
    second = tool.run({"code": "2"}, ctx)                # the standing permission answers, no ask
    assert second.ok is True
    assert len(fake.calls) == 2
    assert store.pending_approvals() == []


def test_denied_approval_blocks_execution(store, config, tmp_path, strict_containment):
    _, run, ctx = make_ctx(store, config, tmp_path)
    fake = FakeManager(tmp_path)
    tool = RunPythonTool(manager_factory=lambda c, conv: fake)
    result, worker = run_in_thread(tool, ctx, {"code": "1"})
    approval = wait_for_approval(store)
    resolve_approval(store, approval.id, approve=False, by="human")
    worker.join(10)
    assert result["value"].ok is False
    assert result["value"].output.startswith("error:")
    assert fake.calls == []


def test_readonly_tier_refuses(store, config, tmp_path, strict_containment):
    _, _, ctx = make_ctx(store, config, tmp_path, tier="readonly")
    fake = FakeManager(tmp_path)
    result = RunPythonTool(manager_factory=lambda c, conv: fake).run({"code": "1"}, ctx)
    assert result.ok is False and "read-only" in result.output
    assert fake.calls == []
    assert store.pending_approvals() == []


def test_trusted_tier_runs_without_asking(store, config, tmp_path, strict_containment):
    _, _, ctx = make_ctx(store, config, tmp_path, tier="trusted")
    fake = FakeManager(tmp_path)
    result = RunPythonTool(manager_factory=lambda c, conv: fake).run({"code": "1"}, ctx)
    assert result.ok is True
    assert len(fake.calls) == 1
    assert store.pending_approvals() == []


# --------------------------------------------------------------------- receipts


def test_code_receipt_block_matches_the_contract(store, config, tmp_path, strict_containment, approval_mode=ApprovalMode.auto):
    _, run, ctx = make_ctx(store, config, tmp_path, approval_mode=approval_mode)
    code = "total = 40 + 2\nprint(f'the answer is {total}')"
    fake = FakeManager(tmp_path, response=ok_response(code))
    result = RunPythonTool(manager_factory=lambda c, conv: fake).run(
        {"code": code, "timeout_seconds": 30}, ctx)
    assert result.ok is True
    blocks = result.data["blocks"]
    assert len(blocks) == 2                              # the receipt plus the emitted text block
    receipt = blocks[0]
    assert receipt["kind"] == "code_receipt"
    assert receipt["provenance"] == {"run_id": run.id, "tool": "run_python"}
    assert receipt["text_fallback"].startswith("Ran 2 lines of Python;")
    payload = receipt["payload"]
    assert payload["source"] == code                     # the EXACT submitted code
    assert payload["language"] == "python"
    assert payload["source_sha256"] == hashlib.sha256(code.encode()).hexdigest()
    execution = payload["execution"]
    assert execution["ordinal"] == 3
    assert execution["environment_generation"] == 7
    assert execution["status"] == "ok"
    assert execution["stdout_chars_total"] == 5 and execution["stderr_chars_total"] == 0
    assert payload["stdout_tail"] == "hello\n"
    assert payload["result_repr"] == "42"
    assert payload["produced_files"] == [{"name": "out.txt", "sha256": "a" * 64, "bytes": 3}]
    # the whole data['blocks'] list survives the contract's own validator
    parsed, errors = parse_blocks(blocks)
    assert errors == [] and len(parsed) == 2
    assert [b["kind"] for b in parsed] == ["code_receipt", "text"]


def test_interrupted_receipt_maps_to_cancelled(store, config, tmp_path, strict_containment, approval_mode=ApprovalMode.auto):
    _, _, ctx = make_ctx(store, config, tmp_path, approval_mode=approval_mode)
    code = "while True: pass"
    fake = FakeManager(tmp_path, response=ok_response(code, **{
        "receipt": {"ordinal": 4, "environment_generation": 7,
                    "started_at": "2026-10-11T00:00:00+00:00",
                    "finished_at": "2026-10-11T00:00:02+00:00",
                    "source_sha256": protocol.sha256_of_source(code),
                    "status": "interrupted", "stdout_chars_total": 0, "stderr_chars_total": 0}}))
    result = RunPythonTool(manager_factory=lambda c, conv: fake).run({"code": code}, ctx)
    execution = result.data["blocks"][0]["payload"]["execution"]
    assert execution["status"] == "cancelled"            # the contract has no 'interrupted'
    parsed, errors = parse_blocks(result.data["blocks"])
    assert errors == [] and parsed


def test_interrupt_unconfirmed_is_reported_not_claimed(store, config, tmp_path, strict_containment, approval_mode=ApprovalMode.auto):
    _, _, ctx = make_ctx(store, config, tmp_path, approval_mode=approval_mode)
    code = "while True: pass"
    receipt = {"ordinal": 5, "environment_generation": 7,
               "started_at": "2026-10-11T00:00:00+00:00",
               "finished_at": "2026-10-11T00:00:05+00:00",
               "source_sha256": protocol.sha256_of_source(code),
               "status": "interrupt_unconfirmed", "stdout_chars_total": 0,
               "stderr_chars_total": 0,
               "note": "interrupt requested; the kernel did not acknowledge"}
    fake = FakeManager(tmp_path, response={
        "op": "exec", "id": "wx", "status": "interrupt_unconfirmed", "receipt": receipt,
        "stdout_tail": "", "stderr_tail": "", "result_repr": "",
        "blocks": [], "produced_files": [],
        "error": {"type": "InterruptUnconfirmed", "value": "the cell did not acknowledge"}})
    result = RunPythonTool(manager_factory=lambda c, conv: fake).run({"code": code}, ctx)
    assert result.ok is False
    assert "interrupt_unconfirmed" in result.output and "reset_workspace" in result.output
    kinds = [b["kind"] for b in result.data["blocks"]]
    assert "status" in kinds                             # a status block carries the problem
    parsed, errors = parse_blocks(result.data["blocks"])
    assert errors == []
    status_block = next(b for b in parsed if b["kind"] == "status")
    assert status_block["payload"]["state"] == "cancelled"
    execution = result.data["blocks"][0]["payload"]["execution"]
    assert execution["status"] == "interrupt_unconfirmed"


def test_timeout_and_lost_statuses_are_honest(store, config, tmp_path, strict_containment, approval_mode=ApprovalMode.auto):
    _, _, ctx = make_ctx(store, config, tmp_path, approval_mode=approval_mode)
    code = "1"
    base = ok_response(code)
    base["status"] = "timeout"
    base["receipt"] = dict(base["receipt"], status="timeout",
                           note="the kernel never reported the cell's outcome")
    base["error"] = {"type": "TimeoutError", "value": "terminated"}
    fake = FakeManager(tmp_path, response=base)
    result = RunPythonTool(manager_factory=lambda c, conv: fake).run({"code": code}, ctx)
    assert result.ok is False
    assert "hit its 60s limit" in result.output or "limit" in result.output
    parsed, errors = parse_blocks(result.data["blocks"])
    assert errors == []
    assert next(b for b in parsed if b["kind"] == "status")["payload"]["state"] == "failed"

    lost = dict(base)
    lost.update(status="lost",
                error={"type": "WorkspaceLost", "value": "the workspace kernel exited mid-execution"})
    lost["receipt"] = dict(base["receipt"], status="error")
    fake2 = FakeManager(tmp_path, response=lost)
    result = RunPythonTool(manager_factory=lambda c, conv: fake2).run({"code": code}, ctx)
    assert result.ok is False
    assert "GONE" in result.output or "gone" in result.output


def test_busy_response_never_queues(store, config, tmp_path, strict_containment, approval_mode=ApprovalMode.auto):
    _, _, ctx = make_ctx(store, config, tmp_path, approval_mode=approval_mode)
    fake = FakeManager(tmp_path, response={
        "op": "exec", "id": "wx", "status": "busy",
        "error": {"type": "Busy", "value": "another cell is already running; nothing was queued"}})
    result = RunPythonTool(manager_factory=lambda c, conv: fake).run({"code": "1"}, ctx)
    assert result.ok is False
    assert "already running" in result.output and "nothing was queued" in result.output
    assert result.data["blocks"] == []


def test_model_facing_text_is_bounded(store, config, tmp_path, strict_containment, approval_mode=ApprovalMode.auto):
    _, _, ctx = make_ctx(store, config, tmp_path, approval_mode=approval_mode)
    code = "1"
    chatty = ok_response(code)
    chatty["result_repr"] = "x" * 500_000
    chatty["stdout_tail"] = "y" * 100_000
    chatty["blocks"] = []
    fake = FakeManager(tmp_path, response=chatty)
    result = RunPythonTool(manager_factory=lambda c, conv: fake).run({"code": code}, ctx)
    # bounded like every tool: clip's one-line omission disclosure may trail the limit
    assert len(result.output) <= OUTPUT_TEXT_LIMIT + 100
    assert "clipped" in result.output or len(result.output) <= OUTPUT_TEXT_LIMIT
    assert result.data["blocks"][0]["payload"]["result_repr"] == "x" * 2000   # capped at the contract bound


def test_timeout_seconds_are_clamped(store, config, tmp_path, strict_containment, approval_mode=ApprovalMode.auto):
    _, _, ctx = make_ctx(store, config, tmp_path, approval_mode=approval_mode)
    fake = FakeManager(tmp_path)
    tool = RunPythonTool(manager_factory=lambda c, conv: fake)
    tool.run({"code": "1", "timeout_seconds": 9999}, ctx)
    tool.run({"code": "2", "timeout_seconds": 0}, ctx)
    tool.run({"code": "3"}, ctx)
    # 0 falls back to the default exactly like shell's `args.get("timeout") or 120`
    assert [c[1] for c in fake.calls] == [300_000, 60_000, 60_000]


# ---------------------------------------------------------------- reset workspace


def test_reset_success_returns_stale_status_block(store, config, tmp_path, strict_containment, approval_mode=ApprovalMode.auto):
    _, run, ctx = make_ctx(store, config, tmp_path, approval_mode=approval_mode)
    fake = FakeManager(tmp_path)
    result = ResetWorkspaceTool(manager_factory=lambda c, conv: fake).run({}, ctx)
    assert result.ok is True
    assert fake.restarts == ["reset_workspace tool"]
    [block] = result.data["blocks"]
    assert block["kind"] == "status"
    assert block["payload"]["state"] == "stale"
    assert block["payload"]["detail"].startswith("Workspace reset by request")
    assert "generation 7 -> 8" in block["text_fallback"]
    assert "in-memory state is gone" in result.output
    assert "environment_generation" in result.output
    parsed, errors = parse_blocks(result.data["blocks"])
    assert errors == []


def test_reset_busy_refuses_honestly(store, config, tmp_path, strict_containment, approval_mode=ApprovalMode.auto):
    _, _, ctx = make_ctx(store, config, tmp_path, approval_mode=approval_mode)
    fake = FakeManager(tmp_path, restart_result={
        "ok": False, "status": "busy",
        "error": {"type": "Busy", "value": "a cell is still running; interrupt() it first, then reset"}})
    result = ResetWorkspaceTool(manager_factory=lambda c, conv: fake).run({}, ctx)
    assert result.ok is False
    assert "interrupt" in result.output
