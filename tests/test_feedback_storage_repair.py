"""An additive repair reopens retained conversations without resetting user state."""
import sqlite3

import pytest

from hutch.models import Bot, Run, Task
from hutch.store import Store, SCHEMA_VERSION, _migrate_78


def test_feedback_repair_preserves_existing_rows_and_is_idempotent():
    with sqlite3.connect(":memory:") as db:
        _migrate_78(db)
        db.execute("INSERT INTO persona_feedback VALUES ('conv','msg',1,2,'needs_work','accuracy','now')")
        _migrate_78(db)
        assert db.execute("SELECT revision,rating,reason FROM persona_feedback").fetchone() == (2, "needs_work", "accuracy")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO persona_feedback VALUES ('conv','bad',1,1,'helpful','accuracy','now')")


def test_missing_feedback_table_in_v77_gets_backup_and_keeps_conversation_history(config):
    original = Store(config)
    bot = original.create_bot(Bot(name="retained-reader", tools=[]))
    conv, _ = original.create_conversation(bot.id, "Retained chat", idem_key="retained", request_hash="retained")
    prompt = "Keep this existing conversation."
    original.submit_conversation_message(conv["id"], prompt, Run(bot_id=bot.id, prompt=prompt),
        Task(bot_id=bot.id, prompt=prompt), idem_key="retained-message", request_hash="retained-message")
    assert original.list_conversation_messages(conv["id"])[0]["content"] == prompt
    original._db.execute("DROP TABLE persona_feedback")
    original._db.execute("PRAGMA user_version=77")
    original._db.commit()
    with pytest.raises(sqlite3.OperationalError, match="persona_feedback"):
        original.list_conversation_messages(conv["id"])
    original.close()
    repaired = Store(config)
    try:
        assert repaired.schema_version == SCHEMA_VERSION
        messages = repaired.list_conversation_messages(conv["id"])
        assert messages[0]["content"] == prompt and messages[0]["persona_feedback"] is None
        assert repaired.get_bot(bot.id).name == "retained-reader"
        assert not repaired._db.execute("PRAGMA foreign_key_check").fetchall()
        backup = config.db_path.with_suffix(".db.bak-v77")
        assert backup.exists()
        with sqlite3.connect(backup) as db:
            assert db.execute("PRAGMA user_version").fetchone()[0] == 77
            assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='persona_feedback'").fetchall()
            assert db.execute("SELECT content FROM messages").fetchone()[0] == prompt
    finally:
        repaired.close()


def test_v78_legacy_profile_missing_persona_column_is_repaired_without_history_reset(config):
    original = Store(config)
    bot = original.create_bot(Bot(name="legacy-style-reader", tools=[]))
    conv, _ = original.create_conversation(bot.id, "Retained legacy chat", idem_key="legacy", request_hash="legacy")
    prompt = "Preserve this history during response-style repair."
    original.submit_conversation_message(conv["id"], prompt, Run(bot_id=bot.id, prompt=prompt),
        Task(bot_id=bot.id, prompt=prompt), idem_key="legacy-turn", request_hash="legacy-turn")
    original._db.execute("ALTER TABLE conversations DROP COLUMN persona")
    original._db.execute("PRAGMA user_version=78")
    original._db.commit()
    with pytest.raises(sqlite3.OperationalError, match="persona"):
        original.read_conversation_persona(conv["id"])
    original.close()
    repaired = Store(config)
    try:
        assert repaired.read_conversation_persona(conv["id"]) == (None, 0)
        assert repaired.list_conversation_messages(conv["id"])[0]["content"] == prompt
        assert repaired.get_bot(bot.id).name == "legacy-style-reader"
        assert repaired._db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        backup = config.db_path.with_suffix(".db.bak-v78")
        assert backup.exists()
        with sqlite3.connect(backup) as db:
            assert "persona" not in {row[1] for row in db.execute("PRAGMA table_info(conversations)")}
            assert db.execute("SELECT content FROM messages").fetchone()[0] == prompt
    finally:
        repaired.close()


def test_persona_repair_keeps_existing_style_and_replays_safely(store):
    from hutch.persona import PersonaStyle, encode_persona_state
    from hutch.store import _migrate_79
    bot = store.create_bot(Bot(name="styled-reader", tools=[]))
    conv, _ = store.create_conversation(bot.id, "Styled chat", idem_key="style", request_hash="style")
    encoded = encode_persona_state(PersonaStyle(), 3)
    with store._tx() as db:
        db.execute("UPDATE conversations SET persona=? WHERE id=?", (encoded, conv["id"]))
        _migrate_79(db)
        _migrate_79(db)
        assert db.execute("SELECT persona FROM conversations WHERE id=?", (conv["id"],)).fetchone()[0] == encoded
    assert store.read_conversation_persona(conv["id"])[1] == 3
