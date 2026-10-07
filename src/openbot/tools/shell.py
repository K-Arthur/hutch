"""Shell tool — jailed to the run workspace, policy-gated, output-clipped.

The subprocess runs with HOME pointed at the run directory so accidental
~/.ssh or ~/.aws access from inside a bot lands on an empty home, not the
user's real one (Grok uploading a user's home directory is the incident this
answers).
"""

from __future__ import annotations

import os
import subprocess
from typing import Any

from .base import Tool, ToolContext, ToolResult, _schema, clip


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

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        command = (args.get("command") or "").strip()
        if not command:
            return ToolResult(ok=False, output="error: 'command' is required")
        timeout = min(int(args.get("timeout") or 120), 300)

        decision = ctx.policy.check_shell(command)
        try:
            ctx.gate.decide("shell", f"$ {command}", {"command": command}, decision)
        except Exception as exc:
            return ToolResult(ok=False, output=f"error: {exc}", data={"command": command})

        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(ctx.workspace),
            "LANG": "C.UTF-8",
            "TERM": "dumb",
        }
        try:
            proc = subprocess.run(
                ["/bin/bash", "-c", command],
                cwd=ctx.workspace,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(ok=False, output=f"error: timed out after {timeout}s", data={"command": command})
        except FileNotFoundError:
            return ToolResult(ok=False, output="error: no shell available", data={"command": command})

        out = proc.stdout
        if proc.stderr:
            out += ("\n" if out else "") + proc.stderr
        return ToolResult(
            ok=proc.returncode == 0,
            output=clip(f"exit={proc.returncode}\n{out.strip() or '(no output)'}"),
            data={"command": command, "exit_code": proc.returncode},
        )
