"""Tool protocol and registry shared by all runtimes."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from .. import procguard
from ..config import hutchConfig
from ..models import Bot, Run
from ..safety import PolicyEngine
from ..approvals import ApprovalGate
from ..store import Store


@dataclass
class ToolResult:
    ok: bool
    output: str = ""          # text fed back to the model
    data: dict[str, Any] = field(default_factory=dict)


def rehearsed(what: str, decision=None) -> ToolResult:
    """What a mutating tool returns in Rehearse mode: nothing ran, and the policy's verdict on it is reported, so a
    person (and the model) sees both what would happen and whether it would be allowed."""
    if decision is not None and decision.verdict.value == "deny":
        return ToolResult(ok=False, output=f"[rehearsal] would be BLOCKED: {decision.reason}. Nothing was changed.",
                          data={"simulated": True, "blocked": True})
    verdict = ""
    if decision is not None:
        verdict = {"allow": " Policy: allowed.", "ask": f" Policy: would pause for approval ({decision.reason})."}.get(
            decision.verdict.value, "")
    return ToolResult(ok=True, output=f"[rehearsal] would {what}.{verdict} Nothing was changed.", data={"simulated": True})


class Tool:
    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {}  # JSON Schema for the arguments object

    def run(self, args: dict[str, Any], ctx: "ToolContext") -> ToolResult:  # pragma: no cover
        raise NotImplementedError

    def effect(self, args: dict[str, Any], ctx: "ToolContext") -> str:
        """What kind of lasting effect this call can have: "" (none: a read), "fs", "process" or "web".

        A call with an effect gets an intent row before it runs and a receipt after (ADR-0003), so a crash in between is
        reported as an unknown outcome and never silently replayed."""
        return ""

    def spec(self) -> dict[str, Any]:
        """OpenAI-style function tool schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ProcRegistry:
    """Every process a run starts, so ending the run can end them - not just the agent loop (UI-2, ADR-0004).

    Children are started in their own session (process group), so a shell that forked helpers is ended as a tree. The registry
    remembers every group it was ever given, not only the live ones: a command that backgrounds a server and exits leaves a group
    with no registered leader, and "nothing a run started may outlive it" must still hold. After signalling it VERIFIES
    (``survivors``): success is measured, not assumed.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._procs: dict[int, subprocess.Popen] = {}
        self._groups: dict[int, int] = {}          # pgid -> start time of the process that led it
        self.killed = False
        self.survivors: list[Any] = []             # processes still alive after the last kill_all (procguard.Proc)
        #: persistence hooks, set by the engine: (pid, pgid, starttime, kind) / (pid)
        self.on_register: Optional[Callable[[int, int, int, str], None]] = None
        self.on_unregister: Optional[Callable[[int], None]] = None

    def register(self, proc: subprocess.Popen, kind: str = "tool") -> None:
        ident = procguard.identity(proc.pid)
        with self._lock:
            self._procs[proc.pid] = proc
            self._groups[proc.pid] = ident.starttime if ident else 0
            if self.killed:  # stop arrived between spawn and register
                self._signal(proc, signal.SIGKILL)
        if self.on_register:
            try:
                self.on_register(proc.pid, proc.pid, ident.starttime if ident else 0, kind)
            except Exception:
                pass

    def unregister(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._procs.pop(proc.pid, None)
        if self.on_unregister:
            try:
                self.on_unregister(proc.pid)
            except Exception:
                pass

    @staticmethod
    def _signal(proc: subprocess.Popen, sig: int) -> None:
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.send_signal(sig)
            except (ProcessLookupError, OSError):
                pass

    def alive(self) -> int:
        with self._lock:
            return sum(1 for p in self._procs.values() if p.poll() is None)

    def kill_all(self, grace: float = 2.0) -> int:
        """End everything the run started: SIGTERM, wait ``grace`` seconds, SIGKILL survivors, then verify. Returns the count
        of live direct children that were signalled; ``self.survivors`` lists anything still alive afterwards."""
        with self._lock:
            self.killed = True
            procs = [p for p in self._procs.values() if p.poll() is None]
            groups = dict(self._groups)
        for p in procs:
            self._signal(p, signal.SIGTERM)
        deadline = time.monotonic() + grace
        for p in procs:
            try:
                p.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                self._signal(p, signal.SIGKILL)
        if groups:
            # the groups' remaining members and their descendants (a backgrounded helper outlives its shell)
            self.survivors = procguard.end_groups(groups.keys(), not_before=min(groups.values()), term_grace=0.2, kill_grace=1.5)
        return len(procs)


@dataclass
class ToolContext:
    bot: Bot
    run: Run
    store: Store
    policy: PolicyEngine
    gate: ApprovalGate
    config: hutchConfig
    workspace: Path
    headless: bool = True
    on_finish: list[Callable[[], None]] = field(default_factory=list)
    emit: Optional[Callable[[Any], None]] = None  # sink for run events (used by browser pause-to-human)
    procs: ProcRegistry = field(default_factory=ProcRegistry)
    cancel_hooks: list[Callable[[], None]] = field(default_factory=list)  # abort in-flight I/O on stop
    dry_run: bool = False             # Rehearse mode: mutating actions are simulated, reads still run
    closed: bool = False              # the run is over: a worker that outlived it must not start another action
    receipt: Optional[Callable[[], Optional[str]]] = None   # set per call by the runtime: records the intent (see begin_effect)

    def begin_effect(self) -> Optional[str]:
        """Call right BEFORE performing a lasting effect, after policy and approval have said yes. Records the intent
        (ADR-0003) and checks the run is still ours and not being stopped. Returns None to proceed, or the reason the action
        must not start. Waiting for a human is not an effect, so a run killed during an approval is not "unknown"."""
        if self.receipt is None:
            return None
        begin, self.receipt = self.receipt, None          # once per call
        return begin()


#: Tools return up to this much (a hard memory bound). What the MODEL sees is truncated to a per-tool limit in
#: ``runtime.steps.call_tool`` and the full text is saved as an artifact (PF-2): "MCP tools dumping huge JSON
#: into context" is a documented failure, but silently losing the rest is a worse one.
MAX_TOOL_OUTPUT = 1_000_000


def clip(text: str, limit: int = MAX_TOOL_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n… [output clipped, {len(text) - limit} chars omitted]"


def _schema(required: list[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required}
