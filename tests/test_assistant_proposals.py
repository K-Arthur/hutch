"""The main assistant can suggest an assistant; only the person creates one (references: Grok Bot, OpenClaw).

Grok Bot's primary Bot may "suggest or create a focused Bot" and is told to "ask before creating several"; OpenClaw requires
operator approval for an agent-created agent. Here the tool can only record a bounded suggestion. Nothing is created from it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from hutch import proposals
from hutch.models import Bot
from hutch.proposals import MAX_PENDING, ProposalError
from hutch.server.app import create_app
from hutch.toolcalling.validate import validate_call
from hutch.tools.assistant_proposal import ProposeAssistantTool

JOB = "Own my weekly research briefing: collect sources, summarise what changed, hand back one page."


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture()
def store(client):
    return client.app.state.store


def _ctx(store, bot, conversation="conv_1", dry_run=False):
    from types import SimpleNamespace
    return SimpleNamespace(store=store, bot=bot, dry_run=dry_run, run=SimpleNamespace(conversation_id=conversation))


def test_the_contract_accepts_a_proposal_and_refuses_the_rest_before_dispatch():
    schema = ProposeAssistantTool.parameters
    assert validate_call(schema, {"name": "Research Briefing", "job": JOB}) == []
    assert validate_call(schema, {"name": "Research Briefing", "job": JOB, "why": "It recurs weekly."}) == []
    assert validate_call(schema, {"name": "R", "job": JOB}), "a one-character name"
    assert validate_call(schema, {"name": "Research", "job": "too short"}), "a job that says nothing"
    assert validate_call(schema, {"name": "Research", "job": JOB, "tools": ["shell"]}), "no way to ask for tools or permissions"
    assert validate_call(schema, {"job": JOB}) and validate_call(schema, "nope")


def test_only_the_main_assistant_is_given_the_tool(store):
    from hutch.tools import build_tools
    main = store.create_bot(Bot(name="juno", display_name="Juno", model="ollama/llama3.2:3b", tools=[]))
    other = store.create_bot(Bot(name="scribe", display_name="Scribe", model="ollama/llama3.2:3b", tools=[]))
    store.set_workspace_coordinator(main.id)
    from types import SimpleNamespace
    def offered(bot):
        ctx = SimpleNamespace(store=store, bot=bot, run=SimpleNamespace(conversation_id="conv_1", parent_run_id=None), skills=None,
                              delegation_submit=None)
        return "propose_assistant" in build_tools([], ctx)
    assert offered(main) is True and offered(other) is False


def test_the_tool_records_a_suggestion_and_creates_nothing(store):
    main = store.create_bot(Bot(name="juno", display_name="Juno", model="ollama/llama3.2:3b", tools=[]))
    store.set_workspace_coordinator(main.id)
    result = ProposeAssistantTool().run({"name": "Research Briefing", "job": JOB, "why": "weekly"}, _ctx(store, main))
    assert result.ok and "Nothing was created" in result.output
    assert [bot.name for bot in store.list_bots()] == ["juno"]
    assert [item["name"] for item in proposals.pending(store)] == ["Research Briefing"]


def test_another_assistant_cannot_suggest(store):
    main = store.create_bot(Bot(name="juno", display_name="Juno", model="ollama/llama3.2:3b", tools=[]))
    other = store.create_bot(Bot(name="scribe", display_name="Scribe", model="ollama/llama3.2:3b", tools=[]))
    store.set_workspace_coordinator(main.id)
    result = ProposeAssistantTool().run({"name": "Research", "job": JOB}, _ctx(store, other))
    assert not result.ok and "only the main assistant" in result.output and proposals.pending(store) == []


def test_it_asks_before_creating_several(store):
    for name in ("Research Briefing", "Inbox Triage", "Tidy Downloads"):
        proposals.propose(store, name=name, job=JOB)
    with pytest.raises(ProposalError, match=f"{MAX_PENDING} suggestions are already waiting"):
        proposals.propose(store, name="One More", job=JOB)


def test_duplicates_and_existing_assistants_are_refused(store):
    store.create_bot(Bot(name="scribe", display_name="Scribe", model="ollama/llama3.2:3b", tools=[]))
    with pytest.raises(ProposalError, match="already exists"):
        proposals.propose(store, name="Scribe", job=JOB)
    proposals.propose(store, name="Research Briefing", job=JOB)
    with pytest.raises(ProposalError, match="already suggested"):
        proposals.propose(store, name="research briefing", job=JOB)


def test_a_suggestion_disappears_once_an_assistant_with_that_name_exists(store):
    proposals.propose(store, name="Research Briefing", job=JOB)
    assert len(proposals.pending(store)) == 1
    store.create_bot(Bot(name="research-briefing", display_name="Research Briefing", model="ollama/llama3.2:3b", tools=[]))
    assert proposals.pending(store) == []


def test_the_api_lists_and_dismisses_and_has_no_way_to_create(client, store):
    item = proposals.propose(store, name="Research Briefing", job=JOB, why="weekly")
    listed = client.get("/api/v1/assistant-proposals").json()
    assert listed["limit"] == MAX_PENDING and [entry["name"] for entry in listed["proposals"]] == ["Research Briefing"]
    assert set(listed["proposals"][0]) == {"id", "name", "job", "why", "created_at"}, "nothing about who or what to grant"
    assert client.post("/api/v1/assistant-proposals/nope/dismiss").status_code == 404
    assert client.post(f"/api/v1/assistant-proposals/{item['id']}/dismiss").status_code == 200
    assert client.get("/api/v1/assistant-proposals").json()["proposals"] == []
    assert client.post(f"/api/v1/assistant-proposals/{item['id']}/create").status_code in (404, 405)
    assert store.list_bots() == []
