"""File tools — read/list/write strictly inside the run workspace (path jail)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .base import (
    MAX_TOOL_OUTPUT,
    Tool,
    ToolContext,
    ToolResult,
    _schema,
    clip,
    read_text_bounded,
    rehearsed,
    truncation_meta,
)
from .filewrite import destination, replace_reviewed, revision


def _resolve(path: str, ctx: ToolContext):
    ws = ctx.workspace.resolve()
    p = (ws / path if not Path(path).is_absolute() else Path(path)).resolve()
    return ws, p


class FilesReadTool(Tool):
    name = "read_file"
    description = "Read a text file from the bot workspace."
    parameters = _schema(["path"], {"path": {"type": "string", "description": "Path relative to the workspace"}})

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = args.get("path", "")
        decision = ctx.policy.check_path(path, ctx.workspace, write=False)
        if decision.verdict.value == "deny":
            return ToolResult(ok=False, output=f"error: {decision.reason}")
        try:
            ws, p = _resolve(path, ctx)
            if p.is_symlink() or not p.is_file():
                return ToolResult(ok=False, output=f"error: not a regular file: {path}")
            output, meta = read_text_bounded(p, MAX_TOOL_OUTPUT)
            return ToolResult(ok=True, output=output, data={"path": path, **meta})
        except OSError as exc:
            return ToolResult(ok=False, output=f"error: {exc}")


class FilesListTool(Tool):
    name = "list_files"
    description = "List files and directories under a workspace path (recursive, max depth 4)."
    parameters = _schema(
        [],
        {"path": {"type": "string", "description": "Sub-directory to list (default: workspace root)"}},
    )

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        rel = args.get("path") or "."
        decision = ctx.policy.check_path(rel, ctx.workspace, write=False)
        if decision.verdict.value == "deny":
            return ToolResult(ok=False, output=f"error: {decision.reason}")
        ws, base = _resolve(rel, ctx)
        if not base.exists():
            return ToolResult(ok=False, output=f"error: no such directory: {rel}")
        lines: list[str] = []
        retained = 0
        truncated = False
        listed = 0
        for root, dirs, files in os.walk(base):
            depth = len(Path(root).relative_to(ws).parts)
            if depth >= 4:
                dirs[:] = []
                continue
            for name in sorted(files):
                listed += 1
                entry = str((Path(root) / name).relative_to(ws))
                # +1 for the newline that will join lines
                cost = len(entry) + (1 if lines else 0)
                if retained + cost > MAX_TOOL_OUTPUT:
                    truncated = True
                    dirs[:] = []
                    break
                lines.append(entry)
                retained += cost
            if truncated:
                break
        output = "\n".join(lines) or "(empty)"
        data: dict[str, Any] = {"count": len(lines), "listed_entries": listed}
        if truncated:
            output = clip(output + f"\n… [listing clipped; retained {len(lines):,} paths, scanned {listed:,}]")
            data.update(truncation_meta(stream="listing", retained=len(output), limit=MAX_TOOL_OUTPUT,
                                        reason="capture_limit", observed=listed))
        return ToolResult(ok=True, output=output, data=data)


class FilesWriteTool(Tool):
    name = "write_file"
    description = "Create or overwrite a text file in the bot workspace. Requires approval unless allowed for the bot."
    parameters = _schema(
        ["path", "content"],
        {
            "path": {"type": "string", "description": "Path relative to the workspace"},
            "content": {"type": "string", "description": "Full file contents to write"},
        },
    )

    def effect(self, args: dict[str, Any], ctx: ToolContext) -> str:
        return "fs"

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path, content = args.get("path", ""), args.get("content", "")
        if not isinstance(path, str) or not path or not isinstance(content, str):
            return ToolResult(ok=False, output="error: path and content must be strings, with a nonempty path")
        decision = ctx.policy.check_path(path, ctx.workspace, write=True)
        if ctx.dry_run:
            return rehearsed(f"write {path} ({len(content)} chars)", decision)
        try:
            if decision.verdict.value == "deny":
                ctx.gate.decide("files", f"write {path}", {"path": path, "content": content}, decision)
            ws, parts = destination(path, ctx.workspace)
            expected = revision(ws, parts)
            detail = {"path": path, "content": content, "workspace": str(ws), "revision": expected}
            ctx.gate.decide("files", f"write {path} ({len(content)} chars)", detail, decision)
            replace_reviewed(ws, parts, content, expected, ctx.begin_effect)
        except Exception as exc:
            return ToolResult(ok=False, output=f"error: {exc}")
        return ToolResult(ok=True, output=f"wrote {path} ({len(content)} chars)", data={"path": path})
