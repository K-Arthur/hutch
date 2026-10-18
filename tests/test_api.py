from __future__ import annotations

import hashlib
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from hutch.models import Bot, Event, EventType, Run, RunStatus, RuntimeKind, Task
from hutch.server.app import create_app
from hutch.store import ActiveRunConflict, Store


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    with TestClient(app) as c:
        yield c


def make_bot(client, name="api-bot", **overrides):
    body = {
        "name": name, "model": "mock/demo",
        "tools": ["files", "memory", "shell"],
        "approval_mode": "auto",
        "description": "api test bot",
        "instructions": "test",
    }
    body.update(overrides)
    res = client.post("/api/bots", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def create_owned_human_wait(store, bot_id, prompt="finish a login"):
    run = store.create_run(Run(bot_id=bot_id, prompt=prompt))
    claimed = store.claim_run(run.id, "fixture-human-wait-owner", lease_seconds=30)
    assert claimed is not None
    store.transition_run(run.id, RunStatus.running, fence=claimed.fence)
    store.transition_run(run.id, RunStatus.waiting_human, fence=claimed.fence)
    store.append_event(Event(run_id=run.id, type=EventType.human_needed,
                             data={"reason": "Sign in to continue"}))
    return store.get_run(run.id), store.list_events(run.id)[-1].seq


def test_health_and_stats(client):
    assert client.get("/api/health").json()["status"] == "ok"
    stats = client.get("/api/stats").json()
    assert stats["bots"] == 0 and stats["pending_approvals"] == 0


def test_the_local_surface_carries_the_strict_csp_too(client):
    """Mission §11: the local dashboard is protected like the paired one.

    A stored injection in a page the owner's browser already trusts must not
    reach another origin or inline a script. The SPA loads only same-origin
    scripts, so the strict policy is compatible with the shipped UI.
    """
    response = client.get("/")
    csp = response.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp and "connect-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    assert "img-src 'self' data:" in csp


def test_tool_compatibility_reports_route_evidence_without_a_probe(client):
    make_bot(client, "local-tools-bot", model="ollama/llama3.2")
    report = client.get("/api/v1/tool-compatibility", params={"ref": "local-tools-bot"})
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["model"] == "ollama/llama3.2" and body["requested"] == "auto"
    assert body["profile"]["provider"] == "ollama" and body["profile"]["endpoint_class"] == "local"
    assert body["eligibility"]["native"]["available"] is True
    assert body["eligibility"]["constrained"]["available"] is True
    assert body["observations"] == [] and "validator" in body
    assert "advertised is not verified" in body["evidence_note"]

    make_bot(client, "hosted-tools-bot", model="lmstudio/qwen2.5-7b")
    hosted = client.get("/api/v1/tool-compatibility", params={"ref": "hosted-tools-bot"}).json()
    assert hosted["eligibility"]["constrained"]["available"] is False
    assert hosted["eligibility"]["native"]["available"] is True
    assert client.get("/api/v1/tool-compatibility", params={"ref": "missing"}).status_code == 404


def test_tool_protocol_is_a_validated_bot_setting(client):
    bot = make_bot(client, "protocol-bot")
    assert bot["tool_protocol"] == "auto"
    res = client.patch("/api/bots/protocol-bot", json={"tool_protocol": "constrained"})
    assert res.status_code == 200 and res.json()["tool_protocol"] == "constrained"
    assert client.patch("/api/bots/protocol-bot", json={"tool_protocol": "yolo"}).status_code == 422


def test_task_focus_presets_are_real_bot_settings_with_safe_validation(client):
    presets = client.get("/api/v1/task-presets")
    assert presets.status_code == 200, presets.text
    assert {item["id"] for item in presets.json()} >= {
        "router", "research", "extraction", "coding", "planner", "vision",
    }
    research = next(item for item in presets.json() if item["id"] == "research")
    assert research["title"] == "Research"
    assert research["want_context"] > research["minimum_context"] > 0

    created = client.post("/api/v1/bots", headers={"Idempotency-Key": "create-research-focus"}, json={
        "name": "research-focus-bot", "model": "mock/demo", "tools": [], "preset": "research",
    })
    assert created.status_code == 201, created.text
    assert created.json()["preset"] == "research"
    assert client.app.state.store.get_bot("research-focus-bot").preset == "research"

    template = client.post("/api/v1/bots", headers={"Idempotency-Key": "keep-template-task-focus"}, json={
        "name": "template-focus-bot", "template": "repo-sweeper", "model": "mock/demo", "tools": [],
    })
    assert template.status_code == 201, template.text
    assert template.json()["preset"] == "coding"

    cleared = client.patch("/api/bots/research-focus-bot", json={"preset": ""})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["preset"] is None

    invalid = client.patch("/api/bots/research-focus-bot", json={"preset": "provider-that-does-not-exist"})
    assert invalid.status_code == 422
    assert client.app.state.store.get_bot("research-focus-bot").preset is None

    invalid_create = client.post("/api/v1/bots", headers={"Idempotency-Key": "reject-unknown-focus"}, json={
        "name": "invalid-focus-bot", "model": "mock/demo", "tools": [], "preset": "unknown-focus",
    })
    assert invalid_create.status_code == 422
    assert client.app.state.store.get_bot("invalid-focus-bot") is None


def test_workspace_task_continuation_route_returns_not_found_for_missing_history(client):
    response = client.post("/api/v1/workspace/tasks/wst_missing/continue",
                           headers={"Idempotency-Key": "continue-missing-task"})
    assert response.status_code == 404
    assert response.json()["detail"] == "This task is no longer available."


def test_bot_memory_export_preserves_history_and_shares_without_other_private_data(client):
    import json

    owner = make_bot(client, name="memory-export-owner", paused=True)
    recipient = make_bot(client, name="memory-export-recipient", paused=True)
    store = client.app.state.store
    first = store.remember(owner["id"], "report_style", "Use concise bullet points.")
    reviewed = client.post(f"/api/v1/bots/{owner['id']}/facts/{first.id}/review",
                           headers={"Idempotency-Key": "review-memory-export-fact"},
                           json={"content_hash": first.content_hash, "action": "approve"})
    assert reviewed.status_code == 200, reviewed.text
    share = client.post(f"/api/v1/bots/{owner['id']}/facts/{first.id}/shares",
                        headers={"Idempotency-Key": "share-memory-export-fact"},
                        json={"target_bot_id": recipient["id"]})
    assert share.status_code == 201, share.text
    newer = store.remember(owner["id"], "report_style", "Use one short paragraph.")
    archived = store.remember(owner["id"], "old_project", "An archived reference.")
    archived_result = client.post(f"/api/v1/bots/{owner['id']}/facts/{archived.id}/review",
                                  headers={"Idempotency-Key": "archive-memory-export-fact"},
                                  json={"content_hash": archived.content_hash, "action": "archive"})
    assert archived_result.status_code == 200, archived_result.text
    store.remember(recipient["id"], "private_to_recipient", "Do not include in owner export.")

    response = client.get(f"/api/v1/bots/{owner['id']}/memory/export")

    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"] == 'attachment; filename="hutch-memory-memory-export-owner.json"'
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert payload["format"] == "hutch-bot-memory-export-v1"
    assert payload["bot"]["id"] == owner["id"]
    records = {fact["id"]: fact for fact in payload["facts"]}
    assert records[first.id]["status"] == "approved"
    assert records[first.id]["scope_kind"] == "bot"
    assert records[newer.id]["status"] == "proposed"
    assert records[archived.id]["status"] == "archived"
    assert any(review["action"] == "approve" and review["fact_id"] == first.id
               for review in payload["reviews"])
    assert any(review["action"] == "archive" and review["fact_id"] == archived.id
               for review in payload["reviews"])
    assert payload["shares"]["outgoing"][0]["id"] == share.json()["id"]
    assert payload["shares"]["outgoing"][0]["state"] == "source_revised"
    assert "Do not include in owner export." not in json.dumps(payload)
    assert any("workspace files" in item for item in payload["scope"]["excluded"])
    assert "plaintext" in payload["scope"]["notice"].lower()


def test_bot_creation_records_only_an_explicit_user_message_source(client):
    source = make_bot(client, name="source-conversation-bot", paused=True)
    store = client.app.state.store
    conversation, _ = store.create_conversation(
        source["id"], "Planning chat", idem_key="bot-source-conversation", request_hash="source-conversation")
    source_request = "Track the launch checklist and tell me when a blocker needs my attention."
    with store._tx() as db:
        store._insert_conversation_message(db, message_id="bot-source-user-message",
            conversation_id=conversation["id"], seq=1, run_id="", role="user",
            content=source_request, created_at=conversation["created_at"])
        store._insert_conversation_message(db, message_id="bot-source-assistant-message",
            conversation_id=conversation["id"], seq=2, run_id="", role="assistant",
            content="I can help you create a dedicated launch coordinator.", created_at=conversation["created_at"])

    payload = {
        "name": "launch-checklist", "description": "Monitor the launch checklist",
        "instructions": "Track launch blockers; ask before notifying people.", "model": "mock/demo", "tools": [],
        "source_conversation_id": conversation["id"], "source_message_id": "bot-source-user-message",
    }
    headers = {"Idempotency-Key": "create-launch-checklist"}
    created = client.post("/api/v1/bots", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    bot = client.app.state.store.get_bot("launch-checklist")
    assert bot is not None
    assert bot.instructions == payload["instructions"]
    assert "original_request" not in created.json()["creation_source"]
    assert bot.creation_source.model_dump() == {
        "conversation_id": conversation["id"], "message_id": "bot-source-user-message",
        "source_bot_id": source["id"], "sequence": 1, "created_at": conversation["created_at"],
        "original_request": source_request,
    }

    replay = client.post("/api/v1/bots", headers=headers, json=payload)
    assert replay.status_code == 200
    assert replay.json()["creation_source"] == {
        "conversation_id": conversation["id"], "message_id": "bot-source-user-message",
        "source_bot_id": source["id"], "sequence": 1, "created_at": conversation["created_at"],
    }
    changed = client.post("/api/v1/bots", headers=headers,
                          json={**payload, "source_message_id": "bot-source-assistant-message"})
    assert changed.status_code == 409

    invalid = client.post("/api/v1/bots", headers={"Idempotency-Key": "source-must-be-user"},
                          json={**payload, "name": "invalid-source", "source_message_id": "bot-source-assistant-message"})
    assert invalid.status_code == 404
    assert client.app.state.store.get_bot("invalid-source") is None

    other, _ = store.create_conversation(source["id"], "Another chat",
        idem_key="other-bot-source-conversation", request_hash="other-source-conversation")
    with store._tx() as db:
        store._insert_conversation_message(db, message_id="other-chat-user-message", conversation_id=other["id"],
            seq=1, run_id="", role="user", content="This request belongs to another chat.",
            created_at=other["created_at"])
    cross_chat = client.post("/api/v1/bots", headers={"Idempotency-Key": "source-must-be-same-chat"},
        json={**payload, "name": "cross-chat-source", "source_message_id": "other-chat-user-message"})
    assert cross_chat.status_code == 404
    assert client.app.state.store.get_bot("cross-chat-source") is None

    unpaired = client.post("/api/v1/bots", headers={"Idempotency-Key": "source-fields-must-pair"},
                           json={**payload, "name": "unpaired-source", "source_message_id": None})
    assert unpaired.status_code == 422
    legacy = client.post("/api/bots", json={**payload, "name": "legacy-source"})
    assert legacy.status_code == 422 and client.app.state.store.get_bot("legacy-source") is None


def test_bot_creation_records_only_selected_same_chat_user_context(client):
    source = make_bot(client, name="context-source-bot")
    store = client.app.state.store
    conversation, _ = store.create_conversation(
        source["id"], "Launch planning", idem_key="selected-context-chat", request_hash="selected-context-chat")
    messages = [
        ("context-private", "user", "Payroll notes are private and unrelated."),
        ("context-assistant", "assistant", "I suggest asking the launch team for updates."),
        ("context-constraint", "user", "Use public launch notes only; never contact stakeholders."),
        ("context-current-request", "user", "Track the launch checklist and report blockers."),
        ("context-oversized", "user", "x" * 20_000),
    ]
    with store._tx() as db:
        for sequence, (message_id, role, content) in enumerate(messages, 1):
            store._insert_conversation_message(db, message_id=message_id, conversation_id=conversation["id"],
                seq=sequence, run_id="", role=role, content=content, created_at=conversation["created_at"])

    instructions = ("Track the launch checklist and report blockers.\n\n"
                    "Owner-selected background context from this chat:\n"
                    "Message 3:\nUse public launch notes only; never contact stakeholders.")
    payload = {
        "name": "launch-context-monitor", "model": "mock/demo", "tools": [], "instructions": instructions,
        "source_conversation_id": conversation["id"], "source_message_id": "context-current-request",
        "source_context_message_ids": ["context-constraint"],
    }
    headers = {"Idempotency-Key": "create-launch-context-monitor"}
    created = client.post("/api/v1/bots", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    bot = store.get_bot("launch-context-monitor")
    assert bot is not None and bot.instructions == instructions
    assert bot.creation_source and bot.creation_source.message_id == "context-current-request"
    assert [source.model_dump() for source in bot.creation_context_sources] == [{
        "conversation_id": conversation["id"], "message_id": "context-constraint", "source_bot_id": source["id"],
        "sequence": 3, "created_at": conversation["created_at"],
        "original_request": "Use public launch notes only; never contact stakeholders.",
    }]
    assert "original_request" not in created.json()["creation_context_sources"][0]
    assert "Payroll notes" not in bot.instructions
    assert "context-assistant" not in str(bot.creation_context_sources)

    replay = client.post("/api/v1/bots", headers=headers, json=payload)
    assert replay.status_code == 200
    assert replay.json()["creation_context_sources"] == created.json()["creation_context_sources"]
    changed_context = client.post("/api/v1/bots", headers=headers,
        json={**payload, "source_context_message_ids": ["context-private"]})
    assert changed_context.status_code == 409
    assert store.get_bot("launch-context-monitor").instructions == instructions

    assistant_context = client.post("/api/v1/bots", headers={"Idempotency-Key": "assistant-context-rejected"},
        json={**payload, "name": "assistant-context", "source_context_message_ids": ["context-assistant"]})
    assert assistant_context.status_code == 404
    assert store.get_bot("assistant-context") is None

    duplicate = client.post("/api/v1/bots", headers={"Idempotency-Key": "duplicate-context-rejected"},
        json={**payload, "name": "duplicate-context", "source_context_message_ids": [
            "context-constraint", "context-constraint"]})
    assert duplicate.status_code == 422
    assert store.get_bot("duplicate-context") is None

    too_much = client.post("/api/v1/bots", headers={"Idempotency-Key": "oversized-context-rejected"},
        json={**payload, "name": "oversized-context", "source_context_message_ids": ["context-oversized"]})
    assert too_much.status_code == 422
    assert store.get_bot("oversized-context") is None

    other_conversation, _ = store.create_conversation(
        source["id"], "Another launch chat", idem_key="other-selected-context-chat", request_hash="other-selected-context-chat")
    with store._tx() as db:
        store._insert_conversation_message(db, message_id="other-chat-context", conversation_id=other_conversation["id"],
            seq=1, run_id="", role="user", content="Context from another chat.", created_at=other_conversation["created_at"])
    cross_chat = client.post("/api/v1/bots", headers={"Idempotency-Key": "cross-chat-context-rejected"},
        json={**payload, "name": "cross-chat-context", "source_context_message_ids": ["other-chat-context"]})
    assert cross_chat.status_code == 404
    assert store.get_bot("cross-chat-context") is None

    legacy = client.post("/api/bots", json={**payload, "name": "legacy-context"})
    assert legacy.status_code == 422 and store.get_bot("legacy-context") is None


def test_bot_display_name_is_durable_editable_and_keeps_legacy_address(client):
    created = client.post("/api/v1/bots", headers={"Idempotency-Key": "professional-bot-name"}, json={
        "name": "launch-checklist", "display_name": "  Launch Readiness Analyst  ",
        "model": "mock/demo", "tools": [],
    })
    assert created.status_code == 201, created.text
    bot = client.app.state.store.get_bot("launch-checklist")
    assert bot is not None
    assert bot.display_name == "Launch Readiness Analyst"
    assert created.json()["display_name"] == "Launch Readiness Analyst"
    assert client.get("/api/bots/launch-checklist").json()["name"] == "launch-checklist"

    updated = client.patch("/api/bots/launch-checklist", json={"display_name": "Release Operations Lead"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["display_name"] == "Release Operations Lead"
    assert client.app.state.store.get_bot("launch-checklist").display_name == "Release Operations Lead"

    legacy = make_bot(client, name="qa-review-bot")
    assert legacy["display_name"] == "QA Review Bot"
    assert client.patch("/api/bots/qa-review-bot", json={"display_name": "   "}).status_code == 422
    assert client.app.state.store.get_bot("qa-review-bot").display_name == "QA Review Bot"


def test_bot_pin_preference_persists_without_changing_execution_policy(client):
    bot = make_bot(client, name="pinned-reviewer")
    assert bot["pinned"] is False

    pinned = client.patch("/api/bots/pinned-reviewer", json={"pinned": True})
    assert pinned.status_code == 200, pinned.text
    assert pinned.json()["pinned"] is True
    saved = client.app.state.store.get_bot("pinned-reviewer")
    assert saved is not None and saved.pinned is True
    assert saved.tools == bot["tools"]
    assert saved.approval_mode.value == bot["approval_mode"]

    unpinned = client.patch("/api/bots/pinned-reviewer", json={"pinned": False})
    assert unpinned.status_code == 200 and unpinned.json()["pinned"] is False
    assert client.app.state.store.get_bot("pinned-reviewer").pinned is False


def test_workspace_schedule_control_is_durable_and_separate_from_bot_pause(client):
    bot = make_bot(client, name="schedule-control-bot", cron="0 9 * * 1", timezone="America/Vancouver")
    store = client.app.state.store
    live = store.create_run(Run(bot_id=bot["id"], prompt="already admitted", status=RunStatus.running))

    initial = client.get("/api/v1/schedules/control")
    assert initial.status_code == 200, initial.text
    assert initial.json()["paused"] is False and initial.json()["changed"] is False

    cursor = store.list_resource_changes()["cursor"]
    paused = client.put("/api/v1/schedules/control", json={"paused": True})
    assert paused.status_code == 200, paused.text
    assert paused.json()["paused"] is True and paused.json()["changed"] is True
    invalidations = store.list_resource_changes(cursor)["changes"]
    assert any(change["resource"] == "workspace" for change in invalidations)
    repeated = client.put("/api/v1/schedules/control", json={"paused": True})
    assert repeated.status_code == 200 and repeated.json()["changed"] is False
    assert repeated.json()["updated_at"] == paused.json()["updated_at"]

    row = next(row for row in client.get("/api/v1/schedules").json() if row["bot_id"] == bot["id"])
    assert row["paused"] is False                    # legacy per-Bot pause field remains unchanged
    assert row["workspace_paused"] is True
    assert row["effective_paused"] is True
    assert store.get_run(live.id).status is RunStatus.running  # pausing future schedules never stops a run

    assert client.patch("/api/bots/schedule-control-bot", json={"paused": True}).status_code == 200
    resumed = client.put("/api/v1/schedules/control", json={"paused": False})
    assert resumed.status_code == 200 and resumed.json()["paused"] is False
    row = next(row for row in client.get("/api/v1/schedules").json() if row["bot_id"] == bot["id"])
    assert row["paused"] is True and row["workspace_paused"] is False
    assert row["effective_paused"] is True              # a Bot-specific pause survives workspace resume


def test_named_workspace_coordinator_is_recoverable_and_clears_when_bot_is_deleted(tmp_path, monkeypatch):
    state = tmp_path / "coordinator-state"
    monkeypatch.setenv("HUTCH_STATE_DIR", str(state))
    with TestClient(create_app()) as client:
        assert client.get("/api/v1/workspace/coordinator").json() == {"coordinator": None}
        coordinator = make_bot(client, name="workspace-coordinator")
        specialist = make_bot(client, name="workspace-specialist")

        selected = client.put("/api/v1/workspace/coordinator", json={"bot_id": coordinator["id"]})
        assert selected.status_code == 200, selected.text
        assert selected.json() == {"coordinator": {"id": coordinator["id"], "name": "workspace-coordinator",
                                                     "display_name": "Workspace Coordinator"}}
        assert client.get("/api/v1/workspace/coordinator").json() == selected.json()
        bots = {bot["id"]: bot for bot in client.get("/api/bots").json()}
        assert bots[coordinator["id"]]["is_workspace_coordinator"] is True
        assert bots[specialist["id"]]["is_workspace_coordinator"] is False

        roster = client.get("/api/v1/workspace/specialists")
        assert roster.status_code == 200, roster.text
        assert roster.json()["coordinator_bot_id"] == coordinator["id"]
        assert roster.json()["specialist_bot_ids"] == []
        assert roster.json()["bots"] == [{"id": specialist["id"], "name": specialist["name"],
                                          "display_name": specialist["display_name"]}]
        cursor = client.app.state.store.list_resource_changes()["cursor"]
        saved_roster = client.put("/api/v1/workspace/specialists", json={"bot_ids": [specialist["id"]]})
        assert saved_roster.status_code == 200, saved_roster.text
        assert saved_roster.json()["specialist_bot_ids"] == [specialist["id"]]
        changes = client.app.state.store.list_resource_changes(cursor)["changes"]
        assert any(change["resource"] == "workspace" for change in changes)
        assert client.put("/api/v1/workspace/specialists", json={"bot_ids": [specialist["id"], specialist["id"]]}).status_code == 422
        assert client.put("/api/v1/workspace/specialists", json={"bot_ids": [coordinator["id"]]}).status_code == 409
        assert client.put("/api/v1/workspace/specialists", json={"bot_ids": ["missing-bot"]}).status_code == 404

        missing = client.put("/api/v1/workspace/coordinator", json={"bot_id": "missing-bot"})
        assert missing.status_code == 404
        assert client.get("/api/v1/workspace/coordinator").json() == selected.json()

    # The workspace role is durable state, not a browser-only preference.
    with TestClient(create_app()) as reopened:
        assert reopened.get("/api/v1/workspace/coordinator").json() == {
            "coordinator": {"id": coordinator["id"], "name": "workspace-coordinator",
                            "display_name": "Workspace Coordinator"}}
        assert reopened.get("/api/v1/workspace/specialists").json()["specialist_bot_ids"] == [specialist["id"]]
        promoted = reopened.put("/api/v1/workspace/coordinator", json={"bot_id": specialist["id"]})
        assert promoted.status_code == 200, promoted.text
        assert reopened.get("/api/v1/workspace/specialists").json()["specialist_bot_ids"] == []
        assert reopened.delete("/api/bots/workspace-specialist").status_code == 200
        assert reopened.get("/api/v1/workspace/coordinator").json() == {"coordinator": None}
        assert reopened.get("/api/v1/workspace/specialists").json()["specialist_bot_ids"] == []


def test_unavailable_external_runtime_can_be_migrated_to_builtin_only(client):
    store = client.app.state.store
    bot = store.create_bot(Bot(name="legacy-opencode", model="ollama/qwen3:4b",
                               runtime=RuntimeKind.opencode, tools=[]))

    migrated = client.patch(f"/api/bots/{bot.id}", json={"runtime": "builtin"})
    assert migrated.status_code == 200, migrated.text
    assert migrated.json()["runtime"] == "builtin"
    assert store.get_bot(bot.id).runtime is RuntimeKind.builtin

    legacy_pi = store.create_bot(Bot(name="legacy-pi", model="ollama/qwen3:4b",
                                     runtime=RuntimeKind.pi, tools=[]))
    pi_migrated = client.patch(f"/api/bots/{legacy_pi.id}", json={"runtime": "builtin"})
    assert pi_migrated.status_code == 200 and pi_migrated.json()["runtime"] == "builtin"
    assert store.get_bot(legacy_pi.id).runtime is RuntimeKind.builtin

    unsupported = client.patch(f"/api/bots/{bot.id}", json={"runtime": "pi"})
    assert unsupported.status_code == 422
    assert store.get_bot(bot.id).runtime is RuntimeKind.builtin

    no_route = store.create_bot(Bot(name="legacy-pi-no-route", runtime=RuntimeKind.pi,
                                    model="", tools=[]))
    rejected = client.patch(f"/api/bots/{no_route.id}", json={"runtime": "builtin"})
    assert rejected.status_code == 422 and "No model route is configured" in rejected.text
    assert store.get_bot(no_route.id).runtime is RuntimeKind.pi

    waiting = store.create_bot(Bot(name="legacy-opencode-waiting", model="ollama/qwen3:4b",
                                   runtime=RuntimeKind.opencode, tools=[]))
    create_owned_human_wait(store, waiting.id)
    blocked = client.patch(f"/api/bots/{waiting.id}", json={"runtime": "builtin"})
    assert blocked.status_code == 409 and "active run" in blocked.text
    assert store.get_bot(waiting.id).runtime is RuntimeKind.opencode
    with pytest.raises(ActiveRunConflict):
        store.upsert_bot(waiting.model_copy(update={"runtime": RuntimeKind.builtin}), require_no_active_runs=True)


def test_run_output_artifacts_are_paged_scoped_and_hash_checked(client, tmp_path):
    bot = make_bot(client, name="artifact-bot")
    store, config = client.app.state.store, client.app.state.config
    run = Run(bot_id=bot["id"], prompt="inspect a large result")
    store.create_run(run)
    artifact_dir = config.run_dir(bot["name"], run.id) / "artifacts"
    artifact_dir.mkdir(parents=True)
    filename = "001-read_file.txt"
    payload = b"full output that was too large for model context\n"
    (artifact_dir / filename).write_bytes(payload)
    store.append_event(Event(run_id=run.id, type=EventType.tool_result, data={
        "tool": "read_file", "ok": True, "output": "[clipped]", "chars": 5000,
        "artifact": f"artifacts/{filename}", "artifact_sha256": hashlib.sha256(payload).hexdigest(),
        "artifact_bytes": len(payload),
    }))
    second_filename = "002-read_file.txt"
    second_payload = b"a later output from the same tool\n"
    (artifact_dir / second_filename).write_bytes(second_payload)
    store.append_event(Event(run_id=run.id, type=EventType.tool_result, data={
        "tool": "read_file", "ok": True, "output": "[later clipped result]", "chars": 7000,
        "artifact": f"artifacts/{second_filename}",
        "artifact_sha256": hashlib.sha256(second_payload).hexdigest(),
        "artifact_bytes": len(second_payload),
    }))
    store.append_event(Event(run_id=run.id, type=EventType.tool_result, data={
        "tool": "read_file", "ok": True, "output": "[legacy clipped result]", "chars": 6000,
        "artifact": "artifacts/003-read_file.txt",
    }))
    generated_filename = "004-workspace_file.txt"
    generated_payload = b"invoice,total\nA-100,42\n"
    (artifact_dir / generated_filename).write_bytes(generated_payload)
    combined_output_filename = "005-write_file.txt"
    combined_output_payload = b"wrote report.csv (23 chars) plus clipped metadata"
    (artifact_dir / combined_output_filename).write_bytes(combined_output_payload)
    store.append_event(Event(run_id=run.id, type=EventType.tool_result, data={
        "tool": "write_file", "ok": True, "output": "[clipped write result]",
        "artifact": f"artifacts/{combined_output_filename}",
        "artifact_sha256": hashlib.sha256(combined_output_payload).hexdigest(),
        "artifact_bytes": len(combined_output_payload), "chars": 5000,
        "workspace_file": {
            "artifact": f"artifacts/{generated_filename}",
            "sha256": hashlib.sha256(generated_payload).hexdigest(),
            "bytes": len(generated_payload), "name": "report.csv", "path": "report.csv",
        },
    }))

    url = f"/api/v1/tasks/runs/{run.id}/artifacts"
    first = client.get(url, params={"limit": 1})
    assert first.status_code == 200, first.text
    page = first.json()
    assert page["next_offset"] == 1 and len(page["artifacts"]) == 1
    artifact = page["artifacts"][0]
    assert artifact["version"] > 0 and artifact["conversation_id"] == ""
    assert artifact["filename"] == filename and artifact["state"] == "available"
    assert artifact["sha256"] == hashlib.sha256(payload).hexdigest()

    later = client.get(url, params={"limit": 1, "offset": 1}).json()["artifacts"][0]
    assert later["state"] == "available" and later["filename"] == second_filename
    assert later["version"] > artifact["version"] and later["id"] != artifact["id"]
    assert client.get(later["download_url"]).content == second_payload

    old = client.get(url, params={"limit": 1, "offset": 2}).json()["artifacts"][0]
    assert old["state"] == "unverified" and old["download_url"] is None
    combined_output = client.get(url, params={"limit": 1, "offset": 3}).json()["artifacts"][0]
    assert combined_output["kind"] == "tool_output" and combined_output["id"].endswith(":tool_output")
    assert client.get(combined_output["download_url"]).content == combined_output_payload
    generated = client.get(url, params={"limit": 1, "offset": 4}).json()["artifacts"][0]
    assert generated["kind"] == "workspace_file" and generated["filename"] == "report.csv"
    assert generated["id"].endswith(":workspace_file")
    assert generated["state"] == "available" and generated["sha256"] == hashlib.sha256(generated_payload).hexdigest()
    generated_download = client.get(generated["download_url"])
    assert generated_download.content == generated_payload
    assert generated_download.headers["content-disposition"] == 'attachment; filename="report.csv"'
    assert generated_download.headers["x-hutch-artifact-verified"] == "sha256"
    (artifact_dir / generated_filename).write_bytes(generated_payload.replace(b"A-100", b"A-101"))
    tampered_generated = client.get(generated["download_url"])
    assert tampered_generated.status_code == 409 and "SHA-256" in tampered_generated.text
    assert client.get(url + "/not-a-generated-name").status_code == 404

    download = client.get(artifact["download_url"])
    assert download.status_code == 200 and download.content == payload
    assert download.headers["x-hutch-artifact-verified"] == "sha256"
    assert download.headers["etag"] == f'"{hashlib.sha256(payload).hexdigest()}"'

    path = artifact_dir / filename
    path.write_bytes(payload.replace(b"full", b"evil", 1))
    changed = client.get(artifact["download_url"])
    assert changed.status_code == 409 and "SHA-256" in changed.text
    path.unlink()
    outside = tmp_path / "outside.txt"
    outside.write_bytes(payload)
    path.symlink_to(outside)
    assert client.get(artifact["download_url"]).status_code == 404
    path.unlink()
    safe_dir = artifact_dir.with_name("artifacts-safe")
    artifact_dir.rename(safe_dir)
    artifact_dir.symlink_to(tmp_path, target_is_directory=True)
    assert client.get(artifact["download_url"]).status_code == 404
    artifact_dir.unlink()
    safe_dir.rename(artifact_dir)


def test_conversation_artifacts_are_scoped_and_paged(client):
    bot = make_bot(client, name="artifact-owner", paused=True)
    other_bot = make_bot(client, name="other-artifact-owner", paused=True)
    store, config = client.app.state.store, client.app.state.config

    def add_conversation(bot_record, title, key, contents):
        conversation, _ = store.create_conversation(
            bot_record["id"], title, idem_key=f"conversation-{key}", request_hash=f"request-{key}")
        prompt = f"run {key}"
        run = Run(bot_id=bot_record["id"], prompt=prompt, conversation_id=conversation["id"],
                  status=RunStatus.succeeded)
        store.create_run(run)
        with store._tx() as db:
            db.execute("INSERT INTO conversation_runs (conversation_id, run_id, attached_at) VALUES (?, ?, ?)",
                       (conversation["id"], run.id, run.created_at))
        run_id = run.id
        artifact_dir = config.run_dir(bot_record["name"], run_id) / "artifacts"
        artifact_dir.mkdir(parents=True)
        for index, (kind, name, payload) in enumerate(contents, 1):
            stored = f"{index:03d}-{key}.txt"
            (artifact_dir / stored).write_bytes(payload)
            data = {"tool": "write_file" if kind == "workspace_file" else "read_file",
                    "output": "saved", "artifact": f"artifacts/{stored}",
                    "artifact_sha256": hashlib.sha256(payload).hexdigest(),
                    "artifact_bytes": len(payload), "chars": len(payload)}
            if kind == "workspace_file":
                data["workspace_file"] = {"artifact": f"artifacts/{stored}",
                                           "sha256": hashlib.sha256(payload).hexdigest(),
                                           "bytes": len(payload), "name": name, "path": name}
            store.append_event(Event(run_id=run_id, type=EventType.tool_result, data=data))
        return conversation, run_id

    conversation, own_run = add_conversation(bot, "Project notes", "own", [
        ("tool_output", "output", b"saved tool result"),
        ("workspace_file", "summary.txt", b"created file"),
    ])
    _, sibling_run = add_conversation(bot, "Private chat", "sibling", [
        ("workspace_file", "private.txt", b"another conversation"),
    ])
    add_conversation(other_bot, "Other bot", "other", [
        ("workspace_file", "other.txt", b"another bot's file"),
    ])

    url = f"/api/v1/conversations/{conversation['id']}/artifacts"
    page = client.get(url, params={"limit": 1})
    assert page.status_code == 200, page.text
    first_page = page.json()
    assert first_page["next_cursor"] and len(first_page["artifacts"]) == 1
    assert first_page["artifacts"][0]["kind"] == "tool_output"

    # A new artifact inserted while browsing sorts before the current keyset boundary;
    # it must not shift older pages or cause a duplicate/skip in this traversal.
    late_filename = "999-late.txt"
    late_payload = b"added after the first page"
    late_dir = config.run_dir(bot["name"], own_run) / "artifacts"
    (late_dir / late_filename).write_bytes(late_payload)
    store.append_event(Event(run_id=own_run, type=EventType.tool_result, data={
        "tool": "write_file", "output": "saved", "artifact": f"artifacts/{late_filename}",
        "artifact_sha256": hashlib.sha256(late_payload).hexdigest(),
        "artifact_bytes": len(late_payload), "chars": len(late_payload),
    }))

    items = first_page["artifacts"]
    second_page = client.get(url, params={"limit": 1, "cursor": first_page["next_cursor"]}).json()
    assert second_page["artifacts"][0]["kind"] == "workspace_file"
    assert second_page["artifacts"][0]["version"] == items[0]["version"]
    assert second_page["next_cursor"]
    items += second_page["artifacts"]
    third_page = client.get(url, params={"limit": 1, "cursor": second_page["next_cursor"]}).json()
    assert third_page["next_cursor"] is None
    items += third_page["artifacts"]
    assert len(items) == 3, [(item["id"], item["kind"], item["filename"]) for item in items]
    assert late_filename not in {item["filename"] for item in items}
    assert {item["run_id"] for item in items} == {own_run}
    assert {item["kind"] for item in items} == {"tool_output", "workspace_file"}
    generated = next(item for item in items if item["kind"] == "workspace_file")
    assert generated["filename"] == "summary.txt" and generated["state"] == "available"
    assert client.get(generated["download_url"]).content == b"created file"
    assert client.get(url, params={"limit": 101}).status_code == 422
    assert client.get(url, params={"cursor": "not-a-valid-cursor"}).status_code == 422
    assert client.get("/api/v1/conversations/conv_missing/artifacts").status_code == 404
    assert client.get(f"/api/v1/conversations/{conversation['id']}/artifacts",
                      params={"limit": 100}).json()["artifacts"]
    assert all(item["run_id"] != sibling_run for item in items)


def test_conversation_artifact_share_is_explicit_cross_bot_idempotent_and_revocable(client, tmp_path):
    source_bot = make_bot(client, name="share-source", paused=True)
    target_bot = make_bot(client, name="share-target", paused=True)
    store, config = client.app.state.store, client.app.state.config
    source, _ = store.create_conversation(source_bot["id"], "Private source", idem_key="share-source-conv",
                                          request_hash="share-source-request")
    target, _ = store.create_conversation(target_bot["id"], "Selected recipient", idem_key="share-target-conv",
                                          request_hash="share-target-request")
    run = Run(bot_id=source_bot["id"], prompt="build report", conversation_id=source["id"],
              status=RunStatus.succeeded)
    store.create_run(run)
    with store._tx() as db:
        db.execute("INSERT INTO conversation_runs (conversation_id, run_id, attached_at) VALUES (?, ?, ?)",
                   (source["id"], run.id, run.created_at))
    payload = b"approved report contents\n"
    filename = "001-report.txt"
    artifact_dir = config.run_dir(source_bot["name"], run.id) / "artifacts"
    artifact_dir.mkdir(parents=True)
    path = artifact_dir / filename
    path.write_bytes(payload)
    store.append_event(Event(run_id=run.id, type=EventType.tool_result, data={
        "tool": "write_file", "output": "report saved", "chars": len(payload),
        "artifact": f"artifacts/{filename}", "artifact_sha256": hashlib.sha256(payload).hexdigest(),
        "artifact_bytes": len(payload),
        "workspace_file": {"artifact": f"artifacts/{filename}", "sha256": hashlib.sha256(payload).hexdigest(),
                           "bytes": len(payload), "name": "report.txt", "path": "report.txt"},
    }))

    source_url = f"/api/v1/conversations/{source['id']}/artifacts"
    target_url = f"/api/v1/conversations/{target['id']}/artifacts"
    assert len(client.get(source_url).json()["artifacts"]) == 2
    assert client.get(target_url).json()["artifacts"] == []
    share_url = f"/api/v1/conversations/{target['id']}/artifact-shares"
    body = {"source_run_id": run.id, "source_version": 1, "kind": "workspace_file"}
    changes_before_share = store.list_resource_changes()["cursor"]
    assert client.post(share_url, json=body).status_code == 428

    headers = {"Idempotency-Key": "explicit-report-share"}
    created = client.post(share_url, json=body, headers=headers)
    assert created.status_code == 201, created.text
    share = created.json()
    assert share["target_conversation_id"] == target["id"]
    assert share["source_run_id"] == run.id and share["source_version"] == 1
    assert share["kind"] == "workspace_file" and share["actor"] == "operator"
    assert share["revoked_at"] is None
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        with store._tx() as db:
            db.execute("UPDATE conversation_artifact_shares SET source_run_id = 'forged' WHERE id = ?",
                       (share["id"],))
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        with store._tx() as db:
            db.execute("DELETE FROM conversation_artifact_shares WHERE id = ?", (share["id"],))

    replay = client.post(share_url, json=body, headers=headers)
    assert replay.status_code == 200 and replay.json()["id"] == share["id"]
    assert client.post(share_url, json={**body, "kind": "tool_output"}, headers=headers).status_code == 409
    duplicate = client.post(share_url, json=body, headers={"Idempotency-Key": "another-share-key"})
    assert duplicate.status_code == 200 and duplicate.json()["id"] == share["id"]
    share_changes = [item for item in store.list_resource_changes(changes_before_share)["changes"]
                     if item["resource"] == "conversations"]
    target_share_changes = [item for item in share_changes if item["resource_id"] == target["id"]]
    source_share_changes = [item for item in share_changes if item["resource_id"] == source["id"]]
    assert sum(item["operation"] == "created" for item in target_share_changes) == 1
    assert sum(item["operation"] == "updated" for item in source_share_changes) == 1

    source_items = client.get(source_url).json()["artifacts"]
    source_workspace_file = next(item for item in source_items if item["kind"] == "workspace_file")
    assert source_workspace_file["shared_with"] == [{
        "id": share["id"], "target_conversation_id": target["id"],
        "target_conversation_title": "Selected recipient", "created_at": share["created_at"],
    }]

    shared = client.get(target_url).json()["artifacts"]
    assert len(shared) == 1
    assert shared[0]["share_id"] == share["id"] and shared[0]["shared_from"] == "Private source"
    assert shared[0]["run_id"] == run.id and shared[0]["filename"] == "report.txt"
    shared_url = shared[0]["download_url"]
    assert f"/conversations/{target['id']}/artifact-shares/{share['id']}/content" in shared_url
    assert client.get(shared_url).content == payload
    assert client.get(f"/api/v1/conversations/{source['id']}/artifact-shares/{share['id']}/content").status_code == 404
    assert client.get(f"/api/v1/conversations/{target['id']}").json()["messages"] == []
    assert client.post(f"/api/v1/conversations/{source['id']}/artifact-shares", json=body,
                       headers={"Idempotency-Key": "share-to-source"}).status_code == 409

    revoke_url = f"/api/v1/conversations/{target['id']}/artifact-shares/{share['id']}"
    revoke_headers = {"Idempotency-Key": "revoke-report-share"}
    revoked = client.delete(revoke_url, headers=revoke_headers)
    assert revoked.status_code == 200 and revoked.json()["revoked_at"]
    revoke_changes = [item for item in store.list_resource_changes(changes_before_share)["changes"]
                      if item["resource"] == "conversations"]
    target_revoke_changes = [item for item in revoke_changes if item["resource_id"] == target["id"]]
    source_revoke_changes = [item for item in revoke_changes if item["resource_id"] == source["id"]]
    assert sum(item["operation"] == "updated" for item in target_revoke_changes) == 1
    assert sum(item["operation"] == "updated" for item in source_revoke_changes) == 2
    assert client.get(target_url).json()["artifacts"] == []
    revoke_replay = client.delete(revoke_url, headers=revoke_headers)
    assert revoke_replay.status_code == 200 and revoke_replay.json()["id"] == share["id"]
    assert client.get(shared_url).status_code == 404, "revocation must stop later downloads through the grant"
    assert client.get(f"/api/v1/tasks/runs/{run.id}/artifacts/{filename}").content == payload
    source_items = client.get(source_url).json()["artifacts"]
    assert next(item for item in source_items if item["kind"] == "workspace_file")["shared_with"] == []

    renewed = client.post(share_url, json=body, headers={"Idempotency-Key": "share-again"})
    assert renewed.status_code == 201 and renewed.json()["id"] != share["id"]
    assert len(client.get(target_url).json()["artifacts"]) == 1
    source_items = client.get(source_url).json()["artifacts"]
    assert next(item for item in source_items if item["kind"] == "workspace_file")["shared_with"][0]["id"] == renewed.json()["id"]
    rows = store._db.execute("SELECT id, revoked_at FROM conversation_artifact_shares ORDER BY created_at, id").fetchall()
    assert len(rows) == 2 and rows[0]["id"] == share["id"] and rows[0]["revoked_at"]


def test_only_verified_artifacts_can_be_shared_and_share_history_is_immutable(client):
    bot = make_bot(client, name="share-verification", paused=True)
    store = client.app.state.store
    source, _ = store.create_conversation(bot["id"], "Source", idem_key="unverified-source",
                                          request_hash="unverified-source-request")
    target, _ = store.create_conversation(bot["id"], "Target", idem_key="unverified-target",
                                          request_hash="unverified-target-request")
    run = Run(bot_id=bot["id"], prompt="old output", conversation_id=source["id"], status=RunStatus.succeeded)
    store.create_run(run)
    store.append_event(Event(run_id=run.id, type=EventType.tool_result, data={
        "tool": "read_file", "output": "old", "artifact": "artifacts/001-old.txt", "chars": 100,
    }))
    url = f"/api/v1/conversations/{target['id']}/artifact-shares"
    response = client.post(url, json={"source_run_id": run.id, "source_version": 1, "kind": "tool_output"},
                           headers={"Idempotency-Key": "reject-unverified"})
    assert response.status_code == 409 and "verified" in response.text
    assert store._db.execute("SELECT COUNT(*) FROM conversation_artifact_shares").fetchone()[0] == 0


def test_artifact_bytes_are_checked_again_when_sharing_and_downloading(client, tmp_path):
    bot = make_bot(client, name="share-integrity", paused=True)
    store, config = client.app.state.store, client.app.state.config
    source, _ = store.create_conversation(bot["id"], "Integrity source", idem_key="integrity-source",
                                          request_hash="integrity-source-request")
    target, _ = store.create_conversation(bot["id"], "Integrity target", idem_key="integrity-target",
                                          request_hash="integrity-target-request")
    run = Run(bot_id=bot["id"], prompt="save verified output", conversation_id=source["id"],
              status=RunStatus.succeeded)
    store.create_run(run)
    with store._tx() as db:
        db.execute("INSERT INTO conversation_runs (conversation_id, run_id, attached_at) VALUES (?, ?, ?)",
                   (source["id"], run.id, run.created_at))
    payload = b"verified bytes"
    filename = "001-report.txt"
    artifact_dir = config.run_dir(bot["name"], run.id) / "artifacts"
    artifact_dir.mkdir(parents=True)
    path = artifact_dir / filename
    path.write_bytes(payload)
    store.append_event(Event(run_id=run.id, type=EventType.tool_result, data={
        "tool": "read_file", "output": "saved", "chars": len(payload),
        "artifact": f"artifacts/{filename}", "artifact_sha256": hashlib.sha256(payload).hexdigest(),
        "artifact_bytes": len(payload),
    }))
    body = {"source_run_id": run.id, "source_version": 1, "kind": "tool_output"}
    url = f"/api/v1/conversations/{target['id']}/artifact-shares"
    headers = {"Idempotency-Key": "integrity-share"}
    path.write_bytes(b"changed bytes")
    failed = client.post(url, json=body, headers=headers)
    assert failed.status_code == 409 and "do not match" in failed.text
    assert store._db.execute("SELECT COUNT(*) FROM conversation_artifact_shares").fetchone()[0] == 0

    path.write_bytes(payload)
    created = client.post(url, json=body, headers=headers)
    assert created.status_code == 201, created.text
    shared = client.get(f"/api/v1/conversations/{target['id']}/artifacts").json()["artifacts"][0]
    assert client.get(shared["download_url"]).content == payload
    path.write_bytes(b"tampered bytes")
    replay = client.post(url, json=body, headers=headers)
    assert replay.status_code == 200 and replay.json()["id"] == created.json()["id"]
    checked = client.get(shared["download_url"])
    assert checked.status_code == 409 and "SHA-256" in checked.text


def test_bot_crud_and_validation(client):
    bot = make_bot(client, local_browser_handoff=True)
    assert bot["name"] == "api-bot"
    assert bot["local_browser_handoff"] is True
    assert bot["tools"] == ["read_file", "list_files", "write_file", "remember", "recall", "shell"]

    # duplicate
    assert client.post("/api/bots", json={"name": "api-bot"}).status_code == 409
    # bad slug
    assert client.post("/api/bots", json={"name": "Bad!"}).status_code == 422
    # unknown tool
    assert client.post("/api/bots", json={"name": "x-bot", "tools": ["laser"]}).status_code == 422

    detail = client.get("/api/bots/api-bot").json()
    assert detail["recent_runs"] == []

    patched = client.patch("/api/bots/api-bot", json={"paused": True, "cron": "0 9 * * 1"}).json()
    assert patched["paused"] is True and patched["schedule"]["cron"] == "0 9 * * 1"
    tools = client.patch("/api/bots/api-bot", json={"tools": ["files", "memory", "delegate_task", "delegate_task"]})
    assert tools.status_code == 200, tools.text
    assert tools.json()["tools"] == ["read_file", "list_files", "write_file", "remember", "recall", "delegate_task"]
    unknown_patch = client.patch("/api/bots/api-bot", json={"tools": ["laser"]})
    assert unknown_patch.status_code == 422
    assert "delegate_task" in client.get("/api/bots/api-bot").json()["tools"]
    local = client.patch("/api/bots/api-bot", json={"local_browser_handoff": True}).json()
    assert local["local_browser_handoff"] is True
    disabled = client.patch("/api/bots/api-bot", json={"local_browser_handoff": False}).json()
    assert disabled["local_browser_handoff"] is False

    assert client.delete("/api/bots/api-bot").status_code == 200
    assert client.get("/api/bots/api-bot").status_code == 404


def test_bot_create_requires_a_real_route_outside_the_test_harness(client, monkeypatch):
    monkeypatch.delenv("HUTCH_TESTING", raising=False)
    missing = client.post("/api/bots", json={"name": "unconfigured"})
    assert missing.status_code == 422 and "No model route is configured" in missing.json()["detail"]
    retired = client.post("/api/bots", json={"name": "legacy-mock", "model": "mock/demo"})
    assert retired.status_code == 422 and "test-only" in retired.json()["detail"]
    assert client.get("/api/bots").json() == []


def test_v1_bot_creation_is_atomic_idempotent_and_does_not_start_a_run(client):
    body = {
        "name": "guided-researcher",
        "model": "mock/demo",
        "tools": ["files"],
        "description": "Research briefs",
        "instructions": "Prepare a concise research brief.",
        "workspace_mode": "managed",
        "approval_mode": "ask",
        "inference_mode": "hybrid",
    }
    url = "/api/v1/bots"
    assert client.post(url, json=body).status_code == 428
    headers = {"Idempotency-Key": "create-guided-researcher"}

    created = client.post(url, json=body, headers=headers)
    assert created.status_code == 201, created.text
    bot = created.json()
    assert bot["name"] == "guided-researcher"
    assert bot["description"] == "Research briefs"
    assert bot["workspace_mode"] == "managed"
    assert set(bot["tools"]) == {"list_files", "read_file", "write_file"}
    assert client.get("/api/v1/tasks/runs?limit=10").json() == []

    replay = client.post(url, json=body, headers=headers)
    assert replay.status_code == 200 and replay.json()["id"] == bot["id"]
    assert len(client.get("/api/v1/bots").json()) == 1

    changed = client.post(url, json={**body, "instructions": "Different draft."}, headers=headers)
    assert changed.status_code == 409 and "Idempotency-Key" in changed.text
    duplicate_name = client.post(url, json=body, headers={"Idempotency-Key": "create-again"})
    assert duplicate_name.status_code == 409


def test_v1_bot_creation_is_atomic_across_store_connections(client):
    config = client.app.state.config
    first_store = client.app.state.store
    second_store = Store(config)
    barrier = Barrier(2)
    key = "concurrent-bot-create"
    digest = "canonical-bot-request"

    def create(store):
        bot = Bot(name="same-concurrent-bot", model="ollama/fake:1b", tools=[])
        barrier.wait()
        return store.create_bot_idempotent(bot, idem_key=key, request_hash=digest)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(create, (first_store, second_store)))
        assert len({bot.id for bot, _created in results}) == 1
        assert sorted(created for _bot, created in results) == [False, True]
        assert len(first_store.list_bots()) == 1
        replay, created = first_store.create_bot_idempotent(
            Bot(name="same-concurrent-bot", model="ollama/fake:1b", tools=[]),
            idem_key=key, request_hash=digest)
        assert replay.id == results[0][0].id and not created
        with pytest.raises(ValueError, match="different request"):
            first_store.create_bot_idempotent(Bot(name="same-concurrent-bot"), idem_key=key,
                                              request_hash="changed")
    finally:
        second_store.close()


def test_v1_model_route_picker_returns_advisory_choices_without_creating_state(client):
    routes = client.get("/api/v1/model-routes?inference_mode=hybrid")
    assert routes.status_code == 200, routes.text
    assert isinstance(routes.json(), list)
    assert all({"spec", "state", "label", "group"} <= set(route) for route in routes.json())
    assert not any(route["spec"].startswith("mock/") and route["state"] == "ready"
                   for route in routes.json())
    assert client.get("/api/v1/bots").json() == []
    assert client.get("/api/v1/tasks/runs?limit=10").json() == []


def test_workspace_model_defaults_seed_only_new_bots_and_explicit_routes_win(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key-never-sent-to-a-provider")
    existing = make_bot(client, name="already-configured", model="openai/gpt-4o-mini")

    before = client.get("/api/v1/preferences/model-defaults")
    assert before.status_code == 200, before.text
    assert before.json() == {"model": "", "inference_mode": "hybrid", "configured": False}

    saved = client.put("/api/v1/preferences/model-defaults", json={
        "model": "openai/gpt-4o-mini", "inference_mode": "hybrid",
    })
    assert saved.status_code == 200, saved.text
    assert saved.json() == {"model": "openai/gpt-4o-mini", "inference_mode": "hybrid", "configured": True}
    assert client.app.state.store.get_bot(existing["id"]).model == "openai/gpt-4o-mini"

    inherited = client.post("/api/v1/bots", headers={"Idempotency-Key": "workspace-default-bot"}, json={
        "name": "workspace-default-bot", "tools": [],
    })
    assert inherited.status_code == 201, inherited.text
    assert inherited.json()["model"] == "openai/gpt-4o-mini"
    assert inherited.json()["inference_mode"] == "hybrid"

    explicit = client.post("/api/v1/bots", headers={"Idempotency-Key": "explicit-model-bot"}, json={
        "name": "explicit-model-bot", "model": "mock/test", "inference_mode": "hybrid", "tools": [],
    })
    assert explicit.status_code == 201, explicit.text
    assert explicit.json()["model"] == "mock/test"
    assert explicit.json()["inference_mode"] == "hybrid"


def test_workspace_model_defaults_reject_unavailable_routes_and_can_be_cleared(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key-never-sent-to-a-provider")
    saved = client.put("/api/v1/preferences/model-defaults", json={
        "model": "openai/gpt-4o-mini", "inference_mode": "hybrid",
    })
    assert saved.status_code == 200, saved.text

    rejected = client.put("/api/v1/preferences/model-defaults", json={
        "model": "provider-that-does-not-exist/model", "inference_mode": "hybrid",
    })
    assert rejected.status_code == 422
    assert client.get("/api/v1/preferences/model-defaults").json()["model"] == "openai/gpt-4o-mini"

    mode_mismatch = client.put("/api/v1/preferences/model-defaults", json={
        "model": "openai/gpt-4o-mini", "inference_mode": "local",
    })
    assert mode_mismatch.status_code == 422
    assert client.get("/api/v1/preferences/model-defaults").json()["inference_mode"] == "hybrid"

    cleared = client.put("/api/v1/preferences/model-defaults", json={"model": "", "inference_mode": "hybrid"})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json() == {"model": "", "inference_mode": "hybrid", "configured": False}

    mode_only = client.put("/api/v1/preferences/model-defaults", json={"model": "", "inference_mode": "local"})
    assert mode_only.status_code == 200, mode_only.text
    # Isolate inference-mode inheritance from provider availability; no model call occurs.
    monkeypatch.setattr("hutch.modelchoices.validate_override", lambda config, store, bot, spec: spec)
    created = client.post("/api/v1/bots", headers={"Idempotency-Key": "workspace-mode-only-bot"}, json={
        "name": "workspace-mode-only-bot", "model": "ollama/llama3.1", "tools": [],
    })
    assert created.status_code == 201, created.text
    assert created.json()["model"] == "ollama/llama3.1"
    assert created.json()["inference_mode"] == "local"
    assert [bot["name"] for bot in client.get("/api/v1/bots").json()] == ["workspace-mode-only-bot"]


def test_bot_limits_are_editable_and_validated(client):
    make_bot(client)
    saved = client.patch("/api/bots/api-bot", json={"limits": {
        "max_steps": 12, "timeout_seconds": 300, "daily_token_cap": 5000,
        "max_turn_tokens": 1500, "max_cost_usd": 0.75, "daily_cost_cap_usd": 4.25,
    }})
    assert saved.status_code == 200, saved.text
    assert saved.json()["limits"] == {
        "max_steps": 12, "timeout_seconds": 300, "daily_token_cap": 5000,
        "max_turn_tokens": 1500, "max_cost_usd": 0.75, "daily_cost_cap_usd": 4.25,
    }
    assert client.patch("/api/bots/api-bot", json={"limits": {"max_steps": 0}}).status_code == 422
    assert client.patch("/api/bots/api-bot", json={"limits": {"max_cost_usd": -0.01}}).status_code == 422


def test_bot_setup_yaml_preview_is_validated_sanitized_and_never_persists(client):
    import yaml

    body = {
        "name": "yaml-preview-bot", "display_name": "Avery · Project Reporter",
        "description": "Prepare project updates", "instructions": "Summarize confirmed facts only.",
        "model": "mock/demo", "tools": ["files"], "inference_mode": "hybrid",
        "workspace_mode": "managed", "approval_mode": "ask", "risk_tier": "supervised",
        "local_browser_handoff": True,
        "limits": {"max_steps": 12, "timeout_seconds": 300, "daily_token_cap": 5000,
                   "max_turn_tokens": 1000, "max_cost_usd": 0.25, "daily_cost_cap_usd": 1.5},
        "cron": None, "schedule_prompt": "",
        "base_url": "https://private.example/v1?token=must-not-export",
        "source_conversation_id": "private-conversation-id",
        "source_message_id": "private-message-id",
    }

    response = client.post("/api/v1/bot-configs/preview", json=body)

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    document = yaml.safe_load(response.json()["yaml"])
    assert document["apiVersion"] == "hutch.ai/v1"
    assert document["kind"] == "BotConfig"
    assert document["spec"]["name"] == "yaml-preview-bot"
    assert document["spec"]["instructions"] == body["instructions"]
    assert document["spec"]["limits"] == body["limits"]
    assert document["spec"]["tools"] == ["files"]
    assert document["spec"]["local_browser_handoff"] is True
    serialized = response.text
    assert "must-not-export" not in serialized
    assert "private-conversation-id" not in serialized
    assert "private-message-id" not in serialized
    assert "base_url" not in document["spec"] and "workdir" not in document["spec"]
    assert client.get("/api/bots").json() == []
    assert client.app.state.store.list_runs(limit=10) == []


def test_bot_setup_yaml_preview_rejects_invalid_configuration_without_saving(client):
    response = client.post("/api/v1/bot-configs/preview", json={
        "name": "Invalid Bot!", "model": "mock/demo", "tools": ["not-a-tool"],
    })
    assert response.status_code == 422
    assert client.get("/api/bots").json() == []


def test_bot_setup_yaml_import_accepts_only_exported_safe_draft_and_never_persists(client):
    body = {
        "name": "yaml-round-trip-bot", "display_name": "Jordan Reed · Project Reporter",
        "description": "Summarize updates", "instructions": "Prepare a short weekly summary.",
        "model": "mock/demo", "tools": ["read_file"], "inference_mode": "hybrid",
        "workspace_mode": "managed", "approval_mode": "ask", "risk_tier": "supervised",
        "local_browser_handoff": False,
        "limits": {"max_steps": 11, "timeout_seconds": 240, "daily_token_cap": 4000,
                   "max_turn_tokens": 800, "max_cost_usd": 0.1, "daily_cost_cap_usd": 0.9},
        "cron": "0 9 * * 1", "timezone": "America/Vancouver", "catch_up": "skip",
        "schedule_prompt": "Prepare the Monday summary.",
    }
    preview = client.post("/api/v1/bot-configs/preview", json=body)
    assert preview.status_code == 200, preview.text

    imported = client.post("/api/v1/bot-configs/import", json={"yaml": preview.json()["yaml"]})

    assert imported.status_code == 200, imported.text
    assert imported.headers["cache-control"] == "no-store"
    assert imported.json()["saved"] is False
    config = imported.json()["configuration"]
    assert config["name"] == body["name"]
    assert config["display_name"] == body["display_name"]
    assert config["instructions"] == body["instructions"]
    assert config["model"] == body["model"]
    assert config["tools"] == body["tools"]
    assert config["workspace_mode"] == body["workspace_mode"]
    assert config["timezone"] == body["timezone"] and config["catch_up"] == body["catch_up"]
    assert config["limits"] == body["limits"]
    assert "base_url" not in config and "workdir" not in config
    assert "source_conversation_id" not in config
    assert client.get("/api/bots").json() == []
    assert client.app.state.store.list_runs(limit=10) == []


def test_bot_setup_yaml_import_can_review_route_before_local_credentials_exist(client, monkeypatch):
    import yaml

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    document = {
        "apiVersion": "hutch.ai/v1", "kind": "BotConfig", "spec": {
            "name": "portable-import-bot", "display_name": "Portable Import Bot",
            "description": "Review a project update", "instructions": "Summarize the update.",
            "model": "openai/gpt-4o-mini", "inference_mode": "hybrid", "tools": ["read_file"],
            "memory_enabled": False, "workspace_mode": "managed", "approval_mode": "ask",
            "risk_tier": "supervised", "local_browser_handoff": False,
            "limits": {"max_steps": 10, "timeout_seconds": 120, "daily_token_cap": 3000,
                       "max_turn_tokens": 500, "max_cost_usd": 0, "daily_cost_cap_usd": 0},
        },
    }

    imported = client.post("/api/v1/bot-configs/import", json={"yaml": yaml.safe_dump(document)})

    assert imported.status_code == 200, imported.text
    assert imported.json()["configuration"]["model"] == "openai/gpt-4o-mini"
    assert imported.json()["saved"] is False
    create = client.post("/api/v1/bots", json=imported.json()["configuration"],
                         headers={"Idempotency-Key": "import-unconfigured-route"})
    assert create.status_code == 422 and "API key" in create.json()["detail"]
    assert client.get("/api/bots").json() == []
    assert client.app.state.store.list_runs(limit=10) == []


def test_bot_setup_yaml_import_rejects_unsafe_or_unsupported_documents(client):
    valid_spec = {
        "name": "imported-safe-bot", "display_name": "Avery Lee · Project Reviewer",
        "description": "Review project notes", "instructions": "Review the provided notes.",
        "model": "mock/demo", "inference_mode": "hybrid", "tools": ["read_file"],
        "memory_enabled": False, "workspace_mode": "managed", "approval_mode": "ask",
        "risk_tier": "supervised", "local_browser_handoff": False,
        "limits": {"max_steps": 10, "timeout_seconds": 120, "daily_token_cap": 3000,
                   "max_turn_tokens": 500, "max_cost_usd": 0, "daily_cost_cap_usd": 0},
    }
    import yaml

    document = {"apiVersion": "hutch.ai/v1", "kind": "BotConfig", "spec": valid_spec}
    valid_yaml = yaml.safe_dump(document, sort_keys=False)
    inputs = [
        valid_yaml.replace("apiVersion: hutch.ai/v1", "apiVersion: hutch.ai/v2"),
        yaml.safe_dump({**document, "spec": {**valid_spec, "workdir": "/home/user/Downloads"}}),
        yaml.safe_dump({**document, "spec": {**valid_spec, "approval_mode": "auto"}}),
        yaml.safe_dump({**document, "spec": {**valid_spec, "shell_network": True}}),
        "!!python/object/apply:os.system ['touch /tmp/should-not-exist']",
        "defaults: &defaults {name: imported-safe-bot}\napiVersion: hutch.ai/v1\nkind: BotConfig\nspec: *defaults\n",
        "apiVersion: hutch.ai/v1\napiVersion: hutch.ai/v1\nkind: BotConfig\nspec: {}\n",
        "x" * 65_537,
    ]

    for index, text in enumerate(inputs):
        response = client.post("/api/v1/bot-configs/import", json={"yaml": text})
        assert response.status_code == 422, (index, response.status_code, response.text)
    assert client.get("/api/bots").json() == []
    assert client.app.state.store.list_runs(limit=10) == []


def test_templates_endpoint(client):
    templates = client.get("/api/bots/templates").json()
    names = {t["name"] for t in templates}
    assert {"research-briefing", "repo-sweeper", "tidy-downloads"} <= names


def test_spa_connections_api_never_echoes_key_and_validates_allowance(client):
    created = client.post("/api/connections", json={
        "template": "custom-openai", "name": "fixture-endpoint", "base_url": "https://example.invalid/v1",
    })
    assert created.status_code == 201, created.text
    assert created.json() == {"added": "fixture-endpoint"}

    listing = client.get("/api/connections").json()
    connection = next(row for row in listing["connections"] if row["name"] == "fixture-endpoint")
    assert connection["has_key"] is False
    assert "key" not in connection

    secret = "fixture-secret-do-not-use"
    saved = client.post("/api/connections/fixture-endpoint/set-key", json={"key": secret})
    assert saved.status_code == 200 and secret not in saved.text
    assert "key" not in saved.json()
    listing = client.get("/api/connections").json()
    connection = next(row for row in listing["connections"] if row["name"] == "fixture-endpoint")
    assert connection["has_key"] is True
    assert secret not in client.get("/api/connections").text

    assert client.post("/api/connections/fixture-endpoint/allowance",
                       json={"window": "week", "tokens": 12345}).status_code == 200
    assert client.post("/api/connections/fixture-endpoint/allowance",
                       json={"window": "week", "tokens": -1}).status_code == 422
    assert client.post("/api/connections/fixture-endpoint/clear-key", json={}).status_code == 200
    assert client.post("/api/connections/fixture-endpoint/remove", json={}).status_code == 200
    assert all(row["name"] != "fixture-endpoint" for row in client.get("/api/connections").json()["connections"])


def test_full_mock_run_via_api(client):
    bot = make_bot(client)
    res = client.post("/api/bots/api-bot/run", json={"prompt": "research the news and summarize"})
    assert res.status_code == 201
    run_id = res.json()["id"]

    deadline = time.time() + 20
    while time.time() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] not in ("pending", "running", "waiting_approval"):
            break
        time.sleep(0.2)
    assert run["status"] == "succeeded"
    assert run["steps"] >= 3
    assert len(run["events"]) >= 5
    assert any(e["type"] == "tool_call" for e in run["events"])

    listing = client.get("/api/runs").json()
    assert listing[0]["bot_name"] == "api-bot"

    after = client.get(f"/api/runs/{run_id}/events?after={run['events'][0]['id']}").json()
    assert len(after["events"]) == len(run["events"]) - 1


def test_v1_manual_run_is_idempotent_and_legacy_alias_remains(client):
    bot = make_bot(client, name="retryable-run", paused=True)
    url = "/api/v1/tasks/runs"
    body = {"bot": bot["id"], "prompt": "prepare a short report", "rehearse": True}

    assert client.post(url, json=body).status_code == 428

    headers = {"Idempotency-Key": "manual-run-create-once"}
    created = client.post(url, json=body, headers=headers)
    assert created.status_code == 201, created.text
    run_id = created.json()["id"]
    assert created.json()["replayed"] is False

    replay = client.post(url, json=body, headers=headers)
    assert replay.status_code == 200, replay.text
    assert replay.json()["id"] == run_id and replay.json()["replayed"] is True

    changed = client.post(url, json={**body, "prompt": "different request"}, headers=headers)
    assert changed.status_code == 409
    changed_bot = client.post(url, json={**body, "bot": "missing-bot"}, headers=headers)
    assert changed_bot.status_code == 409
    cross_command = client.post("/api/v1/conversations", json={"bot": bot["id"], "title": "Other command"},
                                headers=headers)
    assert cross_command.status_code == 409

    store = client.app.state.store
    assert store._db.execute("SELECT COUNT(*) FROM runs WHERE bot_id = ?", (bot["id"],)).fetchone()[0] == 1
    assert store._db.execute("SELECT COUNT(*) FROM tasks WHERE bot_id = ?", (bot["id"],)).fetchone()[0] == 1

    legacy = client.post("/api/bots/retryable-run/run", json={"prompt": "legacy request"})
    assert legacy.status_code == 201, legacy.text
    assert legacy.json()["id"] != run_id
    assert store._db.execute("SELECT COUNT(*) FROM runs WHERE bot_id = ?", (bot["id"],)).fetchone()[0] == 2

    # A lost-response retry can still retrieve its committed result during restore
    # review; a genuinely new command remains held and creates no work.
    with store._tx() as db:
        db.execute("INSERT INTO state_restores(id, created_at, source_schema, manifest_hash, verified_code_hash, report_json) "
                   "VALUES (?, ?, ?, ?, ?, ?)",
                   ("restore_retry_test", "2026-10-09T00:00:00Z", store.schema_version, "fixture", "fixture", "{}"))
    replay_while_held = client.post(url, json=body, headers=headers)
    assert replay_while_held.status_code == 200 and replay_while_held.json()["id"] == run_id
    assert replay_while_held.json()["replayed"] is True
    held = client.post(url, json=body, headers={"Idempotency-Key": "manual-run-new-during-hold"})
    assert held.status_code == 409 and held.json()["code"] == "restore_review_required"
    assert store._db.execute("SELECT COUNT(*) FROM runs WHERE bot_id = ?", (bot["id"],)).fetchone()[0] == 2
    assert store._db.execute("SELECT COUNT(*) FROM tasks WHERE bot_id = ?", (bot["id"],)).fetchone()[0] == 2


def test_v1_run_idempotency_is_atomic_across_store_connections(client):
    bot = make_bot(client, name="concurrent-run", paused=True)
    config = client.app.state.config
    first_store = client.app.state.store
    second_store = Store(config)
    barrier = Barrier(2)
    key = "same-run-from-two-connections"
    digest = "request-hash-for-concurrent-run"

    def submit(store):
        run = Run(bot_id=bot["id"], prompt="the same run", origin="manual:api:v1", rehearsal=True)
        task = Task(bot_id=bot["id"], kind="on_demand", prompt="the same run")
        barrier.wait()
        return store.submit_run_idempotent(run, task, idem_key=key, request_hash=digest)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, (first_store, second_store)))
        assert len({run.id for run, _created in results}) == 1
        assert sorted(created for _run, created in results) == [False, True]
        assert first_store._db.execute("SELECT COUNT(*) FROM runs WHERE bot_id = ?", (bot["id"],)).fetchone()[0] == 1
        assert first_store._db.execute("SELECT COUNT(*) FROM tasks WHERE bot_id = ?", (bot["id"],)).fetchone()[0] == 1
    finally:
        second_store.close()


def test_v1_resume_is_idempotent_and_bound_to_one_human_wait(client):
    bot = make_bot(client, name="human-wait", paused=True)
    store = client.app.state.store
    run, first_wait_seq = create_owned_human_wait(store, bot["id"])
    url = f"/api/v1/tasks/runs/{run.id}/resume"
    body = {"human_event_seq": first_wait_seq}

    assert client.post(url, json=body).status_code == 428
    headers = {"Idempotency-Key": "resume-login-wait-once"}
    resumed = client.post(url, json=body, headers=headers)
    assert resumed.status_code == 200, resumed.text
    assert resumed.json() == {"resumed": run.id, "human_event_seq": first_wait_seq, "replayed": False}
    assert store.kv_get(f"resume:{run.id}") == "1"

    replay = client.post(url, json=body, headers=headers)
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    assert store.kv_get(f"resume:{run.id}") == "1"

    duplicate_wait = client.post(url, json=body, headers={"Idempotency-Key": "resume-same-wait-again"})
    assert duplicate_wait.status_code == 409
    assert store.consume_resume(run.id)
    assert not store.consume_resume(run.id)

    store.append_event(Event(run_id=run.id, type=EventType.human_needed,
                             data={"reason": "Confirm the second sign-in step"}))
    second_wait_seq = store.list_events(run.id)[-1].seq
    assert second_wait_seq > first_wait_seq
    assert client.post(url, json=body, headers=headers).json()["replayed"] is True
    assert store.kv_get(f"resume:{run.id}") == "0", "replaying an old wait must not resume a later challenge"
    stale = client.post(url, json=body, headers={"Idempotency-Key": "resume-stale-wait"})
    assert stale.status_code == 409

    current = client.post(url, json={"human_event_seq": second_wait_seq},
                          headers={"Idempotency-Key": "resume-second-wait"})
    assert current.status_code == 200 and current.json()["human_event_seq"] == second_wait_seq
    assert store.kv_get(f"resume:{run.id}") == "1"
    assert store.consume_resume(run.id)
    store.transition_run(run.id, RunStatus.running, event={"reason": "fixture completed the human wait"})
    assert client.post(url, json={"human_event_seq": second_wait_seq},
                       headers={"Idempotency-Key": "resume-second-wait"}).json()["replayed"] is True
    rejected = client.post(url, json={"human_event_seq": second_wait_seq},
                           headers={"Idempotency-Key": "resume-after-wait-ended"})
    assert rejected.status_code == 409 and "not waiting" in rejected.text


def test_v1_resume_accepts_only_one_concurrent_command_per_human_wait(client):
    bot = make_bot(client, name="concurrent-human-wait", paused=True)
    first_store = client.app.state.store
    second_store = Store(client.app.state.config)
    run, event_seq = create_owned_human_wait(first_store, bot["id"])
    barrier = Barrier(2)

    keys = ("human-wait-race-a", "human-wait-race-b")

    def resume(store, key):
        barrier.wait()
        try:
            return store.resume_run_idempotent(
                run.id, event_seq, idem_key=key, request_hash=f"request-{key}")
        except ValueError as exc:
            return str(exc)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda args: resume(*args), zip((first_store, second_store), keys)))
        assert sum(isinstance(result, tuple) and result[1] for result in results) == 1
        assert sum(isinstance(result, str) and "already has a resume command" in result
                   for result in results) == 1
        assert first_store.kv_get(f"resume:{run.id}") == "1"
        assert first_store._db.execute("SELECT COUNT(*) FROM human_wait_resumes WHERE run_id = ?",
                                       (run.id,)).fetchone()[0] == 1
        winner_key = keys[next(index for index, result in enumerate(results)
                               if isinstance(result, tuple) and result[1])]
        replay_store = Store(client.app.state.config)
        try:
            replay, created = replay_store.resume_run_idempotent(
                run.id, event_seq, idem_key=winner_key, request_hash=f"request-{winner_key}")
            assert not created and replay["human_event_seq"] == event_seq
            assert replay_store.kv_get(f"resume:{run.id}") == "1"
        finally:
            replay_store.close()
    finally:
        second_store.close()


def test_v1_resume_rejects_a_wait_without_a_live_owner(client):
    bot = make_bot(client, name="expired-human-wait", paused=True)
    store = client.app.state.store
    run, event_seq = create_owned_human_wait(store, bot["id"])
    with store._tx() as db:
        db.execute("UPDATE runs SET lease_expires_at = ? WHERE id = ?",
                   ("2000-01-01T00:00:00+00:00", run.id))
    response = client.post(f"/api/v1/tasks/runs/{run.id}/resume", json={"human_event_seq": event_seq},
                           headers={"Idempotency-Key": "resume-expired-worker"})
    assert response.status_code == 409 and "active owner" in response.text
    assert store.kv_get(f"resume:{run.id}") is None
    assert store._db.execute("SELECT COUNT(*) FROM human_wait_resumes WHERE run_id = ?",
                             (run.id,)).fetchone()[0] == 0
def test_tool_limits_patch_and_artifact_serving(client):
    """PF-2: per-tool caps are configurable, truncation keeps the full output,
    and the artifact endpoint serves only files inside this run's directory."""
    bot = make_bot(client)

    res = client.patch(f"/api/bots/{bot['name']}", json={"tool_limits": {"list_files": 1}})
    assert res.status_code == 200 and res.json()["tool_limits"] == {"list_files": 1}
    assert client.patch(f"/api/bots/{bot['name']}", json={"tool_limits": {"nope": 5}}).status_code == 422
    assert client.patch(f"/api/bots/{bot['name']}", json={"tool_limits": {"list_files": -3}}).status_code == 422
    assert client.patch(f"/api/bots/{bot['name']}", json={"tool_limits": {"list_files": 0}}).status_code == 422

    res = client.post("/api/bots/api-bot/run", json={"prompt": "research the news"})
    assert res.status_code == 201
    run_id = res.json()["id"]
    deadline = time.time() + 20
    while time.time() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] not in ("pending", "running", "waiting_approval"):
            break
        time.sleep(0.2)
    assert run["status"] == "succeeded"

    art_ev = next(e for e in run["events"] if e["type"] == "tool_result" and e["data"].get("artifact"))
    rel = art_ev["data"]["artifact"]
    assert rel.startswith("artifacts/")
    assert "omitted" in art_ev["data"]["output"]       # the display carries the truncation note

    got = client.get(f"/api/runs/{run_id}/{rel}")
    assert got.status_code == 200
    assert got.headers["content-type"].startswith("text/plain")
    assert len(got.text) == art_ev["data"]["chars"]    # served file is the FULL output
    assert "omitted" not in got.text                   # ... and not the cut view

    # traversal, absolute, unknown-file and unknown-run are all refused
    assert client.get(f"/api/runs/{run_id}/artifacts/..%2F..%2F..%2Fetc%2Fpasswd").status_code == 404
    assert client.get(f"/api/runs/{run_id}/artifacts/%2Fetc%2Fpasswd").status_code == 404
    assert client.get(f"/api/runs/{run_id}/artifacts/nope.txt").status_code == 404
    assert client.get("/api/runs/run_nope/artifacts/x.txt").status_code == 404


def test_approval_flow_via_api(client):
    make_bot(client, name="asker", approval_mode="ask")
    res = client.post("/api/bots/asker/run", json={"prompt": "sort my downloads"})
    run_id = res.json()["id"]

    deadline = time.time() + 15
    approvals = []
    while time.time() < deadline:
        approvals = client.get("/api/approvals").json()
        if approvals:
            break
        time.sleep(0.2)
    assert approvals, "expected a write_file approval to appear"
    req = approvals[0]
    assert req["bot_name"] == "asker" and req["tool"] in ("files", "shell")
    approval_id = req["id"]
    assert client.get(f"/api/approvals/{approval_id}").json()["status"] == "pending"

    assert client.post(f"/api/approvals/{approval_id}/approve", json={"always": True}).status_code == 200
    # duplicate resolution is rejected
    assert client.post(f"/api/approvals/{approval_id}/approve", json={}).status_code == 409
    decided = client.get(f"/api/approvals/{approval_id}").json()
    assert decided["status"] == "approved" and decided["decided_by"]
    assert any(a["id"] == approval_id for a in client.get("/api/approvals?status=resolved&limit=8").json())
    assert client.get("/api/approvals/does-not-exist").status_code == 404

    deadline = time.time() + 20
    while time.time() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] not in ("pending", "running", "waiting_approval"):
            break
        time.sleep(0.2)
    assert run["status"] == "succeeded"

    # sticky allow recorded on the bot
    detail = client.get("/api/bots/asker").json()
    assert req["sticky_key"] in detail["sticky_allows"]


def test_dashboard_page_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "hutch" in res.text.lower()
    assert res.headers["content-type"].startswith("text/html")
    css = client.get("/static/style.css")
    assert css.status_code == 200
    js = client.get("/static/app.js")
    assert js.status_code == 200


def test_sticky_and_memory_deletion(client):
    make_bot(client, name="mem-bot")
    # inject memory and sticky via internal store or approval
    # we can call the store via client app state or run a quick task
    # or test deletion on non-existent (idempotent 200)
    res_mem = client.delete("/api/bots/mem-bot/memory/test-key")
    assert res_mem.status_code == 200
    assert res_mem.json() == {"forgot": "test-key", "operation": "archived",
                              "scope": "all facts with this key for this bot", "history_retained": True}

    res_sticky = client.delete("/api/bots/mem-bot/sticky-allows/shell:echo")
    assert res_sticky.status_code == 200
    assert res_sticky.json() == {"revoked": "shell:echo"}


def test_versioned_stop_is_idempotent_and_rejects_key_reuse(client):
    from hutch.models import Bot, Run

    bot = client.app.state.store.create_bot(Bot(name="idem-stop", model="mock/demo"))
    first = client.app.state.store.create_run(Run(bot_id=bot.id, prompt="first"))
    second = client.app.state.store.create_run(Run(bot_id=bot.id, prompt="second"))
    url = f"/api/v1/tasks/runs/{first.id}/stop"
    assert client.post(url).status_code == 428
    headers = {"Idempotency-Key": "stop-one"}
    assert client.post(url, headers=headers).status_code == 200
    assert client.post(url, headers=headers).status_code == 200
    conflict = client.post(f"/api/v1/tasks/runs/{second.id}/stop", headers=headers)
    assert conflict.status_code == 409


def test_versioned_approval_resolution_is_idempotent_and_hash_bound(client):
    from hutch.models import ApprovalRequest, Bot, Run

    store = client.app.state.store
    bot = store.create_bot(Bot(name="idem-approval", model="mock/demo"))
    run = store.create_run(Run(bot_id=bot.id, prompt="approve this"))
    request = store.create_approval(ApprovalRequest(run_id=run.id, bot_id=bot.id, tool="files",
                                                    action="write report", detail={"path": "report.txt"},
                                                    sticky_key="files:write:report.txt", action_hash="fingerprint"))
    url = f"/api/v1/actions/approvals/{request.id}/approve"
    body = {"always": True, "action_hash": request.action_hash}
    assert client.post(url, json=body).status_code == 428
    headers = {"Idempotency-Key": "approve-one"}
    approved = client.post(url, json=body, headers=headers)
    assert approved.status_code == 200, approved.text
    assert client.post(url, json=body, headers=headers).status_code == 200
    assert store.is_sticky_allowed(bot.id, request.sticky_key)
    changed = client.post(url, json={**body, "always": False}, headers=headers)
    assert changed.status_code == 409


def test_versioned_connections_schedules_and_capabilities_are_typed_and_secret_free(client):
    from hutch.connections import ConnectionBook

    book = ConnectionBook(client.app.state.config.state_dir)
    book.add("custom-openai", name="private-route", base_url="https://models.example.test/v1",
             account_id="api-account", account_daily_cost_cap_usd=5.0,
             quota={"window": "day", "tokens": 5000})
    book.set_key("private-route", "never-return-this-key")
    connections = client.get("/api/v1/connections")
    assert connections.status_code == 200
    route = next(row for row in connections.json() if row["name"] == "private-route")
    assert route["key_present"] is True and route["protocol"] == "openai-chat"
    assert route["account_id"] == "api-account" and route["account_daily_cost_cap_usd"] == 5.0
    assert route["configured_account_daily_cost_cap_usd"] == 5.0
    bot = client.app.state.store.create_bot(Bot(name="reservation-api"))
    # Keep the fixture out of the live supervisor's pending queue; its fence
    # owns production reservations, while this API resource check is synthetic.
    run = client.app.state.store.create_run(Run(bot_id=bot.id, prompt="api status", status=RunStatus.running))
    client.app.state.store.reserve_usage(run_id=run.id, bot_id=bot.id, provider="private-route",
                                         account_id="api-account", model="m", reserved_tokens=123,
                                         reserved_cost_usd=0.45)
    reservations = client.get("/api/v1/usage/reservations").json()
    assert reservations[0]["account_id"] == "api-account" and reservations[0]["reserved_tokens"] == 123
    route = next(row for row in client.get("/api/v1/connections").json() if row["name"] == "private-route")
    assert route["quota_reserved_tokens"] == 123 and route["account_daily_cost_reserved_usd"] == 0.45
    assert "never-return-this-key" not in connections.text

    from hutch.lifecycle import LeaseLost

    store = client.app.state.store
    bot = store.create_bot(Bot(name="capability-evidence-api"))
    run = store.create_run(Run(bot_id=bot.id, prompt="use a tool"))
    claimed = store.claim_run(run.id, "capability-api-test", 30)
    assert claimed is not None
    run = store.transition_run(run.id, RunStatus.running, fence=claimed.fence)
    first_reservation = store.reserve_usage(run_id=run.id, bot_id=bot.id, provider="private-route",
                                            account_id="account-safe-id", model="fixture-model", reserved_tokens=10,
                                            reserved_cost_usd=0, expected_fence=run.fence)
    store.mark_usage_uncertain(first_reservation, "fixture response usage omitted", expected_fence=run.fence)
    store.record_model_capability_observation(
        run, provider="private-route", account_id="account-safe-id", model="fixture-model",
        route_revision="a" * 64, capability="function_tool_calls", source_tool="list_files")
    second_bot = store.create_bot(Bot(name="capability-evidence-api-2"))
    second = store.create_run(Run(bot_id=second_bot.id, prompt="use another tool"))
    second_claim = store.claim_run(second.id, "capability-api-test-2", 30)
    assert second_claim is not None
    second = store.transition_run(second.id, RunStatus.running, fence=second_claim.fence)
    second_reservation = store.reserve_usage(run_id=second.id, bot_id=second_bot.id, provider="private-route",
                                             account_id="account-safe-id", model="fixture-model-2",
                                             reserved_tokens=10, reserved_cost_usd=0, expected_fence=second.fence)
    store.mark_usage_uncertain(second_reservation, "fixture response usage omitted", expected_fence=second.fence)
    store.record_model_capability_observation(
        second, provider="private-route", account_id="account-safe-id", model="fixture-model-2",
        route_revision="b" * 64, capability="function_tool_calls", source_tool="read_file")
    store.transition_run(run.id, RunStatus.succeeded, fence=run.fence)
    with pytest.raises(LeaseLost, match="lease expired|ownership lease expired"):
        store.record_model_capability_observation(
            run, provider="private-route", account_id="account-safe-id", model="fixture-model-3",
            route_revision="c" * 64, capability="function_tool_calls", source_tool="list_files")
    unreserved_bot = store.create_bot(Bot(name="capability-evidence-unreserved"))
    unreserved = store.create_run(Run(bot_id=unreserved_bot.id, prompt="no usage reservation"))
    unreserved_claim = store.claim_run(unreserved.id, "capability-unreserved-test", 30)
    assert unreserved_claim is not None
    unreserved = store.transition_run(unreserved.id, RunStatus.running, fence=unreserved_claim.fence)
    with pytest.raises(ValueError, match="usage reservation"):
        store.record_model_capability_observation(
            unreserved, provider="private-route", account_id="account-safe-id", model="unreserved-model",
            route_revision="d" * 64, capability="function_tool_calls", source_tool="list_files")

    first_page = client.get("/api/v1/model-capabilities?limit=1")
    assert first_page.status_code == 200
    body = first_page.json()
    assert len(body["items"]) == 1 and body["next_after_id"] is not None
    assert body["items"][0]["status"] == "observed"
    assert body["items"][0]["scope"] == "exact connection, account, model, and route revision"
    assert "secret" not in first_page.text.lower()
    next_page = client.get(f"/api/v1/model-capabilities?limit=1&after_id={body['next_after_id']}")
    assert next_page.status_code == 200
    assert len(next_page.json()["items"]) == 1
    latest_page = client.get("/api/v1/model-capabilities?direction=desc&limit=1")
    assert latest_page.status_code == 200
    latest = latest_page.json()
    assert latest["items"][0]["model"] == "fixture-model-2" and latest["next_after_id"] is not None
    older_page = client.get(f"/api/v1/model-capabilities?direction=desc&limit=1&after_id={latest['next_after_id']}")
    assert older_page.status_code == 200
    assert older_page.json()["items"][0]["model"] == "fixture-model"
    assert client.get("/api/v1/model-capabilities?limit=101").status_code == 422
    assert client.get("/api/v1/model-capabilities?direction=sideways").status_code == 422

    bot = make_bot(client, name="scheduled-v1", cron="0 9 * * 1", timezone="America/Vancouver",
                   schedule_prompt="Review new release notes and write a concise report.")
    schedules = client.get("/api/v1/schedules").json()
    schedule = next(row for row in schedules if row["bot_id"] == bot["id"])
    assert schedule["cron"] == "0 9 * * 1" and schedule["timezone"] == "America/Vancouver"
    assert schedule["prompt"] == "Review new release notes and write a concise report."
    assert schedule["name"] == "Scheduled task"
    assert schedule["next_fire"] and schedule["last_dispatched"]
    assert client.get("/api/bots/scheduled-v1").json()["schedule"]["prompt"] == schedule["prompt"]
    updated = client.patch("/api/bots/scheduled-v1", json={"schedule_prompt": "Check the weekly security feed."})
    assert updated.status_code == 200 and updated.json()["schedule"]["prompt"] == "Check the weekly security feed."
    reset = client.patch("/api/bots/scheduled-v1", json={"schedule_prompt": ""})
    assert reset.status_code == 200 and reset.json()["schedule"]["prompt"] == ""
    multi = client.app.state.store.get_bot("scheduled-v1")
    from hutch.models import Schedule
    multi.set_schedules([multi.schedule, Schedule(id="quarterly", name="Quarterly review",
                                                   cron="0 9 1 1,4,7,10 *", prompt="Review the quarter")])
    client.app.state.store.upsert_bot(multi)
    listed = [row for row in client.get("/api/v1/schedules").json() if row["bot_id"] == multi.id]
    assert {row["id"] for row in listed} == {multi.schedule.id, "quarterly"}
    assert next(row for row in listed if row["id"] == "quarterly")["name"] == "Quarterly review"
    legacy_edit = client.patch("/api/bots/scheduled-v1", json={"schedule_prompt": "First task changed"})
    assert legacy_edit.status_code == 200 and legacy_edit.json()["schedule"]["prompt"] == "First task changed"
    assert {item["id"] for item in legacy_edit.json()["schedules"]} == {multi.schedule.id, "quarterly"}
    non_schedule_edit = client.patch("/api/bots/scheduled-v1", json={"description": "keep the sibling"})
    assert non_schedule_edit.status_code == 200
    assert {item["id"] for item in non_schedule_edit.json()["schedules"]} == {multi.schedule.id, "quarterly"}
    body = {"name": "Morning brief", "cron": "0 8 * * 1-5", "timezone": "UTC",
            "catch_up": "coalesce", "prompt": "Summarize priority messages."}
    created = client.put(f"/api/v1/bots/{multi.id}/schedules/morning", json=body)
    assert created.status_code == 200 and created.json()["next_fire"]
    assert client.put(f"/api/v1/bots/{multi.id}/schedules/morning", json=body).json() == created.json()
    listed = [row for row in client.get("/api/v1/schedules").json() if row["bot_id"] == multi.id]
    assert {row["id"] for row in listed} == {multi.schedule.id, "quarterly", "morning"}
    first_page = client.get("/api/v1/schedules", params={"bot": multi.id, "limit": 1, "offset": 0}).json()
    second_page = client.get("/api/v1/schedules", params={"bot": multi.id, "limit": 1, "offset": 1}).json()
    assert len(first_page) == len(second_page) == 1 and first_page[0]["id"] != second_page[0]["id"]
    other = client.app.state.store.create_bot(Bot(name="other-scheduled-bot"))
    assert client.put(f"/api/v1/bots/{other.id}/schedules/morning", json=body).status_code == 409
    invalid = client.put(f"/api/v1/bots/{multi.id}/schedules/invalid", json={**body, "timezone": "Mars/Olympus"})
    assert invalid.status_code == 422
    removed_id = multi.schedule.id
    assert client.delete(f"/api/v1/bots/{multi.id}/schedules/{removed_id}").status_code == 204
    after_delete = client.app.state.store.get_bot("scheduled-v1")
    assert after_delete.schedule.id == "quarterly" and len(after_delete.schedules) == 2
    assert client.put(f"/api/v1/bots/{multi.id}/schedules/{removed_id}", json=body).status_code == 409
    assert client.delete(f"/api/v1/bots/{multi.id}/schedules/missing").status_code == 404
    assert client.patch("/api/bots/scheduled-v1", json={"clear_cron": True,
                      "schedule_prompt": "Prompt without a schedule"}).status_code == 422
    no_cron_prompt = client.post("/api/bots", json={"name": "prompt-needs-cron", "model": "mock/demo",
                                                     "schedule_prompt": "Prompt without a schedule"})
    assert no_cron_prompt.status_code == 422
    overlong_prompt = client.post("/api/bots", json={"name": "prompt-too-long", "model": "mock/demo",
                                                      "cron": "0 9 * * 1", "schedule_prompt": "x" * 4001})
    assert overlong_prompt.status_code == 422

    capabilities = {row["id"]: row for row in client.get("/api/v1/capabilities").json()}
    assert capabilities["strict_offline"]["status"] in {"experimental", "unavailable"}
    assert capabilities["strict_offline"]["verification"] == "network_pid_namespace_tcp_unix_socket_probe"
    assert capabilities["remote_pairing"]["status"] == "experimental"
    assert capabilities["browser_handoff"]["status"] in {"experimental", "unavailable"}
    assert capabilities["browser_handoff"]["verification"] in {
        "host_display_and_playwright_check", "host_prerequisite_check"}
    assert capabilities["phone_control"]["status"] == "experimental"
    assert capabilities["phone_control"]["verification"] == "paired_phone_api_and_browser_fixtures"
    assert "computer interaction is unavailable" in capabilities["phone_control"]["reason"].lower()
    assert capabilities["external_runtimes"]["status"] == "unavailable"
