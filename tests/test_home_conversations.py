"""Persistent direct chats are pointers, never transcript or authority merges."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from hutch.models import Bot
from hutch.server.app import create_app
from hutch.store import Store


def conversation(store, bot, key):
    return store.create_conversation(bot.id, key, idem_key=key, request_hash=key)[0]


def test_home_is_atomic_and_independent_of_model_defaults(store, config):
    bot = store.create_bot(Bot(name="hutch", model="ollama/first", tools=[]))
    peer = Store(config)
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda i: (store if i % 2 else peer).ensure_assistant_home_conversation(bot.id), range(16)))
    finally:
        peer.close()
    assert len({result[0] for result in results}) == 1
    assert sum(created for _, created in results) == 1
    home_id = results[0][0]
    assert len(store.list_conversations(bot.id)) == 1
    bot.model = "ollama/second"
    store.upsert_bot(bot)
    assert store.ensure_assistant_home_conversation(bot.id) == (home_id, False)
    reopened = Store(config)
    try:
        assert reopened.assistant_home_conversation_id(bot.id) == home_id
    finally:
        reopened.close()


def test_home_adopts_only_one_owned_direct_chat_and_preserves_history(store):
    bot = store.create_bot(Bot(name="hutch", tools=[]))
    other = store.create_bot(Bot(name="research", tools=[]))
    first, second = conversation(store, bot, "first"), conversation(store, bot, "second")
    foreign = conversation(store, other, "foreign")
    with pytest.raises(ValueError):
        store.ensure_assistant_home_conversation(bot.id, foreign["id"])
    assert store.assistant_home_conversation_id(bot.id) is None
    assert store.ensure_assistant_home_conversation(bot.id, first["id"]) == (first["id"], True)
    assert store.ensure_assistant_home_conversation(bot.id, second["id"]) == (first["id"], False)
    assert {row["id"] for row in store.list_conversations(bot.id)} == {first["id"], second["id"]}
    with pytest.raises(sqlite3.IntegrityError):
        with store._tx() as db:
            db.execute("UPDATE assistant_home_conversations SET conversation_id = ? WHERE bot_id = ?", (foreign["id"], bot.id))
    with pytest.raises(sqlite3.IntegrityError):
        with store._tx() as db:
            db.execute("UPDATE conversations SET bot_id = ? WHERE id = ?", (other.id, first["id"]))


def test_archived_home_stays_history_instead_of_being_silently_restored(store):
    bot = store.create_bot(Bot(name="hutch", tools=[]))
    home_id, _ = store.ensure_assistant_home_conversation(bot.id)
    with store._tx() as db:
        db.execute("UPDATE conversations SET archived = 1 WHERE id = ?", (home_id,))
    assert store.assistant_home_conversation_id(bot.id) is None
    next_home, created = store.ensure_assistant_home_conversation(bot.id)
    assert created and next_home != home_id
    assert store.get_conversation(home_id)["archived"]


@pytest.mark.parametrize("flag", ["archived", "is_legacy"])
def test_home_never_adopts_archived_or_legacy_history(store, flag):
    bot = store.create_bot(Bot(name="hutch", tools=[]))
    history = conversation(store, bot, "retained-history")
    with store._tx() as db:
        db.execute(f"UPDATE conversations SET {flag} = 1 WHERE id = ?", (history["id"],))
    with pytest.raises(ValueError):
        store.ensure_assistant_home_conversation(bot.id, history["id"])
    home_id, created = store.ensure_assistant_home_conversation(bot.id)
    assert created and home_id != history["id"]
    assert store.get_conversation(history["id"])[flag]


def test_home_api_is_explicit_idempotent_and_starts_no_work(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    with TestClient(app) as client:
        bot = app.state.store.create_bot(Bot(name="hutch", model="ollama/fixture", tools=[]))
        url = f"/api/v1/bots/{bot.id}/home-conversation"
        assert client.get(url).json()["conversation"] is None
        assert app.state.store.list_conversations(bot.id) == []
        response = client.put(url, json={})
        assert response.status_code == 201, response.text
        home = response.json()["conversation"]
        assert home["bot_id"] == bot.id and home["message_count"] == 0
        repeated = client.put(url, json={})
        assert repeated.status_code == 200 and repeated.json()["conversation"]["id"] == home["id"]
        assert client.get(url).json()["conversation"]["id"] == home["id"]
        assert client.put(url, json={"model": "other/route"}).status_code == 422
        assert app.state.store.list_runs(limit=10) == []
        assert app.state.store.get_bot(bot.id).model == "ollama/fixture"


def test_home_migration_preserves_existing_chat_without_automatic_binding(config):
    previous = Store(config, maintenance=True)
    bot = previous.create_bot(Bot(name="hutch", tools=[]))
    existing = conversation(previous, bot, "before-upgrade")
    previous.close()
    # Reconstruct the exact preceding schema: migration 77 adds only these
    # pointers/triggers. No user conversation is backfilled by the upgrade.
    with sqlite3.connect(config.db_path) as database:
        database.execute("DROP TRIGGER assistant_home_conversation_scope")
        database.execute("DROP TABLE assistant_home_conversations")
        database.execute("PRAGMA user_version = 76")
    upgraded = Store(config, maintenance=True)
    try:
        assert upgraded.assistant_home_conversation_id(bot.id) is None
        assert upgraded.get_conversation(existing["id"])["title"] == "before-upgrade"
        assert upgraded.ensure_assistant_home_conversation(bot.id) == (existing["id"], True)
        assert config.db_path.with_suffix(".db.bak-v76").is_file()
    finally:
        upgraded.close()


def test_replaying_home_migration_keeps_existing_home_and_scope_guards(store):
    from hutch.store import _migrate_77
    bot = store.create_bot(Bot(name="replayed-home", tools=[]))
    other = store.create_bot(Bot(name="other-home", tools=[]))
    home, _ = store.ensure_assistant_home_conversation(bot.id)
    _migrate_77(store._db)
    store._db.commit()
    assert store.assistant_home_conversation_id(bot.id) == home
    with pytest.raises(sqlite3.IntegrityError, match="ownership cannot change"):
        store._db.execute("UPDATE conversations SET bot_id=? WHERE id=?", (other.id, home))
    store._db.rollback()


def test_archiving_a_home_does_not_promote_unrelated_history_to_the_main_chat(store):
    bot = store.create_bot(Bot(name="fresh-after-archive", tools=[]))
    home, _ = store.ensure_assistant_home_conversation(bot.id)
    older = conversation(store, bot, "Separate research history")
    with store._tx() as db:
        db.execute("UPDATE conversations SET archived=1 WHERE id=?", (home,))
    replacement, created = store.ensure_assistant_home_conversation(bot.id)
    assert created and replacement not in {home, older["id"]}
    assert store.list_conversation_messages(replacement) == []
    assert not store.get_conversation(older["id"])["archived"]
    assert store.get_conversation(home)["archived"]
