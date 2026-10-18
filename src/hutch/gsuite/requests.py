"""Google Workspace request contracts: Docs, Sheets, Drive, Calendar.

These are the deterministic, credential-free halves of the Workspace connectors: request
builders and verifiers that encode the documented semantics so the transport layer cannot
skip them. The transport (OAuth + HTTP) plugs in later; nothing here performs I/O.

Rules encoded here (each has a test, sources in the lane ledger):

* Docs — text updates carry an explicit ``tabId``; a request without a resolved tab is
  refused rather than defaulting to "the first tab". Scoped updates carry
  ``writeControl.requiredRevisionId`` when the caller has a revision, so a lost human edit
  produces a conflict instead of a silent overwrite. Whole-document replacement is not
  offered. Insert-inline-image refuses a private URI unless the caller explicitly attests
  the URI is public.
* Sheets — appends use ``RAW`` by default (untrusted literal values never become
  formulas); ``USER_ENTERED`` is only reachable for values the caller explicitly marks as
  trusted formulas. Column kinds coerce deterministically: text keeps leading zeros,
  numbers are refused when they would lose precision (> 2**53), blanks stay blank and are
  never turned into zeros, dates stay literal ISO strings. The target sheet is resolved
  by title **and** verified against the expected sheetId. Header-only reads are bounded.
* Drive — created files get their IDs from ``files.generateIds`` so a lost response can be
  reconciled by a later ``files.get`` on the same ID; destinations are explicit folder IDs
  (never name lookups); sharing is a separate request this module does not build.
* Calendar — timed events need an IANA timezone (or explicit offset), all-day events use
  date fields with the documented exclusive end, reminder overrides are relative offsets
  in a documented range, ``sendUpdates`` is always explicit, and a caller-supplied event
  ID is derived deterministically so create-recovery can look the event up.

Absolute-time reminders are **not** representable: `route_reminder` says so and points at
the supported mechanisms instead of approximating.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DOCS_API = "https://docs.googleapis.com/v1"
SHEETS_API = "https://sheets.googleapis.com/v4"
DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"
CALENDAR_API = "https://www.googleapis.com/calendar/v3"

DOC_MIME = "application/vnd.google-apps.document"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"

#: incremental least-privilege: Drive access is per-file (app-created / user-opened only),
#: never full-Drive discovery; Docs and Sheets carry their own scopes.
GOOGLE_WORKSPACE_SCOPES = (
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
)

MAX_DOC_INSERT_CHARS = 200_000
MAX_SHEET_ROWS = 5_000
MAX_SHEET_COLUMNS = 200
MAX_UPLOAD_BYTES = 64_000_000  # single request; larger media would use resumable upload
REMINDER_MINUTES_MAX = 40_320  # four weeks, the documented maximum offset

#: Google requires event IDs to use lowercase base32hex (a–v, 0–9), 5–1024 chars.
_EVENT_ID_RE = re.compile(r"^[a-v0-9]{5,1024}$")
_COLUMN_KINDS = ("text", "number", "integer", "date", "datetime", "boolean", "blank")


class WorkspaceRequestError(ValueError):
    """The request cannot be built as asked; nothing was sent."""


# ---------------------------------------------------------------------------
# Docs


def docs_create_payload(title: str) -> dict[str, Any]:
    title = str(title or "").strip()
    if not title:
        raise WorkspaceRequestError("a document needs a title")
    return {"title": title[:400]}


def walk_tabs(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Every tab in document order, children included, as flat descriptors."""
    out: list[dict[str, Any]] = []

    def visit(tab: dict[str, Any], depth: int) -> None:
        props = tab.get("tabProperties") or {}
        out.append({
            "tab_id": props.get("tabId", ""),
            "title": props.get("title", ""),
            "index": props.get("index", 0),
            "depth": depth,
            "child_count": len(tab.get("childTabs") or []),
        })
        for child in tab.get("childTabs") or []:
            visit(child, depth + 1)

    for tab in document.get("tabs") or []:
        visit(tab, 0)
    return out


def resolve_tab(document: dict[str, Any], *, tab_id: str = "", title: str = "") -> str:
    """Resolve an explicit tab id — never a silent first-tab default.

    Documents fetched with ``includeTabsContent=true`` put content under ``tabs``; a
    legacy body is only acceptable when the document truly has one tab.
    """
    tabs = walk_tabs(document)
    if tab_id:
        if all(t["tab_id"] != tab_id for t in tabs):
            raise WorkspaceRequestError(f"tab {tab_id} is not in this document")
        return tab_id
    if title:
        matches = [t for t in tabs if t["title"] == title]
        if len(matches) != 1:
            raise WorkspaceRequestError(
                f"tab title {title!r} matches {len(matches)} tabs; use its tab id")
        return matches[0]["tab_id"]
    if len(tabs) == 1 and tabs[0]["tab_id"]:
        return tabs[0]["tab_id"]
    if not tabs:
        raise WorkspaceRequestError(
            "the document was fetched without tabs content; call documents.get with "
            "includeTabsContent=true before building tab-scoped requests")
    raise WorkspaceRequestError("this document has several tabs; pass a tab id")


def docs_insert_text_requests(text: str, *, tab_id: str, index: int = 1,
                              style: str = "NORMAL_TEXT") -> list[dict[str, Any]]:
    if not tab_id:
        raise WorkspaceRequestError("a tab id is required for a scoped insert")
    if not text:
        raise WorkspaceRequestError("nothing to insert")
    if len(text) > MAX_DOC_INSERT_CHARS:
        raise WorkspaceRequestError(f"insert exceeds {MAX_DOC_INSERT_CHARS} characters")
    if index < 1:
        raise WorkspaceRequestError("a document index starts at 1")
    requests: list[dict[str, Any]] = [
        {"insertText": {"location": {"index": index, "tabId": tab_id}, "text": text}}
    ]
    if style and style != "NORMAL_TEXT":
        requests.append({
            "updateParagraphStyle": {
                "range": {"startIndex": index, "endIndex": index + len(text), "tabId": tab_id},
                "paragraphStyle": {"namedStyleType": style},
                "fields": "namedStyleType",
            }
        })
    return requests


def docs_replace_text_requests(find: str, replace: str, *, tab_id: str, match_case: bool = True,
                               ignore_whitespace: bool = False) -> list[dict[str, Any]]:
    """A scoped literal replace in one tab.

    ``ReplaceAllTextRequest`` defaults to **all** tabs, so the tab IDs list is always
    populated explicitly — a correction must not silently edit other tabs.
    """
    if not find:
        raise WorkspaceRequestError("nothing to replace")
    return [{
        "replaceAllText": {
            "containsText": {"text": find, "matchCase": bool(match_case)},
            "replaceText": replace,
            "tabsCriteria": {"tabIds": [tab_id]},
        }
    }]


def docs_table_requests(rows: list[list[str]], *, tab_id: str, index: int) -> list[dict[str, Any]]:
    if not rows or not rows[0]:
        raise WorkspaceRequestError("a table needs at least one header row")
    columns = len(rows[0])
    if any(len(r) != columns for r in rows):
        raise WorkspaceRequestError("every table row must have the same number of cells")
    if columns > 20 or len(rows) > 200:
        raise WorkspaceRequestError("table exceeds 20 columns x 200 rows")
    return [{
        "insertTable": {
            "location": {"index": index, "tabId": tab_id},
            "rows": len(rows),
            "columns": columns,
        }
    }]


def docs_image_request(uri: str, *, tab_id: str, index: int,
                       dimensions_pt: Optional[tuple[float, float]] = None) -> dict[str, Any]:
    """Insert-inline-image, gated against carrying credentials (R9).

    Docs fetches the URI from Google's servers; a private asset must travel as a Drive
    attachment/link instead. This builder refuses URIs that carry obvious secrets or
    key names, because the URI is persisted in the document.
    """
    if not uri.startswith("https://"):
        raise WorkspaceRequestError("the image URI must be https")
    lowered = uri.lower()
    for marker in ("x-goog-signature", "signature=", "token=", "key=", "secret=",
                   "expires=", "credential=", "access_token"):
        if marker in lowered:
            raise WorkspaceRequestError(
                "image URIs must not carry signatures or tokens (a persisted secret in a "
                "document is refused); upload the asset and use a Drive attachment instead")
    request: dict[str, Any] = {"insertInlineImage": {
        "uri": uri, "location": {"index": index, "tabId": tab_id}}}
    if dimensions_pt:
        request["insertInlineImage"]["objectSize"] = {
            "height": {"magnitude": float(dimensions_pt[1]), "unit": "PT"},
            "width": {"magnitude": float(dimensions_pt[0]), "unit": "PT"},
        }
    return request


def docs_batch_update_body(requests: list[dict[str, Any]], *,
                           required_revision_id: str = "") -> dict[str, Any]:
    if not requests:
        raise WorkspaceRequestError("an empty batch would be a no-op")
    body: dict[str, Any] = {"requests": requests}
    if required_revision_id:
        body["writeControl"] = {"requiredRevisionId": required_revision_id}
    return body


def docs_read_control(document: dict[str, Any]) -> dict[str, str]:
    """Revision and tab summary for review: what the caller is editing exactly."""
    return {
        "document_id": document.get("documentId", ""),
        "revision_id": document.get("revisionId", ""),
        "tabs": json.dumps(walk_tabs(document)[:40]),
    }


def docs_content_text(tab: dict[str, Any]) -> str:
    """Flatten one tab's body text (verification helper for read-back)."""
    body = (tab.get("documentTab") or {}).get("body") or {}
    parts: list[str] = []
    for element in body.get("content") or []:
        para = element.get("paragraph")
        if not para:
            continue
        for run in para.get("elements") or []:
            text = (run.get("textRun") or {}).get("content")
            if text:
                parts.append(text)
    return "".join(parts)


def docs_verify_text(document: dict[str, Any], *, tab_id: str, expected: str) -> list[str]:
    """Problems (empty == verified) that the expected text is present in that tab."""
    tabs = walk_tabs(document)
    match = [t for t in tabs if t["tab_id"] == tab_id]
    if not match:
        return [f"tab {tab_id} is missing from the read-back"]
    for tab in _iter_tab_objects(document.get("tabs") or []):
        if (tab.get("tabProperties") or {}).get("tabId") == tab_id:
            text = docs_content_text(tab)
            return [] if expected in text else [f"expected text not found in tab {tab_id}"]
    return [f"tab {tab_id} has no readable content"]


def _iter_tab_objects(tabs: Iterable[dict[str, Any]]):
    for tab in tabs:
        yield tab
        yield from _iter_tab_objects(tab.get("childTabs") or [])


# ---------------------------------------------------------------------------
# Sheets

ColumnKind = Literal["text", "number", "integer", "date", "datetime", "boolean", "blank"]


@dataclass
class ColumnSpec:
    name: str
    kind: ColumnKind = "text"

    def coerce(self, value: Any) -> Any:
        """One value under this column's rules. Raises instead of guessing."""
        if value is None:
            if self.kind != "blank" and self.kind != "text":
                raise WorkspaceRequestError(f"column {self.name!r}: blank cell for a {self.kind} column")
            return ""
        if self.kind in ("blank", "text"):
            text = str(value)
            return text
        if self.kind == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str) and value.lower() in ("true", "false"):
                return value.lower() == "true"
            raise WorkspaceRequestError(f"column {self.name!r}: {value!r} is not a boolean")
        if self.kind == "number":
            number = float(value)
            if abs(number) > 2 ** 53:
                raise WorkspaceRequestError(
                    f"column {self.name!r}: {value!r} exceeds exact float range; store large "
                    "identifiers as text")
            return number
        if self.kind == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise WorkspaceRequestError(f"column {self.name!r}: {value!r} is not an integer")
            if abs(value) > 2 ** 53:
                raise WorkspaceRequestError(
                    f"column {self.name!r}: {value!r} exceeds exact integer range; store large "
                    "identifiers as text")
            return value
        if self.kind == "date":
            if isinstance(value, datetime):
                raise WorkspaceRequestError(f"column {self.name!r}: use a date, not a datetime")
            if isinstance(value, date):
                return value.isoformat()
            if isinstance(value, str):
                try:
                    return date.fromisoformat(value).isoformat()
                except ValueError as exc:
                    raise WorkspaceRequestError(
                        f"column {self.name!r}: {value!r} is not an ISO date") from exc
            raise WorkspaceRequestError(f"column {self.name!r}: {value!r} is not a date")
        if self.kind == "datetime":
            if isinstance(value, datetime):
                if value.tzinfo is None:
                    raise WorkspaceRequestError(
                        f"column {self.name!r}: a datetime must carry its offset or zone")
                return value.isoformat()
            if isinstance(value, str):
                try:
                    parsed = datetime.fromisoformat(value)
                except ValueError as exc:
                    raise WorkspaceRequestError(
                        f"column {self.name!r}: {value!r} is not ISO 8601") from exc
                if parsed.tzinfo is None:
                    raise WorkspaceRequestError(
                        f"column {self.name!r}: {value!r} has no offset or zone")
                return parsed.isoformat()
            raise WorkspaceRequestError(f"column {self.name!r}: {value!r} is not a datetime")
        raise WorkspaceRequestError(f"column {self.name!r}: unknown kind {self.kind!r}")


def sheets_create_payload(title: str, sheet_titles: list[str]) -> dict[str, Any]:
    title = str(title or "").strip()
    if not title:
        raise WorkspaceRequestError("a spreadsheet needs a title")
    if not sheet_titles or len(sheet_titles) > 50:
        raise WorkspaceRequestError("provide 1-50 sheet titles")
    if len(set(sheet_titles)) != len(sheet_titles):
        raise WorkspaceRequestError("sheet titles must be unique")
    for t in sheet_titles:
        if not t or len(t) > 100:
            raise WorkspaceRequestError("sheet titles must be 1-100 characters")
    return {
        "properties": {"title": title[:400]},
        "sheets": [{"properties": {"title": t}} for t in sheet_titles],
    }


def sheets_resolve_sheet(spreadsheet: dict[str, Any], *, title: str = "",
                         sheet_id: Optional[int] = None) -> dict[str, Any]:
    """Resolve the exact sheet by id when given, else by unique title — verified not guessed."""
    sheets = [s.get("properties", {}) for s in spreadsheet.get("sheets") or []]
    if sheet_id is not None:
        for props in sheets:
            if props.get("sheetId") == sheet_id:
                if title and props.get("title") != title:
                    raise WorkspaceRequestError(
                        f"sheet id {sheet_id} is titled {props.get('title')!r}, not {title!r}")
                return {"sheet_id": sheet_id, "title": props.get("title", "")}
        raise WorkspaceRequestError(f"sheet id {sheet_id} is not in this spreadsheet")
    matches = [p for p in sheets if p.get("title") == title]
    if len(matches) != 1:
        raise WorkspaceRequestError(
            f"sheet title {title!r} matches {len(matches)} sheets; resolve it by sheet id")
    return {"sheet_id": matches[0]["sheetId"], "title": matches[0]["title"]}


def a1_sheet_title(title: str) -> str:
    """Quote a sheet title for A1 notation only when it needs quoting."""
    if re.search(r"[^A-Za-z0-9_]", title):
        return "'" + title.replace("'", "''") + "'"
    return title


def sheets_header_read_range(title: str, columns: int) -> str:
    if columns < 1 or columns > MAX_SHEET_COLUMNS:
        raise WorkspaceRequestError(f"columns must be 1-{MAX_SHEET_COLUMNS}")
    return f"{a1_sheet_title(title)}!A1:{_column_letter(columns)}1"


def sheets_append_spec(*, resolved: dict[str, Any], columns: list[ColumnSpec],
                       rows: list[Iterable[Any]], range_start: str = "A1",
                       insert_data_option: str = "INSERT_ROWS") -> dict[str, Any]:
    """A bounded RAW append into one verified sheet.

    Returns a spec the transport posts to ``spreadsheets.values.append``: the caller can
    assert ``resolved`` came from :func:`sheets_resolve_sheet` against freshly fetched
    metadata. Values are coerced per column; strings that would look like formulas stay
    literal because the value input option is RAW for everything unmarked.
    """
    if not columns:
        raise WorkspaceRequestError("an append needs column specs")
    if len(columns) > MAX_SHEET_COLUMNS:
        raise WorkspaceRequestError(f"too many columns (>{MAX_SHEET_COLUMNS})")
    if len(rows) > MAX_SHEET_ROWS:
        raise WorkspaceRequestError(f"too many rows in one append (>{MAX_SHEET_ROWS})")
    values: list[list[Any]] = []
    for r_index, row in enumerate(rows):
        cells = list(row)
        if len(cells) != len(columns):
            raise WorkspaceRequestError(
                f"row {r_index} has {len(cells)} cells but {len(columns)} columns are defined")
        values.append([col.coerce(cell) for col, cell in zip(columns, cells)])
    if not values:
        raise WorkspaceRequestError("nothing to append")
    return {
        "sheet_id": resolved.get("sheet_id"),
        "sheet_title": resolved.get("title", ""),
        "range": f"{a1_sheet_title(resolved.get('title', ''))}!{range_start}",
        "value_input_option": "RAW",
        "insert_data_option": insert_data_option,
        "major_dimension": "ROWS",
        "values": values,
        "body": {"values": values, "majorDimension": "ROWS"},
    }


def sheets_values_lookup_spec(*, resolved: dict[str, Any], first_column: int, last_column: int,
                              max_rows: int = 50) -> dict[str, Any]:
    """A bounded lookup in one verified sheet (never the whole workbook)."""
    if first_column < 1 or last_column < first_column or last_column > MAX_SHEET_COLUMNS:
        raise WorkspaceRequestError("invalid column window")
    if max_rows < 1 or max_rows > 1_000:
        raise WorkspaceRequestError("max_rows must be 1-1000")
    title = a1_sheet_title(resolved.get("title", ""))
    return {
        "sheet_id": resolved.get("sheet_id"),
        "range": f"{title}!{_column_letter(first_column)}2:{_column_letter(last_column)}{max_rows + 1}",
        "major_dimension": "ROWS",
    }


def sheets_verify_append(response: dict[str, Any], spec: dict[str, Any]) -> list[str]:
    """Problems (empty == verified) that Google wrote exactly the intended rows."""
    problems: list[str] = []
    updates = response.get("updates") or {}
    rng = str(updates.get("updatedRange", ""))
    if not rng:
        problems.append("the append response carries no updatedRange")
    title = spec.get("sheet_title", "")
    if title and title not in rng and a1_sheet_title(title).strip("'") not in rng:
        problems.append(f"the append landed in {rng!r}, not sheet {title!r}")
    updated_rows = int(updates.get("updatedRows", 0) or 0)
    if updated_rows != len(spec.get("values") or []):
        problems.append(
            f"the append reports {updated_rows} rows, not the intended "
            f"{len(spec.get('values') or [])}")
    updated_columns = int(updates.get("updatedColumns", 0) or 0)
    expected_columns = len((spec.get("values") or [[]])[0])
    if updated_columns != expected_columns:
        problems.append(
            f"the append reports {updated_columns} columns, not the intended {expected_columns}")
    return problems


def _column_letter(index: int) -> str:
    if index < 1 or index > 18_278:
        raise WorkspaceRequestError("column index out of range")
    letters = ""
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


# ---------------------------------------------------------------------------
# Drive


def drive_generate_ids_request(count: int, *, space: str = "drive") -> dict[str, Any]:
    if count < 1 or count > 100:
        raise WorkspaceRequestError("request 1-100 ids")
    return {"count": count, "space": space, "type": "files"}


def drive_create_file_metadata(name: str, *, mime_type: str, parent_id: str,
                               app_properties: Optional[dict[str, str]] = None,
                               description: str = "") -> dict[str, Any]:
    if not name or len(name) > 250:
        raise WorkspaceRequestError("a file name of 1-250 characters is required")
    if not parent_id:
        raise WorkspaceRequestError(
            "an explicit destination folder id is required; Hutch never resolves folders by name")
    meta: dict[str, Any] = {"name": name, "mimeType": mime_type, "parents": [parent_id]}
    if app_properties:
        meta["appProperties"] = {str(k)[:124]: str(v)[:124] for k, v in app_properties.items()}
    if description:
        meta["description"] = description[:1000]
    return meta


def drive_multipart_body(metadata: dict[str, Any], content: bytes, *, mime_type: str) -> tuple[bytes, str]:
    """A multipart/related upload body for small media (<= MAX_UPLOAD_BYTES)."""
    if not content:
        raise WorkspaceRequestError("refusing to upload empty content")
    if len(content) > MAX_UPLOAD_BYTES:
        raise WorkspaceRequestError(
            f"content exceeds {MAX_UPLOAD_BYTES // 1_000_000} MB; use a resumable upload")
    boundary = "hutch-" + secrets.token_hex(16)
    head = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(metadata)}\r\n"
        f"--{boundary}\r\nContent-Type: {mime_type}\r\n\r\n"
    ).encode("utf-8")
    tail = f"\r\n--{boundary}--".encode("utf-8")
    return head + content + tail, f"multipart/related; boundary={boundary}"


def drive_verify_file(metadata: dict[str, Any], *, expected_id: str, expected_name: str = "",
                      expected_parents: Optional[list[str]] = None) -> list[str]:
    problems: list[str] = []
    if metadata.get("id") != expected_id:
        problems.append(f"file id is {metadata.get('id')!r}, expected {expected_id!r}")
    if metadata.get("trashed"):
        problems.append("the file is in the trash")
    if expected_name and metadata.get("name") != expected_name:
        problems.append(f"file name is {metadata.get('name')!r}, expected {expected_name!r}")
    if expected_parents:
        parents = metadata.get("parents") or []
        for parent in expected_parents:
            if parent not in parents:
                problems.append(f"file is not in expected folder {parent!r}")
    return problems


def drive_is_native(metadata: dict[str, Any]) -> bool:
    """Google-native files (Docs/Sheets) have no binary checksum; verify their content by
    read-back through their own API instead of pretending bytes were checked."""
    return str(metadata.get("mimeType", "")).startswith("application/vnd.google-apps")


def drive_list_params(parent_id: str, *, name: str = "", page_size: int = 20) -> dict[str, Any]:
    if not parent_id:
        raise WorkspaceRequestError("a folder id is required")
    safe = name.replace("\\", "\\\\").replace("'", "\\'")
    q = f"'{parent_id}' in parents and trashed = false"
    if name:
        q += f" and name = '{safe}'"
    return {"q": q, "pageSize": max(1, min(page_size, 100)),
            "fields": "files(id,name,mimeType,parents,size,md5Checksum,createdTime,owners)"}


# ---------------------------------------------------------------------------
# Calendar

ReminderMethod = Literal["popup", "email"]


def calendar_event_id(seed: str) -> str:
    """A deterministic, format-valid event id for create-recovery.

    Google documents caller-supplied IDs so a failed insert can be retried and looked up
    instead of duplicated. Derived from a stable seed (plan id + step id).
    """
    if not seed:
        raise WorkspaceRequestError("an event id seed is required")
    digest = hashlib.sha256(("hutch:" + seed).encode("utf-8")).digest()
    candidate = base64.b32hexencode(digest).decode("ascii").lower().rstrip("=")[:52]
    if not _EVENT_ID_RE.match(candidate):
        raise WorkspaceRequestError("generated event id is malformed")  # pragma: no cover
    return candidate


def _validate_timezone(zone: str) -> str:
    if not zone:
        raise WorkspaceRequestError("an IANA timezone is required for a timed event")
    try:
        ZoneInfo(zone)
    except ZoneInfoNotFoundError as exc:
        raise WorkspaceRequestError(f"{zone!r} is not a known IANA timezone") from exc
    return zone


def calendar_timed_event(*, summary: str, start: str, end: str, timezone: str,
                         description: str = "", location: str = "", event_id: str = "",
                         reminders: Optional[dict[ReminderMethod, int]] = None,
                         attendees: Optional[list[str]] = None) -> dict[str, Any]:
    """A timed event with explicit zone, optional deterministic id and relative reminders."""
    if not summary:
        raise WorkspaceRequestError("an event needs a summary")
    _validate_timezone(timezone)
    for label, value in (("start", start), ("end", end)):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise WorkspaceRequestError(f"{label} is not ISO 8601: {value!r}") from exc
        if parsed.tzinfo is None:
            # A wall-clock time without an offset is interpreted in the event timezone —
            # acceptable, but the zone must exist (checked above).
            pass
    event: dict[str, Any] = {
        "summary": summary[:1000],
        "start": {"dateTime": start, "timeZone": timezone},
        "end": {"dateTime": end, "timeZone": timezone},
    }
    if description:
        event["description"] = description[:8000]
    if location:
        event["location"] = location[:1000]
    if event_id:
        if not _EVENT_ID_RE.match(event_id):
            raise WorkspaceRequestError("event ids must be lowercase base32hex (a-v, 0-9)")
        event["id"] = event_id
    if reminders is not None:
        overrides = []
        for method, minutes in reminders.items():
            if method not in ("popup", "email"):
                raise WorkspaceRequestError(f"unsupported reminder method {method!r}")
            if not isinstance(minutes, int) or not 0 <= minutes <= REMINDER_MINUTES_MAX:
                raise WorkspaceRequestError(
                    f"reminder offsets are minutes before start (0-{REMINDER_MINUTES_MAX}); "
                    "absolute times are not a Calendar reminder")
            overrides.append({"method": method, "minutes": minutes})
        if not overrides:
            raise WorkspaceRequestError("reminders must contain at least one override")
        event["reminders"] = {"useDefault": False, "overrides": overrides}
    if attendees:
        normalized = [a.strip() for a in attendees if a and a.strip()]
        if len(normalized) > 100:
            raise WorkspaceRequestError("at most 100 attendees per request")
        for email in normalized:
            if "@" not in email or len(email) > 254 or any(c.isspace() for c in email):
                raise WorkspaceRequestError(f"invalid attendee address {email!r}")
        event["attendees"] = [{"email": e} for e in normalized]
    return event


def calendar_all_day_event(*, summary: str, day: date, event_id: str = "",
                           description: str = "") -> dict[str, Any]:
    """An all-day event; the API's end date is exclusive, so it is day + 1."""
    if not summary:
        raise WorkspaceRequestError("an event needs a summary")
    event: dict[str, Any] = {
        "summary": summary[:1000],
        "start": {"date": day.isoformat()},
        "end": {"date": (day + timedelta(days=1)).isoformat()},
    }
    if description:
        event["description"] = description[:8000]
    if event_id:
        if not _EVENT_ID_RE.match(event_id):
            raise WorkspaceRequestError("event ids must be lowercase base32hex (a-v, 0-9)")
        event["id"] = event_id
    return event


def calendar_send_updates(choice: str) -> str:
    if choice not in ("all", "externalOnly", "none"):
        raise WorkspaceRequestError("sendUpdates must be explicitly all, externalOnly or none")
    return choice


def calendar_verify_event(event: dict[str, Any], *, expected_id: str, expected_summary: str = "",
                          expected_start: str = "", expected_timezone: str = "",
                          expected_reminders: Optional[dict[str, int]] = None) -> list[str]:
    """Problems (empty == verified) in the read-back event."""
    problems: list[str] = []
    if expected_id and event.get("id") != expected_id:
        problems.append(f"event id is {event.get('id')!r}, expected {expected_id!r}")
    if event.get("status") == "cancelled":
        problems.append("the event is cancelled")
    if expected_summary and event.get("summary") != expected_summary:
        problems.append(f"summary is {event.get('summary')!r}, expected {expected_summary!r}")
    start = event.get("start") or {}
    if expected_start and start.get("dateTime") != expected_start:
        problems.append(f"start is {start.get('dateTime')!r}, expected {expected_start!r}")
    if expected_timezone and start.get("timeZone") != expected_timezone:
        problems.append(f"timezone is {start.get('timeZone')!r}, expected {expected_timezone!r}")
    if expected_reminders is not None:
        overrides = ((event.get("reminders") or {}).get("overrides")) or []
        found = {o.get("method"): o.get("minutes") for o in overrides}
        for method, minutes in expected_reminders.items():
            if found.get(method) != minutes:
                problems.append(
                    f"reminder {method} is {found.get(method)!r}, expected {minutes!r}")
    return problems


# ---------------------------------------------------------------------------
# reminder routing: what each mechanism can honestly carry


@dataclass
class ReminderRoute:
    request: str  # "task" | "event_relative" | "exact_time"
    supported: bool
    mechanism: str  # "tasks.due" | "calendar.reminders" | "hutch.routine" | "unsupported"
    explanation: str
    payload_hint: dict[str, Any]


def route_reminder(kind: str, *, minutes_before: Optional[int] = None,
                   exact_at: str = "") -> ReminderRoute:
    """Say exactly which mechanism can carry this reminder, and what it cannot do.

    Google Tasks' ``due`` records only a date (the documented API discards the time), so
    an exact-time reminder is never routed there. Calendar reminders are offsets from the
    event start. An exact wall-clock alert on a day with no event is a Hutch routine.
    """
    if kind == "task":
        return ReminderRoute(
            request="task", supported=True, mechanism="tasks.due",
            explanation=("Google Tasks stores only the date; the time of day is discarded by the "
                         "API and cannot be read back. Do not use it for an alert."),
            payload_hint={"due": "<date only>"},
        )
    if kind == "event_relative":
        if minutes_before is None or not 0 <= int(minutes_before) <= REMINDER_MINUTES_MAX:
            raise WorkspaceRequestError(
                f"event-relative reminders need an offset in 0-{REMINDER_MINUTES_MAX} minutes")
        return ReminderRoute(
            request="event_relative", supported=True, mechanism="calendar.reminders",
            explanation=("Calendar reminder overrides are relative offsets before the event start; "
                         "they fire around the event occurrence, not at an arbitrary wall-clock time."),
            payload_hint={"reminders": {"overrides": [{"method": "popup", "minutes": int(minutes_before)}],
                                        "useDefault": False}},
        )
    if kind == "exact_time":
        if not exact_at:
            raise WorkspaceRequestError("an exact-time reminder needs its instant")
        return ReminderRoute(
            request="exact_time", supported=True, mechanism="hutch.routine",
            explanation=("No Google API here delivers an exact wall-clock alert without an event: "
                         "Tasks discards the time and Calendar offsets are event-relative. Hutch's "
                         "own scheduled routine is the supported path; configuring it is a separate, "
                         "reviewed action."),
            payload_hint={"routine": {"at": exact_at}},
        )
    raise WorkspaceRequestError(f"unknown reminder kind {kind!r}")
