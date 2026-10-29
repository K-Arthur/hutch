"""run_python / reset_workspace: the contained persistent Python workspace.

Follows ``tools/shell.py``'s policy sequence (policy check -> approval gate ->
begin_effect -> run -> receipt) with one deliberate difference, stated in the
module docstring of ``hutch.workspace.manager``: there is NO uncontained mode.
The shell can run with containment off when a bot owner chooses it; Python
cells cannot, a persistent interpreter that remembered state between cells
would be exactly the trust boundary the strict profile exists to draw. When
strict containment is off or unavailable the tools refuse, fail-closed.

Approval semantics mirror the shell's sticky pattern: ask-by-default with
sticky keys (``python:exec`` / ``workspace:reset``), so a standing "always
allow" covers later calls; the tier translates the ask the same way
``PolicyEngine._tier`` does for shell commands (readonly denies, trusted
allows). Bot shell rules are not matched against Python source, a glob
written for command segments says nothing about a cell.

The model sees a bounded textual summary only; everything rich travels as
typed blocks on ``ToolResult.data["blocks"]``: one hash-bound ``code_receipt``
(the EXACT submitted code plus execution evidence) plus any blocks the cell
emitted. Validation of those blocks happens once, in ``call_tool``, the same
as every other tool; this module never bypasses it.
"""

from __future__ import annotations

from typing import Any, Callable

from .. import sandbox
from ..outputblocks import new_block_id
from ..safety import Decision, Verdict
from ..workspace import protocol
from ..workspace.manager import WorkspaceManager, manager_for_conversation
from .base import Tool, ToolContext, ToolResult, _schema, clip, rehearsed

#: protocol receipt status -> code_receipt execution status (the block
#: contract's vocabulary; a confirmed interrupt is reported as 'cancelled',#: the execution did not finish, and 'interrupted' is not a contract status).
EXECUTION_STATUS = {
    "ok": "ok",
    "error": "error",
    "timeout": "timeout",
    "interrupted": "cancelled",
    "interrupt_unconfirmed": "interrupt_unconfirmed",
}

#: code_receipt.source bound (contract): submissions past it cannot produce
#: a valid receipt, so they are refused up front.
MAX_CODE_CHARS = 100_000

#: The model-facing summary stays small; the receipt carries the detail.
OUTPUT_TEXT_LIMIT = 2_000

ManagerFactory = Callable[[ToolContext, str], WorkspaceManager]


def _default_manager_factory(ctx: ToolContext, conversation_id: str) -> WorkspaceManager:
    return manager_for_conversation(ctx.store, conversation_id, ctx.config.state_dir)


def _python_decision(policy: Any) -> Decision:
    """Ask-by-default, tier-translated like ``PolicyEngine._tier``."""
    decision = Decision(Verdict.ask, "runs Python code in the contained workspace",
                        "python:exec", rule="ask:python-exec", risk="medium")
    if decision.verdict is not Verdict.ask:  # pragma: no cover - defensive
        return decision
    tier = getattr(policy, "tier", "supervised")
    if tier == "readonly":
        return Decision(Verdict.deny, "this bot is read-only, so it may not run Python",
                        rule="deny:tier-readonly", risk="medium")
    if tier == "trusted":
        return Decision(Verdict.allow, "allowed: this bot is trusted", rule="allow:tier-trusted",
                        risk="medium")
    return decision


def _conversation_id(ctx: ToolContext) -> str:
    return getattr(ctx.run, "conversation_id", "") or ""


def _first_line(text: str, limit: int = 80) -> str:
    line = text.strip().splitlines()[0] if text.strip() else ""
    return line[:limit]


def _receipt_fallback(code: str, receipt: dict[str, Any], response: dict[str, Any]) -> str:
    """The readable alternative for the code_receipt (mirrors the contract
    fixture's wording, bounded)."""
    lines = code.count("\n") + 1
    status = receipt.get("status", "ok")
    if status == "ok":
        printed = _first_line(response.get("stdout_tail", ""))
        returned = (response.get("result_repr") or "None")[:80]
        printed_part = f"it printed {printed!r} and " if printed else "it "
        return f"Ran {lines} lines of Python; {printed_part}returned {returned}."
    if status == "error":
        error = response.get("error") or {}
        detail = f"{error.get('type', 'Error')}: {_first_line(str(error.get('value', '')), 100)}" \
            if error else "it raised"
        return f"Ran {lines} lines of Python; it failed ({detail})."
    if status == "timeout":
        return (f"Ran {lines} lines of Python; it was terminated at its time/output limit "
                "with the tails up to the cut preserved.")
    if status == "interrupt_unconfirmed":
        return (f"Ran {lines} lines of Python; an interrupt was sent but the cell never "
                "confirmed it stopped.")
    return f"Ran {lines} lines of Python; the interrupt was confirmed." if status == "interrupted" \
        else f"Ran {lines} lines of Python ({status})."


def _block_envelope(kind: str, payload: dict[str, Any], text_fallback: str,
                    run_id: str, tool: str) -> dict[str, Any]:
    return {
        "v": protocol.PROTOCOL_VERSION,
        "id": new_block_id(),
        "kind": kind,
        "revision": 1,
        "availability": "ready",
        "text_fallback": text_fallback[:4000] or f"{kind} block from the Python workspace",
        "provenance": {"run_id": run_id, "tool": tool},
        "payload": payload,
    }


class RunPythonTool(Tool):
    """Run Python in the conversation's contained, persistent workspace."""

    name = "run_python"
    description = (
        "Run Python code in this conversation's persistent workspace (one contained "
        "interpreter; variables and imports survive between calls within the same "
        "environment). Working directory is the workspace; there is no network access. "
        "Every call returns a code receipt; emit_block() inside the cell can present "
        "typed blocks, and files the cell writes are reported. Requires OS containment."
    )
    parameters = _schema(
        ["code"],
        {
            "code": {"type": "string", "description": "The Python source to execute"},
            "timeout_seconds": {"type": "integer",
                                "description": "Wall-clock limit in seconds (default 60, max 300)"},
        },
    )

    def __init__(self, manager_factory: ManagerFactory | None = None):
        self._factory = manager_factory or _default_manager_factory

    def effect(self, args: dict[str, Any], ctx: ToolContext) -> str:
        code = args.get("code") if isinstance(args.get("code"), str) else ""
        return "process" if code.strip() else ""

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        code = args.get("code")
        if not isinstance(code, str) or not code.strip():
            return ToolResult(ok=False, output="error: 'code' is required")
        if len(code) > MAX_CODE_CHARS:
            return ToolResult(ok=False,
                              output=f"error: code is {len(code):,} chars; the receipt is "
                                     f"bounded at {MAX_CODE_CHARS:,} — split the cell")
        try:
            timeout_seconds = min(max(int(args.get("timeout_seconds") or 60), 1), 300)
        except (TypeError, ValueError):
            return ToolResult(ok=False, output="error: 'timeout_seconds' must be an integer")

        conversation_id = _conversation_id(ctx)
        if not conversation_id:
            return ToolResult(ok=False,
                              output="error: run_python needs a conversation-scoped workspace, "
                                     "and this run has no conversation id. Nothing was run.",
                              data={"code_sha256": protocol.sha256_of_source(code)})

        # ---- policy check + approval gate (mirrors shell.py's sequence) ----
        mode = sandbox.mode_for(ctx.bot)
        if mode != "strict":
            return ToolResult(
                ok=False,
                data={"code_sha256": protocol.sha256_of_source(code), "sandbox": mode},
                output=("error: run_python only runs inside OS containment (strict mode); "
                        "there is no uncontained Python workspace. Set the bot's sandbox to "
                        "'strict' to use it. Nothing was run."))
        decision = _python_decision(ctx.policy)
        action = f"run Python code ({len(code):,} chars)"
        if ctx.dry_run:
            return rehearsed(action, decision)      # Rehearse mode: nothing is executed, reads included
        try:
            ctx.gate.decide(self.name, action,
                            {"code": code, "timeout_seconds": timeout_seconds,
                             "conversation_id": conversation_id, "sandbox": mode},
                            decision)
        except Exception as exc:
            return ToolResult(ok=False, output=f"error: {exc}",
                              data={"code_sha256": protocol.sha256_of_source(code)})

        # ---- fail-closed availability (mirrors shell.py:63-69) ----
        st = sandbox.status()
        if not st.ok:
            return ToolResult(
                ok=False,
                data={"code_sha256": protocol.sha256_of_source(code), "sandbox": "unavailable"},
                output=("error: this bot requires the OS sandbox and it is unavailable here: "
                        f"{st.reason}. Nothing was run. Fix it (`hutch doctor`), or do not "
                        "grant run_python to this bot."))

        refusal = ctx.begin_effect()
        if refusal:
            return ToolResult(ok=False, output=f"error: {refusal}",
                              data={"code_sha256": protocol.sha256_of_source(code)})

        try:
            manager = self._factory(ctx, conversation_id)
        except Exception as exc:
            return ToolResult(ok=False, output=f"error: {exc}")
        response = manager.execute(code, timeout_seconds * 1000, procs=ctx.procs)
        return self._present(response, code, timeout_seconds, ctx, manager, mode)

    # ------------------------------------------------------------------ receipt

    def _present(self, response: dict[str, Any], code: str, timeout_seconds: int,
                 ctx: ToolContext, manager: WorkspaceManager, mode: str) -> ToolResult:
        status = response.get("status")
        base_data: dict[str, Any] = {
            "sandbox": mode,
            "workspace": str(manager.workspace_dir),
            "environment_generation": manager.session_info()["generation"],
            "code_sha256": protocol.sha256_of_source(code),
        }
        receipt = response.get("receipt") if isinstance(response.get("receipt"), dict) else None
        if receipt is not None:
            base_data["exec_status"] = receipt.get("status")
            base_data["ordinal"] = receipt.get("ordinal")
            base_data["environment_generation"] = receipt.get("environment_generation",
                                                              base_data["environment_generation"])

        blocks: list[dict[str, Any]] = []
        if receipt is not None:
            blocks.append(_block_envelope(
                "code_receipt",
                {
                    "source": code,
                    "language": "python",
                    "source_sha256": protocol.sha256_of_source(code),
                    "execution": {
                        "ordinal": max(1, int(receipt.get("ordinal") or 1)),
                        "environment_generation": max(1, int(receipt.get("environment_generation") or 1)),
                        "started_at": str(receipt.get("started_at", ""))[:64],
                        "finished_at": str(receipt.get("finished_at", ""))[:64],
                        "status": EXECUTION_STATUS.get(receipt.get("status"), "error"),
                        "stdout_chars_total": max(0, int(receipt.get("stdout_chars_total") or 0)),
                        "stderr_chars_total": max(0, int(receipt.get("stderr_chars_total") or 0)),
                    },
                    "stdout_tail": str(response.get("stdout_tail", ""))[:4000],
                    "stderr_tail": str(response.get("stderr_tail", ""))[:4000],
                    "result_repr": str(response.get("result_repr", ""))[:2000],
                    "produced_files": [f for f in response.get("produced_files", [])
                                       if isinstance(f, dict)][:32],
                },
                _receipt_fallback(code, receipt, response),
                ctx.run.id, self.name))

        # blocks the cell emitted (payload dicts from the child -> envelopes)
        for emitted in response.get("blocks", []) or []:
            if not isinstance(emitted, dict) or "kind" not in emitted or "payload" not in emitted:
                continue
            blocks.append(_block_envelope(
                str(emitted["kind"]), emitted.get("payload"),
                str(emitted.get("text_fallback", "")),
                ctx.run.id, self.name))

        if status in ("lost", "timeout", "interrupt_unconfirmed"):
            blocks.append(_block_envelope(
                "status",
                {"stage": "workspace",
                 "detail": str((response.get("error") or {}).get("value", status))[:2000],
                 "state": "failed" if status != "interrupt_unconfirmed" else "cancelled"},
                f"Python workspace problem: {status}",
                ctx.run.id, self.name))

        base_data["blocks"] = blocks
        return ToolResult(ok=status == "ok" and receipt is not None
                          and receipt.get("status") == "ok",
                          output=clip(self._model_text(status, receipt, response,
                                                       timeout_seconds, base_data),
                                      OUTPUT_TEXT_LIMIT),
                          data=base_data)

    def _model_text(self, status: str, receipt: dict[str, Any] | None, response: dict[str, Any],
                    timeout_seconds: int, data: dict[str, Any]) -> str:
        generation = data.get("environment_generation")
        ordinal = data.get("ordinal", "?")
        if status == "busy":
            return ("error: another Python cell is already running in this workspace; "
                    "wait for it to finish (nothing was queued)")
        if status == "error":
            error = response.get("error") or {}
            return f"error: {error.get('type', 'Error')}: {error.get('value', '')}"
        if status == "lost":
            return ("error: the workspace interpreter died unexpectedly. In-memory state from "
                    "earlier cells is GONE; the next run_python starts a fresh environment "
                    "(a new generation number marks outputs made after this point).")
        if status == "interrupt_unconfirmed":
            return ("error: interrupt sent, but the cell did not acknowledge it within 3s "
                    "(receipt status: interrupt_unconfirmed). reset_workspace guarantees a stop.")
        if status == "timeout":
            return (f"error: the cell hit its {timeout_seconds}s limit and was terminated; "
                    "stdout/stderr tails up to the cut are in the code receipt")
        assert receipt is not None
        cell_status = receipt.get("status")
        produced = len(response.get("produced_files", []) or [])
        emitted = len(response.get("blocks", []) or [])
        head = f"python {cell_status} (generation {generation}, exec #{ordinal})"
        if cell_status == "ok":
            body = response.get("result_repr") or _first_line(response.get("stdout_tail", ""), 400) \
                or "(no output)"
            tail = f"; {produced} file(s) created" if produced else ""
            tail += f"; {emitted} block(s) emitted" if emitted else ""
            return f"{head}\n{body}{tail}"
        error = response.get("error") or {}
        tail_text = _first_line(response.get("stderr_tail", ""), 400) or \
            _first_line(response.get("stdout_tail", ""), 400)
        body = f"{error.get('type', cell_status)}: {error.get('value', '')}".strip()
        if tail_text and cell_status != "error":
            body = body or tail_text
        return f"{head}\n{body}".strip()


class ResetWorkspaceTool(Tool):
    """Terminate the conversation's Python workspace and bump its generation."""

    name = "reset_workspace"
    description = (
        "Reset this conversation's Python workspace: the interpreter process is terminated "
        "(verified) and a fresh environment generation starts on the next run_python. ALL "
        "in-memory state (variables, imports, open handles) is gone; files written to the "
        "workspace directory remain. Outputs produced before the reset carry an older "
        "environment generation and can be recognised as stale by that number."
    )
    parameters = _schema([], {})

    def __init__(self, manager_factory: ManagerFactory | None = None):
        self._factory = manager_factory or _default_manager_factory

    def effect(self, args: dict[str, Any], ctx: ToolContext) -> str:
        return "process"

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        conversation_id = _conversation_id(ctx)
        if not conversation_id:
            return ToolResult(ok=False,
                              output="error: reset_workspace needs a conversation-scoped "
                                     "workspace, and this run has no conversation id.")
        mode = sandbox.mode_for(ctx.bot)
        if mode != "strict":
            return ToolResult(ok=False,
                              output="error: reset_workspace applies to the contained Python "
                                     "workspace, which requires strict mode; there is nothing "
                                     "to reset.",
                              data={"sandbox": mode})
        decision = Decision(Verdict.ask, "terminates the conversation's Python interpreter",
                            "workspace:reset", rule="ask:workspace-reset", risk="medium")
        if ctx.dry_run:
            return rehearsed("reset the Python workspace (all in-memory state is lost)", decision)
        try:
            ctx.gate.decide(self.name, "reset the Python workspace",
                            {"conversation_id": conversation_id, "sandbox": mode}, decision)
        except Exception as exc:
            return ToolResult(ok=False, output=f"error: {exc}")
        refusal = ctx.begin_effect()
        if refusal:
            return ToolResult(ok=False, output=f"error: {refusal}")
        try:
            manager = self._factory(ctx, conversation_id)
            result = manager.restart(reason="reset_workspace tool")
        except Exception as exc:
            return ToolResult(ok=False, output=f"error: {exc}")
        if not result.get("ok"):
            error = result.get("error") or {}
            return ToolResult(ok=False,
                              output=f"error: workspace not reset: {error.get('value', 'busy')} — "
                                     "interrupt the running cell first.",
                              data={"sandbox": mode})
        stale = result.get("stale", {})
        blocks = [_block_envelope(
            "status",
            {"stage": "workspace",
             "detail": (f"Workspace reset by request: environment generation "
                        f"{stale.get('generation_ended')} ended; the next run_python starts "
                        f"generation {result.get('generation')}. Outputs produced under the old "
                        "generation are stale."),
             "state": "stale"},
            (f"Python workspace reset: generation {stale.get('generation_ended')} -> "
             f"{result.get('generation')}; prior outputs are stale."),
            ctx.run.id, self.name)]
        return ToolResult(
            ok=True,
            output=clip(
                f"workspace reset: generation {stale.get('generation_ended')} -> "
                f"{result.get('generation')} (verified teardown, {result.get('survivors', 0)} "
                "survivors). All in-memory state is gone; files in the workspace directory "
                "remain. Outputs from the old generation are stale (compare "
                "environment_generation on their receipts).",
                OUTPUT_TEXT_LIMIT),
            data={"blocks": blocks, "sandbox": mode, "generation": result.get("generation"),
                  "stale": stale})


TOOLS: list[Tool] = [RunPythonTool(), ResetWorkspaceTool()]
