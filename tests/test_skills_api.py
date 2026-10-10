"""The Skills API and CLI: the same lifecycle the product exposes, plus Bot binding and readiness."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from hutch.cli import app as cli_app
from hutch.server.app import create_app
from hutch.templates import TEMPLATES
from hutch.tools import expand_tools

runner = CliRunner()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    with TestClient(app) as c:
        yield c


def make_bot(client, name="skill-bot", **overrides):
    body = {"name": name, "model": "mock/demo", "tools": ["files", "memory"], "approval_mode": "auto"}
    body.update(overrides)
    res = client.post("/api/bots", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def install_builtin(client, name="workspace-summary", trust=True):
    res = client.post("/api/v1/skills/install", json={"source": "builtin", "name": name})
    assert res.status_code == 201, res.text
    if trust:
        res = client.post(f"/api/v1/skills/{name}/trust")
        assert res.status_code == 200, res.text
    return res.json()


# ------------------------------------------------------------------ library

def test_library_lists_installed_and_available_bundled_skills(client):
    report = client.get("/api/v1/skills").json()
    assert report["skills"] == []
    bundled = {item["name"] for item in report["available"] if item["source"]["scope"] == "builtin"}
    assert {"workspace-summary", "repo-review", "outlook-mail-digest"} <= bundled
    assert all(item["valid"] for item in report["available"] if item["name"] in bundled)
    assert report["limits"]["max_skills_per_bot"] >= 1


def test_install_trust_disable_enable_round_trip(client):
    detail = install_builtin(client, trust=False)
    assert detail["status"] == "review_required"
    detail = client.get("/api/v1/skills/workspace-summary").json()
    assert detail["trusted"] is False
    assert "## Steps" in detail["body"], "the inspector shows the instructions for review"

    trusted = client.post("/api/v1/skills/workspace-summary/trust").json()
    assert trusted["status"] == "enabled"
    disabled = client.post("/api/v1/skills/workspace-summary/disable").json()
    assert disabled["status"] == "disabled"
    enabled = client.post("/api/v1/skills/workspace-summary/enable").json()
    assert enabled["status"] == "enabled"


def test_install_from_local_path_stages_review_and_rejects_bad_packages(client, tmp_path):
    source = tmp_path / "mine" / "team-notes"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(
        "---\nname: team-notes\ndescription: Turn notes into a team digest.\n---\n\n## Steps\n1. Read the notes.\n",
        encoding="utf-8")
    res = client.post("/api/v1/skills/install", json={"source": "path", "path": str(source)})
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "review_required"

    bad = tmp_path / "mine" / "broken"
    bad.mkdir(parents=True)
    (bad / "SKILL.md").write_text("---\nname: broken\n---\nno description\n", encoding="utf-8")
    res = client.post("/api/v1/skills/install", json={"source": "path", "path": str(bad)})
    assert res.status_code == 422
    assert "description" in res.json()["detail"]

    missing = client.post("/api/v1/skills/install", json={"source": "path", "path": str(tmp_path / "nope")})
    assert missing.status_code == 422


def test_update_flow_keeps_the_reviewed_version_active_until_applied(client, tmp_path):
    source = tmp_path / "mine" / "team-notes"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(
        "---\nname: team-notes\ndescription: Turn notes into a team digest.\n---\n\nBody one.\n", encoding="utf-8")
    client.post("/api/v1/skills/install", json={"source": "path", "path": str(source)})
    client.post("/api/v1/skills/team-notes/trust")
    first = client.get("/api/v1/skills/team-notes").json()

    (source / "SKILL.md").write_text(
        "---\nname: team-notes\ndescription: Turn notes into a team digest.\n---\n\nBody two, changed.\n", encoding="utf-8")
    staged = client.post("/api/v1/skills/team-notes/update").json()
    assert staged["hash"] == first["hash"]
    assert staged["staged_update"]["hash"] != first["hash"]
    assert staged["status"] == "update_pending"
    active = client.get("/api/v1/skills/team-notes").json()
    assert active["hash"] == first["hash"], "active version is unchanged until review"

    applied = client.post("/api/v1/skills/team-notes/update/apply").json()
    assert applied["hash"] != first["hash"] and applied["status"] == "enabled"
    rolled = client.post("/api/v1/skills/team-notes/rollback").json()
    assert rolled["hash"] == first["hash"]


def test_uninstall_and_detail_after(client):
    install_builtin(client)
    res = client.delete("/api/v1/skills/workspace-summary")
    assert res.status_code == 200
    assert client.get("/api/v1/skills/workspace-summary").status_code == 404


# ------------------------------------------------------------------- bots

def test_bot_binding_requires_a_reviewed_installed_skill(client):
    make_bot(client)
    untrusted = client.patch("/api/bots/skill-bot", json={"skills": ["workspace-summary"]})
    assert untrusted.status_code == 422
    assert "unknown skill" in untrusted.json()["detail"]

    install_builtin(client, trust=False)
    unreviewed = client.patch("/api/bots/skill-bot", json={"skills": ["workspace-summary"]})
    assert unreviewed.status_code == 422 and "reviewed" in unreviewed.json()["detail"]

    client.post("/api/v1/skills/workspace-summary/trust")
    bound = client.patch("/api/bots/skill-bot", json={"skills": ["workspace-summary"]})
    assert bound.status_code == 200 and bound.json()["skills"] == ["workspace-summary"]

    cleared = client.patch("/api/bots/skill-bot", json={"skills": []})
    assert cleared.status_code == 200 and cleared.json()["skills"] == [], "an explicit empty list clears the bindings"


def test_create_bot_with_skill_bindings_and_detail_lists_bound_bots(client):
    install_builtin(client)
    bot = make_bot(client, name="bound-bot", skills=["workspace-summary"])
    assert bot["skills"] == ["workspace-summary"]
    detail = client.get("/api/v1/skills/workspace-summary").json()
    assert [item["name"] for item in detail["bound_bots"]] == ["bound-bot"]

    bad = client.post("/api/bots", json={"name": "bad-bot", "model": "mock/demo",
                                           "skills": ["not-a-skill"]})
    assert bad.status_code == 422


def test_template_create_keeps_template_tools_unless_explicitly_overridden(client):
    # The template's tools survive an omitted tool list...
    res = client.post("/api/bots", json={"name": "research-bot", "model": "mock/demo",
                                         "template": "research-briefing"})
    assert res.status_code == 201, res.text
    bot = res.json()
    assert set(bot["tools"]) == set(expand_tools(list(TEMPLATES["research-briefing"].tools)))
    # ...an explicit empty list means no tools...
    res = client.post("/api/bots", json={"name": "bare-bot", "model": "mock/demo",
                                         "template": "research-briefing", "tools": []})
    assert res.status_code == 201, res.text
    assert res.json()["tools"] == []
    # ...and an explicit list replaces them.
    explicit = make_bot(client, name="explicit-bot", tools=["files"])
    assert explicit["tools"] == ["read_file", "list_files", "write_file"]

    # Two Bots from the same template get distinct identities (regression: template deep-copies
    # used to share the template singleton's Bot ID and the second create conflicted).
    res = client.post("/api/bots", json={"name": "research-bot-2", "model": "mock/demo",
                                         "template": "research-briefing"})
    assert res.status_code == 201, res.text
    assert res.json()["id"] != bot["id"]


# --------------------------------------------------------------- readiness

def test_readiness_reports_skills_model_and_tools_separately(client):
    install_builtin(client)
    make_bot(client, name="ready-bot", skills=["workspace-summary"])
    report = client.get("/api/v1/bots/ready-bot/readiness").json()
    areas = {area["id"]: area for area in report["areas"]}
    assert report["ready"] is True
    assert areas["skills"]["items"][0]["status"] == "ok"
    assert areas["model"]["status"] == "ok"
    assert areas["runtime"]["status"] == "ok"

    # A disabled binding is a visible capability loss, not a blocked Bot: the area warns, the run
    # simply does not load it.
    client.post("/api/v1/skills/workspace-summary/disable")
    report = client.get("/api/v1/bots/ready-bot/readiness").json()
    areas = {area["id"]: area for area in report["areas"]}
    assert areas["skills"]["status"] == "warning"
    assert "disabled" in areas["skills"]["items"][0]["detail"]

    # An uninstalled skill blocks the configured workflow and must be reported as missing.
    client.delete("/api/v1/skills/workspace-summary")
    report = client.get("/api/v1/bots/ready-bot/readiness").json()
    areas = {area["id"]: area for area in report["areas"]}
    assert report["ready"] is False
    assert areas["skills"]["status"] == "missing"
    assert "not installed" in areas["skills"]["items"][0]["detail"]


def test_readiness_explains_a_missing_connection_for_an_integration_skill(client):
    install_builtin(client, name="outlook-mail-digest")
    make_bot(client, name="mail-bot", skills=["outlook-mail-digest"])
    report = client.get("/api/v1/bots/mail-bot/readiness").json()
    areas = {area["id"]: area for area in report["areas"]}
    assert report["ready"] is False
    assert areas["connections"]["status"] == "missing"
    assert "Outlook Mail" in areas["connections"]["items"][0]["detail"]
    assert areas["skills"]["status"] == "warning"
    assert "Outlook Mail" in areas["skills"]["items"][0]["detail"]


# -------------------------------------------------------------------- runs

def test_run_submission_validates_and_records_skill_activation(client):
    install_builtin(client)
    make_bot(client, name="runner-bot", skills=["workspace-summary"])
    res = client.post("/api/v1/tasks/runs", headers={"Idempotency-Key": "skills-run-1"},
                       json={"bot": "runner-bot", "prompt": "summarize it", "skills": ["workspace-summary"]})
    assert res.status_code == 201, res.text
    assert res.json()["skill_activation"] == ["workspace-summary"]

    unknown = client.post("/api/v1/tasks/runs", headers={"Idempotency-Key": "skills-run-2"},
                           json={"bot": "runner-bot", "prompt": "go", "skills": ["nope"]})
    assert unknown.status_code == 422 and "unknown skill" in unknown.json()["detail"]

    unbound = client.post("/api/v1/tasks/runs", headers={"Idempotency-Key": "skills-run-3"},
                           json={"bot": "runner-bot", "prompt": "go", "skills": []})
    assert unbound.status_code == 201

    client.post("/api/v1/skills/workspace-summary/disable")
    revoked = client.post("/api/v1/tasks/runs", headers={"Idempotency-Key": "skills-run-4"},
                           json={"bot": "runner-bot", "prompt": "go", "skills": ["workspace-summary"]})
    assert revoked.status_code == 422 and "disabled" in revoked.json()["detail"]


# --------------------------------------------------------------------- CLI

@pytest.fixture()
def state_env(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))


def test_cli_skills_lifecycle(state_env):
    listed = runner.invoke(cli_app, ["skills", "list"])
    assert listed.exit_code == 0 and "workspace-summary" in listed.output

    installed = runner.invoke(cli_app, ["skills", "install", "--builtin", "workspace-summary"])
    assert installed.exit_code == 0 and "needs review" in runner.invoke(cli_app, ["skills", "list"]).output

    trusted = runner.invoke(cli_app, ["skills", "trust", "workspace-summary"])
    assert trusted.exit_code == 0
    shown = runner.invoke(cli_app, ["skills", "show", "workspace-summary"])
    assert shown.exit_code == 0 and "enabled" in shown.output and "hash" in shown.output

    disabled = runner.invoke(cli_app, ["skills", "disable", "workspace-summary"])
    assert disabled.exit_code == 0
    assert "disabled" in runner.invoke(cli_app, ["skills", "show", "workspace-summary"]).output
    assert runner.invoke(cli_app, ["skills", "enable", "workspace-summary"]).exit_code == 0

    removed = runner.invoke(cli_app, ["skills", "uninstall", "workspace-summary", "--yes"])
    assert removed.exit_code == 0
    assert "no such installed skill" in runner.invoke(cli_app, ["skills", "show", "workspace-summary"]).output


def test_cli_bot_create_template_tools_and_skill_binding(state_env):
    runner.invoke(cli_app, ["skills", "install", "--builtin", "workspace-summary"])
    runner.invoke(cli_app, ["skills", "trust", "workspace-summary"])

    created = runner.invoke(cli_app, ["bot", "create", "research-bot", "--model", "mock/demo",
                                      "--template", "research-briefing", "--skills", "workspace-summary"])
    assert created.exit_code == 0, created.output
    from hutch.cli import _store
    store = _store()
    try:
        bot = store.get_bot("research-bot")
        assert set(bot.tools) == set(expand_tools(list(TEMPLATES["research-briefing"].tools))), "the template's tools were kept"
        assert bot.skills == ["workspace-summary"]
    finally:
        store.close()

    empty = runner.invoke(cli_app, ["bot", "create", "bare-bot", "--model", "mock/demo", "--tools", ""])
    assert empty.exit_code == 0, empty.output
    store = _store()
    try:
        assert store.get_bot("bare-bot").tools == []
    finally:
        store.close()

    unknown_skill = runner.invoke(cli_app, ["bot", "create", "bad-bot", "--model", "mock/demo",
                                            "--skills", "nope"])
    assert unknown_skill.exit_code == 1 and "unknown skill" in unknown_skill.output
