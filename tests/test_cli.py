from __future__ import annotations

import pytest
from typer.testing import CliRunner

from hutch.cli import app

runner = CliRunner()


@pytest.fixture()
def state_env(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("COLUMNS", "300")  # keep rich tables from wrapping cell text


def test_init_seeds_templates(state_env):
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    assert "research-briefing" in result.output

    listing = runner.invoke(app, ["bot", "list"])
    assert listing.exit_code == 0
    for name in ("research-briefing", "repo-sweeper", "tidy-downloads"):
        assert name in listing.output


def test_bot_create_and_validation(state_env):
    runner.invoke(app, ["init"])
    ok = runner.invoke(app, ["bot", "create", "my-scout", "--model", "mock/demo",
                             "--tools", "web_fetch,files", "--approvals", "auto"])
    assert ok.exit_code == 0, ok.output

    bad_name = runner.invoke(app, ["bot", "create", "Bad Name"])
    assert bad_name.exit_code != 0

    bad_tool = runner.invoke(app, ["bot", "create", "another", "--tools", "laser"])
    assert bad_tool.exit_code != 0
    assert "unknown tools" in bad_tool.output


def test_run_command_mock_bot_succeeds(state_env):
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["bot", "create", "quick", "--model", "mock/demo",
                                 "--tools", "files,memory", "--approvals", "auto"])
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["run", "quick", "summarize the report please"])
    assert result.exit_code == 0, result.output
    assert "succeeded" in result.output

    runs = runner.invoke(app, ["runs", "list"])
    assert "quick" in runs.output and "succeeded" in runs.output


def test_status_and_approvals_empty(state_env):
    runner.invoke(app, ["init"])
    status = runner.invoke(app, ["status"])
    assert status.exit_code == 0 and "research-briefing" in status.output
    approvals = runner.invoke(app, ["approvals", "list"])
    assert approvals.exit_code == 0 and "no pending approvals" in approvals.output


def test_bot_pause_resume_forget(state_env):
    runner.invoke(app, ["init"])
    assert runner.invoke(app, ["bot", "pause", "research-briefing"]).exit_code == 0
    show = runner.invoke(app, ["bot", "show", "research-briefing"])
    assert '"paused": true' in show.output
    assert runner.invoke(app, ["bot", "resume", "research-briefing"]).exit_code == 0


def test_demo_seed_leaves_waiting_approval(state_env):
    result = runner.invoke(app, ["demo", "seed"])
    assert result.exit_code == 0, result.output
    # tidy-downloads run should be waiting on its write_file approval
    approvals = runner.invoke(app, ["approvals", "list"])
    assert "tidy-downloads" in approvals.output
