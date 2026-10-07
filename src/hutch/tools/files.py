"""File tools — read/list/write strictly inside the run workspace (path jail)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .base import Tool, ToolContext, ToolResult, _schema, clip


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
            if not p.is_file():
                return ToolResult(ok=False, output=f"error: not a file: {path}")
            return ToolResult(ok=True, output=clip(p.read_text(errors="replace")), data={"path": path})
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
        for root, dirs, files in os.walk(base):
            depth = len(Path(root).relative_to(ws).parts)
            if depth >= 4:
                dirs[:] = []
                continue
            for name in sorted(files):
                lines.append(str((Path(root) / name).relative_to(ws)))
        return ToolResult(ok=True, output=clip("\n".join(lines) or "(empty)"), data={"count": len(lines)})


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

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path, content = args.get("path", ""), args.get("content", "")
        decision = ctx.policy.check_path(path, ctx.workspace, write=True)
        try:
            ctx.gate.decide("files", f"write {path} ({len(content)} chars)", {"path": path}, decision)
        except Exception as exc:
            return ToolResult(ok=False, output=f"error: {exc}")
        try:
            ws, p = _resolve(path, ctx)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            return ToolResult(ok=True, output=f"wrote {path} ({len(content)} chars)", data={"path": path})
        except OSError as exc:
            return ToolResult(ok=False, output=f"error: {exc}")
