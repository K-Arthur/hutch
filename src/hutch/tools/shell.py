"""Shell tool — jailed to the run workspace, policy-gated, output-clipped.

The subprocess runs with HOME pointed at the run directory so accidental
~/.ssh or ~/.aws access from inside a bot lands on an empty home, not the
user's real one (Grok uploading a user's home directory is the incident this
answers).
"""

from __future__ import annotations

import os
import selectors
import subprocess
import time
from typing import Any

from .. import sandbox
from ..safety import Verdict, is_read_only
from .base import MAX_TOOL_OUTPUT, Tool, ToolContext, ToolResult, _schema, clip, rehearsed


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
        capture_limit = MAX_TOOL_OUTPUT - 512  # leave room for status and the truncation marker
        mode = sandbox.mode_for(ctx.bot)
        if mode == "strict" and ctx.bot.shell_network:
            return ToolResult(ok=False, data={"command": command, "sandbox": "strict"},
                              output=("error: this bot requests shell network access, which strict mode cannot grant safely. "
                                      "Nothing was run. Use Hutch's checked web_fetch tool for public-page requests, "
                                      "or turn off OS containment for this bot explicitly."))

        decision = ctx.policy.check_shell(command)
        if ctx.dry_run and not (decision.verdict is Verdict.allow and is_read_only(command)):
            return rehearsed(f"run `{command}`", decision)         # reads still run; anything else is only described
        try:
            ctx.gate.decide("shell", f"$ {command}", {"command": command, "timeout": timeout,
                            "workspace": str(ctx.workspace.resolve()), "sandbox": mode}, decision)
        except Exception as exc:
            return ToolResult(ok=False, output=f"error: {exc}", data={"command": command})

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
        runner_env = dict(env)
        if mode == "strict":
            # systemd-run must reach the logged-in user manager. These variables stay with
            # the host-side scope launcher; bubblewrap clears them before starting the bot.
            runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
            runner_env["XDG_RUNTIME_DIR"] = runtime_dir
            runner_env["DBUS_SESSION_BUS_ADDRESS"] = os.environ.get(
                "DBUS_SESSION_BUS_ADDRESS", f"unix:path={runtime_dir}/bus")
        argv = ["/bin/bash", "-c", command]
        if mode == "strict":
            try:
                argv = sandbox.shell_argv(command, sandbox.policy_for(ctx.bot, ctx.workspace))
            except (OSError, RuntimeError, ValueError) as exc:
                return ToolResult(ok=False, data={"command": command, "sandbox": "unavailable"},
                                  output=f"error: this bot requires the OS sandbox but its resource limits are unavailable: {exc}. Nothing was run.")
        try:
            proc = subprocess.Popen(
                argv,
                cwd=ctx.workspace,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True,  # own process group: Stop and timeouts kill the whole tree
                env=runner_env if mode == "strict" else env,
            )
        except FileNotFoundError:
            return ToolResult(ok=False, output="error: no shell available", data={"command": command})
        ctx.procs.register(proc, "shell")
        captured = bytearray()
        truncated = False
        timed_out = False
        selector = selectors.DefaultSelector()
        try:
            assert proc.stdout is not None and proc.stderr is not None
            selector.register(proc.stdout, selectors.EVENT_READ)
            selector.register(proc.stderr, selectors.EVENT_READ)
            deadline = time.monotonic() + timeout
            while selector.get_map():
                if not timed_out and time.monotonic() >= deadline:
                    timed_out = True
                    ctx.procs.terminate(proc, grace=0.2)
                if timed_out and proc.poll() is not None and ctx.procs.survivors:
                    break  # incomplete cleanup stays visible at the run level; do not wait on an inherited pipe forever
                for key, _ in selector.select(timeout=0.05):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    room = max(0, capture_limit - len(captured))
                    if room:
                        captured.extend(chunk[:room])
                    if len(chunk) > room:
                        truncated = True
            if proc.poll() is None:
                if timed_out:
                    ctx.procs.terminate(proc, grace=0.1)
                try:
                    proc.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    pass
        finally:
            selector.close()
            for stream in (proc.stdout, proc.stderr):
                if stream is not None:
                    stream.close()
            ctx.procs.unregister(proc)

        output = captured.decode("utf-8", "replace")
        if truncated:
            output += f"\n… [output clipped while draining; captured at most {capture_limit:,} bytes]"
        if ctx.procs.killed:
            return ToolResult(ok=False, output="error: stopped — command was killed", data={"command": command})
        if timed_out:
            return ToolResult(ok=False, output=clip(f"error: timed out after {timeout}s\n{output}"),
                              data={"command": command, "timeout": True, "cleanup_incomplete": bool(ctx.procs.survivors)})
        return ToolResult(
            ok=proc.returncode == 0,
            output=clip(f"exit={proc.returncode}\n{output.strip() or '(no output)'}"),
            data={"command": command, "exit_code": proc.returncode, "sandbox": mode},
        )
