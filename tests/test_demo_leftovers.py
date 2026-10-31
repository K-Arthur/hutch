"""A workspace that still holds assistants from the removed demo is told so, with the way out (owner report).

`hutch init` used to print "No bots were created" while three demo assistants sat in the workspace, and nothing said
why first run never started. It now reports what exists, names the ones that cannot run, and gives the command.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from hutch.cli import app
from hutch.config import get_config
from hutch.demo_leftovers import RETIRED_DEMO, demo_warning, init_summary, retired_demo_assistants
from hutch.models import Bot
from hutch.store import Store


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    opened = Store(get_config())
    yield opened
    opened.close()


def _add(store, name, model):
    return store.create_bot(Bot(name=name, display_name=name.replace("-", " ").title(), model=model, tools=[]))


@pytest.mark.parametrize("model,demo", [("mock/demo", True), ("MOCK/anything", True), ("demo", True), ("", False),
                                        ("ollama/llama3.2:3b", False), ("opencode/opencode/glm-free", False), ("demonstrator/x", False)])
def test_only_the_retired_demo_routes_count(model, demo):
    assert bool(RETIRED_DEMO.match(model)) is demo


def test_an_empty_workspace_is_told_how_first_run_starts(store):
    assert "No assistants exist yet" in init_summary(store) and demo_warning(store) == ""


def test_demo_assistants_are_named_with_both_ways_out(store):
    for name in ("design-partner", "research-briefing", "tidy-downloads"):
        _add(store, name, "mock/demo")
    _add(store, "real-one", "ollama/llama3.2:3b")
    _add(store, "no-route-yet", "")
    assert [bot.name for bot in retired_demo_assistants(store)] == ["design-partner", "research-briefing", "tidy-downloads"]
    text = init_summary(store)
    assert "5 assistants already exist; init created none" in text
    assert "3 assistants left over from an earlier demo version (Design Partner, Research Briefing, Tidy Downloads)" in text
    assert "Review install" in text and "hutch bot destroy" in text and "choose Remove" in text
    assert "Real One" not in text and "No Route Yet" not in text, "only demo assistants are called demo"


def test_hutch_init_stops_claiming_nothing_exists_when_something_does(store):
    _add(store, "design-partner", "mock/demo")
    result = CliRunner().invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    assert "No bots were created" not in result.output
    assert "1 assistant already exist; init created none" in result.output
    assert "left over from an earlier demo version" in result.output and "Design Partner" in result.output


def test_hutch_init_on_a_clean_workspace_points_to_first_run(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "fresh"))
    result = CliRunner().invoke(app, ["init"])
    assert result.exit_code == 0 and "No assistants exist yet" in result.output
