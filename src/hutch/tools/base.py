"""Tool protocol and registry shared by all runtimes."""

from __future__ import annotations

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

    def recorded_arguments(self, args: dict[str, Any], ctx: "ToolContext") -> dict[str, Any]:
        """Return the safe-to-persist view of a tool call and its action receipt.

        Most tools record their frozen arguments verbatim. Tools that accept
        transient secrets or other sensitive values must override this method.
        The returned object is used only for audit events and receipts; the
        original immutable arguments are still passed to ``run`` in memory.
        """
        return args

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
        self._cleanup_lock = threading.Lock()
        self._kill_lock = threading.Lock()
        self._cleanup_threads: list[threading.Thread] = []
        self._finished = False
        self._procs: dict[int, subprocess.Popen] = {}
        self._groups: dict[int, dict[str, object]] = {}  # pgid -> verified group identity
        self.killed = False
        self.survivors: list[Any] = []             # processes still alive after the last kill_all (procguard.Proc)
        #: persistence hook, set by the engine: (pid, pgid, starttime, kind, boot_id)
        self.on_register: Optional[Callable[[int, int, int, str, str], None]] = None

    def register(self, proc: subprocess.Popen, kind: str = "tool") -> None:
        ident = procguard.identity(proc.pid)
        with self._lock:
            self._procs[proc.pid] = proc
            self._groups[proc.pid] = {"pid": proc.pid, "pgid": proc.pid,
                                      "starttime": ident.starttime if ident else 0,
                                      "boot_id": procguard.boot_id() if ident else ""}
            if self.killed:  # stop arrived between spawn and register
                self._signal(proc, 9)
        if self.on_register:
            try:
                self.on_register(proc.pid, proc.pid, ident.starttime if ident else 0, kind,
                                 procguard.boot_id() if ident else "")
            except Exception:
                pass

    def unregister(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._procs.pop(proc.pid, None)

    @staticmethod
    def _signal(proc: subprocess.Popen, sig: int) -> None:
        try:
            # Popen holds an unreaped child identity. Descendants are handled through verified
            # process-group identities and pidfds below.
            proc.send_signal(sig)
        except (ProcessLookupError, OSError):
            pass

    def alive(self) -> int:
        with self._lock:
            return sum(1 for p in self._procs.values() if p.poll() is None)

    def kill_all(self, grace: float = 2.0) -> int:
        # Cancellation and final verification may race. Serialize their survivor
        # reports so an older cleanup cannot overwrite the final result.
        with self._kill_lock:
            return self._kill_all(grace)

    def request_cleanup(self) -> None:
        """Start cancellable cleanup once; finish() owns and joins this work."""
        with self._cleanup_lock:
            if self._finished or any(t.is_alive() for t in self._cleanup_threads):
                return
            with self._lock:
                self.killed = True
            thread = threading.Thread(target=self.kill_all, name="hutch-process-cleanup", daemon=False)
            self._cleanup_threads.append(thread)
            thread.start()

    def finish(self, grace: float = 0.5) -> None:
        """Seal async cleanup, join it, then verify before terminal status."""
        with self._cleanup_lock:
            self._finished = True
            threads = list(self._cleanup_threads)
        for thread in threads:
            thread.join()
        self.kill_all(grace)

    def _kill_all(self, grace: float) -> int:
        """End everything the run started: SIGTERM, wait ``grace`` seconds, SIGKILL survivors, then verify. Returns the count
        of live direct children that were signalled; ``self.survivors`` lists anything still alive afterwards."""
        with self._lock:
            self.killed = True
            procs = [p for p in self._procs.values() if p.poll() is None]
            groups = list(self._groups.values())
        for p in procs:
            self._signal(p, 15)
        self.survivors = procguard.end_recorded(groups, term_grace=grace, kill_grace=1.5)
        for p in procs:
            try:
                p.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                self._signal(p, 9)
                try:
                    p.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    pass
        return len(procs)

    def terminate(self, proc: subprocess.Popen, grace: float = 0.2) -> list[Any]:
        """End one registered subprocess and its verified descendants, then return any survivors."""
        with self._lock:
            record = self._groups.get(proc.pid)
        if record is None:
            self._signal(proc, 15)
            try:
                proc.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                self._signal(proc, 9)
            return []
        left = procguard.end_recorded([record], term_grace=grace, kill_grace=1.0)
        self.survivors = left
        try:
            proc.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            self._signal(proc, 9)
        return left


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
    workflow_action_identity: Optional[dict[str, str]] = None  # stable site/instance/slot for workflow effect receipts
    delegation_submit: Optional[Callable[[str, str, str], ToolResult]] = None  # supervised, strict-offline child admission
    delegation_resume: Optional[Callable[[str], ToolResult]] = None  # read a completed child after a durable parent wait
    tool_call_index: Optional[int] = None   # position of this call inside the model response, set by the built-in loop
    skills: Optional[Any] = None      # skills.ResolvedSkills for this run; the engine resolves it once at start
    model_execution_profile: Optional[dict[str, Any]] = None  # exact profile for the active provider turn, if reported

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


def truncation_meta(*, stream: str, retained: int, limit: int, reason: str,
                    observed: int | None = None, omitted: int | None = None,
                    artifact: str | None = None) -> dict[str, Any]:
    """Structured truncation metadata for tool/API/UI consumers."""
    meta: dict[str, Any] = {
        "truncated": True,
        "stream": stream,
        "retained_chars": retained,
        "limit_chars": limit,
        "truncation_reason": reason,
    }
    if observed is not None:
        meta["observed_chars"] = observed
    if omitted is not None:
        meta["omitted_chars"] = omitted
    if artifact is not None:
        meta["artifact"] = artifact
    return meta


def read_text_bounded(path: Path, limit: int = MAX_TOOL_OUTPUT) -> tuple[str, dict[str, Any]]:
    """Read a text file without materializing more than ``limit`` characters."""
    p = path if isinstance(path, Path) else Path(path)
    parts: list[str] = []
    retained = 0
    truncated = False
    with p.open("rb") as fh:
        while retained < limit:
            chunk = fh.read(65_536)
            if not chunk:
                break
            text = chunk.decode("utf-8", errors="replace")
            room = limit - retained
            if len(text) <= room:
                parts.append(text)
                retained += len(text)
            else:
                parts.append(text[:room])
                retained += room
                truncated = True
                break
        else:
            # Retained filled the budget; peek whether more bytes remain.
            if fh.read(1):
                truncated = True
    try:
        file_bytes = p.stat().st_size
    except OSError:
        file_bytes = None
    output = "".join(parts)
    data: dict[str, Any] = {"retained_chars": retained, "limit_chars": limit,
                            "truncated": truncated}
    if file_bytes is not None:
        data["file_bytes"] = file_bytes
    if truncated:
        note = f"\n… [output clipped while reading; retained {retained:,} of at most {limit:,} chars"
        if file_bytes is not None:
            note += f"; file is {file_bytes:,} bytes"
        note += "]"
        output += note
        data.update(truncation_meta(stream="stdout", retained=retained, limit=limit,
                                    reason="capture_limit",
                                    observed=None if file_bytes is None else None))
    return output, data


def _schema(required: list[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required}
