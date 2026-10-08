"""A bot's working folder: validated hard, used for real, never created for you."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from hutch.cli import app as cli_app
from hutch.engine import Engine
from hutch.models import ApprovalMode, Bot, EventType, RunStatus
from hutch.runtime.ladder import reset_provider_cache
from hutch.server.app import create_app
from hutch.workdir import check_workdir_at_run, validate_workdir
from tests.fakes import FakeOllama, agent_script

runner = CliRunner()


@pytest.fixture()
def state(tmp_path):
    s = tmp_path / "state"
    s.mkdir()
    return s


def ok(tmp_path, state, name="Downloads"):
    d = tmp_path / name
    d.mkdir(exist_ok=True)
    return validate_workdir(str(d), state)


# ----------------------------------------------------------------------------- validation

def test_a_real_folder_is_accepted_and_resolved(tmp_path, state):
    d = tmp_path / "data"
    d.mkdir()
    assert ok(tmp_path, state, "data") == d.resolve()
    assert validate_workdir(str(d) + "/", state) == d.resolve()


def test_tilde_is_expanded(tmp_path, state, monkeypatch):
    home = tmp_path / "home"
    (home / "Downloads").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    assert validate_workdir("~/Downloads", state) == (home / "Downloads").resolve()


@pytest.mark.parametrize("raw,needle", [
    ("", "needs a path"), ("   ", "needs a path"), ("relative/dir", "not an absolute path"),
    ("/definitely/not/here/xyz", "does not exist"), ("/", "whole disk"), ("/etc", "system location"),
    ("/usr/share", "system location"), ("/proc", "system location"), ("/dev", "system location"),
])
def test_bad_folders_are_refused_with_the_reason(raw, needle, state):
    with pytest.raises(ValueError, match=needle):
        validate_workdir(raw, state)


def test_a_file_is_not_a_folder(tmp_path, state):
    f = tmp_path / "f.txt"
    f.write_text("x")
    with pytest.raises(ValueError, match="not a folder"):
        validate_workdir(str(f), state)


def test_the_whole_home_and_its_parents_are_too_broad(tmp_path, state, monkeypatch):
    home = tmp_path / "home" / "me"
    home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    with pytest.raises(ValueError, match="whole home folder"):
        validate_workdir(str(home), state)
    with pytest.raises(ValueError, match="contains your home"):
        validate_workdir(str(home.parent), state)


def test_hutchs_own_state_cannot_be_a_working_folder(tmp_path, state):
    inner = state / "bots"
    inner.mkdir()
    for p in (state, inner, state.parent):
        with pytest.raises(ValueError, match="state folder"):
            validate_workdir(str(p), state)


def test_a_credentials_location_is_refused(tmp_path, state):
    ssh = tmp_path / ".ssh"
    ssh.mkdir()
    with pytest.raises(ValueError, match="credentials"):
        validate_workdir(str(ssh), state)


def test_a_symlink_into_a_system_folder_is_resolved_and_refused(tmp_path, state):
    link = tmp_path / "innocent"
    link.symlink_to("/etc")
    with pytest.raises(ValueError, match="system location"):
        validate_workdir(str(link), state)


def test_an_unreadable_folder_is_refused(tmp_path, state):
    if os.geteuid() == 0:
        pytest.skip("root can read anything")
    d = tmp_path / "locked"
    d.mkdir()
    d.chmod(0)
    try:
        with pytest.raises(ValueError, match="not readable"):
            validate_workdir(str(d), state)
    finally:
        d.chmod(0o700)


def test_run_time_check_reports_a_folder_that_vanished_or_became_forbidden(tmp_path, state):
    d = tmp_path / "gone"
    d.mkdir()
    assert check_workdir_at_run(str(d), state) is None and check_workdir_at_run(None, state) is None
    d.rmdir()
    assert "does not exist" in check_workdir_at_run(str(d), state)


# ------------------------------------------------------------------------ through a real run

@pytest.fixture()
def eng(tmp_path, monkeypatch, config, store):
    s = FakeOllama({"tiny:1b": {"params": "1B", "size": 500_000_000}})
    monkeypatch.setenv("OLLAMA_HOST", s.url)
    reset_provider_cache()
    yield Engine(config, store), store, s, config
    s.close()


def drive(eng, workdir, calls, **kw):
    engine, store, fake, _ = eng
    fake.script = agent_script([{"content": "working", "tool_calls": calls}, {"content": "finished"}])
    bot = store.create_bot(Bot(name="folk", model="ollama/tiny:1b", tools=["files", "shell"], approval_mode=ApprovalMode.auto,
                               selfcheck=False, workdir=str(workdir) if workdir else None, **kw))
    return engine.run_blocking(bot, "go"), bot, store


def test_a_run_works_in_the_real_folder_and_the_files_persist(eng, tmp_path):
    folder = tmp_path / "Downloads"
    folder.mkdir()
    (folder / "existing.txt").write_text("already here")
    run, bot, store = drive(eng, folder, [{"name": "write_file", "arguments": {"path": "report.md", "content": "hello"}},
                                          {"name": "shell", "arguments": {"command": "ls > listing.txt"}}])
    assert run.status is RunStatus.succeeded, run.error
    assert (folder / "report.md").read_text() == "hello", "the file landed in the user's folder, not a scratch dir"
    assert "existing.txt" in (folder / "listing.txt").read_text() and "report.md" in (folder / "listing.txt").read_text()
    assert Path(run.workspace) == folder.resolve()


def test_a_second_run_sees_what_the_first_wrote(eng, tmp_path):
    folder = tmp_path / "persist"
    folder.mkdir()
    drive(eng, folder, [{"name": "write_file", "arguments": {"path": "note.md", "content": "from run one"}}])
    engine, store, fake, _ = eng
    fake.script = agent_script([{"content": "reading", "tool_calls": [{"name": "read_file", "arguments": {"path": "note.md"}}]},
                                {"content": "finished"}])
    run = engine.run_blocking(store.get_bot("folk"), "again")
    outs = [e.data["output"] for e in store.list_events(run.id) if e.type is EventType.tool_result]
    assert any("from run one" in o for o in outs)


def test_the_jail_is_the_folder_and_not_the_disk(eng, tmp_path):
    folder = tmp_path / "jail"
    folder.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret-ish")
    run, bot, store = drive(eng, folder, [{"name": "read_file", "arguments": {"path": str(outside)}},
                                          {"name": "write_file", "arguments": {"path": "../escape.txt", "content": "x"}}])
    results = [e.data for e in store.list_events(run.id) if e.type is EventType.tool_result]
    assert all(r["ok"] is False and "jail" in r["output"] for r in results), results
    assert not (tmp_path / "escape.txt").exists()


def test_a_missing_folder_fails_the_run_clearly_and_is_not_created(eng, tmp_path):
    folder = tmp_path / "vanished"
    run, bot, store = drive(eng, folder, [{"name": "write_file", "arguments": {"path": "x", "content": "x"}}]) if False else (None, None, None)
    engine, store, fake, _ = eng
    bot = store.create_bot(Bot(name="gone", model="ollama/tiny:1b", tools=["files"], selfcheck=False, workdir=str(folder)))
    run = engine.run_blocking(bot, "go")
    assert run.status is RunStatus.failed and "does not exist" in run.error and str(folder) in run.error
    assert not folder.exists(), "Hutch must never create the user's folder"


def test_a_folder_that_became_forbidden_fails_the_run(eng, tmp_path):
    engine, store, fake, config = eng
    bot = store.create_bot(Bot(name="sneaky", model="ollama/tiny:1b", tools=["files"], selfcheck=False, workdir=str(config.state_dir)))
    run = engine.run_blocking(bot, "go")
    assert run.status is RunStatus.failed and "state folder" in run.error


def test_a_bot_without_a_folder_still_gets_a_fresh_workspace(eng):
    run, bot, store = drive(eng, None, [{"name": "write_file", "arguments": {"path": "a.txt", "content": "x"}}])
    assert run.status is RunStatus.succeeded and Path(run.workspace).name == "workspace" and bot.id[:3] == "bot"
    assert (Path(run.workspace) / "a.txt").exists()


def test_rehearsal_does_not_change_the_users_folder(eng, tmp_path):
    folder = tmp_path / "rehearse"
    folder.mkdir()
    engine, store, fake, _ = eng
    fake.script = agent_script([{"content": "w", "tool_calls": [{"name": "write_file", "arguments": {"path": "new.md", "content": "x"}}]},
                                {"content": "done"}])
    bot = store.create_bot(Bot(name="reh", model="ollama/tiny:1b", tools=["files"], approval_mode=ApprovalMode.auto,
                               selfcheck=False, workdir=str(folder)))
    engine.run_blocking(bot, "go", rehearsal=True)
    assert not (folder / "new.md").exists()


# ------------------------------------------------------------------------- CLI / API / page

def test_cli_sets_validates_and_clears_the_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    d = tmp_path / "Downloads"
    d.mkdir()
    assert runner.invoke(cli_app, ["bot", "create", "tidy", "--model", "mock/demo", "--workdir", str(d)]).exit_code == 0
    assert str(d.resolve()) in runner.invoke(cli_app, ["bot", "show", "tidy"]).output
    bad = runner.invoke(cli_app, ["bot", "update", "tidy", "--workdir", "/etc"])
    assert bad.exit_code == 1 and "system location" in bad.output
    assert runner.invoke(cli_app, ["bot", "update", "tidy", "--clear-workdir"]).exit_code == 0
    assert '"workdir": null' in runner.invoke(cli_app, ["bot", "show", "tidy"]).output


def test_api_and_bot_page(tmp_path, monkeypatch):
    import re
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    d = tmp_path / "data"
    d.mkdir()
    with TestClient(create_app()) as c:
        assert c.post("/api/bots", json={"name": "wd", "workdir": "/etc"}).status_code == 422
        r = c.post("/api/bots", json={"name": "wd", "workdir": str(d)})
        assert r.status_code == 201 and r.json()["workdir"] == str(d.resolve())
        assert c.patch("/api/bots/wd", json={"workdir": "/nope/nope"}).status_code == 422
        assert c.patch("/api/bots/wd", json={"workdir": ""}).json()["workdir"] is None
        c.patch("/api/bots/wd", json={"workdir": str(d)})
        page = c.get("/bots/wd").text
        assert "folder: " in page and 'name="workdir"' in page
        tok = re.search(r'name="csrf" content="([^"]+)"', page).group(1)
        form = {"csrf": tok, "description": "", "model": "mock/demo", "instructions": "", "approval_mode": "ask",
                "risk_tier": "supervised", "command_rules": ""}
        r = c.post("/bots/wd/update", data={**form, "workdir": "/etc"}, follow_redirects=True)
        assert "Working folder not saved" in r.text and "system location" in r.text
        assert c.get("/api/bots/wd").json()["workdir"] == str(d.resolve()), "a bad edit changes nothing"
        c.post("/bots/wd/update", data={**form, "workdir": ""}, follow_redirects=True)
        assert c.get("/api/bots/wd").json()["workdir"] is None
