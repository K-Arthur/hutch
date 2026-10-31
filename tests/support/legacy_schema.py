"""Simulate an older database shape for upgrade tests.

``TABLE_CREATED_AT`` records the migration that created each table the helper may drop, so a
simulated version keeps the tables a real database of that version would already have.
"""

TABLE_CREATED_AT = {
    "conversation_questions": 26, "google_calendar_grants": 27, "workspace_settings": 28,
    "workspace_tasks": 29, "workspace_task_checkpoints": 31, "workspace_task_fact_shares": 32,
    "workspace_task_continuations": 34, "memory_fact_shares": 38, "code_handoffs": 39,
    "code_handoff_receipts": 89,
    "workspace_specialists": 41, "task_templates": 44, "doc_index_chunks": 50, "doc_index_fts": 50,
    "doc_index_generations": 50, "document_versions": 50, "documents": 50, "event_sources": 50,
    "job_steps": 50, "jobs": 50, "source_events": 50,
}


def remove_later_conversation_schema(db, legacy_version=0):
    """Remove schema added after the simulated legacy version before lowering user_version.

    Tables created at or before ``legacy_version`` belong to that version's real schema and are
    kept. The default of 0 drops every listed table, which is what the older callers expect."""
    for trigger in (
        "workspace_task_checkpoint_event_insert", "messages_workspace_task_result_insert",
        "messages_workspace_task_result_update", "messages_pending_question_result_insert",
        "messages_pending_question_result_update", "messages_choice_question_insert",
        "messages_choice_question_update", "conversation_question_definition_immutable",
        "conversation_question_resolve_once", "messages_reply_target_insert", "messages_reply_target_update",
        "workspace_task_fact_share_source_guard", "workspace_task_fact_share_immutable",
        "workspace_task_fact_share_no_delete", "workspace_task_continuation_source_guard",
        "workspace_task_continuation_immutable", "workspace_task_continuation_no_delete",
        "workspace_specialists_reject_coordinator_insert", "workspace_specialists_reject_coordinator_update",
        "workspace_settings_remove_promoted_specialist",
        "conversations_assistant_message_unread", "conversations_user_message_read",
        "resource_outbox_conversations_insert", "resource_outbox_conversations_update",
        "resource_outbox_conversations_delete",
    ):
        db.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    db.execute("DROP INDEX IF EXISTS idx_messages_workspace_task_result")
    db.execute("DROP INDEX IF EXISTS idx_conversations_bot_pin_update")
    db.execute("DROP INDEX IF EXISTS idx_documents_conversation")
    db.execute("DROP INDEX IF EXISTS idx_documents_bot")
    db.execute("DROP INDEX IF EXISTS idx_document_versions_run")
    db.execute("DROP INDEX IF EXISTS idx_usage_run")
    db.execute("DROP INDEX IF EXISTS idx_uploads_conversation")
    db.execute("DROP INDEX IF EXISTS idx_media_jobs_run")
    db.execute("DROP INDEX IF EXISTS idx_media_jobs_conversation")
    db.execute("DROP INDEX IF EXISTS idx_runs_conversation_created")
    for table in ("uploads", "media_jobs", "workspace_sessions", "document_versions", "documents",
                  "budget_pause_releases", "budget_policies", "run_compactions",
                  "inv_stream_cursors", "inv_answers", "inv_observations", "inv_media_frames", "inv_media",
                  "inv_evidence", "inv_claims", "inv_sources", "inv_query_attempts", "investigations",
                  "doc_index_fts", "doc_index_chunks", "doc_index_generations",
                  "job_steps", "jobs", "source_events", "event_sources",
                  "workspace_task_continuations", "workspace_task_fact_shares", "workspace_task_checkpoints",
                  "workspace_tasks", "workspace_specialists", "workspace_settings",
                  "conversation_questions", "google_calendar_grants", "memory_fact_shares",
                  "code_handoff_receipts", "code_handoffs",
                  "task_templates"):
        if TABLE_CREATED_AT.get(table, 10**9) > legacy_version:
            db.execute(f"DROP TABLE IF EXISTS {table}")
    reservation_columns = {row[1] for row in db.execute("PRAGMA table_info(usage_reservations)")}
    for column in ("cost_unknown", "quote_source", "quote_verified_on"):
        if column in reservation_columns:
            db.execute(f"ALTER TABLE usage_reservations DROP COLUMN {column}")
    usage_columns = {row[1] for row in db.execute("PRAGMA table_info(usage)")}
    for column in ("cost_source", "reported_cost_usd"):
        if column in usage_columns:
            db.execute(f"ALTER TABLE usage DROP COLUMN {column}")
    columns = {row[1] for row in db.execute("PRAGMA table_info(messages)")}
    for column in ("workspace_task_result_id", "workspace_task_result_message_id",
                   "workspace_task_result_display_name", "workspace_task_result_content",
                   "workspace_task_result_truncated", "choice_question_id", "reply_to_message_id"):
        if column in columns:
            db.execute(f"ALTER TABLE messages DROP COLUMN {column}")
    conversation_columns = {row[1] for row in db.execute("PRAGMA table_info(conversations)")}
    for column in ("section", "read_seq", "unread", "pinned", "persona"):
        if column in conversation_columns:
            db.execute(f"ALTER TABLE conversations DROP COLUMN {column}")
