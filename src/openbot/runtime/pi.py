"""Pi runtime adapter — drives the Pi coding agent (https://pi.dev) over RPC stdio.

One `pi` process per run, with cwd pinned to the run workspace: natural
process/workspace isolation, no ports, no daemon. Wire protocol follows
pi.dev/docs/latest/rpc (JSONL request lines in, event/result lines out).

Trade-off (documented in docs/safety.md): Pi runs with its own tool system;
OpenBot's approval gates apply to the workspace boundary (cwd jail, policy on
commands OpenBot itself runs) but not to Pi-internal tool calls.

Requires `pi` on PATH:  npm i -g @earendil-works/pi-coding-agent
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
from typing import Callable

from ..models import Event, EventType, Run
from ..tools import Tool, ToolContext
from .base import RunAborted

RPC_TIMEOUT = 600


class PiRuntime:
    kind = "pi"

    def __init__(self, binary: str = "pi"):
        self.binary = binary

    def execute(
        self,
        run: Run,
        ctx: ToolContext,
        tools: dict[str, Tool],
        stop: Callable[[], bool],
    ) -> str:
        if not shutil.which(self.binary):
            raise RunAborted(
                "error",
                f"'{self.binary}' not found on PATH — install Pi (npm i -g @earendil-works/pi-coding-agent) "
                "or switch this bot to the builtin runtime",
            )

        argv = [self.binary, "--mode", "rpc", "--no-session"]
        try:
            proc = subprocess.Popen(
                argv, cwd=ctx.workspace,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, start_new_session=True,
            )
        except OSError as exc:
            raise RunAborted("error", f"failed to start pi: {exc}") from exc

        final_parts: list[str] = []
        lines: list[str] = []

        def reader():
            assert proc.stdout is not None
            for line in proc.stdout:
                lines.append(line)

        thread = threading.Thread(target=reader, daemon=True)
        thread.start()

        try:
            request = {"id": 1, "method": "prompt", "params": {"text": run.prompt}}
            assert proc.stdin is not None
            proc.stdin.write(json.dumps(request) + "\n")
            proc.stdin.flush()

            import time
            deadline = time.monotonic() + RPC_TIMEOUT
            while time.monotonic() < deadline:
                if stop():
                    proc.terminate()
                    raise RunAborted("stopped", "user requested stop")
                if thread.is_alive() or lines:
                    self._drain(lines, run, final_parts)
                if proc.poll() is not None and not lines:
                    break
                thread.join(timeout=0.5)
                if proc.poll() is not None:
                    self._drain(lines, run, final_parts)
                    break
                if not thread.is_alive() and not lines:
                    break
            else:
                proc.kill()
                raise RunAborted("timeout", "pi RPC did not finish in time")
        finally:
            if proc.poll() is None:
                proc.terminate()

        self._drain(lines, run, final_parts)
        summary = "\n".join(final_parts).strip()
        if proc.returncode not in (0, None):
            err = (proc.stderr.read() if proc.stderr else "") or ""
            raise RunAborted("failed", f"pi exited {proc.returncode}: {err[:500]}")
        if not summary:
            summary = "(pi produced no final message — see run transcript)"
        ctx.emit(Event(run_id=run.id, type=EventType.message,
                       data={"role": "assistant", "content": summary}))
        return summary

    @staticmethod
    def _drain(lines: list[str], run: Run, final_parts: list[str]) -> None:
        while lines:
            line = lines.pop(0)
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = str(ev.get("type") or ev.get("event") or "").lower()
            text = ev.get("text") or ev.get("content") or ev.get("message") or ""
            if not isinstance(text, str):
                text = json.dumps(text)
            if kind in ("error",):
                ctx_note = f"pi error: {text[:500]}"
                final_parts.append(ctx_note)
                continue
            if kind in ("result", "done", "completed", "message", "assistant"):
                if text:
                    final_parts.append(text)
            elif text:
                run.steps += 1
