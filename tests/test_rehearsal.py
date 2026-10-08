"""Rehearse mode (a dry run) must change NOTHING: reads run, everything else is only described, with the policy's verdict.

It used to be a sentence in the prompt that no tool honoured (found while testing working folders: a rehearsal wrote a real
file). These tests drive real runs through a scripted model and check the disk, the memory and the approvals."""

from __future__ import annotations

from pathlib import Path

import pytest

from hutch.engine import Engine
from hutch.models import ApprovalMode, Bot, EventType, RunStatus
from hutch.runtime.ladder import reset_provider_cache
from hutch.safety import PolicyEngine, is_read_only
from tests.fakes import FakeOllama, agent_script


@pytest.fixture()
def eng(tmp_path, monkeypatch, config, store):
    s = FakeOllama({"tiny:1b": {"params": "1B", "size": 500_000_000}})
    monkeypatch.setenv("OLLAMA_HOST", s.url)
    reset_provider_cache()
    folder = tmp_path / "work"
    folder.mkdir()
    (folder / "existing.txt").write_text("keep me")
    yield Engine(config, store), store, s, folder
    s.close()


def rehearse(eng, calls, mode=ApprovalMode.ask, tools=("files", "shell", "memory"), **kw):
    engine, store, fake, folder = eng
    fake.script = agent_script([{"content": "trying", "tool_calls": calls}, {"content": "finished"}])
    bot = store.create_bot(Bot(name="rh", model="ollama/tiny:1b", tools=list(tools), approval_mode=mode, selfcheck=False,
                               workdir=str(folder), **kw))
    run = engine.run_blocking(bot, "go", rehearsal=True)
    results = [e.data for e in store.list_events(run.id) if e.type is EventType.tool_result]
    return run, results, store, folder, bot


def snapshot(folder: Path):
    return sorted((str(p.relative_to(folder)), p.read_text() if p.is_file() else None) for p in folder.rglob("*"))


# ------------------------------------------------------------------------------- files

def test_a_rehearsed_write_does_not_touch_the_disk_and_says_what_policy_would_do(eng):
    before = snapshot(eng[3])
    run, results, store, folder, _ = rehearse(eng, [{"name": "write_file", "arguments": {"path": "new.md", "content": "x" * 50}},
                                                    {"name": "write_file", "arguments": {"path": "existing.txt", "content": "overwritten"}}])
    assert run.status is RunStatus.succeeded
    assert snapshot(folder) == before, "a rehearsal must not create or change any file"
    assert all(r["simulated"] and r["ok"] for r in results)
    assert "[rehearsal] would write new.md (50 chars)" in results[0]["output"] and "would pause for approval" in results[0]["output"]
    assert not store.pending_approvals(), "a simulated action asks nobody"


def test_a_rehearsed_write_outside_the_jail_reports_that_it_would_be_blocked(eng):
    run, results, *_ = rehearse(eng, [{"name": "write_file", "arguments": {"path": "../escape.txt", "content": "x"}}])
    assert results[0]["ok"] is False and "would be BLOCKED" in results[0]["output"] and results[0]["simulated"]
    assert not (eng[3].parent / "escape.txt").exists()


# ------------------------------------------------------------------------------- shell

def test_mutating_commands_are_described_not_run(eng):
    before = snapshot(eng[3])
    run, results, store, folder, _ = rehearse(eng, [
        {"name": "shell", "arguments": {"command": "rm existing.txt"}},
        {"name": "shell", "arguments": {"command": "touch made.txt && echo hi > out.txt"}},
        {"name": "shell", "arguments": {"command": "mkdir sub"}},
        {"name": "shell", "arguments": {"command": "mv existing.txt renamed.txt"}}])
    assert snapshot(folder) == before and not store.pending_approvals()
    assert all(r["simulated"] for r in results)
    assert "would pause for approval" in results[0]["output"], "rm asks, so the rehearsal says it would ask"


def test_read_only_commands_really_run(eng):
    run, results, store, folder, _ = rehearse(eng, [{"name": "shell", "arguments": {"command": "ls && cat existing.txt | wc -c"}}])
    assert not results[0].get("simulated") and "existing.txt" in results[0]["output"] and "7" in results[0]["output"]


def test_a_hard_denied_command_is_reported_as_blocked(eng):
    run, results, *_ = rehearse(eng, [{"name": "shell", "arguments": {"command": "sudo rm -rf /"}}])
    assert results[0]["simulated"] and results[0]["ok"] is False and "would be BLOCKED" in results[0]["output"]


def test_nothing_slips_through_wrappers_or_substitutions(eng):
    before = snapshot(eng[3])
    rehearse(eng, [{"name": "shell", "arguments": {"command": "bash -c 'rm existing.txt'"}},
                   {"name": "shell", "arguments": {"command": "echo $(rm existing.txt)"}},
                   {"name": "shell", "arguments": {"command": "ls & rm existing.txt"}},
                   {"name": "shell", "arguments": {"command": "env X=1 touch pwned"}},
                   {"name": "shell", "arguments": {"command": "find . -delete"}},
                   {"name": "shell", "arguments": {"command": "cat existing.txt > copy.txt"}}])
    assert snapshot(eng[3]) == before


# ------------------------------------------------------------------------------ memory

def test_a_rehearsed_remember_stores_nothing(eng):
    run, results, store, folder, bot = rehearse(eng, [{"name": "remember", "arguments": {"key": "k", "value": "v"}}])
    assert results[0]["simulated"] and "would remember 'k'" in results[0]["output"]
    assert store.recall_all(bot.id) == []


# --------------------------------------------------------------------- transcript and UI

def test_simulated_results_are_marked_in_the_transcript_and_on_the_run_page(eng, tmp_path, monkeypatch):
    run, results, store, folder, bot = rehearse(eng, [{"name": "write_file", "arguments": {"path": "a", "content": "b"}}])
    from jinja2 import Environment, FileSystemLoader
    from hutch.server.pages import TEMPLATE_DIR
    assert any(e.data.get("simulated") for e in store.list_events(run.id) if e.type is EventType.tool_result)
    src = (TEMPLATE_DIR / "_events.html").read_text()
    assert "d.simulated" in src and "simulated" in src


def test_a_normal_run_is_unaffected(eng):
    engine, store, fake, folder = eng
    fake.script = agent_script([{"content": "w", "tool_calls": [{"name": "write_file", "arguments": {"path": "real.md", "content": "x"}}]},
                                {"content": "done"}])
    bot = store.create_bot(Bot(name="real", model="ollama/tiny:1b", tools=["files"], approval_mode=ApprovalMode.auto, selfcheck=False,
                               workdir=str(folder)))
    run = engine.run_blocking(bot, "go")
    assert (folder / "real.md").read_text() == "x"
    assert not any(e.data.get("simulated") for e in store.list_events(run.id) if e.type is EventType.tool_result)


# ------------------------------------------------------------------- the read-only classifier

READ_ONLY = ["ls", "ls -la | head", "cat a.txt", "git status", "git log --oneline | wc -l", "grep -r foo . | sort | uniq",
             "find . -name '*.py'", "echo hi", "pwd && date", "(cd sub && ls)", "echo $(date)", "wc -l a b", "git diff HEAD~1",
             "ls > /dev/null", "cat a 2>/dev/null"]
NOT_READ_ONLY = ["rm a", "touch a", "mkdir d", "mv a b", "cp a b", "echo hi > a", "cat a >> b", "ls & touch a", "find . -delete",
                 "find . -exec rm {} \;", "sort -o out a", "sort a --output=b", "git commit -m x", "git push", "git checkout x", "git branch -D x",
                 "sed -i s/a/b/ f", "awk 'BEGIN{system(\"rm a\")}'", "python3 -c 'x'", "bash -c ls", "env ls", "xargs ls", "tee a",
                 "curl http://x", "echo $(touch a)", "ls | tee a", "cat <<EOF\nx\nEOF", "$(echo ls)", "echo 'unterminated", "", "   "]


@pytest.mark.parametrize("cmd", READ_ONLY)
def test_known_read_only_commands(cmd):
    assert is_read_only(cmd) and PolicyEngine().check_shell(cmd).verdict.value == "allow", cmd


@pytest.mark.parametrize("cmd", NOT_READ_ONLY)
def test_anything_else_is_not_treated_as_read_only(cmd):
    assert not is_read_only(cmd), cmd
