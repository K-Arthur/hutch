"""Google Workspace request contracts (Docs, Sheets, Drive, Calendar).

Pure request builders/verifiers encoding the documented API semantics; the OAuth
transport plugs in separately. See ``docs/research/synthesis-workspace-failures-2026-10-11.md``.
"""

from .requests import (  # noqa: F401
    GOOGLE_WORKSPACE_SCOPES,
    ColumnSpec,
    ReminderRoute,
    WorkspaceRequestError,
    calendar_all_day_event,
    calendar_event_id,
    calendar_send_updates,
    calendar_timed_event,
    calendar_verify_event,
    docs_batch_update_body,
    docs_content_text,
    docs_create_payload,
    docs_image_request,
    docs_insert_text_requests,
    docs_replace_text_requests,
    docs_table_requests,
    docs_verify_text,
    drive_create_file_metadata,
    drive_generate_ids_request,
    drive_is_native,
    drive_list_params,
    drive_multipart_body,
    drive_verify_file,
    resolve_tab,
    route_reminder,
    sheets_append_spec,
    sheets_create_payload,
    sheets_header_read_range,
    sheets_resolve_sheet,
    sheets_values_lookup_spec,
    sheets_verify_append,
    walk_tabs,
)
