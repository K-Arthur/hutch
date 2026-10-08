"""Approve the stored payload, and refuse a destination revised during the wait."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from hutch.approvals import resolve_approval_ex
from hutch.tools.files import FilesWriteTool
from tests.test_tools import make_ctx


def decide_at_wait(ctx, monkeypatch, review):
    wait = ctx.gate._wait

    def human(req, action):
        stored = ctx.store.get_approval(req.id)
        review(stored)
        assert resolve_approval_ex(ctx.store, req.id, True, expected_hash=stored.action_hash).won
        return wait(req, action)

    monkeypatch.setattr(ctx.gate, "_wait", human)


def test_full_payload_persisted_and_caller_change_cannot_change_approved_write(store, config, tmp_path, monkeypatch):
    ctx = make_ctx(store, config, tmp_path)
    args = {"path": "draft.md", "content": "reviewed text"}

    def review(req):
        assert req.detail["content"] == "reviewed text"
        assert req.detail["workspace"] == str(ctx.workspace.resolve())
        assert req.detail["revision"] == {"exists": False}
        args.update(path="other.md", content="unreviewed text")

    decide_at_wait(ctx, monkeypatch, review)
    assert FilesWriteTool().run(args, ctx).ok
    assert (ctx.workspace / "draft.md").read_text() == "reviewed text"
    assert not (ctx.workspace / "other.md").exists()


def test_same_length_payloads_have_different_persisted_approval_hashes(store, config, tmp_path, monkeypatch):
    ctx = make_ctx(store, config, tmp_path)
    hashes = []
    decide_at_wait(ctx, monkeypatch, lambda req: hashes.append(req.action_hash))
    for content in ("first", "other"):
        assert FilesWriteTool().run({"path": "draft.md", "content": content}, ctx).ok
        (ctx.workspace / "draft.md").unlink()
    assert len(set(hashes)) == 2


@pytest.mark.parametrize("initial", [None, "original"])
def test_revised_destination_requires_new_review(store, config, tmp_path, monkeypatch, initial):
    ctx = make_ctx(store, config, tmp_path)
    path = ctx.workspace / "draft.md"
    if initial is not None:
        path.write_text(initial)

    def review(req):
        if initial is not None:
            assert req.detail["revision"]["sha256"] == hashlib.sha256(initial.encode()).hexdigest()
        path.write_text("human edit while waiting")

    decide_at_wait(ctx, monkeypatch, review)
    effects = []
    ctx.receipt = lambda: effects.append("started")
    result = FilesWriteTool().run({"path": "draft.md", "content": "bot replacement"}, ctx)
    assert not result.ok and "changed after review" in result.output
    assert path.read_text() == "human edit while waiting"
    assert effects == []
    assert not list(ctx.workspace.glob(".hutch-write-*"))


@pytest.mark.parametrize("at_parent", [False, True])
def test_symlink_swap_during_review_does_not_write_outside_workspace(store, config, tmp_path, monkeypatch, at_parent):
    ctx = make_ctx(store, config, tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / "draft.md"
    victim.write_text("private")
    relative = "nested/draft.md" if at_parent else "draft.md"

    def review(req):
        if at_parent:
            (ctx.workspace / "nested").symlink_to(outside, target_is_directory=True)
        else:
            (ctx.workspace / "draft.md").symlink_to(victim)

    decide_at_wait(ctx, monkeypatch, review)
    result = FilesWriteTool().run({"path": relative, "content": "replacement"}, ctx)
    assert not result.ok
    assert victim.read_text() == "private"


def test_atomic_replacement_does_not_modify_external_hardlink(store, config, tmp_path):
    ctx = make_ctx(store, config, tmp_path)
    outside = tmp_path / "external.txt"
    outside.write_text("private")
    Path(ctx.workspace / "draft.md").hardlink_to(outside)
    store.allow_sticky(ctx.bot.id, "files:write")
    assert FilesWriteTool().run({"path": "draft.md", "content": "replacement"}, ctx).ok
    assert outside.read_text() == "private"
    assert (ctx.workspace / "draft.md").read_text() == "replacement"


def test_shell_review_uses_effective_timeout_and_containment(store, config, tmp_path, monkeypatch):
    from hutch.tools.shell import ShellTool
    ctx = make_ctx(store, config, tmp_path)

    def review(req):
        assert req.detail == {"command": "mkdir output", "timeout": 300,
                              "workspace": str(ctx.workspace.resolve()), "sandbox": "off"}

    decide_at_wait(ctx, monkeypatch, review)
    assert ShellTool().run({"command": "mkdir output", "timeout": 999}, ctx).ok
    assert (ctx.workspace / "output").is_dir()
