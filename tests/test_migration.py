"""A database written by the baseline (schema v4) upgrades to the current schema without losing anything.

tests/fixtures/state_v4.db.fixture was produced by the baseline code (commit b3e4b15, SCHEMA_VERSION 4) with two bots, a
schedule, memory, a sticky allow, finished runs with hash-chained events, a usage row, a pending approval, a queued run, and a
run that was 'running' when its process died (a legacy orphan).
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from hutch.config import get_config, hutchConfig
from hutch.engine import Engine
from hutch.lifecycle import IllegalTransition
from hutch.models import RunStatus
from hutch.store import (SCHEMA_VERSION, Store, _migrate_25, _migrate_26, _migrate_27, _migrate_28,
                         _migrate_29, _migrate_30, _migrate_31, _migrate_32, _migrate_33, _migrate_34, _migrate_45,
                         _migrate_35, _migrate_37, _migrate_40, _migrate_41, _migrate_46, _migrate_47,
                         _migrate_48, _migrate_57, _migrate_58, _migrate_59)

FIXTURE = Path(__file__).parent / "fixtures" / "state_v4.db.fixture"
BRIEFING, SWEEPER = "bot_7eef563ee683", "bot_611a4b96d543"
FINISHED_1, FINISHED_2, ORPHAN, QUEUED = "run_582f4cc75ea4", "run_fa7f70664c38", "run_3cefb894fd73", "run_e169d5380ff5"


def test_v57_preserves_existing_workflow_mode_and_adds_revisioned_conversation_policy():
    db = sqlite3.connect(":memory:")
    try:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("CREATE TABLE bots (id TEXT PRIMARY KEY, doc TEXT NOT NULL)")
        db.execute("INSERT INTO bots VALUES ('legacy', '{\"name\":\"legacy\"}')")
        db.execute("INSERT INTO bots VALUES ('explicit', '{\"name\":\"explicit\",\"workflow_mode\":\"off\"}')")
        db.execute("CREATE TABLE conversations (id TEXT PRIMARY KEY)")
        db.execute("INSERT INTO conversations VALUES ('conversation-a')")
        _migrate_57(db)
        _migrate_57(db)
        assert json.loads(db.execute("SELECT doc FROM bots WHERE id='legacy'").fetchone()[0])["workflow_mode"] == "off"
        assert json.loads(db.execute("SELECT doc FROM bots WHERE id='explicit'").fetchone()[0])["workflow_mode"] == "off"
        db.execute("INSERT INTO conversation_workflow_policies VALUES ('conversation-a', 'suggest', 1, 'now')")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO conversation_workflow_policies VALUES ('missing', 'auto', 1, 'now')")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO conversation_workflow_policies VALUES ('conversation-a', 'unknown', 2, 'now')")
        assert SCHEMA_VERSION >= 57
    finally:
        db.close()


def test_v58_amendment_history_preserves_revision_links_and_is_idempotent():
    db = sqlite3.connect(":memory:")
    try:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("CREATE TABLE workflow_runs (id TEXT PRIMARY KEY)")
        db.execute("CREATE TABLE workflow_revisions (id TEXT PRIMARY KEY)")
        db.execute("INSERT INTO workflow_runs VALUES ('wrun-a')")
        db.execute("INSERT INTO workflow_revisions VALUES ('wrev-before')")
        db.execute("INSERT INTO workflow_revisions VALUES ('wrev-after')")

        _migrate_58(db)
        _migrate_58(db)
        db.execute("""INSERT INTO workflow_amendment_history
                      (id, workflow_run_id, previous_revision_id, adopted_revision_id,
                       previous_attempt_run_id, previous_status, previous_plan_hash,
                       adopted_plan_hash, preview_json, nodes_json, questions_json, result_json, created_at)
                      VALUES ('wamend-a', 'wrun-a', 'wrev-before', 'wrev-after', 'run-a', 'waiting',
                              'before', 'after', '{}', '[]', '[]', '{}', 'now')""")
        assert db.execute("SELECT COUNT(*) FROM workflow_amendment_history").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("DELETE FROM workflow_revisions WHERE id='wrev-before'")
        assert SCHEMA_VERSION >= 58
    finally:
        db.close()


def test_v59_workflow_pause_defaults_to_unpaused_and_is_idempotent():
    db = sqlite3.connect(":memory:")
    try:
        db.execute("CREATE TABLE workflow_runs (id TEXT PRIMARY KEY)")
        db.execute("INSERT INTO workflow_runs VALUES ('wrun-old')")
        _migrate_59(db)
        _migrate_59(db)
        assert db.execute("SELECT pause_requested FROM workflow_runs WHERE id='wrun-old'").fetchone()[0] == 0
        db.execute("UPDATE workflow_runs SET pause_requested=1 WHERE id='wrun-old'")
        assert db.execute("SELECT pause_requested FROM workflow_runs WHERE id='wrun-old'").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE workflow_runs SET pause_requested=2 WHERE id='wrun-old'")
        assert SCHEMA_VERSION >= 59
    finally:
        db.close()


def test_outlook_mail_grant_migration_adds_account_scoped_bot_access():
    db = sqlite3.connect(":memory:")
    try:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("CREATE TABLE bots (id TEXT PRIMARY KEY)")
        db.execute("INSERT INTO bots VALUES ('bot-1')")
        _migrate_35(db)
        db.execute("INSERT INTO outlook_mail_grants VALUES ('bot-1', 'msmail_000000000000000000000001', 'now')")
        row = db.execute("SELECT bot_id, account_id, granted_at FROM outlook_mail_grants").fetchone()
        assert row == ("bot-1", "msmail_000000000000000000000001", "now")
        assert SCHEMA_VERSION >= 35
    finally:
        db.close()


def test_model_capability_observation_migration_adds_immutable_route_evidence():
    db = sqlite3.connect(":memory:")
    try:
        db.execute("CREATE TABLE runs (id TEXT PRIMARY KEY)")
        db.execute("INSERT INTO runs VALUES ('run-before-migration')")
        _migrate_37(db)
        db.execute("INSERT INTO model_capability_observations "
                   "(run_id, provider, account_id, model, route_revision, capability, source_tool, observed_at) "
                   "VALUES ('run-before-migration', 'local-route', 'account-a', 'model-a', '" + "a" * 64 + "', "
                   "'function_tool_calls', 'list_files', '2026-10-09T00:00:00+00:00')")
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute("UPDATE model_capability_observations SET model = 'model-b'")
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute("DELETE FROM model_capability_observations")
        assert SCHEMA_VERSION >= 37
    finally:
        db.close()


def test_v39_workspace_settings_gain_durable_schedule_pause_and_outbox():
    from hutch import durable_changes

    db = sqlite3.connect(":memory:")
    try:
        db.execute("CREATE TABLE workspace_settings (id INTEGER PRIMARY KEY, coordinator_bot_id TEXT, updated_at TEXT NOT NULL)")
        db.execute("INSERT INTO workspace_settings VALUES (1, NULL, '2026-10-01T00:00:00+00:00')")
        db.execute("""CREATE TABLE resource_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT, previous_id INTEGER NOT NULL,
            resource TEXT NOT NULL, resource_id TEXT NOT NULL,
            operation TEXT NOT NULL, ts TEXT NOT NULL, context TEXT NOT NULL)""")
        db.execute("CREATE TABLE resource_outbox_meta (singleton INTEGER PRIMARY KEY, epoch TEXT NOT NULL, tail_id INTEGER NOT NULL DEFAULT 0)")
        db.execute("INSERT INTO resource_outbox_meta VALUES (1, 'fixture-epoch', 0)")
        durable_changes.install_resources(db, (("workspace_settings", "workspace", "id",
                                                ("coordinator_bot_id", "updated_at"), ()),))

        _migrate_40(db)
        columns = {row[1] for row in db.execute("PRAGMA table_info(workspace_settings)")}
        assert {"schedules_paused", "schedules_updated_at"} <= columns
        row = db.execute("SELECT schedules_paused, schedules_updated_at FROM workspace_settings WHERE id = 1").fetchone()
        assert row == (0, "2026-10-01T00:00:00+00:00")

        db.execute("UPDATE workspace_settings SET schedules_paused = 1, schedules_updated_at = '2026-10-02T00:00:00+00:00' WHERE id = 1")
        change = db.execute("SELECT resource, resource_id, operation, context FROM resource_outbox").fetchone()
        assert tuple(change) == ("workspace", "1", "updated", "{}")
        assert SCHEMA_VERSION >= 40
    finally:
        db.close()


def test_v41_workspace_specialist_roster_is_empty_and_durably_invalidated():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        db.execute("CREATE TABLE bots (id TEXT PRIMARY KEY)")
        db.execute("INSERT INTO bots VALUES ('specialist-a')")
        db.execute("INSERT INTO bots VALUES ('coordinator-a')")
        db.execute("CREATE TABLE workspace_settings (id INTEGER PRIMARY KEY, coordinator_bot_id TEXT)")
        db.execute("INSERT INTO workspace_settings VALUES (1, 'coordinator-a')")
        db.execute("""CREATE TABLE resource_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT, previous_id INTEGER NOT NULL,
            resource TEXT NOT NULL, resource_id TEXT NOT NULL,
            operation TEXT NOT NULL, ts TEXT NOT NULL, context TEXT NOT NULL)""")
        db.execute("CREATE TABLE resource_outbox_meta (singleton INTEGER PRIMARY KEY, epoch TEXT NOT NULL, tail_id INTEGER NOT NULL DEFAULT 0)")
        db.execute("INSERT INTO resource_outbox_meta VALUES (1, 'fixture-epoch', 0)")

        _migrate_41(db)
        assert db.execute("SELECT COUNT(*) FROM workspace_specialists").fetchone()[0] == 0
        with pytest.raises(sqlite3.IntegrityError, match="cannot be an approved specialist"):
            db.execute("INSERT INTO workspace_specialists VALUES ('coordinator-a', '2026-10-09T00:00:00+00:00')")
        db.execute("INSERT INTO workspace_specialists VALUES ('specialist-a', '2026-10-09T00:00:00+00:00')")
        assert tuple(db.execute("SELECT resource, operation FROM resource_outbox").fetchone()) == ("workspace", "created")
        db.execute("UPDATE workspace_settings SET coordinator_bot_id='specialist-a' WHERE id=1")
        db.execute("DELETE FROM bots WHERE id='specialist-a'")
        assert db.execute("SELECT COUNT(*) FROM workspace_specialists").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM resource_outbox WHERE resource='workspace'").fetchone()[0] == 2
        assert SCHEMA_VERSION >= 41
    finally:
        db.close()


def test_v45_calendar_grants_default_to_read_only_and_store_explicit_event_creation():
    db = sqlite3.connect(":memory:")
    try:
        db.executescript("""
            CREATE TABLE google_calendar_grants (
                bot_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, calendar_id TEXT NOT NULL,
                calendar_name TEXT NOT NULL, granted_at TEXT NOT NULL);
            INSERT INTO google_calendar_grants VALUES ('bot-a', 'account-a', 'primary', 'Personal', 'now');
        """)
        _migrate_45(db)
        assert db.execute("SELECT allow_event_creation FROM google_calendar_grants WHERE bot_id='bot-a'").fetchone()[0] == 0
        db.execute("UPDATE google_calendar_grants SET allow_event_creation=1 WHERE bot_id='bot-a'")
        assert db.execute("SELECT allow_event_creation FROM google_calendar_grants WHERE bot_id='bot-a'").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE google_calendar_grants SET allow_event_creation=2 WHERE bot_id='bot-a'")
        assert SCHEMA_VERSION >= 45
    finally:
        db.close()


def test_v46_outlook_send_grants_are_empty_and_separate_from_read_grants():
    db = sqlite3.connect(":memory:")
    try:
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript("""
            CREATE TABLE bots (id TEXT PRIMARY KEY);
            INSERT INTO bots VALUES ('bot-a');
            CREATE TABLE outlook_mail_grants (bot_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, granted_at TEXT NOT NULL);
            INSERT INTO outlook_mail_grants VALUES ('bot-a', 'msmail_000000000000000000000001', 'now');
        """)
        _migrate_46(db)
        _migrate_46(db)
        assert db.execute("SELECT COUNT(*) FROM outlook_mail_send_grants").fetchone()[0] == 0
        columns = [row[1] for row in db.execute("PRAGMA table_info(outlook_mail_send_grants)")]
        assert columns == ["bot_id", "account_id", "account_label", "granted_at"]
        db.execute("INSERT INTO outlook_mail_send_grants VALUES ('bot-a', 'mssend_000000000000000000000001', 'Work sender', 'now')")
        assert db.execute("SELECT account_id FROM outlook_mail_grants").fetchone()[0].startswith("msmail_")
        assert db.execute("SELECT account_id FROM outlook_mail_send_grants").fetchone()[0].startswith("mssend_")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO outlook_mail_send_grants VALUES ('missing-bot', 'x', '', 'now')")
        assert SCHEMA_VERSION >= 46
    finally:
        db.close()


def test_v47_gmail_send_grants_are_empty_and_separate_from_read_grants():
    db = sqlite3.connect(":memory:")
    try:
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript("""
            CREATE TABLE bots (id TEXT PRIMARY KEY);
            INSERT INTO bots VALUES ('bot-a');
            CREATE TABLE google_mail_grants (bot_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, granted_at TEXT NOT NULL);
            INSERT INTO google_mail_grants VALUES ('bot-a', 'gmail_000000000000000000000001', 'now');
        """)
        _migrate_47(db)
        _migrate_47(db)
        assert db.execute("SELECT COUNT(*) FROM google_mail_send_grants").fetchone()[0] == 0
        columns = [row[1] for row in db.execute("PRAGMA table_info(google_mail_send_grants)")]
        assert columns == ["bot_id", "account_id", "account_label", "granted_at"]
        db.execute("INSERT INTO google_mail_send_grants VALUES ('bot-a', 'gmail_send_000000000000000000000001', 'Work sender', 'now')")
        assert db.execute("SELECT account_id FROM google_mail_grants").fetchone()[0].startswith("gmail_")
        assert db.execute("SELECT account_id FROM google_mail_send_grants").fetchone()[0].startswith("gmail_send_")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO google_mail_send_grants VALUES ('missing-bot', 'x', '', 'now')")
        assert SCHEMA_VERSION >= 47
    finally:
        db.close()


def test_v48_outlook_calendar_write_grants_are_empty_and_separate_from_read_grants():
    db = sqlite3.connect(":memory:")
    try:
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript("""
            CREATE TABLE bots (id TEXT PRIMARY KEY);
            INSERT INTO bots VALUES ('bot-a');
            CREATE TABLE outlook_calendar_grants (
                bot_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, calendar_id TEXT NOT NULL,
                calendar_name TEXT NOT NULL, granted_at TEXT NOT NULL);
            INSERT INTO outlook_calendar_grants VALUES
                ('bot-a', 'mscal_000000000000000000000001', 'calendar-read', 'Work', 'now');
        """)
        _migrate_48(db)
        _migrate_48(db)
        assert db.execute("SELECT COUNT(*) FROM outlook_calendar_write_grants").fetchone()[0] == 0
        columns = [row[1] for row in db.execute("PRAGMA table_info(outlook_calendar_write_grants)")]
        assert columns == ["bot_id", "account_id", "account_label", "calendar_id", "calendar_name", "granted_at"]
        db.execute("INSERT INTO outlook_calendar_write_grants VALUES "
                   "('bot-a', 'mscalw_000000000000000000000001', 'Work events', 'calendar-write', 'Work', 'now')")
        assert db.execute("SELECT account_id FROM outlook_calendar_grants").fetchone()[0].startswith("mscal_")
        assert db.execute("SELECT account_id FROM outlook_calendar_write_grants").fetchone()[0].startswith("mscalw_")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO outlook_calendar_write_grants VALUES "
                       "('missing-bot', 'x', '', 'calendar-write', 'Work', 'now')")
        db.execute("DELETE FROM bots WHERE id='bot-a'")
        assert db.execute("SELECT COUNT(*) FROM outlook_calendar_write_grants").fetchone()[0] == 0
        assert SCHEMA_VERSION >= 48
    finally:
        db.close()


def test_reply_reference_migration_preserves_old_rows_and_guards_scope():
    assert SCHEMA_VERSION >= 26
    db = sqlite3.connect(":memory:")
    try:
        db.execute("CREATE TABLE bots (id TEXT PRIMARY KEY)")
        db.execute("CREATE TABLE runs (id TEXT PRIMARY KEY)")
        db.execute("CREATE TABLE conversations (id TEXT PRIMARY KEY)")
        db.execute("CREATE TABLE messages (id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, seq INTEGER NOT NULL, "
                   "run_id TEXT NOT NULL DEFAULT '', role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL, "
                   "UNIQUE(conversation_id, seq))")
        db.execute("INSERT INTO messages VALUES ('old-assistant', 'chat-a', 1, '', 'assistant', 'prior answer', 'now')")
        db.execute("INSERT INTO messages VALUES ('old-user', 'chat-a', 2, '', 'user', 'legacy question', 'now')")
        db.execute("INSERT INTO messages VALUES ('other-assistant', 'chat-b', 1, '', 'assistant', 'private', 'now')")
        _migrate_25(db)
        _migrate_26(db)
        assert db.execute("SELECT reply_to_message_id FROM messages WHERE id = 'old-user'").fetchone()[0] is None
        db.execute("INSERT INTO messages (id, conversation_id, seq, role, content, created_at, reply_to_message_id) "
                   "VALUES ('new-user', 'chat-a', 3, 'user', 'what?', 'now', 'old-assistant')")
        with pytest.raises(sqlite3.IntegrityError, match="reply target"):
            db.execute("INSERT INTO messages (id, conversation_id, seq, role, content, created_at, reply_to_message_id) "
                       "VALUES ('cross-chat', 'chat-a', 4, 'user', 'what?', 'now', 'other-assistant')")
        with pytest.raises(sqlite3.IntegrityError, match="reply target"):
            db.execute("INSERT INTO messages (id, conversation_id, seq, role, content, created_at, reply_to_message_id) "
                       "VALUES ('reply-to-user', 'chat-a', 4, 'user', 'what?', 'now', 'old-user')")
        with pytest.raises(sqlite3.IntegrityError, match="reply target"):
            db.execute("UPDATE messages SET reply_to_message_id = 'other-assistant' WHERE id = 'new-user'")
    finally:
        db.close()


def test_v25_choice_migration_preserves_existing_messages():
    db = sqlite3.connect(":memory:")
    try:
        db.executescript("""
            CREATE TABLE bots (id TEXT PRIMARY KEY);
            CREATE TABLE runs (id TEXT PRIMARY KEY);
            CREATE TABLE conversations (id TEXT PRIMARY KEY);
            CREATE TABLE messages (
                id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, seq INTEGER NOT NULL,
                run_id TEXT NOT NULL DEFAULT '', role TEXT NOT NULL, content TEXT NOT NULL,
                created_at TEXT NOT NULL, reply_to_message_id TEXT,
                UNIQUE(conversation_id, seq));
            INSERT INTO bots VALUES ('bot-a');
            INSERT INTO runs VALUES ('run-a');
            INSERT INTO conversations VALUES ('chat-a');
            INSERT INTO messages VALUES ('answer-a', 'chat-a', 1, 'run-a', 'assistant', 'prior answer', 'now', NULL);
        """)
        _migrate_26(db)
        columns = {row[1] for row in db.execute("PRAGMA table_info(messages)")}
        assert "choice_question_id" in columns
        assert db.execute("SELECT content, choice_question_id FROM messages WHERE id='answer-a'").fetchone() == (
            "prior answer", None)
        assert db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='conversation_questions'").fetchone()
        assert db.execute("SELECT COUNT(*) FROM conversation_questions").fetchone()[0] == 0
    finally:
        db.close()


def test_v26_calendar_grant_migration_is_empty_and_idempotent():
    db = sqlite3.connect(":memory:")
    try:
        db.execute("CREATE TABLE bots (id TEXT PRIMARY KEY)")
        _migrate_27(db)
        _migrate_27(db)
        columns = [row[1] for row in db.execute("PRAGMA table_info(google_calendar_grants)")]
        assert columns == ["bot_id", "account_id", "calendar_id", "calendar_name", "granted_at"]
        assert db.execute("SELECT COUNT(*) FROM google_calendar_grants").fetchone()[0] == 0
    finally:
        db.close()


def test_v32_outlook_calendar_grant_migration_is_empty_and_idempotent():
    db = sqlite3.connect(":memory:")
    try:
        db.execute("CREATE TABLE bots (id TEXT PRIMARY KEY)")
        _migrate_33(db)
        _migrate_33(db)
        columns = [row[1] for row in db.execute("PRAGMA table_info(outlook_calendar_grants)")]
        assert columns == ["bot_id", "account_id", "calendar_id", "calendar_name", "granted_at"]
        assert db.execute("SELECT COUNT(*) FROM outlook_calendar_grants").fetchone()[0] == 0
    finally:
        db.close()


def test_v34_continuation_lineage_guard_requires_a_committed_task_checkpoint():
    db = sqlite3.connect(":memory:")
    try:
        db.executescript("""
            CREATE TABLE workspace_tasks (
                id TEXT PRIMARY KEY, parent_conversation_id TEXT NOT NULL,
                target_bot_id TEXT NOT NULL, child_run_id TEXT NOT NULL);
            CREATE TABLE events (id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, type TEXT NOT NULL, data TEXT NOT NULL);
            CREATE TABLE workspace_task_checkpoints (
                workspace_task_id TEXT NOT NULL, child_run_id TEXT NOT NULL,
                event_id INTEGER NOT NULL, kind TEXT NOT NULL);
            CREATE TABLE runs (id TEXT PRIMARY KEY, status TEXT NOT NULL);
            INSERT INTO workspace_tasks VALUES ('prior', 'parent', 'specialist', 'run-prior');
            INSERT INTO workspace_tasks VALUES ('continued', 'parent', 'specialist', 'run-new');
            INSERT INTO events VALUES (100, 'run-prior', 'message', '{"role":"assistant","content":"checkpoint"}');
            INSERT INTO runs VALUES ('run-prior', 'failed');
        """)
        _migrate_34(db)
        with pytest.raises(sqlite3.IntegrityError, match="committed task/assistant checkpoint"):
            db.execute("INSERT INTO workspace_task_continuations VALUES ('continued', 'prior', 100, 'now')")
        db.execute("INSERT INTO workspace_task_checkpoints VALUES ('prior', 'run-prior', 100, 'assistant_message')")
        db.execute("INSERT INTO workspace_task_continuations VALUES ('continued', 'prior', 100, 'now')")
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute("UPDATE workspace_task_continuations SET created_at='later' WHERE task_id='continued'")
        with pytest.raises(sqlite3.IntegrityError, match="removed only with its task"):
            db.execute("DELETE FROM workspace_task_continuations WHERE task_id='continued'")
    finally:
        db.close()


def test_v27_workspace_coordinator_migration_tracks_selection_and_bot_deletion():
    db = sqlite3.connect(":memory:")
    db.execute("PRAGMA foreign_keys=ON")
    try:
        db.executescript("""
            CREATE TABLE bots (id TEXT PRIMARY KEY);
            CREATE TABLE resource_outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT, previous_id INTEGER NOT NULL,
                resource TEXT NOT NULL, resource_id TEXT NOT NULL, operation TEXT NOT NULL,
                ts TEXT NOT NULL, context TEXT NOT NULL);
            CREATE TABLE resource_outbox_meta (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1), epoch TEXT NOT NULL, tail_id INTEGER NOT NULL);
            CREATE TABLE conversations (id TEXT PRIMARY KEY);
            INSERT INTO resource_outbox_meta VALUES (1, 'epoch', 0);
            INSERT INTO bots VALUES ('coordinator-bot');
        """)
        _migrate_28(db)
        assert db.execute("SELECT coordinator_bot_id FROM workspace_settings WHERE id=1").fetchone()[0] is None
        db.execute("UPDATE workspace_settings SET coordinator_bot_id='coordinator-bot' WHERE id=1")
        assert db.execute("SELECT resource, operation FROM resource_outbox ORDER BY id DESC LIMIT 1").fetchone() == (
            "workspace", "updated")
        db.execute("DELETE FROM bots WHERE id='coordinator-bot'")
        assert db.execute("SELECT coordinator_bot_id FROM workspace_settings WHERE id=1").fetchone()[0] is None
        assert db.execute("SELECT COUNT(*) FROM resource_outbox WHERE resource='workspace'").fetchone()[0] == 2
        _migrate_29(db)
        assert db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='workspace_tasks'").fetchone()
        db.executescript("""
            CREATE TABLE messages (
                id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, role TEXT NOT NULL,
                run_id TEXT NOT NULL, content TEXT NOT NULL);
            CREATE TABLE runs (id TEXT PRIMARY KEY, status TEXT NOT NULL);
            CREATE TABLE events (
                id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, seq INTEGER NOT NULL,
                type TEXT NOT NULL, data TEXT NOT NULL, ts TEXT NOT NULL);
        """)
        _migrate_30(db)
        columns = {row[1] for row in db.execute("PRAGMA table_info(messages)")}
        assert {"workspace_task_result_id", "workspace_task_result_message_id",
                "workspace_task_result_display_name", "workspace_task_result_content",
                "workspace_task_result_truncated"} <= columns
        assert db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' "
                          "AND name='messages_workspace_task_result_insert'").fetchone()
        db.executemany("INSERT INTO conversations VALUES (?)", [("parent-chat",), ("child-chat",)])
        db.executemany("INSERT INTO runs VALUES (?, ?)", [("parent-run", "succeeded"), ("child-run", "succeeded")])
        db.executemany("INSERT INTO messages(id, conversation_id, role, run_id, content) VALUES (?, ?, ?, ?, ?)", [
            ("source-user", "parent-chat", "user", "parent-run", "Research this."),
            ("source-answer", "parent-chat", "assistant", "parent-run", "Use a specialist."),
            ("child-user", "child-chat", "user", "child-run", "Reviewed specialist request."),
            ("child-answer", "child-chat", "assistant", "child-run", "Result."),
        ])
        db.execute("""INSERT INTO workspace_tasks(
            id, parent_conversation_id, source_run_id, source_user_message_id, source_assistant_message_id,
            target_bot_id, target_display_name, original_request, proposed_brief, task_brief, assumptions,
            child_conversation_id, child_run_id, created_at)
            VALUES ('task-a', 'parent-chat', 'parent-run', 'source-user', 'source-answer', 'bot-b',
                    'Specialist', 'Research this.', 'Use a specialist.', 'Reviewed specialist request.', '',
                    'child-chat', 'child-run', '2026-10-09T00:00:00Z')""")
        db.executemany("INSERT INTO events VALUES (?, 'child-run', ?, ?, ?, ?)", [
            (1, 1, "message", json.dumps({"role": "user", "content": "do not copy this prompt"}), "2026-10-09T00:00:01Z"),
            (2, 2, "status", json.dumps({"status": "running"}), "2026-10-09T00:00:02Z"),
            (3, 3, "approval_request", json.dumps({"approval_id": "approval-a", "arguments": {"secret": "x"}}),
             "2026-10-09T00:00:03Z"),
            (4, 4, "status", json.dumps({"status": "succeeded"}), "2026-10-09T00:00:04Z"),
        ])
        _migrate_31(db)
        checkpoint_columns = {row[1] for row in db.execute("PRAGMA table_info(workspace_task_checkpoints)")}
        assert {"workspace_task_id", "child_run_id", "event_id", "event_seq", "event_type",
                "run_status", "kind", "recovery_state", "reference_id", "created_at"} <= checkpoint_columns
        assert all(row[2] != "events" for row in db.execute("PRAGMA foreign_key_list(workspace_task_checkpoints)")), \
            "checkpoint markers remain readable if the source event stream is compacted"
        assert db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' "
                          "AND name='workspace_task_checkpoint_event_insert'").fetchone()
        assert db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' "
                          "AND name='workspace_task_checkpoint_no_update'").fetchone()
        assert db.execute("SELECT checkpoint_count FROM workspace_tasks WHERE id='task-a'").fetchone()[0] == 4
        checkpoints = db.execute(
            "SELECT kind, run_status, recovery_state, reference_id FROM workspace_task_checkpoints "
            "WHERE workspace_task_id='task-a' ORDER BY event_seq").fetchall()
        assert [tuple(row) for row in checkpoints] == [
            ("task_submitted", "pending", "queued", ""),
            ("status_changed", "running", "active", ""),
            ("approval_requested", "running", "active", "approval-a"),
            ("status_changed", "succeeded", "complete", ""),
        ]
        assert "do not copy this prompt" not in json.dumps([tuple(row) for row in checkpoints])
        assert "secret" not in json.dumps([tuple(row) for row in checkpoints])
        with pytest.raises(sqlite3.IntegrityError, match="checkpoints are immutable"):
            db.execute("UPDATE workspace_task_checkpoints SET recovery_state='reconcile' WHERE event_seq=1")
        with pytest.raises(sqlite3.IntegrityError, match="removed only with their task"):
            db.execute("DELETE FROM workspace_task_checkpoints WHERE event_seq=1")
        db.execute("ALTER TABLE bots ADD COLUMN doc TEXT NOT NULL DEFAULT '{}'")
        db.execute("""CREATE TABLE memory_facts (
            id TEXT PRIMARY KEY, bot_id TEXT NOT NULL, scope_kind TEXT NOT NULL, scope_id TEXT NOT NULL,
            key TEXT NOT NULL, value TEXT NOT NULL, status TEXT NOT NULL, revision INTEGER NOT NULL,
            content_hash TEXT NOT NULL)""")
        _migrate_32(db)
        share_columns = {row[1] for row in db.execute("PRAGMA table_info(workspace_task_fact_shares)")}
        assert {"workspace_task_id", "source_fact_id", "source_bot_id", "source_display_name",
                "source_scope_kind", "source_scope_id", "fact_key", "fact_value", "fact_revision",
                "content_hash", "created_at"} <= share_columns
        assert db.execute("SELECT COUNT(*) FROM workspace_task_fact_shares").fetchone()[0] == 0
        db.execute("DELETE FROM workspace_tasks WHERE id='task-a'")
        assert db.execute("SELECT COUNT(*) FROM workspace_task_checkpoints").fetchone()[0] == 0
    finally:
        db.close()


@pytest.fixture()
def v4(config):
    config.ensure()
    shutil.copy(FIXTURE, config.db_path)
    return config


def test_the_fixture_really_is_schema_v4(v4):
    c = sqlite3.connect(v4.db_path)
    assert c.execute("PRAGMA user_version").fetchone()[0] == 4
    assert "fence" not in [r[1] for r in c.execute("PRAGMA table_info(runs)")]


def test_upgrade_preserves_bot_ids_schedules_memory_and_allows(v4):
    store = Store(v4)
    try:
        assert store.schema_version == SCHEMA_VERSION
        assert store._db.execute("SELECT coordinator_bot_id FROM workspace_settings WHERE id=1").fetchone()[0] is None
        assert store._db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='workspace_tasks'").fetchone()
        assert store._db.execute("SELECT COUNT(*) FROM workspace_specialists").fetchone()[0] == 0
        assert store._db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' "
                                 "AND name='messages_workspace_task_result_insert'").fetchone()
        assert store._db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='conversation_artifact_shares'").fetchone()
        assert store._db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' "
                                 "AND name='conversation_artifact_shares_source_insert_outbox'").fetchone()
        assert store._db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' "
                                 "AND name='conversation_artifact_shares_source_update_outbox'").fetchone()
        assert store._db.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                                 "AND name='human_wait_resumes'").fetchone()
        assert store._db.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                                 "AND name='code_handoffs'").fetchone()
        assert "runner_session" in {row[1] for row in store._db.execute("PRAGMA table_info(code_handoffs)")}
        assert store._db.execute("SELECT COUNT(*) FROM code_handoffs").fetchone()[0] == 0
        bots = {b.id: b for b in store.list_bots()}
        assert set(bots) == {BRIEFING, SWEEPER}                                  # ids unchanged
        briefing = bots[BRIEFING]
        assert briefing.name == "briefing" and briefing.display_name == "Briefing"
        assert briefing.schedule.cron == "0 9 * * 1"
        assert briefing.schedule.timezone == "Europe/London"
        assert briefing.schedules[0].id == f"schedule:{BRIEFING}"
        assert briefing.schedules[0] == briefing.schedule
        assert store._db.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                                 "AND name='schedule_occurrences_v20'").fetchone()
        identity = store._db.execute("SELECT bot_id, removed_at FROM schedule_identities WHERE schedule_id = ?",
                                     (f"schedule:{BRIEFING}",)).fetchone()
        assert identity["bot_id"] == BRIEFING and identity["removed_at"] == ""
        reserved_legacy_id = store._db.execute("SELECT 1 FROM schedule_identities WHERE schedule_id = ?",
                                               (f"schedule:{SWEEPER}",)).fetchone()
        assert reserved_legacy_id is not None
        assert {m.key: (m.value, m.source) for m in store.recall_all(BRIEFING)} == {
            "style": ("concise", "user"), "last-run": ("research briefing for: summarise this week", "bot")}
        assert store.list_sticky_allows(BRIEFING) == ["files:write"]
        assert store.kv_get(f"schedule:{BRIEFING}:last_fire") == "2026-10-05T09:00:00+00:00"   # the schedule position survives
        assert store.usage_tokens_since("mock", 10**9) == 3450      # the ledger written by the baseline, unchanged
        legacy = store._db.execute("SELECT provider, account_id FROM usage ORDER BY id LIMIT 1").fetchone()
        assert legacy["account_id"] == legacy["provider"] == "mock"  # pre-account usage retains its original grouping
        assert store._db.execute("SELECT COUNT(*) FROM usage_reservations").fetchone()[0] == 0
    finally:
        store.close()


def test_upgrade_preserves_transcripts_and_their_hash_chain(v4):
    store = Store(v4)
    try:
        for rid in (FINISHED_1, FINISHED_2):
            run = store.get_run(rid)
            assert run.status is RunStatus.succeeded and run.steps >= 3
            assert len(store.list_events(rid)) >= 5
            chain = store.verify_chain(rid)
            assert chain["ok"] and chain["checked"] >= 5 and chain["legacy"] == 0
    finally:
        store.close()


def test_upgrade_keeps_legacy_run_contexts_separate(v4):
    store = Store(v4)
    try:
        first = store.get_conversation(f"conv_legacy_{FINISHED_1}")
        second = store.get_conversation(f"conv_legacy_{FINISHED_2}")
        assert first and second and first["is_legacy"] and second["is_legacy"]
        assert first["id"] != second["id"] and first["bot_id"] != second["bot_id"]
        assert store.get_run(FINISHED_1).conversation_id == first["id"]
        first_messages = store.list_conversation_messages(first["id"])
        second_messages = store.list_conversation_messages(second["id"])
        assert first_messages[0]["role"] == second_messages[0]["role"] == "user"
        assert first_messages[0]["content"] != second_messages[0]["content"]
        assert all(message["run_id"] == FINISHED_1 for message in first_messages)
        assert all(message["run_id"] == FINISHED_2 for message in second_messages)
    finally:
        store.close()


def test_a_backup_is_written_before_the_upgrade(v4):
    Store(v4).close()
    assert (v4.state_dir / "hutch.db.bak-v4").exists()
    c = sqlite3.connect(v4.state_dir / "hutch.db.bak-v4")
    assert c.execute("PRAGMA user_version").fetchone()[0] == 4                  # the backup is the untouched original


def test_sqlite_backup_can_be_restored_and_upgraded(v4):
    Store(v4).close()
    restore = hutchConfig(state_dir=v4.state_dir / "restored")
    restore.ensure()
    source = sqlite3.connect(v4.state_dir / "hutch.db.bak-v4")
    destination = sqlite3.connect(restore.db_path)
    try:
        source.backup(destination)
    finally:
        destination.close(); source.close()
    recovered = Store(restore)
    try:
        assert recovered.schema_version == SCHEMA_VERSION
        assert recovered.get_bot(BRIEFING) is not None
        assert recovered.get_run(FINISHED_1).status is RunStatus.succeeded
    finally:
        recovered.close()


def test_old_task_rows_keep_their_meaning(v4):
    store = Store(v4)
    try:
        rows = store._db.execute("SELECT done, state FROM tasks ORDER BY done").fetchall()
        assert [(r["done"], r["state"]) for r in rows] == [(0, "queued"), (1, "done"), (1, "done")]
        assert [t.prompt for t in store.pending_tasks(BRIEFING)] == ["queued before the upgrade"]
    finally:
        store.close()


def test_a_legacy_orphan_is_recovered_by_the_pid_check_and_its_approval_expired(v4):
    store = Store(v4)
    try:
        orphan = store.get_run(ORPHAN)
        assert orphan.status is RunStatus.running and orphan.fence == 0 and orphan.lease_owner == ""
        recovered = Engine(v4, store).recover_orphans()
        assert [r.id for r in recovered] == [ORPHAN]
        fixed = store.get_run(ORPHAN)
        assert fixed.status is RunStatus.failed and fixed.exit_reason == "interrupted" and fixed.fence == 1
        assert store.pending_approvals() == []
        assert store.verify_chain(ORPHAN)["ok"]
    finally:
        store.close()


def test_a_run_queued_before_the_upgrade_runs_after_it(v4):
    store = Store(v4)
    try:
        engine = Engine(v4, store)
        engine.recover_orphans()                       # frees the briefing bot's rival, as a restart would
        engine.dispatch_pending()
        import time
        deadline = time.time() + 15
        while time.time() < deadline and store.get_run(QUEUED).status in (RunStatus.pending, RunStatus.running):
            time.sleep(0.1)
        assert store.get_run(QUEUED).status in (RunStatus.succeeded, RunStatus.waiting_approval, RunStatus.failed)
        assert store.get_run(QUEUED).fence >= 1        # it was claimed like any new run
    finally:
        store.close()


def test_running_the_upgrade_twice_changes_nothing(v4):
    Store(v4).close()
    first = sqlite3.connect(v4.db_path).execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    s = Store(v4)
    try:
        assert s.schema_version == SCHEMA_VERSION
    finally:
        s.close()
    assert sqlite3.connect(v4.db_path).execute("SELECT COUNT(*) FROM runs").fetchone()[0] == first


def test_a_database_from_a_newer_hutch_is_refused_not_downgraded(config):
    config.ensure()
    shutil.copy(FIXTURE, config.db_path)
    c = sqlite3.connect(config.db_path)
    c.execute("PRAGMA user_version = 99"); c.commit(); c.close()
    with pytest.raises(RuntimeError, match="newer than this hutch"):
        Store(config)


def test_v51_pending_specialist_questions_are_not_attachable_results():
    """Schema v51 keeps a waiting question out of the accepted-result record, in the database."""
    from hutch.store import _migrate_51

    db = sqlite3.connect(":memory:")
    try:
        db.execute("""CREATE TABLE messages (
            id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, seq INTEGER NOT NULL,
            run_id TEXT NOT NULL DEFAULT '', role TEXT NOT NULL, content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            workspace_task_result_id TEXT, workspace_task_result_message_id TEXT,
            workspace_task_result_display_name TEXT, workspace_task_result_content TEXT,
            workspace_task_result_truncated INTEGER NOT NULL DEFAULT 0)""")
        db.execute("""CREATE TABLE conversation_questions (
            id TEXT PRIMARY KEY, assistant_message_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending')""")
        db.execute("""CREATE TABLE runs (id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, created_at TEXT NOT NULL)""")
        _migrate_51(db)
        assert db.execute("SELECT 1 FROM sqlite_master WHERE type = 'index' "
                          "AND name = 'idx_runs_conversation_created'").fetchone() is not None
        db.execute("INSERT INTO conversation_questions VALUES ('choice_1', 'msg_question', 'pending')")
        with pytest.raises(sqlite3.IntegrityError, match="pending specialist question"):
            db.execute("""INSERT INTO messages (id, conversation_id, seq, role, content, created_at,
                          workspace_task_result_id, workspace_task_result_message_id)
                          VALUES ('msg_attach', 'conv_1', 1, 'user', 'x', 'now', 'wst_1', 'msg_question')""")
        db.execute("UPDATE conversation_questions SET status = 'answered' WHERE id = 'choice_1'")
        db.execute("""INSERT INTO messages (id, conversation_id, seq, role, content, created_at,
                      workspace_task_result_id, workspace_task_result_message_id)
                      VALUES ('msg_attach', 'conv_2', 1, 'user', 'x', 'now', 'wst_1', 'msg_question')""")
        db.execute("UPDATE conversation_questions SET status = 'pending' WHERE id = 'choice_1'")
        with pytest.raises(sqlite3.IntegrityError, match="pending specialist question"):
            db.execute("UPDATE messages SET workspace_task_result_id = 'wst_2' WHERE id = 'msg_attach'")
        assert SCHEMA_VERSION >= 51
    finally:
        db.close()


def _prepare_historical_workflow_schema(config, *, version: int, qualification: bool,
                                        workflow_tables: bool, question_guards: bool) -> None:
    """Build a disposable current DB, then shape it like one historical branch layout."""
    current = Store(config)
    current.close()
    db = sqlite3.connect(config.db_path)
    try:
        db.execute("PRAGMA foreign_keys = OFF")
        if not question_guards:
            db.execute("DROP TRIGGER IF EXISTS messages_pending_question_result_insert")
            db.execute("DROP TRIGGER IF EXISTS messages_pending_question_result_update")
            db.execute("DROP INDEX IF EXISTS idx_runs_conversation_created")
        if not qualification:
            db.execute("DROP INDEX IF EXISTS idx_workflow_role_qualifications_route")
            db.execute("DROP TABLE IF EXISTS workflow_role_qualifications")
        if not workflow_tables:
            for table in ("workflow_questions", "workflow_nodes", "workflow_runs",
                          "workflow_revisions", "workflow_definitions"):
                db.execute(f"DROP TABLE IF EXISTS {table}")
            db.execute("DROP INDEX IF EXISTS idx_runs_kind_status")
            columns = {row[1] for row in db.execute("PRAGMA table_info(runs)")}
            if "kind" in columns:
                db.execute("ALTER TABLE runs DROP COLUMN kind")
        if qualification:
            db.execute("INSERT INTO workflow_role_qualifications "
                       "(provider, model, route_revision, role, state, source, tested_at) "
                       "VALUES ('local', 'candidate', ?, 'worker', 'probed', 'probe', '2026-10-11T00:00:00Z')",
                       ("a" * 64,))
        if workflow_tables:
            db.execute("INSERT INTO workflow_definitions "
                       "(id, name, created_at, updated_at) VALUES ('def_legacy', 'legacy', 'now', 'now')")
        db.execute(f"PRAGMA user_version = {version}")
        db.commit()
    finally:
        db.close()


@pytest.mark.parametrize(
    ("version", "qualification", "workflow_tables", "question_guards"),
    [
        pytest.param(51, False, False, True, id="main-v51-delegation-guards"),
        pytest.param(51, True, False, False, id="workflow-v51-qualification"),
        pytest.param(52, True, True, False, id="workflow-v52-tables"),
    ],
)
def test_historical_schema_51_and_52_variants_converge_on_current_schema(
    config, version, qualification, workflow_tables, question_guards,
):
    _prepare_historical_workflow_schema(
        config, version=version, qualification=qualification,
        workflow_tables=workflow_tables, question_guards=question_guards,
    )

    upgraded = Store(config)
    try:
        assert upgraded.schema_version == SCHEMA_VERSION
        names = {row[0] for row in upgraded._db.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'trigger', 'index')")}
        assert "workflow_role_qualifications" in names
        assert {"workflow_definitions", "workflow_revisions", "workflow_runs",
                "workflow_nodes", "workflow_questions", "workflow_amendment_history"} <= names
        assert {"messages_pending_question_result_insert", "messages_pending_question_result_update",
                "idx_runs_conversation_created"} <= names
        if qualification:
            assert upgraded._db.execute("SELECT COUNT(*) FROM workflow_role_qualifications").fetchone()[0] == 1
        if workflow_tables:
            assert upgraded._db.execute("SELECT name FROM workflow_definitions WHERE id='def_legacy'").fetchone()[0] == "legacy"
    finally:
        upgraded.close()


def test_interrupted_schema_56_to_current_migrations_roll_back_and_retry(config, monkeypatch):
    from hutch import store as store_module
    from hutch.models import Bot

    current = Store(config)
    bot = current.create_bot(Bot(name="migration-policy"))
    conversation, _ = current.create_conversation(
        bot.id, "Migration policy", idem_key="migration-conversation", request_hash="migration-conversation")
    current.close()
    db = sqlite3.connect(config.db_path)
    try:
        db.execute("UPDATE bots SET doc=json_remove(doc, '$.workflow_mode') WHERE id=?", (bot.id,))
        db.execute("DROP TABLE conversation_workflow_policies")
        db.execute("DROP TABLE workflow_amendment_history")
        db.execute("ALTER TABLE workflow_runs DROP COLUMN pause_requested")
        db.execute("PRAGMA user_version = 56")
        db.commit()
    finally:
        db.close()

    def interrupt(_db):
        raise RuntimeError("injected v59 workflow pause migration interruption")

    with monkeypatch.context() as patch:
        patch.setattr(store_module, "_MIGRATIONS", [*store_module._MIGRATIONS[:-1], interrupt])
        with pytest.raises(RuntimeError, match="injected v59 workflow pause migration interruption"):
            Store(config)

    db = sqlite3.connect(config.db_path)
    try:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 56
        doc = json.loads(db.execute("SELECT doc FROM bots WHERE id=?", (bot.id,)).fetchone()[0])
        assert "workflow_mode" not in doc
        assert db.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                          "AND name='conversation_workflow_policies'").fetchone() is None
        assert db.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                          "AND name='workflow_amendment_history'").fetchone() is None
        assert "pause_requested" not in {row[1] for row in db.execute("PRAGMA table_info(workflow_runs)")}
    finally:
        db.close()
    assert config.db_path.with_suffix(".db.bak-v56").exists()

    upgraded = Store(config)
    try:
        assert upgraded.schema_version == SCHEMA_VERSION
        assert upgraded.get_bot(bot.name).workflow_mode == "off"
        assert upgraded.get_conversation_workflow_policy(conversation["id"]) is None
        assert upgraded._db.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                                    "AND name='workflow_amendment_history'").fetchone() is not None
        assert upgraded._db.execute("SELECT pause_requested FROM workflow_runs LIMIT 1").fetchone() is None
    finally:
        upgraded.close()


def test_interrupted_historical_upgrade_rolls_back_and_keeps_backup(config, monkeypatch):
    from hutch import store as store_module

    _prepare_historical_workflow_schema(
        config, version=51, qualification=False, workflow_tables=False, question_guards=True,
    )

    def fail_after_role_migration(_db):
        raise RuntimeError("injected workflow migration interruption")

    with monkeypatch.context() as patch:
        patch.setattr(store_module, "_MIGRATIONS",
                      [*store_module._MIGRATIONS[:-1], fail_after_role_migration])
        with pytest.raises(RuntimeError, match="injected workflow migration interruption"):
            Store(config)

    db = sqlite3.connect(config.db_path)
    try:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 51
        assert db.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                          "AND name='workflow_role_qualifications'").fetchone() is None
    finally:
        db.close()
    backup = config.db_path.with_suffix(".db.bak-v51")
    assert backup.exists()
    backup_db = sqlite3.connect(backup)
    try:
        assert backup_db.execute("PRAGMA user_version").fetchone()[0] == 51
    finally:
        backup_db.close()

    upgraded = Store(config)
    try:
        assert upgraded.schema_version == SCHEMA_VERSION
    finally:
        upgraded.close()


def test_interrupted_schema_53_to_54_upgrade_rolls_back_and_retries(config, monkeypatch):
    from hutch import store as store_module

    # Start from the merged v53 physical shape, including both historical v51 additions,
    # then remove v54+ columns so the v54 receipt migration is exercised directly.
    current = Store(config)
    current.close()
    db = sqlite3.connect(config.db_path)
    try:
        db.execute("DROP INDEX IF EXISTS idx_actions_workflow_identity")
        db.execute("DROP TRIGGER IF EXISTS action_intent_immutable")
        db.execute("DROP TRIGGER IF EXISTS action_receipt_sealed")
        for column in ("result_json", "workflow_fingerprint", "workflow_identity"):
            db.execute(f"ALTER TABLE tool_actions DROP COLUMN {column}")
        for column in ("attempt_run_id", "revision_id"):
            db.execute(f"ALTER TABLE workflow_questions DROP COLUMN {column}")
        db.execute("PRAGMA user_version = 53")
        db.commit()
    finally:
        db.close()

    def interrupt(_db):
        raise RuntimeError("injected v54 receipt migration interruption")

    with monkeypatch.context() as patch:
        patch.setattr(store_module, "_MIGRATIONS",
                      [*store_module._MIGRATIONS[:52], interrupt,
                       *store_module._MIGRATIONS[53:]])
        with pytest.raises(RuntimeError, match="injected v54 receipt migration interruption"):
            Store(config)

    db = sqlite3.connect(config.db_path)
    try:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 53
        action_columns = {row[1] for row in db.execute("PRAGMA table_info(tool_actions)")}
        question_columns = {row[1] for row in db.execute("PRAGMA table_info(workflow_questions)")}
        assert not {"workflow_identity", "workflow_fingerprint", "result_json"} & action_columns
        assert not {"revision_id", "attempt_run_id"} & question_columns
    finally:
        db.close()
    backup = config.db_path.with_suffix(".db.bak-v53")
    assert backup.exists()
    backup_db = sqlite3.connect(backup)
    try:
        assert backup_db.execute("PRAGMA user_version").fetchone()[0] == 53
    finally:
        backup_db.close()

    upgraded = Store(config)
    try:
        assert upgraded.schema_version == SCHEMA_VERSION
        action_columns = {row[1] for row in upgraded._db.execute("PRAGMA table_info(tool_actions)")}
        question_columns = {row[1] for row in upgraded._db.execute("PRAGMA table_info(workflow_questions)")}
        assert {"workflow_identity", "workflow_fingerprint", "result_json"} <= action_columns
        assert {"revision_id", "attempt_run_id"} <= question_columns
    finally:
        upgraded.close()


def test_interrupted_schema_54_to_55_usage_migration_rolls_back_and_retries(config, monkeypatch):
    from hutch import store as store_module

    current = Store(config)
    current.close()
    db = sqlite3.connect(config.db_path)
    try:
        db.execute("DROP INDEX IF EXISTS idx_usage_reservations_workflow")
        for column in ("request_started_at", "workflow_run_id"):
            db.execute(f"ALTER TABLE usage_reservations DROP COLUMN {column}")
        db.execute("PRAGMA user_version = 54")
        db.commit()
    finally:
        db.close()

    def interrupt(_db):
        raise RuntimeError("injected v55 usage migration interruption")

    with monkeypatch.context() as patch:
        patch.setattr(store_module, "_MIGRATIONS",
                      [*store_module._MIGRATIONS[:53], interrupt, *store_module._MIGRATIONS[54:]])
        with pytest.raises(RuntimeError, match="injected v55 usage migration interruption"):
            Store(config)

    db = sqlite3.connect(config.db_path)
    try:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 54
        columns = {row[1] for row in db.execute("PRAGMA table_info(usage_reservations)")}
        assert not {"workflow_run_id", "request_started_at"} & columns
    finally:
        db.close()
    backup = config.db_path.with_suffix(".db.bak-v54")
    assert backup.exists()
    backup_db = sqlite3.connect(backup)
    try:
        assert backup_db.execute("PRAGMA user_version").fetchone()[0] == 54
    finally:
        backup_db.close()

    upgraded = Store(config)
    try:
        assert upgraded.schema_version == SCHEMA_VERSION
        columns = {row[1] for row in upgraded._db.execute("PRAGMA table_info(usage_reservations)")}
        assert {"workflow_run_id", "request_started_at"} <= columns
    finally:
        upgraded.close()


def test_interrupted_schema_55_to_56_probe_migration_rolls_back_and_retries(config, monkeypatch):
    from hutch import store as store_module

    current = Store(config)
    current.close()
    db = sqlite3.connect(config.db_path)
    try:
        for table in ("workflow_probe_requests", "workflow_probe_runs", "workflow_probe_campaigns"):
            db.execute(f"DROP TABLE IF EXISTS {table}")
        db.execute("ALTER TABLE workflow_role_qualifications DROP COLUMN execution_profile_hash")
        db.execute("PRAGMA user_version = 55")
        db.commit()
    finally:
        db.close()

    def interrupt(_db):
        raise RuntimeError("injected v56 qualification migration interruption")

    with monkeypatch.context() as patch:
        patch.setattr(store_module, "_MIGRATIONS",
                      [*store_module._MIGRATIONS[:54], interrupt, *store_module._MIGRATIONS[55:]])
        with pytest.raises(RuntimeError, match="injected v56 qualification migration interruption"):
            Store(config)

    db = sqlite3.connect(config.db_path)
    try:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 55
        assert db.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                          "AND name='workflow_probe_campaigns'").fetchone() is None
        columns = {row[1] for row in db.execute("PRAGMA table_info(workflow_role_qualifications)")}
        assert "execution_profile_hash" not in columns
    finally:
        db.close()
    assert config.db_path.with_suffix(".db.bak-v55").exists()

    upgraded = Store(config)
    try:
        assert upgraded.schema_version == SCHEMA_VERSION
        names = {row[0] for row in upgraded._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"workflow_probe_campaigns", "workflow_probe_runs", "workflow_probe_requests"} <= names
        columns = {row[1] for row in upgraded._db.execute("PRAGMA table_info(workflow_role_qualifications)")}
        assert "execution_profile_hash" in columns
    finally:
        upgraded.close()
