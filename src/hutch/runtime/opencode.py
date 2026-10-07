"""OpenCode runtime adapter — one-shot `opencode run` per run.

Uses OpenCode's headless CLI (`opencode run <prompt> --format json --auto`)
with cwd pinned to the run workspace. `--auto` lets OpenCode approve its own
tool calls (OpenCode's permission config still applies per-project); hutch's
gates own the workspace boundary and everything hutch runs itself. See
docs/safety.md for the trust trade-off.

Requires `opencode` on PATH.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Callable

from ..models import Event, EventType, Run
from ..tools import Tool, ToolContext
from .base import RunAborted

OC_TIMEOUT = 900


class OpenCodeRuntime:
    kind = "opencode"

    def __init__(self, binary: str = "opencode"):
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
                f"'{self.binary}' not found on PATH — install opencode (https://opencode.ai) "
                "or switch this bot to the builtin runtime",
            )

        argv = [self.binary, "run", run.prompt, "--format", "json", "--auto"]
        try:
            proc = subprocess.Popen(
                argv, cwd=ctx.workspace,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, start_new_session=True,
            )
        except OSError as exc:
            raise RunAborted("error", f"failed to start opencode: {exc}") from exc

        import time
        final_parts: list[str] = []
        deadline = time.monotonic() + OC_TIMEOUT
        while True:
            if stop():
                proc.terminate()
                raise RunAborted("stopped", "user requested stop")
            try:
                line = proc.stdout.readline() if proc.stdout else ""
            except ValueError:  # closed pipe
                break
            if not line:
                if proc.poll() is not None:
                    break
                if time.monotonic() > deadline:
                    proc.kill()
                    raise RunAborted("timeout", "opencode run exceeded time budget")
                continue
            self._handle_line(line, run, final_parts)

        proc.wait(timeout=30)
        summary = "\n".join(final_parts).strip() or "(opencode produced no final message — see transcript)"
        if proc.returncode != 0:
            err = (proc.stderr.read() if proc.stderr else "") or ""
            raise RunAborted("failed", f"opencode exited {proc.returncode}: {err[:500]}")
        ctx.emit(Event(run_id=run.id, type=EventType.message,
                       data={"role": "assistant", "content": summary}))
        return summary

    @staticmethod
    def _handle_line(line: str, run: Run, final_parts: list[str]) -> None:
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            if line.strip():
                final_parts.append(line.strip())
            return
        kind = str(ev.get("type", "")).lower()
        text = ev.get("text") or ev.get("content") or ev.get("message") or ""
        if not isinstance(text, str):
            text = json.dumps(text)
        if kind in ("error",):
            final_parts.append(f"opencode error: {text[:500]}")
        elif kind in ("result", "message", "assistant", "done"):
            if text:
                final_parts.append(text)
        elif text:
            run.steps += 1
