from __future__ import annotations

import pytest
from typer.testing import CliRunner

from hutch.cli import app

runner = CliRunner()


@pytest.fixture()
def state_env(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("COLUMNS", "300")  # keep rich tables from wrapping cell text
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-no-network")


def test_init_does_not_seed_fake_bots(state_env):
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    assert "No bots were created" in result.output

    listing = runner.invoke(app, ["bot", "list"])
    assert listing.exit_code == 0
    assert "no bots" in listing.output.lower() or "no bot" in listing.output.lower()


def test_bot_create_and_validation(state_env, monkeypatch):
    runner.invoke(app, ["init"])
    ok = runner.invoke(app, ["bot", "create", "my-scout", "--model", "mock/demo",
                             "--tools", "web_fetch,files", "--approvals", "auto"])
    assert ok.exit_code == 0, ok.output

    bad_name = runner.invoke(app, ["bot", "create", "Bad Name"])
    assert bad_name.exit_code != 0

    bad_tool = runner.invoke(app, ["bot", "create", "another", "--tools", "laser"])
    assert bad_tool.exit_code != 0
    assert "unknown tools" in bad_tool.output

    missing_model = runner.invoke(app, ["bot", "create", "no-route"])
    assert missing_model.exit_code != 0 and "real --model route is required" in missing_model.output
    monkeypatch.delenv("HUTCH_TESTING", raising=False)
    fake_model = runner.invoke(app, ["bot", "create", "pretend", "--model", "mock/demo"])
    assert fake_model.exit_code != 0 and "test-only" in fake_model.output


def test_local_model_route_mode_is_persisted_and_blocks_hosted_cli_updates(state_env):
    assert runner.invoke(app, ["init"]).exit_code == 0
    created = runner.invoke(app, ["bot", "create", "modebot", "--model", "ollama/fake:8b",
                                 "--inference-mode", "local"])
    assert created.exit_code == 0, created.output
    blocked = runner.invoke(app, ["bot", "update", "modebot", "--model", "openai/gpt-4o-mini"])
    assert blocked.exit_code != 0 and "Local model routes setting" in blocked.output
    shown = runner.invoke(app, ["bot", "show", "modebot"])
    assert '"inference_mode": "local"' in shown.output and '"model": "ollama/fake:8b"' in shown.output
    hybrid = runner.invoke(app, ["bot", "update", "modebot", "--inference-mode", "hybrid",
                                 "--model", "openai/gpt-4o-mini"])
    assert hybrid.exit_code == 0, hybrid.output


def test_bot_limit_flags_create_and_update_estimate_controls(state_env):
    assert runner.invoke(app, ["init"]).exit_code == 0
    created = runner.invoke(app, ["bot", "create", "bounded", "--model", "mock/demo",
                                  "--max-steps", "8", "--timeout-seconds", "240",
                                  "--max-turn-tokens", "1024", "--daily-token-cap", "8000",
                                  "--max-cost-usd", "1.25", "--daily-cost-cap-usd", "7.50",
                                  "--local-browser-handoff"])
    assert created.exit_code == 0, created.output
    updated = runner.invoke(app, ["bot", "update", "bounded", "--max-steps", "10",
                                  "--daily-token-cap", "9000", "--daily-cost-cap-usd", "8"])
    assert updated.exit_code == 0, updated.output
    shown = runner.invoke(app, ["bot", "show", "bounded"])
    assert shown.exit_code == 0, shown.output
    for value in ('"max_steps": 10', '"timeout_seconds": 240', '"max_turn_tokens": 1024',
                  '"daily_token_cap": 9000', '"max_cost_usd": 1.25', '"daily_cost_cap_usd": 8.0',
                  '"local_browser_handoff": true'):
        assert value in shown.output
    disabled = runner.invoke(app, ["bot", "update", "bounded", "--no-local-browser-handoff"])
    assert disabled.exit_code == 0, disabled.output
    assert '"local_browser_handoff": false' in runner.invoke(app, ["bot", "show", "bounded"]).output
    invalid = runner.invoke(app, ["bot", "update", "bounded", "--max-cost-usd", "-1"])
    assert invalid.exit_code != 0


def test_run_command_test_scenario_fixture_succeeds(state_env):
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
    assert status.exit_code == 0 and "no bots" in status.output.lower() and "real model route" in status.output.lower()
    approvals = runner.invoke(app, ["approvals", "list"])
    assert approvals.exit_code == 0 and "no pending approvals" in approvals.output


def test_demo_seed_command_is_not_a_product_feature(state_env):
    result = runner.invoke(app, ["demo", "seed"])
    assert result.exit_code != 0


def test_bot_pause_resume_forget(state_env):
    runner.invoke(app, ["init"])
    assert runner.invoke(app, ["bot", "create", "real-bot", "--model", "mock/demo"]).exit_code == 0
    assert runner.invoke(app, ["bot", "pause", "real-bot"]).exit_code == 0
    show = runner.invoke(app, ["bot", "show", "real-bot"])
    assert '"paused": true' in show.output
    assert runner.invoke(app, ["bot", "resume", "real-bot"]).exit_code == 0


def test_fake_demo_seed_command_has_been_removed(state_env):
    result = runner.invoke(app, ["demo", "seed"])
    assert result.exit_code != 0
