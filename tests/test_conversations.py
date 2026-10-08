from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient

from hutch.server.app import create_app


def test_versioned_conversations_are_persisted_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    with TestClient(app) as client:
        bot = client.post("/api/bots", json={
            "name": "conversation-bot", "model": "mock/demo", "tools": ["memory", "write_file"],
            "approval_mode": "auto", "instructions": "Keep responses short.",
        }).json()

        assert client.get("/api/v1/health").json()["status"] == "ok"
        labels = {row["status"]: row for row in client.get("/api/v1/status-labels").json()}
        assert labels["cancelling"]["label"] == "Stopping" and labels["cancelling"]["terminal"] is False
        assert labels["outcome_unknown"]["needs_person"] is True
        assert client.post("/api/v1/conversations", json={"bot": bot["id"]}).status_code == 428
        headers = {"Idempotency-Key": "create-conv-1"}
        created = client.post("/api/v1/conversations", json={"bot": bot["id"], "title": "Project notes"},
                              headers=headers)
        assert created.status_code == 201, created.text
        conversation = created.json()
        assert conversation["bot_id"] == bot["id"] and conversation["message_count"] == 0
        replay = client.post("/api/v1/conversations", json={"bot": bot["id"], "title": "Project notes"},
                             headers=headers)
        assert replay.status_code == 200 and replay.json()["id"] == conversation["id"]
        conflict = client.post("/api/v1/conversations", json={"bot": bot["id"], "title": "Different"},
                               headers=headers)
        assert conflict.status_code == 409

        messages_url = f"/api/v1/conversations/{conversation['id']}/messages"
        assert client.post(messages_url, json={"prompt": "missing key"}).status_code == 428
        first = client.post(messages_url, json={"prompt": "Research project risks"},
                            headers={"Idempotency-Key": "send-1"})
        assert first.status_code == 201, first.text
        run_id = first.json()["id"]
        deadline = time.time() + 15
        while time.time() < deadline:
            run = client.get(f"/api/v1/tasks/runs/{run_id}").json()
            if run["terminal"]:
                break
            time.sleep(0.1)
        assert run["status"] == "succeeded"
        transcript = client.get(f"/api/v1/tasks/runs/{run_id}").json()["events"]
        assert transcript[0]["type"] == "message" and transcript[0]["data"] == {
            "role": "user", "content": "Research project risks"}
        assert app.state.store.verify_chain(run_id)["ok"] is True
        transcript_file = app.state.config.run_dir("conversation-bot", run_id) / "transcript.jsonl"
        app.state.store.flush_transcripts()
        mirrored = [json.loads(line) for line in transcript_file.read_text(encoding="utf-8").splitlines()]
        assert mirrored[0]["data"] == {"role": "user", "content": "Research project risks"}
        assert len(mirrored) == len(transcript)

        same = client.post(messages_url, json={"prompt": "Research project risks"},
                           headers={"Idempotency-Key": "send-1"})
        assert same.status_code == 200 and same.json()["id"] == run_id and same.json()["replayed"] is True
        changed = client.post(messages_url, json={"prompt": "A different prompt"},
                              headers={"Idempotency-Key": "send-1"})
        assert changed.status_code == 409

        second = client.post(messages_url, json={"prompt": "Continue with mitigations"},
                             headers={"Idempotency-Key": "send-2"})
        assert second.status_code == 201, second.text
        second_id = second.json()["id"]
        stored_run = app.state.store.get_run(second_id)
        assert stored_run.conversation_id == conversation["id"]
        assert stored_run.conversation_context[0] == {"role": "user", "content": "Research project risks"}
        assert any(m["role"] == "assistant" and "Research project risks" in m["content"]
                   for m in stored_run.conversation_context)
        second_deadline = time.time() + 15
        while time.time() < second_deadline:
            second_state = client.get(f"/api/v1/tasks/runs/{second_id}").json()
            if second_state["terminal"]:
                break
            time.sleep(0.1)
        assert second_state["status"] == "succeeded"

        detail = client.get(f"/api/v1/conversations/{conversation['id']}?limit=2")
        assert detail.status_code == 200
        assert len(detail.json()["messages"]) == 2 and detail.json()["has_more"] is True
        next_page = client.get(f"/api/v1/conversations/{conversation['id']}?after=2")
        assert [m["role"] for m in next_page.json()["messages"]] == ["user", "assistant"]
        assert client.get("/api/v1/conversations?bot=conversation-bot").json()[0]["id"] == conversation["id"]
        results = client.get("/api/v1/search/messages?q=mitigations").json()
        assert any(result["conversation_id"] == conversation["id"] for result in results)
        assert client.get("/api/v1/search/messages?q=\"unterminated").status_code == 200

        archived = client.post(f"/api/v1/conversations/{conversation['id']}/archive", json={"archived": True},
                               headers={"Idempotency-Key": "archive-1"})
        assert archived.status_code == 200 and archived.json()["archived"] is True
        assert client.post(messages_url, json={"prompt": "This must not run"},
                           headers={"Idempotency-Key": "send-3"}).status_code == 409
        assert client.get("/api/v1/conversations").json() == []

    # The completed history and request de-duplication survive closing every Store connection.
    with TestClient(create_app()) as reopened:
        restored = reopened.get(f"/api/v1/conversations/{conversation['id']}")
        assert restored.status_code == 200
        assert [message["content"] for message in restored.json()["messages"] if message["role"] == "user"] == [
            "Research project risks", "Continue with mitigations"]
        replay = reopened.post(f"/api/v1/conversations/{conversation['id']}/messages",
                               json={"prompt": "Continue with mitigations"},
                               headers={"Idempotency-Key": "send-2"})
        assert replay.status_code == 200 and replay.json()["id"] == second_id


def test_versioned_resources_are_documented(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    with TestClient(app) as client:
        paths = client.get("/openapi.json").json()["paths"]
        assert "/api/v1/conversations" in paths
        assert "/api/v1/tasks/runs/{run_id}" in paths


def submitted_conversation(store):
    from hutch.models import Bot, Run, RunStatus, Task
    bot = store.create_bot(Bot(name="transactional-chat", model="mock/demo", tools=[]))
    conversation, _ = store.create_conversation(bot.id, "durable replies", idem_key="create", request_hash="create")
    run = Run(bot_id=bot.id, prompt="hello")
    store.submit_conversation_message(conversation["id"], "hello", run, Task(bot_id=bot.id, prompt="hello"),
                                      idem_key="message", request_hash="message")
    claimed = store.claim_run(run.id, "worker", 60)
    store.transition_run(run.id, RunStatus.running, fence=claimed.fence)
    return conversation["id"], claimed


def test_terminal_drain_commits_reply_and_history_atomically(store, config):
    import sqlite3
    from hutch.models import Event, EventType, RunStatus
    conversation_id, run = submitted_conversation(store)
    with store._buf_cv:  # deterministic: hold the writer until the transition drains this reply
        store.append_event(Event(run_id=run.id, type=EventType.message, data={"role": "assistant", "content": "durable answer"}))
        store.transition_run(run.id, RunStatus.succeeded, fence=run.fence, event={"reason": "completed"})
        with sqlite3.connect(config.db_path) as observer:
            assert observer.execute("SELECT status FROM runs WHERE id = ?", (run.id,)).fetchone()[0] == "succeeded"
            assert observer.execute("SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY seq",
                                    (conversation_id,)).fetchall() == [("user", "hello"), ("assistant", "durable answer")]
    store.archive_conversation(conversation_id, True, idem_key="archive", request_hash="archive")
    store.flush_events()
    assert len(store.list_conversation_messages(conversation_id)) == 2
    assert store.verify_chain(run.id)["ok"]


def test_same_terminal_transition_cannot_project_a_zombie_reply(store, config):
    import pytest
    from hutch.models import Event, EventType, RunStatus
    from hutch.store import Store
    from hutch.lifecycle import LeaseLost
    conversation_id, run = submitted_conversation(store)
    zombie = Store(config)
    try:
        store.transition_run(run.id, RunStatus.succeeded, fence=run.fence)
        with zombie._buf_cv:
            zombie.append_event(Event(run_id=run.id, type=EventType.message,
                                      data={"role": "assistant", "content": "too late"}))
            with pytest.raises(LeaseLost, match="terminal runs refuse"):
                zombie.transition_run(run.id, RunStatus.succeeded, fence=run.fence)
        zombie.flush_events()
        assert [m["role"] for m in store.list_conversation_messages(conversation_id)] == ["user"]
        assert zombie.dropped_events == 1
        assert store.verify_chain(run.id)["ok"]
    finally:
        zombie.close()


def test_conversation_authority_is_independent_of_message_page_and_other_conversations(store):
    from hutch.models import Bot, Run, RunStatus, Task
    bot = store.create_bot(Bot(name="long-active-chat", model="mock/demo", tools=[]))
    other, _ = store.create_conversation(bot.id, "other", idem_key="other", request_hash="other")
    unrelated = Run(bot_id=bot.id, prompt="another conversation", status=RunStatus.waiting_human)
    store.submit_conversation_message(other["id"], unrelated.prompt, unrelated, Task(bot_id=bot.id, prompt=unrelated.prompt),
                                      idem_key="other-send", request_hash="other-send")
    conv, _ = store.create_conversation(bot.id, "long conversation", idem_key="long", request_hash="long")
    first = None
    for i in range(105):
        run = Run(bot_id=bot.id, prompt=f"turn {i}", status=RunStatus.waiting_approval if i == 0 else RunStatus.pending)
        store.submit_conversation_message(conv["id"], run.prompt, run, Task(bot_id=bot.id, prompt=run.prompt),
                                          idem_key=f"send-{i}", request_hash=f"send-{i}")
        first = first or run
    detail = store.get_conversation(conv["id"])
    assert detail["active_run_id"] == first.id
    assert detail["active_run_status"] == "waiting_approval"
    assert detail["active_run_status_label"] == "Waiting for you"
    assert detail["latest_run_id"] != first.id
    assert all(message["run_id"] != first.id for message in store.list_conversation_messages(conv["id"], after=5))
    listed = next(c for c in store.list_conversations(bot.id) if c["id"] == conv["id"])
    assert listed["active_run_id"] == first.id
