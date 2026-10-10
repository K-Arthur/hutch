"""Tool producers must bound capture before allocation (not clip after a full load)."""

from __future__ import annotations

from pathlib import Path

from hutch.models import ApprovalMode, Bot, Run
from hutch.tools.base import MAX_TOOL_OUTPUT, ToolContext, read_text_bounded
from hutch.tools.files import FilesListTool, FilesReadTool


def _ctx(tmp_path: Path, store, config) -> ToolContext:
    from hutch.approvals import ApprovalGate
    from hutch.safety import PolicyEngine
    bot = store.create_bot(Bot(name="bound", model="mock/demo", tools=["files"],
                               approval_mode=ApprovalMode.auto))
    run = store.create_run(Run(bot_id=bot.id, prompt="x"))
    ws = tmp_path / "ws"
    ws.mkdir()
    policy = PolicyEngine()
    gate = ApprovalGate(store, bot, run, policy, emit=lambda _e: None)
    return ToolContext(bot=bot, run=run, store=store, policy=policy, gate=gate,
                       config=config, workspace=ws)


def test_read_text_bounded_does_not_retain_beyond_limit(tmp_path: Path):
    huge = tmp_path / "huge.txt"
    # Write more than the capture limit without building a giant Python str first.
    with huge.open("wb") as fh:
        chunk = b"a" * 65_536
        for _ in range((MAX_TOOL_OUTPUT // len(chunk)) + 4):
            fh.write(chunk)
    text, meta = read_text_bounded(huge, limit=10_000)
    assert meta.get("truncated") is True
    assert meta["retained_chars"] == 10_000
    assert len(text) < 10_000 + 200  # retained + marker
    assert "clipped while reading" in text


def test_read_file_tool_bounds_capture(tmp_path, store, config):
    ctx = _ctx(tmp_path, store, config)
    target = ctx.workspace / "blob.txt"
    with target.open("wb") as fh:
        fh.write(b"x" * (MAX_TOOL_OUTPUT + 50_000))
    result = FilesReadTool().run({"path": "blob.txt"}, ctx)
    assert result.ok
    assert result.data.get("truncated") is True
    assert result.data["retained_chars"] == MAX_TOOL_OUTPUT


def test_list_files_stops_when_budget_exhausted(tmp_path, store, config, monkeypatch):
    import hutch.tools.files as files_mod
    monkeypatch.setattr(files_mod, "MAX_TOOL_OUTPUT", 400)
    ctx = _ctx(tmp_path, store, config)
    for i in range(50):
        name = ("f" + ("n" * 40) + f"{i:04d}.txt")
        (ctx.workspace / name).write_text("x")
    result = FilesListTool().run({}, ctx)
    assert result.ok
    assert result.data.get("truncated") is True
    assert result.data["count"] < 50
