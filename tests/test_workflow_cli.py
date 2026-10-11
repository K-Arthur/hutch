"""The workflow CLI surface: parity with the API, and the policy command.

These use typer's runner against a throwaway state directory, so they prove the commands a
person actually types (validate, save, mode, show, list, status, answer) work end to end.
"""
from __future__ import annotations

import json
import time

from typer.testing import CliRunner

from hutch.cli import app, _store
from hutch import providers
from hutch.hardware import Hardware
from hutch.models import ACTIVE_STATUSES
from hutch.workflow import probes as probe_module
from tests.fakes import FakeOllama

runner = CliRunner()


def plan() -> dict:
    return {
        "name": "cli-plan",
        "envelope": {"tools": ["list_files"]},
        "budget": {"max_nodes": 10, "max_model_calls": 0},
        "nodes": [
            {"kind": "tool", "id": "scan", "tool": "list_files", "args": {"path": "."}},
            {"kind": "transform", "id": "count", "op": "pluck",
             "args": {"value": {"ref": "scan.data"}, "path": "count"}},
        ],
    }


def test_workflow_cli_validate_save_show_and_list(config, tmp_path):
    assert runner.invoke(app, ["init"]).exit_code == 0
    created = runner.invoke(app, ["bot", "create", "cli-bot", "--model", "ollama/qwen3:4b",
                                  "--tools", "files"])
    assert created.exit_code == 0, created.output
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan()), encoding="utf-8")

    validated = runner.invoke(app, ["workflow", "validate", str(path), "--bot", "cli-bot"])
    assert validated.exit_code == 0, validated.output
    assert "valid" in validated.output and "list_files" in validated.output

    saved = runner.invoke(app, ["workflow", "save", str(path), "--name", "cli-plan"])
    assert saved.exit_code == 0 and "revision 1" in saved.output

    listed = runner.invoke(app, ["workflow", "list"])
    assert "cli-plan" in listed.output and "inactive" in listed.output

    shown = runner.invoke(app, ["workflow", "show", "cli-plan"])
    assert shown.exit_code == 0 and "scan" in shown.output and "count" in shown.output

    exported = runner.invoke(app, ["workflow", "export", "cli-plan"])
    assert exported.exit_code == 0 and "cli-plan" in exported.output

    missing = runner.invoke(app, ["workflow", "show", "nope"])
    assert missing.exit_code == 1


def test_workflow_cli_refuses_an_invalid_plan(config, tmp_path):
    assert runner.invoke(app, ["init"]).exit_code == 0
    assert runner.invoke(app, ["bot", "create", "cli-bot", "--model", "ollama/qwen3:4b",
                               "--tools", "files"]).exit_code == 0
    broken = plan()
    broken["nodes"][1]["args"]["value"] = {"ref": "missing"}
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(broken), encoding="utf-8")
    result = runner.invoke(app, ["workflow", "validate", str(path), "--bot", "cli-bot"])
    assert result.exit_code == 1
    assert "missing" in result.output


def test_workflow_cli_mode_sets_and_reports_the_policy(config):
    assert runner.invoke(app, ["init"]).exit_code == 0
    runner.invoke(app, ["bot", "create", "mode-bot", "--model", "ollama/qwen3:4b", "--tools", "files"])
    set_mode = runner.invoke(app, ["workflow", "mode", "mode-bot", "--mode", "auto",
                                   "--allow-definition", "cli-plan", "--max-nodes", "40",
                                   "--max-tokens", "32000"])
    assert set_mode.exit_code == 0 and "auto" in set_mode.output
    store = _store()
    try:
        bot = store.get_bot("mode-bot")
        assert bot is not None and bot.workflow_mode == "auto"
        assert bot.workflow_limits == {"definitions": ["cli-plan"], "max_nodes": 40, "max_tokens": 32000}
    finally:
        store.close()
    bad = runner.invoke(app, ["workflow", "mode", "mode-bot", "--mode", "sometimes"])
    assert bad.exit_code == 2


def test_workflow_cli_probe_runs_all_held_out_checks_against_the_selected_local_model(config, monkeypatch):
    monkeypatch.setattr(probe_module, "probe_hardware",
                        lambda with_runtimes=False: Hardware(ram_total_gb=24, ram_available_gb=12))
    model = "qwen3:1.7b-q4_K_M"
    server = FakeOllama(models={model: {"params": "1.7B", "quant": "Q4_K_M",
                                        "caps": ["completion", "tools"]}})
    server.version = "0.40.3"
    from tests.test_workflow_probes import _case_id, _reply

    server.script = lambda body: {"content": _reply(_case_id(body))}
    monkeypatch.setattr(providers, "make_provider", lambda _provider, _endpoint=None:
                        __import__("hutch.providers.ollama", fromlist=["OllamaProvider"]).OllamaProvider(server.url))
    try:
        assert runner.invoke(app, ["init"]).exit_code == 0
        created = runner.invoke(app, ["bot", "create", "probe-bot", "--model", f"ollama/{model}",
                                      "--base-url", server.url, "--tools", ""])
        assert created.exit_code == 0, created.output
        result = runner.invoke(app, ["workflow", "qualify", "probe-bot", "--role", "author",
                                     "--probe", "--campaign", "cli-probe-test"])
        assert result.exit_code == 0, result.output
        assert "passed" in result.output and "structure: passed" in result.output
        assert len(server.of("/api/chat")) == 4
        store = _store()
        try:
            records = store.role_qualifications("ollama", model)
            assert records[0]["state"] == "probed"
            assert records[0]["execution_profile_hash"]
        finally:
            store.close()
    finally:
        server.close()


def test_workflow_cli_run_and_status_answer_a_question(config, tmp_path):
    """A plan with a question: `run` prints the id, `answer` records it, `status` reports it."""
    assert runner.invoke(app, ["init"]).exit_code == 0
    created = runner.invoke(app, ["bot", "create", "ask-bot", "--model", "ollama/qwen3:4b",
                                  "--tools", "files"])
    assert created.exit_code == 0, created.output
    ask_plan = {
        "name": "cli-ask",
        "envelope": {"tools": []},
        "budget": {"max_nodes": 5, "max_model_calls": 0},
        "nodes": [{"kind": "ask", "id": "confirm", "question": "Ship it?",
                   "options": ["yes", "no"], "timeout_seconds": 120}],
    }
    path = tmp_path / "ask.json"
    path.write_text(json.dumps(ask_plan), encoding="utf-8")
    assert runner.invoke(app, ["workflow", "save", str(path), "--name", "cli-ask"]).exit_code == 0

    # --no-wait returns immediately with the instance id.
    started = runner.invoke(app, ["workflow", "run", "cli-ask", "--bot", "ask-bot", "--no-wait"])
    assert started.exit_code == 0 and "wrun_" in started.output
    wf_id = next(word for word in started.output.split() if word.startswith("wrun_"))
    wf_id = wf_id.strip("[]")

    # Drive the engine by hand (the CLI's own watch loop is covered by the capture script).
    from hutch.engine import Engine
    from hutch.config import get_config
    from hutch.workflow import persistence as wstore

    config = get_config()
    store = _store()
    engine = Engine(config, store)
    try:
        question = None
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            engine.tick()
            pending = wstore.questions(store, wf_id, status="pending")
            if pending:
                question = pending[0]
                break
            run = store.get_run(wstore.workflow_run(store, wf_id)["attempt_run_id"])
            if run is not None and run.status not in ACTIVE_STATUSES:
                break
            time.sleep(0.05)
        assert question is not None
        # Answer through the CLI while the attempt is genuinely waiting: closing the store
        # under a live attempt would fail the workflow and cancel its question.
        answered = runner.invoke(app, ["workflow", "answer", question["id"], "yes"])
        assert answered.exit_code == 0 and "answer recorded" in answered.output, answered.output
        again = runner.invoke(app, ["workflow", "answer", question["id"], "no"])
        assert again.exit_code == 1 and "recorded answer is unchanged" in again.output, again.output

        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            engine.tick()
            workflow = wstore.workflow_run(store, wf_id)
            if workflow is not None and workflow["status"] in (
                    "succeeded", "failed", "stopped", "outcome_unknown"):
                break
            time.sleep(0.05)
    finally:
        store.close()

    status = runner.invoke(app, ["workflow", "status", wf_id])
    assert status.exit_code == 0, status.output
    assert wf_id in status.output
    missing = runner.invoke(app, ["workflow", "status", "wrun_missing"])
    assert missing.exit_code == 1
