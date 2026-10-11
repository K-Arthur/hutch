"""Per-step accounting shared by every runtime (SR-2, PF-11).

A *step* is one model turn plus the tools it triggered. Wall time includes:

* ``model_ms``    waiting on the model (network + inference)
* ``tool_ms``     inside tools (subprocess, file IO, network)
* ``queue_ms``    local-inference admission waits, excluded from Hutch overhead
* ``overhead_ms`` everything else: Hutch's own cost — policy checks, approval bookkeeping,
                  event emission, accounting. The draft targets < 50 ms per step.

Each step lands in the transcript as a ``step`` event, so the numbers are inspectable per run
and the dashboard can sum them without a separate metrics store.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Optional

from ..lifecycle import LeaseLost
from ..action_receipts import freeze
from ..models import Event, EventType, Run
from ..outputblocks import parse_blocks
from ..tools import Tool, ToolContext
from ..tools.base import ToolResult


@dataclass
class StepTimer:
    t0: float = field(default_factory=time.perf_counter)
    model_ms: float = 0.0
    tool_ms: float = 0.0
    queue_ms: float = 0.0

    def model(self, seconds: float) -> None:
        self.model_ms += seconds * 1000.0


DEFAULT_TOOL_LIMIT = 12_000   # chars shown to the model per tool call unless the bot overrides it (PF-2)


MAX_ARTIFACT_BYTES = 4_000_000  # MAX_TOOL_OUTPUT is one million Unicode characters.
MAX_WORKSPACE_FILE_ARTIFACT_BYTES = 4_000_000
MAX_RUN_ARTIFACT_BYTES = 16_000_000


def run_artifact_bytes(artifact_dir: Path) -> int:
    total = 0
    try:
        entries = os.scandir(artifact_dir)
    except FileNotFoundError:
        return 0
    with entries:
        for entry in entries:
            info = entry.stat(follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                raise OSError("artifact directory contains a non-regular entry")
            total += info.st_size
    return total


def snapshot_workspace_file(ctx: ToolContext, path: str, content: str) -> dict[str, Any]:
    """Save the exact text accepted by a successful write_file action as a bounded artifact."""
    if not isinstance(path, str) or not path:
        raise ValueError("the written file path is unavailable")
    if not isinstance(content, str):
        raise ValueError("the written file content is unavailable")
    workspace = ctx.workspace.resolve()
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            relative = Path(os.path.abspath(candidate)).relative_to(workspace)
        except ValueError:
            raise ValueError("the written file is outside this run's workspace") from None
    else:
        relative = candidate
    parts = relative.parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise ValueError("the written file path is not a safe workspace-relative path")
    if len(content.encode("utf-8")) > MAX_WORKSPACE_FILE_ARTIFACT_BYTES:
        raise ValueError("the file exceeds the 4 MB downloadable snapshot limit")
    ref, digest, byte_size = save_artifact(ctx, "workspace_file", content)
    raw_name = PurePosixPath(path.replace("\\", "/")).name
    download_name = re.sub(r"[^A-Za-z0-9._-]+", "-", raw_name).strip("._-")[:120] or "workspace-file.txt"
    return {
        "artifact": ref,
        "sha256": digest,
        "bytes": byte_size,
        "name": download_name,
        "path": "/".join(parts),
    }


def save_artifact(ctx: ToolContext, tool: str, text: str) -> tuple[str, str, int]:
    """Write an immutable tool-output version and return its run-relative path, hash and byte size."""
    run_dir = ctx.config.run_dir(ctx.bot.name, ctx.run.id)
    art = run_dir / "artifacts"
    art.mkdir(parents=True, exist_ok=True, mode=0o700)
    if art.is_symlink():
        raise OSError("artifact directory may not be a symbolic link")
    content = text.encode("utf-8", errors="replace")
    if len(content) > MAX_ARTIFACT_BYTES:
        raise ValueError("artifact exceeds the 4 MB storage limit")
    if run_artifact_bytes(art) + len(content) > MAX_RUN_ARTIFACT_BYTES:
        raise ValueError("run artifacts exceed the 16 MB storage limit")
    digest = hashlib.sha256(content).hexdigest()
    slug = re.sub(r"[^a-z0-9_-]+", "-", tool.lower()).strip("-")[:40] or "tool"
    for version in range(1, 1_000_000):
        path = art / f"{version:03d}-{slug}.txt"
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        except FileExistsError:
            continue
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fchmod(stream.fileno(), 0o400)
                os.fsync(stream.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return str(path.relative_to(run_dir)), digest, len(content)
    raise OSError("too many artifact versions in one run")


def truncate_for_model(ctx: ToolContext, tool: str, output: str) -> tuple[str, Optional[dict[str, Any]]]:
    """PF-2: cap model context while keeping an immutable, verifiable copy of the full tool output."""
    from ..tools.base import MAX_TOOL_OUTPUT
    limit = int(ctx.bot.tool_limits.get(tool, DEFAULT_TOOL_LIMIT))
    if limit <= 0:
        limit = DEFAULT_TOOL_LIMIT
    limit = min(limit, MAX_TOOL_OUTPUT)
    if len(output) <= limit:
        return output, None
    try:
        rel, digest, byte_size = save_artifact(ctx, tool, output)
    except (OSError, ValueError) as exc:
        note = f"\n... [{len(output) - limit:,} of {len(output):,} characters omitted; full output snapshot unavailable: {exc}]"
        return output[:limit] + note, None
    note = f"\n... [{len(output) - limit:,} of {len(output):,} characters omitted; full output saved as artifact {rel}]"
    return output[:limit] + note, {"path": rel, "sha256": digest, "bytes": byte_size}


def _summary(name: str, args: dict[str, Any]) -> str:
    for key in ("command", "path", "url", "selector", "label", "key", "action"):
        if args.get(key):
            return f"{name}: {str(args[key])[:160]}"
    return name


def _run_with_receipt(tool: Tool, name: str, args: dict[str, Any], ctx: ToolContext, run: Run,
                      *, receipt_args: Optional[dict[str, Any]] = None) -> ToolResult:
    """Run a tool; if the call can have a lasting effect, bracket the EFFECT with an intent and a receipt (ADR-0003).

    The tool calls ``ctx.begin_effect()`` after policy and approval, immediately before it acts; that writes the intent and
    refuses (fail closed) if it cannot be recorded or this worker no longer owns the run. After the tool returns the receipt is
    written. If the process dies between the two, the row stays ``started``: recovery reports an unknown outcome and the action
    is never replayed. Local keys do not make a remote effect exactly-once, and the UI says so."""
    effect = "" if ctx.dry_run else tool.effect(args, ctx)
    if not effect:
        return tool.run(args, ctx)
    recorded = args if receipt_args is None else receipt_args
    key = hashlib.sha256(f"{run.id}|{name}|{json.dumps(recorded, sort_keys=True, default=str)}".encode()).hexdigest()[:24]
    began: dict[str, str] = {}
    ctx.gate.last_authorization = None

    def begin() -> Optional[str]:
        try:
            began["id"] = ctx.store.begin_action(run.id, name, key, effect, _summary(name, recorded), fence=run.fence,
                arguments=recorded, authority=ctx.gate.last_authorization,
                scope={"workspace": str(ctx.workspace.resolve()), "model": run.model_used or ctx.bot.model,
                       "browser_profile": ctx.bot.id if effect == "web" else None})
        except LeaseLost as exc:
            ctx.closed = True          # we no longer own this run: nothing more may start from this worker
            return f"{exc}; the action was not started"
        except Exception as exc:
            return f"the action could not be recorded ({exc}), so it was not run"
        return None

    ctx.receipt = begin
    result = None
    try:
        result = tool.run(args, ctx)
        return result
    finally:
        ctx.receipt = None
        if "id" in began and result is None:
            # An exception after admission is not a returned failure receipt:
            # the effect may already have happened. Preserve the missing row
            # for atomic uncertainty sealing and prohibit further tools.
            ctx.closed = True
        elif "id" in began:              # actions that never began have nothing to receipt
            try:
                ctx.store.finish_action(began["id"], "done" if result.ok else "failed",
                                        hashlib.sha256(result.output.encode(errors="replace")).hexdigest()[:16],
                                        expected_fence=run.fence)
            except Exception as exc:
                # The effect may have completed, but we cannot report a saved
                # receipt or let another tool begin after losing audit storage.
                ctx.closed = True
                from .base import RunAborted
                raise RunAborted("action_receipt_missing", "the action may have happened but its receipt could not be saved; "
                                 "verify the destination before repeating it") from exc


def _presented_blocks(data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate a tool's ``data['blocks']`` list. Never raises, never silent:
    every rejected block comes back as a labeled error entry (outputblocks.py
    owns the budgets - at most 24 blocks / 256k compact-JSON chars per result)."""
    if "blocks" not in data:
        return [], []
    try:
        return parse_blocks(data.get("blocks"))
    except Exception as exc:  # parse_blocks never raises by contract; belt and braces
        return [], [{"error": f"output blocks could not be validated ({exc!r})"}]


def _blocks_summary(blocks: list[dict[str, Any]], errors: list[dict[str, Any]]) -> str:
    """The ONE line of block awareness the model ever sees. Block JSON itself
    never enters the model-facing text."""
    if blocks:
        line = "[presented: " + ", ".join(f"{b['kind']} {b['id']}" for b in blocks) + "]"
    else:
        line = f"[presented: none — {len(errors)} output block(s) failed validation]"
    if errors:
        line += f" ({len(errors)} output block(s) could not be validated; see block_errors)"
    return line


def call_tool(run: Run, ctx: ToolContext, tools: dict[str, Tool], name: str, args: dict[str, Any],
              timer: Optional[StepTimer] = None, output_chars: int = 2_000) -> ToolResult:
    """Emit the call, run the tool (timed), emit the result. Used by production and test runtimes."""
    if ctx.closed:                       # fenced: the run already ended (timeout, stop, recovery); nothing new may start
        return ToolResult(ok=False, output="error: this run has ended; the action was not started")
    try:
        if not isinstance(args, dict):
            raise ValueError("tool arguments must be a JSON object")
        # The caller cannot revise arguments during the human wait. Tools and
        # the eventual receipt use the same private snapshot.
        args = freeze(args)
        if len(json.dumps(args, ensure_ascii=False).encode()) > 1024 * 1024:
            raise ValueError("tool arguments exceed 1 MiB; reduce the request")
    except (TypeError, ValueError, RecursionError) as exc:
        return ToolResult(ok=False, output=f"error: invalid tool arguments ({exc}); nothing was run")
    tool = tools.get(name)
    recorded_args = args
    if tool is not None:
        try:
            recorded_args = freeze(tool.recorded_arguments(args, ctx))
        except Exception:
            # A tool's persistence boundary must fail closed: raw arguments are
            # never emitted if the tool cannot produce its safe representation.
            result = ToolResult(ok=False, output="error: tool arguments could not be made safe to record; nothing was run")
            ctx.emit(Event(run_id=run.id, type=EventType.tool_call,
                           data={"tool": name, "args": {"redacted": True}}))
            ctx.emit(Event(run_id=run.id, type=EventType.tool_result,
                           data={"tool": name, "ok": False, "output": result.output}))
            return result
    ctx.emit(Event(run_id=run.id, type=EventType.tool_call, data={"tool": name, "args": recorded_args}))
    t1 = time.perf_counter()
    if tool is None:
        result = ToolResult(ok=False, output=f"error: unknown tool '{name}' — available: {sorted(tools)}")
    else:
        result = _run_with_receipt(tool, name, args, ctx, run, receipt_args=recorded_args)
    if timer is not None:
        timer.tool_ms += (time.perf_counter() - t1) * 1000.0
    if name == "write_file" and result.ok and not result.data.get("simulated"):
        try:
            result.data["workspace_file"] = snapshot_workspace_file(
                ctx, result.data.get("path", args.get("path", "")), args.get("content", ""))
        except (OSError, UnicodeError, ValueError) as exc:
            result.data["workspace_file"] = {"error": str(exc)[:240]}
    full_chars = len(result.output)
    result.output, artifact = truncate_for_model(ctx, name, result.output)
    # Typed output blocks: validated once here, then carried as plain data on the
    # tool_result event. Message prose and tool output text are NEVER parsed for
    # blocks - only a tool that explicitly supplies data['blocks'] presents any.
    has_blocks = "blocks" in result.data
    blocks, block_errors = _presented_blocks(result.data) if has_blocks else ([], [])
    if blocks or block_errors:
        result.output = f"{result.output}\n{_blocks_summary(blocks, block_errors)}"
    data: dict[str, Any] = {"tool": name, "ok": result.ok, "output": result.output[:output_chars]}
    if artifact:
        data.update(artifact=artifact["path"], artifact_sha256=artifact["sha256"],
                    artifact_bytes=artifact["bytes"], chars=full_chars)
    if has_blocks:
        data["blocks"] = blocks
        if block_errors:
            data["block_errors"] = block_errors
    workspace_file = result.data.get("workspace_file")
    if isinstance(workspace_file, dict):
        data["workspace_file"] = workspace_file
    document = result.data.get("document")
    if isinstance(document, dict):
        data["document"] = document
    if result.data.get("simulated"):
        data["simulated"] = True                                 # Rehearse mode: nothing actually ran
    if result.data.get("investigation_id"):
        data["investigation_id"] = str(result.data["investigation_id"])[:64]
    if result.data.get("media_id"):
        data["media_id"] = str(result.data["media_id"])[:64]
    ctx.emit(Event(run_id=run.id, type=EventType.tool_result, data=data))
    return result


def finish_step(run: Run, ctx: ToolContext, timer: StepTimer, *, model: str = "",
                prompt_tokens: int = 0, completion_tokens: int = 0, cached_tokens: int = 0,
                cost_usd: float = 0.0, account_id: str = "", reservation_id: Optional[str] = None,
                cost_source: str = "", reported_cost_usd: Optional[float] = None,
                **extra: Any) -> None:
    """Fold a step into the run's totals and append its ``step`` event."""
    total_ms = (time.perf_counter() - timer.t0) * 1000.0
    overhead_ms = max(0.0, total_ms - timer.model_ms - timer.tool_ms - timer.queue_ms)
    run.prompt_tokens += prompt_tokens
    run.completion_tokens += completion_tokens
    run.cached_tokens += cached_tokens
    run.cost_usd = round(run.cost_usd + cost_usd, 8)
    run.model_ms += timer.model_ms
    run.tool_ms += timer.tool_ms
    run.overhead_ms += overhead_ms
    if model:
        run.model_used = model
    ctx.store.update_run(run)  # persist running totals so the meters (UI-4) are live, not end-of-run
    if reservation_id and not (prompt_tokens or completion_tokens):
        ctx.store.mark_usage_uncertain(reservation_id, "provider response did not report token usage", expected_fence=run.fence)
    elif prompt_tokens or completion_tokens:
        provider, _, name = (model or run.model_used or "unknown/unknown").partition("/")
        ctx.store.add_usage(run.id, run.bot_id, provider, name or provider, prompt_tokens, completion_tokens,
                            cached_tokens, cost_usd, account_id=account_id, reservation_id=reservation_id,
                            expected_fence=run.fence, cost_source=cost_source,
                            reported_cost_usd=reported_cost_usd)
    ctx.emit(Event(run_id=run.id, type=EventType.step, data={
        "n": run.steps, "model": model or run.model_used,
        "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
        "cached_tokens": cached_tokens, "cost_usd": round(cost_usd, 8), "cost_source": cost_source,
        "reported_cost_usd": reported_cost_usd,
        "model_ms": round(timer.model_ms, 2), "tool_ms": round(timer.tool_ms, 2), "queue_ms": round(timer.queue_ms, 2),
        "overhead_ms": round(overhead_ms, 3), **extra,
    }))
