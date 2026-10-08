"""The template gallery: every template must be valid, honest about what it can do, and actually runnable."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hutch.cli import app as cli_app
from hutch.engine import Engine
from hutch.models import Bot, RunStatus
from hutch.safety import PolicyEngine
from hutch.templates import CATEGORIES, TEMPLATE_INFO, TEMPLATES, gallery
from hutch.tools import ALL_TOOL_NAMES, expand_tools

runner = CliRunner()
ALL = sorted(TEMPLATE_INFO)
PRESETS = set(json.loads((Path(__file__).parent.parent / "src/hutch/data/presets.json").read_text())["presets"])


def test_the_gallery_has_the_roles_the_reference_products_ship():
    cats = {i.category for i in TEMPLATE_INFO.values()}
    assert {"Sales", "Product", "Marketing", "Analytics", "Support"} <= cats, "Team Bots' sales / PM / marketing / analytics, plus support"
    assert len(TEMPLATE_INFO) >= 12


@pytest.mark.parametrize("key", ALL)
def test_every_template_is_a_valid_bot(key):
    i = TEMPLATE_INFO[key]
    b = i.bot
    assert b.name == key == b.template and re.fullmatch(r"[a-z0-9][a-z0-9-]{1,40}", key)
    assert Bot.model_validate(b.model_dump()) == b
    assert i.category in CATEGORIES and i.tagline and i.reads and i.produces and i.safety
    assert b.preset in PRESETS and not b.model, "templates describe tasks but do not choose or simulate a model"
    assert set(expand_tools(b.tools)) <= set(ALL_TOOL_NAMES) | {"browser"}
    assert len(b.instructions) > 150 and b.workdir is None
    if b.schedule:
        assert len(b.schedule.cron.split()) == 5


@pytest.mark.parametrize("key", ALL)
def test_a_template_never_promises_a_tool_it_does_not_have(key):
    b = TEMPLATES[key]
    text = b.instructions.lower()
    names = set(expand_tools(b.tools))
    if re.search(r"\bfetch\b|public (web|website|page)|the web", text):
        assert "web_fetch" in names, f"{key} talks about fetching but has no web_fetch"
    if re.search(r"`git |\bshell\b|use shell|\bawk\b|\bpython3\b", text):
        assert "shell" in names, f"{key} uses commands but has no shell"
    if "memory" in text or "remember" in text:
        assert "remember" in names, f"{key} talks about its memory but cannot remember"
    if re.search(r"write |writes |append|draft", text):
        assert "write_file" in names or "shell" in names, f"{key} writes files but has no way to"


@pytest.mark.parametrize("key", ALL)
def test_a_template_that_reads_your_files_says_so_and_a_folderless_one_does_not(key):
    i = TEMPLATE_INFO[key]
    mentions_files = bool(re.search(r"\.txt|\.csv|\.md|working folder|git repo|tickets/|meetings/|notes/", i.bot.instructions))
    assert i.needs_folder == mentions_files or key == "research-briefing", key


@pytest.mark.parametrize("key", [k for k in ALL if TEMPLATE_INFO[k].category in ("Sales", "Support")])
def test_templates_that_face_people_draft_and_cannot_send(key):
    names = set(expand_tools(TEMPLATES[key].tools))
    assert not names & {"shell", "browser"}, "no way to send, post or submit anything"
    assert "cannot send" in TEMPLATE_INFO[key].safety.lower() or "no way to" in TEMPLATE_INFO[key].safety.lower()
    assert re.search(r"cannot (contact|send)|must not suggest|no way", TEMPLATES[key].instructions.lower() + TEMPLATE_INFO[key].safety.lower())


@pytest.mark.parametrize("key", ["repo-sweeper", "pm-standup-digest", "release-notes"])
def test_read_only_git_templates_deny_what_would_change_the_repo(key):
    e = PolicyEngine(TEMPLATES[key].risk_tier, TEMPLATES[key].command_rules)
    for bad in ("git push origin main", "git commit -m x", "git reset --hard", "rm -rf build", "mv a b", "echo $(git push)", "bash -c 'git push'"):
        assert e.check_shell(bad).verdict.value == "deny", (key, bad)
    for good in ("git log --oneline", "git status", "git diff", "ls", "cat README.md"):
        assert e.check_shell(good).verdict.value == "allow", (key, good)


def test_the_data_reporter_cannot_download_anything():
    t = TEMPLATES["data-reporter"]
    e = PolicyEngine(t.risk_tier, t.command_rules)
    for bad in ("curl http://x.io", "wget http://x.io", "nohup curl http://x", "bash -c 'curl http://x'"):
        assert e.check_shell(bad).verdict.value == "deny", bad
    assert e.check_shell("head -5 data.csv | cut -d, -f1 | sort | uniq -c").verdict.value == "allow"


def test_gallery_groups_by_category_in_a_stable_order():
    g = gallery()
    assert [c for c, _ in g] == [c for c in CATEGORIES if any(i.category == c for i in TEMPLATE_INFO.values())]
    assert sum(len(items) for _, items in g) == len(TEMPLATE_INFO)


def test_templates_never_create_seeded_bots_or_fake_model_routes(store):
    assert not store.list_bots()
    assert all(not template.model for template in TEMPLATES.values())


@pytest.mark.parametrize("key", ALL)
def test_every_template_exercises_the_governed_tool_pipeline_in_test_fixture(key, config, store):
    engine = Engine(config, store)
    bot = TEMPLATES[key].model_copy(deep=True)
    bot.name = f"t-{key}"[:41]
    bot = store.create_bot(bot)
    run = engine.run_blocking(bot, "go", rehearsal=True)
    assert run.status is RunStatus.succeeded, (key, run.error)
    assert not store.pending_approvals()


def test_cli_lists_templates_by_category_and_warns_when_a_folder_is_needed(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    out = runner.invoke(cli_app, ["bot", "templates"]).output
    for needle in ("Sales", "Support", "Analytics", "sales-prospector", "support-triage", "needs a folder"):
        assert needle in out, needle
    made = runner.invoke(cli_app, ["bot", "create", "mine", "--template", "support-triage",
                                   "--model", "mock/demo"]).output
    assert "reads files" in made and "--workdir" in made
    d = tmp_path / "tickets-folder"
    d.mkdir()
    ok = runner.invoke(cli_app, ["bot", "create", "mine2", "--template", "support-triage", "--workdir", str(d),
                                 "--model", "mock/demo"]).output
    assert "reads files" not in ok
    assert runner.invoke(cli_app, ["bot", "create", "mine3", "--template", "nope"]).exit_code == 1


def test_api_exposes_what_a_gallery_needs(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from hutch.server.app import create_app
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    with TestClient(create_app()) as c:
        rows = {r["name"]: r for r in c.get("/api/bots/templates").json()}
        assert set(rows) == set(ALL)
        r = rows["sales-prospector"]
        assert r["category"] == "Sales" and r["needs_folder"] and "prospects.txt" in r["reads"] and r["safety"]
        assert rows["pm-standup-digest"]["rules"] and rows["pm-standup-digest"]["schedule"]["cron"] == "0 9 * * 1-5"
        made = c.post("/api/bots", json={"name": "from-tpl", "template": "meeting-actions", "model": "mock/demo"})
        assert made.status_code == 201 and made.json()["template"] == "meeting-actions"
