"""Google Workspace request-contract tests (no I/O, no credentials)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from hutch.gsuite.requests import (
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
    drive_multipart_body,
    drive_verify_file,
    route_reminder,
    sheets_append_spec,
    sheets_create_payload,
    sheets_header_read_range,
    sheets_resolve_sheet,
    sheets_values_lookup_spec,
    sheets_verify_append,
    ColumnSpec,
    walk_tabs,
)

# ---------------------------------------------------------------------------
# Docs


def _document(tab_a="t.aaa", tab_b="t.bbb", child="t.ccc"):
    return {
        "documentId": "doc123",
        "revisionId": "rev7",
        "tabs": [
            {"tabProperties": {"tabId": tab_a, "title": "Main", "index": 0},
             "documentTab": {"body": {"content": [
                 {"paragraph": {"elements": [{"textRun": {"content": "Hello from Main.\n"}}]}}]}},
             "childTabs": [
                 {"tabProperties": {"tabId": child, "title": "Details", "index": 0},
                  "documentTab": {"body": {"content": [
                      {"paragraph": {"elements": [{"textRun": {"content": "Child text.\n"}}]}}]}},
                  "childTabs": []},
             ]},
            {"tabProperties": {"tabId": tab_b, "title": "Appendix", "index": 1},
             "documentTab": {"body": {"content": []}}, "childTabs": []},
        ],
    }


def test_walk_tabs_flattens_children_in_order():
    tabs = walk_tabs(_document())
    assert [(t["title"], t["depth"]) for t in tabs] == [
        ("Main", 0), ("Details", 1), ("Appendix", 0)]


def test_resolve_tab_never_defaults_to_first_of_several():
    from hutch.gsuite.requests import resolve_tab
    doc = _document()
    assert resolve_tab(doc, tab_id="t.bbb") == "t.bbb"
    assert resolve_tab(doc, title="Details") == "t.ccc"
    with pytest.raises(WorkspaceRequestError):
        resolve_tab(doc, title="Missing")
    with pytest.raises(WorkspaceRequestError):
        resolve_tab(doc, tab_id="t.zzz")
    with pytest.raises(WorkspaceRequestError):
        resolve_tab(doc)  # several tabs, no explicit target
    single = {"tabs": [{"tabProperties": {"tabId": "only", "title": "Main"}, "childTabs": []}]}
    assert resolve_tab(single) == "only"
    with pytest.raises(WorkspaceRequestError) as exc:
        resolve_tab({"body": {}})
    assert "includeTabsContent" in str(exc.value)


def test_docs_insert_style_and_bounds():
    with pytest.raises(WorkspaceRequestError):
        docs_insert_text_requests("text", tab_id="")
    with pytest.raises(WorkspaceRequestError):
        docs_insert_text_requests("", tab_id="t1")
    with pytest.raises(WorkspaceRequestError):
        docs_insert_text_requests("x", tab_id="t1", index=0)
    reqs = docs_insert_text_requests("Title\n", tab_id="t1", index=1, style="HEADING_1")
    assert reqs[0]["insertText"]["location"] == {"index": 1, "tabId": "t1"}
    assert reqs[1]["updateParagraphStyle"]["paragraphStyle"]["namedStyleType"] == "HEADING_1"
    assert reqs[1]["updateParagraphStyle"]["range"]["tabId"] == "t1"


def test_docs_replace_targets_one_tab_not_all():
    reqs = docs_replace_text_requests("12%", "21%", tab_id="t.aaa")
    assert reqs[0]["replaceAllText"]["tabsCriteria"] == {"tabIds": ["t.aaa"]}
    assert reqs[0]["replaceAllText"]["containsText"]["matchCase"] is True


def test_docs_table_and_image_rules():
    with pytest.raises(WorkspaceRequestError):
        docs_table_requests([["a", "b"], ["c"]], tab_id="t", index=1)
    reqs = docs_table_requests([["a", "b"], ["c", "d"]], tab_id="t1", index=1)
    assert reqs[0]["insertTable"] == {"location": {"index": 1, "tabId": "t1"}, "rows": 2, "columns": 2}

    with pytest.raises(WorkspaceRequestError):
        docs_image_request("http://x/i.png", tab_id="t1", index=1)
    with pytest.raises(WorkspaceRequestError) as exc:
        docs_image_request("https://cdn.example.org/i.png?X-Goog-Signature=abc", tab_id="t1", index=1)
    assert "persisted secret" in str(exc.value)
    ok = docs_image_request("https://cdn.example.org/i.png?w=800", tab_id="t1", index=1,
                            dimensions_pt=(200, 100))
    assert ok["insertInlineImage"]["objectSize"]["width"]["magnitude"] == 200.0


def test_docs_batch_body_and_read_back():
    with pytest.raises(WorkspaceRequestError):
        docs_batch_update_body([])
    body = docs_batch_update_body([{"insertText": {}}], required_revision_id="rev7")
    assert body["writeControl"] == {"requiredRevisionId": "rev7"}

    doc = _document()
    assert "Hello from Main." in docs_content_text(doc["tabs"][0])
    assert docs_verify_text(doc, tab_id="t.aaa", expected="Hello from Main.") == []
    problems = docs_verify_text(doc, tab_id="t.ccc", expected="Hello from Main.")
    assert problems and "not found" in problems[0]
    assert docs_verify_text(doc, tab_id="t.zzz", expected="x")


# ---------------------------------------------------------------------------
# Sheets


def _spreadsheet():
    return {
        "spreadsheetId": "sheet123",
        "properties": {"title": "Brief"},
        "sheets": [
            {"properties": {"sheetId": 7, "title": "Rows", "index": 0}},
            {"properties": {"sheetId": 8, "title": "Summary", "index": 1}},
            {"properties": {"sheetId": 9, "title": "Rows", "index": 2}},  # duplicate title
        ],
    }


def test_sheets_create_and_resolve():
    payload = sheets_create_payload("Brief", ["Rows", "Summary"])
    assert [s["properties"]["title"] for s in payload["sheets"]] == ["Rows", "Summary"]
    with pytest.raises(WorkspaceRequestError):
        sheets_create_payload("Brief", ["Rows", "Rows"])
    with pytest.raises(WorkspaceRequestError):
        sheets_create_payload("", ["Rows"])

    book = _spreadsheet()
    assert sheets_resolve_sheet(book, sheet_id=8) == {"sheet_id": 8, "title": "Summary"}
    with pytest.raises(WorkspaceRequestError) as exc:
        sheets_resolve_sheet(book, title="Rows")  # ambiguous by name
    assert "sheet id" in str(exc.value)
    with pytest.raises(WorkspaceRequestError):
        sheets_resolve_sheet(book, sheet_id=8, title="Rows")
    with pytest.raises(WorkspaceRequestError):
        sheets_resolve_sheet(book, sheet_id=99)


def test_sheets_header_range_quoting_and_bounds():
    assert sheets_header_read_range("Summary", 3) == "Summary!A1:C1"
    assert sheets_header_read_range("My Sheet's Rows", 2) == "'My Sheet''s Rows'!A1:B1"
    with pytest.raises(WorkspaceRequestError):
        sheets_header_read_range("x", 0)


def test_sheets_append_is_raw_typed_and_bounded():
    resolved = {"sheet_id": 7, "title": "Rows"}
    columns = [ColumnSpec("id", "text"), ColumnSpec("count", "integer"),
               ColumnSpec("rate", "number"), ColumnSpec("day", "date"),
               ColumnSpec("ok", "boolean"), ColumnSpec("note", "text")]
    spec = sheets_append_spec(
        resolved=resolved, columns=columns,
        rows=[["007", 42, 12.5, "2026-10-11", True, "=SUM(A1:A2)"]],
    )
    assert spec["value_input_option"] == "RAW"
    assert spec["insert_data_option"] == "INSERT_ROWS"
    assert spec["range"] == "Rows!A1"
    assert spec["values"] == [["007", 42, 12.5, "2026-10-11", True, "=SUM(A1:A2)"]]
    assert spec["body"]["majorDimension"] == "ROWS"

    with pytest.raises(WorkspaceRequestError):
        sheets_append_spec(resolved=resolved, columns=columns, rows=[["a", 1]])
    with pytest.raises(WorkspaceRequestError) as exc:
        sheets_append_spec(resolved=resolved, columns=[
            ColumnSpec("big", "integer")], rows=[[2 ** 53 + 1]])
    assert "text" in str(exc.value)
    with pytest.raises(WorkspaceRequestError):
        sheets_append_spec(resolved=resolved, columns=[ColumnSpec("n", "number")], rows=[[None]])
    blank_text = sheets_append_spec(resolved=resolved, columns=[ColumnSpec("t", "text")],
                                    rows=[[None]])
    assert blank_text["values"] == [[""]]
    with pytest.raises(WorkspaceRequestError):
        sheets_append_spec(resolved=resolved, columns=[ColumnSpec("b", "boolean")], rows=[["yes"]])
    with pytest.raises(WorkspaceRequestError):
        sheets_append_spec(resolved=resolved, columns=[ColumnSpec("d", "datetime")],
                           rows=[[datetime(2026, 1, 1)]])  # naive datetime has no zone
    aware = sheets_append_spec(resolved=resolved, columns=[ColumnSpec("d", "datetime")],
                               rows=[[datetime(2026, 1, 1, 9, 30, tzinfo=timezone.utc)]])
    assert aware["values"][0][0].startswith("2026-01-01T09:30:00")
    # too many rows refused without allocating anything
    with pytest.raises(WorkspaceRequestError):
        sheets_append_spec(resolved=resolved, columns=[ColumnSpec("n", "integer")],
                           rows=[[i] for i in range(5001)])


def test_sheets_verify_append_reports_wrong_target_and_shape():
    resolved = {"sheet_id": 7, "title": "Rows"}
    spec = sheets_append_spec(resolved=resolved, columns=[ColumnSpec("a", "text")], rows=[["x"]])
    ok = {"updates": {"updatedRange": "Rows!A2:A2", "updatedRows": 1, "updatedColumns": 1}}
    assert sheets_verify_append(ok, spec) == []
    wrong_sheet = {"updates": {"updatedRange": "Summary!A2:A2", "updatedRows": 1, "updatedColumns": 1}}
    assert sheets_verify_append(wrong_sheet, spec)
    wrong_rows = {"updates": {"updatedRange": "Rows!A2:A3", "updatedRows": 2, "updatedColumns": 1}}
    assert sheets_verify_append(wrong_rows, spec)


def test_sheets_lookup_is_bounded_to_a_window():
    resolved = {"sheet_id": 7, "title": "Rows"}
    spec = sheets_values_lookup_spec(resolved=resolved, first_column=1, last_column=3, max_rows=20)
    assert spec["range"] == "Rows!A2:C21"
    with pytest.raises(WorkspaceRequestError):
        sheets_values_lookup_spec(resolved=resolved, first_column=3, last_column=1)


# ---------------------------------------------------------------------------
# Drive


def test_drive_ids_metadata_and_multipart():
    with pytest.raises(WorkspaceRequestError):
        drive_generate_ids_request(0)
    assert drive_generate_ids_request(3)["count"] == 3

    with pytest.raises(WorkspaceRequestError):
        drive_create_file_metadata("x.wav", mime_type="audio/wav", parent_id="")
    meta = drive_create_file_metadata("episode.wav", mime_type="audio/wav", parent_id="folder1",
                                      app_properties={"hutch_manifest": "syn_a"})
    assert meta["parents"] == ["folder1"] and meta["appProperties"]["hutch_manifest"] == "syn_a"

    with pytest.raises(WorkspaceRequestError):
        drive_multipart_body(meta, b"", mime_type="audio/wav")
    body, ctype = drive_multipart_body(meta, b"RIFFDATA", mime_type="audio/wav")
    assert ctype.startswith("multipart/related; boundary=") and b"RIFFDATA" in body

    problems = drive_verify_file({"id": "f1", "name": "episode.wav", "parents": ["folder1"]},
                                 expected_id="f1", expected_name="episode.wav",
                                 expected_parents=["folder1"])
    assert problems == []
    assert drive_verify_file({"id": "f2", "trashed": True}, expected_id="f1")
    assert drive_is_native({"mimeType": "application/vnd.google-apps.document"})
    assert not drive_is_native({"mimeType": "audio/wav"})


# ---------------------------------------------------------------------------
# Calendar


def test_event_id_is_deterministic_and_format_valid():
    a = calendar_event_id("plan_1:step_doc")
    b = calendar_event_id("plan_1:step_doc")
    c = calendar_event_id("plan_1:step_sheet")
    assert a == b and a != c
    assert len(a) == 52
    import re

    assert re.fullmatch(r"[a-v0-9]{5,1024}", a)


def test_timed_event_timezone_reminders_and_invites():
    with pytest.raises(WorkspaceRequestError):
        calendar_timed_event(summary="x", start="2026-10-12T09:00:00", end="2026-10-12T10:00:00",
                             timezone="Mars/Olympus")
    with pytest.raises(WorkspaceRequestError):
        calendar_timed_event(summary="x", start="2026-10-12T09:00:00", end="2026-10-12T10:00:00",
                             timezone="")
    event = calendar_timed_event(
        summary="Design review", start="2026-10-12T09:00:00", end="2026-10-12T10:00:00",
        timezone="America/Los_Angeles", event_id=calendar_event_id("s1"),
        reminders={"popup": 10},
        attendees=["a@example.com"],
    )
    assert event["start"]["timeZone"] == "America/Los_Angeles"
    assert event["reminders"] == {"useDefault": False, "overrides": [{"method": "popup", "minutes": 10}]}
    assert event["attendees"] == [{"email": "a@example.com"}]
    with pytest.raises(WorkspaceRequestError):
        calendar_timed_event(summary="x", start="a", end="b", timezone="UTC")
    with pytest.raises(WorkspaceRequestError) as exc:
        calendar_timed_event(summary="x", start="2026-10-12T09:00:00", end="2026-10-12T10:00:00",
                             timezone="UTC", reminders={"popup": 99_999})
    assert "absolute" in str(exc.value)
    with pytest.raises(WorkspaceRequestError):
        calendar_timed_event(summary="x", start="2026-10-12T09:00:00", end="2026-10-12T10:00:00",
                             timezone="UTC", attendees=["not-an-email"])
    with pytest.raises(WorkspaceRequestError):
        calendar_timed_event(summary="x", start="2026-10-12T09:00:00", end="2026-10-12T10:00:00",
                             timezone="UTC", event_id="BAD ID!")


def test_all_day_event_has_exclusive_end():
    event = calendar_all_day_event(summary="Holiday", day=date(2026, 10, 12))
    assert event["start"] == {"date": "2026-10-12"}
    assert event["end"] == {"date": "2026-10-13"}


def test_verify_event_and_send_updates():
    event = {"id": "abc123", "summary": "Design review", "status": "confirmed",
             "start": {"dateTime": "2026-10-12T09:00:00-07:00", "timeZone": "America/Los_Angeles"},
             "reminders": {"overrides": [{"method": "popup", "minutes": 10}]}}
    assert calendar_verify_event(event, expected_id="abc123", expected_summary="Design review",
                                 expected_timezone="America/Los_Angeles",
                                 expected_reminders={"popup": 10}) == []
    assert calendar_verify_event(event, expected_id="other")
    assert calendar_verify_event({**event, "status": "cancelled"}, expected_id="abc123")
    assert calendar_verify_event(event, expected_id="abc123", expected_reminders={"popup": 30})
    assert calendar_send_updates("externalOnly") == "externalOnly"
    with pytest.raises(WorkspaceRequestError):
        calendar_send_updates("silent")


# ---------------------------------------------------------------------------
# reminder routing semantics


def test_reminder_routing_is_honest_about_mechanisms():
    task = route_reminder("task")
    assert task.mechanism == "tasks.due" and "discarded" in task.explanation

    relative = route_reminder("event_relative", minutes_before=15)
    assert relative.mechanism == "calendar.reminders"
    assert relative.payload_hint["reminders"]["overrides"][0]["minutes"] == 15
    with pytest.raises(WorkspaceRequestError):
        route_reminder("event_relative")

    exact = route_reminder("exact_time", exact_at="2026-10-12T07:00:00-07:00")
    assert exact.mechanism == "hutch.routine"
    assert "Tasks discards the time" in exact.explanation
    with pytest.raises(WorkspaceRequestError):
        route_reminder("exact_time")
    with pytest.raises(WorkspaceRequestError):
        route_reminder("vibes")
