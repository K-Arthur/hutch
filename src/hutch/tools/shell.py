"""Shell tool — jailed to the run workspace, policy-gated, output-clipped.

The subprocess runs with HOME pointed at the run directory so accidental
~/.ssh or ~/.aws access from inside a bot lands on an empty home, not the
user's real one (Grok uploading a user's home directory is the incident this
answers).
"""

from __future__ import annotations

import os
import signal
import subprocess
from typing import Any

from .. import sandbox
from ..safety import Verdict, is_read_only
from .base import Tool, ToolContext, ToolResult, _schema, clip, rehearsed


class ShellTool(Tool):
    name = "shell"
    description = (
        "Run a bash command inside this bot's workspace. Working directory is the workspace. "
        "Read-only commands run freely; mutating or risky commands require user approval. "
        "Output is combined stdout+stderr, truncated."
    )
    parameters = _schema(
        ["command"],
        {
            "command": {"type": "string", "description": "The bash command line to run"},
            "timeout": {"type": "integer", "description": "Timeout in seconds (default 120, max 300)"},
        },
    )

    def effect(self, args: dict[str, Any], ctx: ToolContext) -> str:
        command = (args.get("command") or "").strip()
        return "" if (not command or is_read_only(command)) else "process"

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        command = (args.get("command") or "").strip()
        if not command:
            return ToolResult(ok=False, output="error: 'command' is required")
        timeout = min(int(args.get("timeout") or 120), 300)

        decision = ctx.policy.check_shell(command)
        if ctx.dry_run and not (decision.verdict is Verdict.allow and is_read_only(command)):
            return rehearsed(f"run `{command}`", decision)         # reads still run; anything else is only described
        try:
            ctx.gate.decide("shell", f"$ {command}", {"command": command}, decision)
        except Exception as exc:
            return ToolResult(ok=False, output=f"error: {exc}", data={"command": command})

        mode = sandbox.mode_for(ctx.bot)
        if mode == "strict":
            st = sandbox.status()
            if not st.ok:                 # fail closed: a bot that requires containment never runs uncontained by accident
                return ToolResult(ok=False, data={"command": command, "sandbox": "unavailable"},
                                  output=("error: this bot requires the OS sandbox and it is unavailable here: "
                                          f"{st.reason}. Nothing was run. Fix it (`hutch doctor`), or set the bot's sandbox to "
                                          "'off' to run commands uncontained."))
        refusal = ctx.begin_effect()
        if refusal:
            return ToolResult(ok=False, output=f"error: {refusal}", data={"command": command})
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(ctx.workspace),
            "LANG": "C.UTF-8",
            "TERM": "dumb",
        }
        argv = ["/bin/bash", "-c", command]
        if mode == "strict":
            argv = sandbox.shell_argv(command, sandbox.policy_for(ctx.bot, ctx.workspace))
        try:
            proc = subprocess.Popen(
                argv,
                cwd=ctx.workspace, env=env, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True,  # own process group: Stop and timeouts kill the whole tree
            )
        except FileNotFoundError:
            return ToolResult(ok=False, output="error: no shell available", data={"command": command})
        ctx.procs.register(proc, "shell")
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            ctx.procs._signal(proc, signal.SIGKILL)
            proc.communicate()
            return ToolResult(ok=False, output=f"error: timed out after {timeout}s", data={"command": command})
        finally:
            ctx.procs.unregister(proc)

        if ctx.procs.killed:
            return ToolResult(ok=False, output="error: stopped — command was killed", data={"command": command})
        out = stdout
        if stderr:
            out += ("\n" if out else "") + stderr
        return ToolResult(
            ok=proc.returncode == 0,
            output=clip(f"exit={proc.returncode}\n{out.strip() or '(no output)'}"),
            data={"command": command, "exit_code": proc.returncode, "sandbox": mode},
        )
