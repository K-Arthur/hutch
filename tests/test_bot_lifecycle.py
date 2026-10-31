"""Bot lifecycle: an assistant can be retired without losing its history.

These tests exercise the real Store and the real HTTP surface. They assert the three things that
make archiving safe rather than cosmetic: new work is refused at every admission path, existing
history stays readable, and restoring changes nothing else.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from hutch.models import Bot, Run, RunStatus, Task
from hutch.server.app import create_app
from hutch.bot_lifecycle import ArchiveRefused, BotArchived, archive_bot
from hutch.store import Store


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    with TestClient(create_app()) as app_client:
        yield app_client


def make_bot(store: Store, name: str = "retire-me", **overrides) -> Bot:
    fields = {"name": name, "display_name": name.title(), "model": "mock/demo", "tools": ["files"]}
    fields.update(overrides)
    return store.create_bot(Bot(**fields))


def seed_history(store: Store, bot: Bot) -> dict:
    """A conversation with two completed turns and no live run."""
    conversation, _ = store.create_conversation(bot.id, "Chat", idem_key=f"conv-{bot.id}", request_hash="h1")
    stamp = "2026-10-11T12:00:00+00:00"
    with store._tx() as db:
        store._insert_conversation_message(db, message_id=f"u-{bot.id}", conversation_id=conversation["id"],
                                           seq=1, run_id="", role="user", content="hello", created_at=stamp)
        store._insert_conversation_message(db, message_id=f"a-{bot.id}", conversation_id=conversation["id"],
                                           seq=2, run_id="", role="assistant", content="hi", created_at=stamp)
    return conversation


def test_archive_keeps_history_and_refuses_new_work(client):
    store = client.app.state.store
    bot = make_bot(store)
    conversation = seed_history(store, bot)
    before = store.list_conversation_messages(conversation["id"])
    assert [m["role"] for m in before] == ["user", "assistant"]

    archived, changed = archive_bot(store, bot.name, True, idem_key="archive-1", request_hash="h3")
    assert changed is True and archived.archived is True

    # History is untouched and still readable after retirement.
    after = store.list_conversation_messages(conversation["id"])
    assert [m["id"] for m in after] == [m["id"] for m in before]

    # New work is refused on the canonical conversation path.
    run = Run(bot_id=bot.id, prompt="again", conversation_id=conversation["id"])
    task = Task(bot_id=bot.id, kind="chat", prompt="again")
    with pytest.raises(BotArchived) as refused:
        store.submit_conversation_message(conversation["id"], "again", run, task,
                                          idem_key="msg-archived", request_hash="h4")
    assert refused.value.name == bot.name

    # ...and on the legacy run paths.
    with pytest.raises(BotArchived):
        store.create_run(Run(bot_id=bot.id, prompt="legacy"))
    with pytest.raises(BotArchived):
        store.submit_run(Run(bot_id=bot.id, prompt="legacy"), Task(bot_id=bot.id, kind="task", prompt="legacy"))


def submit_message(store: Store, bot: Bot) -> None:
    """One real admission on the canonical conversation path (leaves a pending run)."""
    conversation, _ = store.create_conversation(bot.id, "Chat", idem_key=f"conv-{bot.id}", request_hash="h1")
    run = Run(bot_id=bot.id, prompt="hello", conversation_id=conversation["id"])
    task = Task(bot_id=bot.id, kind="chat", prompt="hello")
    store.submit_conversation_message(conversation["id"], "hello", run, task,
                                      idem_key=f"msg-{bot.id}", request_hash="h2")


def test_restore_makes_the_assistant_eligible_again(client):
    store = client.app.state.store
    bot = make_bot(store, "come-back")
    archive_bot(store, bot.name, True, idem_key="archive-a", request_hash="h1")
    archive_bot(store, bot.name, False, idem_key="archive-b", request_hash="h2")

    restored = store.get_bot(bot.id)
    assert restored is not None and restored.archived is False
    submit_message(store, restored)  # admitted again


def test_archive_is_refused_while_a_run_is_active(client):
    store = client.app.state.store
    bot = make_bot(store, "busy-bot")
    run = store.create_run(Run(bot_id=bot.id, prompt="working", status=RunStatus.running))
    with pytest.raises(ArchiveRefused) as refused:
        archive_bot(store, bot.name, True, idem_key="archive-busy", request_hash="h1")
    assert refused.value.run_id == run.id
    assert store.get_bot(bot.id).archived is False


def test_archive_command_is_idempotent_per_key(client):
    store = client.app.state.store
    bot = make_bot(store, "twice")
    first, changed_first = archive_bot(store, bot.name, True, idem_key="same-key", request_hash="h1")
    second, changed_second = archive_bot(store, bot.name, True, idem_key="same-key", request_hash="h1")
    assert changed_first is True and changed_second is False
    assert first.archived is True and second.archived is True


def test_coordinator_cannot_be_archived(client):
    store = client.app.state.store
    bot = make_bot(store, "main-assistant")
    store.set_workspace_coordinator(bot.id)
    with pytest.raises(PermissionError):
        archive_bot(store, bot.name, True, idem_key="archive-main", request_hash="h1")


def test_archived_assistant_is_not_offered_as_a_specialist(client):
    store = client.app.state.store
    keep = make_bot(store, "keep-me")
    retire = make_bot(store, "retire-me")
    store.set_workspace_coordinator(keep.id)
    assert [b["name"] for b in store.workspace_specialists()["bots"]] == ["retire-me"]
    archive_bot(store, retire.name, True, idem_key="archive-spec", request_hash="h1")
    assert store.workspace_specialists()["bots"] == []


def test_archived_bot_refuses_a_message_over_http(client):
    store = client.app.state.store
    bot = make_bot(store, "http-bot")
    conversation, _ = store.create_conversation(bot.id, "Chat", idem_key="c1", request_hash="h1")
    archive_bot(store, bot.name, True, idem_key="archive-http", request_hash="h2")

    response = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={"prompt": "hello"},
        headers={"Idempotency-Key": "http-msg-1"},
    )
    assert response.status_code == 409
    assert "archived" in response.json()["detail"].lower()


def test_archive_and_restore_over_http(client):
    store = client.app.state.store
    bot = make_bot(store, "api-bot")

    archived = client.post(f"/api/v1/bots/{bot.name}/archive", json={"archived": True},
                           headers={"Idempotency-Key": "http-archive-1"})
    assert archived.status_code == 200
    assert archived.json()["archived"] is True

    listed = {item["name"]: item for item in client.get("/api/v1/bots").json()}
    assert listed["api-bot"]["archived"] is True

    restored = client.post(f"/api/v1/bots/{bot.name}/archive", json={"archived": False},
                           headers={"Idempotency-Key": "http-archive-2"})
    assert restored.status_code == 200
    assert restored.json()["archived"] is False


def test_archive_requires_an_idempotency_key(client):
    store = client.app.state.store
    bot = make_bot(store, "no-key")
    response = client.post(f"/api/v1/bots/{bot.name}/archive", json={"archived": True})
    assert response.status_code == 428
