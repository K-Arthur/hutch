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


def test_bot_limit_flags_create_and_update_estimate_controls(state_env):
    assert runner.invoke(app, ["init"]).exit_code == 0
    created = runner.invoke(app, ["bot", "create", "bounded", "--model", "mock/demo",
                                  "--max-steps", "8", "--timeout-seconds", "240",
                                  "--max-turn-tokens", "1024", "--daily-token-cap", "8000",
                                  "--max-cost-usd", "1.25", "--daily-cost-cap-usd", "7.50"])
    assert created.exit_code == 0, created.output
    updated = runner.invoke(app, ["bot", "update", "bounded", "--max-steps", "10",
                                  "--daily-token-cap", "9000", "--daily-cost-cap-usd", "8"])
    assert updated.exit_code == 0, updated.output
    shown = runner.invoke(app, ["bot", "show", "bounded"])
    assert shown.exit_code == 0, shown.output
    for value in ('"max_steps": 10', '"timeout_seconds": 240', '"max_turn_tokens": 1024',
                  '"daily_token_cap": 9000', '"max_cost_usd": 1.25', '"daily_cost_cap_usd": 8.0'):
        assert value in shown.output
    invalid = runner.invoke(app, ["bot", "update", "bounded", "--max-cost-usd", "-1"])
    assert invalid.exit_code != 0


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


def test_demo_seed_queues_a_run_for_a_live_engine_instead_of_leaving_a_zombie(state_env):
    """The seeded approval must be executed by a long-lived process. Parked inside the short-lived CLI it
    became a zombie: Approve in the dashboard flipped a database row that nothing was waiting on."""
    import time
    from hutch.config import get_config
    from hutch.engine import Engine
    from hutch.models import RunStatus
    from hutch.store import Store

    result = runner.invoke(app, ["demo", "seed"])
    assert result.exit_code == 0, result.output
    store = Store(get_config())
    queued = [r for r in store.list_runs() if r.origin == "manual:demo"]
    assert len(queued) == 1 and queued[0].status is RunStatus.pending
    assert not [r for r in store.active_runs() if r.status is RunStatus.waiting_approval]

    # a live engine (what `hutch serve` is) picks it up and parks on a REAL approval
    engine = Engine(get_config(), store)
    engine.dispatch_pending()
    deadline = time.time() + 10
    while time.time() < deadline and not store.pending_approvals():
        time.sleep(0.05)
    pending = store.pending_approvals()
    assert pending and pending[0].run_id == queued[0].id
    from hutch.approvals import resolve_approval
    resolve_approval(store, pending[0].id, approve=True, by="test")
    deadline = time.time() + 10
    while time.time() < deadline and store.get_run(queued[0].id).status is not RunStatus.succeeded:
        time.sleep(0.05)
    assert store.get_run(queued[0].id).status is RunStatus.succeeded   # approving really resumes the run
    store.close()
