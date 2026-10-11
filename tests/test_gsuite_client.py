"""Google Workspace transport tests against a local fake Google API.

The real client code paths run over real HTTP: OAuth (PKCE exchange + refresh), Drive
id generation, Docs create/write/read-back, Sheets create/rename/append/read-back,
multipart uploads with md5 verification, 401-refresh-once, and ambiguous-outcome
reconciliation. No Google host is contacted and no credential exists on this machine.
"""

from __future__ import annotations

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

from hutch.actions.execute import ExecutorResult, execute_plan, plan_outcome_report
from hutch.actions.plan import build_plan
from hutch.gsuite.client import GoogleWorkspaceClient, GoogleWorkspaceError
from hutch.gsuite.executors import workspace_executors
from hutch.gsuite.requests import ColumnSpec

SCOPES = ("https://www.googleapis.com/auth/documents "
          "https://www.googleapis.com/auth/spreadsheets "
          "https://www.googleapis.com/auth/drive.file")


class FakeSecrets:
    """In-memory SecretStore (the real one needs the desktop keyring)."""

    def __init__(self):
        self.values: dict[str, str] = {}

    def available(self) -> bool:
        return True

    def put(self, account_id: str, value: str) -> None:
        self.values[account_id] = value

    def get(self, account_id: str):
        return self.values.get(account_id)

    def delete(self, account_id: str) -> None:
        self.values.pop(account_id, None)


class _Handler(BaseHTTPRequestHandler):
    server_version = "fake-google/1"

    def log_message(self, *args):
        pass

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    def _send(self, status: int, payload: dict | None):
        body = json.dumps(payload or {}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _route(self, method: str):
        server = self.server
        path = urlsplit(self.path).path
        server.calls.append({"method": method, "path": self.path,
                             "body_len": int(self.headers.get("Content-Length", 0) or 0)})
        key = f"{method} {path}"
        if key in server.drops:
            server.drops.discard(key)
            self.close_connection = True
            return  # no response: an ambiguous write
        if key in server.overrides:
            entry = server.overrides[key]
            status, payload = entry.pop(0) if isinstance(entry, list) else entry
            if not entry:
                server.overrides.pop(key, None)
            self._send(status, payload)
            return
        body = self._read_body()
        if path == "/token" and method == "POST":
            return self._token(body)
        if path.startswith("/v1/documents"):
            return self._docs(method, path, body)
        if "/v4/spreadsheets" in path:
            return self._sheets(method, path, body)
        if path.startswith("/upload/drive/v3/files"):
            return self._upload(body)
        if "/drive/v3/files" in path:
            return self._drive(method, path, body)
        self._send(404, {"error": {"message": f"unknown route {path}"}})

    def _token(self, body: bytes):
        form = {k: v[0] for k, v in parse_qs(body.decode()).items()}
        self.server.token_grants.append(form)  # type: ignore[attr-defined]
        scope = getattr(self.server, "token_scope", SCOPES)
        payload = {"access_token": f"tok-{len(self.server.token_grants)}",  # type: ignore[attr-defined]
                   "expires_in": 3600, "scope": scope, "token_type": "Bearer"}
        if form.get("grant_type") == "authorization_code":
            payload["refresh_token"] = "refresh-1"
        self._send(200, payload)

    def _docs(self, method: str, path: str, body: bytes):
        server = self.server
        if method == "GET" and "/documents/" in path:
            doc_id = path.rsplit("/", 1)[-1]
            if doc_id not in server.docs:  # type: ignore[attr-defined]
                return self._send(404, {"error": {"message": "document not found"}})
            return self._send(200, {
                "documentId": doc_id, "revisionId": "rev1",
                "tabs": [{"tabProperties": {"tabId": "tab-1", "title": "Main", "index": 0},
                          "documentTab": {"body": {"content": [
                              {"paragraph": {"elements": [
                                  {"textRun": {"content": server.docs[doc_id]}}]}}]}},
                          "childTabs": []}],
            })
        if method == "POST" and path.endswith(":batchUpdate") and "/documents/" in path:
            doc_id = path.split("/documents/")[1].split(":")[0]
            payload = json.loads(body or b"{}")
            for request in payload.get("requests") or []:
                insert = request.get("insertText") or {}
                if insert and insert.get("location", {}).get("tabId") != "tab-1":
                    return self._send(400, {"error": {"message": "insert without the known tab id"}})
                server.docs[doc_id] = server.docs.get(doc_id, "") + str(insert.get("text", ""))
            return self._send(200, {"replies": [{} for _ in payload.get("requests") or []]})
        self._send(404, {"error": {"message": "unknown docs route"}})

    def _sheets(self, method: str, path: str, body: bytes):
        server = self.server
        rest = path.split("/v4/spreadsheets/")[1]
        spreadsheet_id = rest.split("/")[0].split(":")[0]
        book = server.spreadsheets.get(spreadsheet_id)  # type: ignore[attr-defined]
        if method == "GET" and rest == spreadsheet_id:
            if book is None:
                return self._send(404, {"error": {"message": "not found"}})
            return self._send(200, {
                "spreadsheetId": spreadsheet_id,
                "spreadsheetUrl": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}",
                "sheets": [{"properties": p} for p in book["sheets"]]})
        if book is None:
            return self._send(404, {"error": {"message": "not found"}})
        if method == "POST" and rest.endswith(":batchUpdate"):
            payload = json.loads(body or b"{}")
            for request in payload.get("requests") or []:
                rename = request.get("updateSheetProperties")
                if rename:
                    for props in book["sheets"]:
                        if props["sheetId"] == rename["properties"]["sheetId"]:
                            props["title"] = rename["properties"]["title"]
                add = request.get("addSheet")
                if add:
                    book["sheets"].append({"sheetId": max(p["sheetId"] for p in book["sheets"]) + 1,
                                           "title": add["properties"]["title"],
                                           "index": len(book["sheets"])})
            return self._send(200, {"replies": [{} for _ in payload.get("requests") or []]})
        if method == "POST" and rest.endswith(":append"):
            rng = rest.split("/values/", 1)[1][:-len(":append")]
            title = unquote(rng).rsplit("!", 1)[0].strip("'")
            payload = json.loads(body or b"{}")
            values = payload.get("values") or []
            props = next((p for p in book["sheets"] if p["title"] == title), None)
            if props is None:
                return self._send(404, {"error": {"message": "no such sheet"}})
            props.setdefault("rows", []).extend(values)
            return self._send(200, {"updates": {
                "updatedRange": f"{title}!A{len(props['rows']) - len(values) + 2}",
                "updatedRows": len(values), "updatedColumns": len(values[0]) if values else 0}})
        if method == "GET" and "/values/" in rest:
            rng = unquote(rest.split("/values/", 1)[1])
            title = rng.rsplit("!", 1)[0].strip("'")
            props = next((p for p in book["sheets"] if p["title"] == title), None)
            return self._send(200, {"range": rng, "values": (props or {}).get("rows", [])})
        self._send(404, {"error": {"message": "unknown sheets route"}})

    def _drive(self, method: str, path: str, body: bytes):
        server = self.server
        if method == "GET" and path.endswith("/files/generateIds"):
            server.id_counter += 1  # type: ignore[attr-defined]
            return self._send(200, {"ids": [f"file_{server.id_counter:04d}"]})
        if method == "POST" and path.endswith("/files"):
            metadata = json.loads(body or b"{}")
            file_id = str(metadata.get("id") or f"file_{server.id_counter:04d}")
            server.files[file_id] = {  # type: ignore[attr-defined]
                "id": file_id, "name": metadata.get("name", ""),
                "mimeType": metadata.get("mimeType", ""),
                "parents": metadata.get("parents", []),
                "appProperties": metadata.get("appProperties", {}),
                "webViewLink": f"https://docs.google.com/file/d/{file_id}",
            }
            if metadata.get("mimeType") == "application/vnd.google-apps.spreadsheet":
                server.spreadsheets[file_id] = {"sheets": [  # type: ignore[attr-defined]
                    {"sheetId": 1, "title": "Sheet1", "index": 0}]}
            if metadata.get("mimeType") == "application/vnd.google-apps.document":
                server.docs.setdefault(file_id, "")  # type: ignore[attr-defined]
            return self._send(200, server.files[file_id])
        if method == "GET" and "/files/" in path:
            file_id = path.rsplit("/", 1)[-1]
            stored = server.files.get(file_id)  # type: ignore[attr-defined]
            if not stored or stored.get("trashed"):
                return self._send(404, {"error": {"message": "file not found"}})
            return self._send(200, stored)
        if method == "PATCH" and "/files/" in path:
            file_id = path.rsplit("/", 1)[-1]
            stored = server.files.get(file_id)  # type: ignore[attr-defined]
            if not stored:
                return self._send(404, {"error": {"message": "file not found"}})
            payload = json.loads(body or b"{}")
            stored.update({k: v for k, v in payload.items() if k != "parents"})
            query = parse_qs(urlsplit(self.path).query)
            parents = list(stored.get("parents") or [])
            if query.get("addParents"):
                for p in query["addParents"][0].split(","):
                    if p not in parents:
                        parents.append(p)
            if query.get("removeParents"):
                parents = [p for p in parents if p not in query["removeParents"][0].split(",")]
            stored["parents"] = parents
            return self._send(200, stored)
        self._send(404, {"error": {"message": "unknown drive route"}})

    def _upload(self, body: bytes):
        server = self.server
        ctype = self.headers.get("Content-Type", "")
        boundary = ctype.split("boundary=", 1)[1].encode() if "boundary=" in ctype else b""
        metadata: dict = {}
        content = b""
        for chunk in body.split(b"--" + boundary):
            if b"application/json" in chunk[:200]:
                metadata = json.loads(chunk.split(b"\r\n\r\n", 1)[1].strip())
            elif b"audio/" in chunk[:200] or b"text/" in chunk[:200]:
                content = chunk.split(b"\r\n\r\n", 1)[1].rstrip(b"\r\n")
        file_id = str(metadata.get("id") or f"file_{server.id_counter:04d}")
        stored = {
            "id": file_id, "name": metadata.get("name", ""),
            "mimeType": metadata.get("mimeType", ""), "parents": metadata.get("parents", []),
            "size": str(len(content)), "md5Checksum": hashlib.md5(content).hexdigest(),
            "webViewLink": f"https://drive.google.com/file/d/{file_id}",
            "appProperties": metadata.get("appProperties", {}),
        }
        server.files[file_id] = stored  # type: ignore[attr-defined]
        self._send(200, stored)

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def do_PATCH(self):
        self._route("PATCH")


@pytest.fixture()
def google(tmp_path, monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.calls = []            # type: ignore[attr-defined]
    server.drops = set()         # type: ignore[attr-defined]
    server.overrides = {}        # type: ignore[attr-defined]
    server.files = {}            # type: ignore[attr-defined]
    server.docs = {}             # type: ignore[attr-defined]
    server.spreadsheets = {}     # type: ignore[attr-defined]
    server.id_counter = 0        # type: ignore[attr-defined]
    server.token_grants = []     # type: ignore[attr-defined]
    server.token_scope = SCOPES  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port
    monkeypatch.setattr("hutch.gsuite.client.TOKEN_URL", f"http://127.0.0.1:{port}/token")
    monkeypatch.setattr("hutch.gsuite.client.REVOKE_URL", f"http://127.0.0.1:{port}/revoke")
    secrets = FakeSecrets()
    client = GoogleWorkspaceClient(
        tmp_path, "test-client-id", secrets_store=secrets,
        docs_base=f"http://127.0.0.1:{port}/v1",
        sheets_base=f"http://127.0.0.1:{port}/v4",
        drive_base=f"http://127.0.0.1:{port}/drive/v3",
        upload_base=f"http://127.0.0.1:{port}/upload/drive/v3",
        allow_custom_endpoint=True,
    )
    try:
        yield server, client, secrets
    finally:
        server.shutdown()
        thread.join(timeout=2)


def _connect(server, client, secrets):
    start = client.start("Test account", "http://127.0.0.1:9/cb")
    state = parse_qs(urlsplit(start.url).query)["state"][0]
    assert "code_challenge=" in start.url and "S256" in start.url
    account = client.finish(state, "auth-code", "http://127.0.0.1:9/cb")
    assert account.account_id.startswith("gws_")
    assert json.loads(secrets.values[account.account_id])["refresh_token"] == "refresh-1"
    assert server.token_grants[0]["grant_type"] == "authorization_code"
    assert server.token_grants[0]["code_verifier"]
    return account


def test_oauth_connect_refresh_caching_and_scope_validation(google):
    server, client, secrets = google
    account = _connect(server, client, secrets)
    assert [a.account_id for a in client.accounts()] == [account.account_id]

    client.access_token(account.account_id)
    client.access_token(account.account_id)
    refreshes = [g for g in server.token_grants if g["grant_type"] == "refresh_token"]
    assert len(refreshes) == 1  # cached

    server.token_scope = SCOPES + " https://www.googleapis.com/auth/drive"
    start = client.start("Broad", "http://127.0.0.1:9/cb")
    state = parse_qs(urlsplit(start.url).query)["state"][0]
    with pytest.raises(GoogleWorkspaceError) as exc:
        client.finish(state, "code", "http://127.0.0.1:9/cb")
    assert "broader" in str(exc.value)

    server.token_scope = SCOPES.split(" ")[0]  # missing most scopes
    start = client.start("Narrow", "http://127.0.0.1:9/cb")
    state = parse_qs(urlsplit(start.url).query)["state"][0]
    with pytest.raises(GoogleWorkspaceError) as exc:
        client.finish(state, "code", "http://127.0.0.1:9/cb")
    assert "did not grant" in str(exc.value)


def test_create_document_writes_with_tab_and_reads_back(google):
    server, client, secrets = google
    account = _connect(server, client, secrets)
    result = client.create_document(account.account_id, title="Thursday brief",
                                    body_text="Agenda:\n- item", parent_folder_id="folder-1")
    assert result["verification"] == []
    stored = server.files[result["document_id"]]
    assert stored["parents"] == ["folder-1"]
    assert stored["mimeType"] == "application/vnd.google-apps.document"
    assert "Agenda:" in server.docs[result["document_id"]]


def test_401_once_refreshes_then_retries(google):
    server, client, secrets = google
    account = _connect(server, client, secrets)
    server.files["file_0001"] = {"id": "file_0001", "name": "x", "parents": [],
                                 "trashed": False, "mimeType": "application/pdf"}
    server.overrides["GET /drive/v3/files/file_0001"] = [
        (401, {"error": {"message": "expired"}}),
        (200, {"id": "file_0001", "name": "x", "parents": [], "trashed": False,
               "mimeType": "application/pdf"}),
    ]
    metadata = client.file_metadata(account.account_id, "file_0001")
    assert metadata["id"] == "file_0001"
    refreshes = [g for g in server.token_grants if g["grant_type"] == "refresh_token"]
    assert len(refreshes) >= 1


def test_sheets_create_names_append_and_read_back(google):
    server, client, secrets = google
    account = _connect(server, client, secrets)
    created = client.create_spreadsheet(account.account_id, title="Tracker",
                                        sheet_titles=["Runs", "Summary"],
                                        parent_folder_id="folder-9", hutch_key="syn_a")
    assert created["verification"] == []
    assert set(created["sheets"]) == {"Runs", "Summary"}
    assert server.files[created["spreadsheet_id"]]["appProperties"]["hutch_key"] == "syn_a"

    result = client.append_rows(
        account.account_id, created["spreadsheet_id"],
        columns=[ColumnSpec("id", "text"), ColumnSpec("n", "integer")],
        rows=[["007", 3]], title="Runs")
    assert result["verification"] == []
    assert result["updated_range"].startswith("Runs!")
    assert result["read_back"][-1] == ["007", 3]
    assert any("values/Runs!A1:append" in c["path"] for c in server.calls)


def test_ambiguous_append_reconciles_without_duplicating(google):
    server, client, secrets = google
    account = _connect(server, client, secrets)
    created = client.create_spreadsheet(account.account_id, title="T", sheet_titles=["Runs"])
    sheet_id = created["spreadsheet_id"]
    server.drops.add(f"POST /v4/spreadsheets/{sheet_id}/values/Runs!A1:append")
    # The row actually landed; only the response was lost.
    server.spreadsheets[sheet_id]["sheets"][0].setdefault("rows", []).append(["r-1", 1])
    result = client.append_rows(account.account_id, sheet_id,
                                columns=[ColumnSpec("id", "text"), ColumnSpec("n", "integer")],
                                rows=[["r-1", 1]], title="Runs")
    assert result["reconciled"] is True
    assert result["verification"] == []
    assert server.spreadsheets[sheet_id]["sheets"][0]["rows"] == [["r-1", 1]]


def test_upload_verifies_md5_and_reports_size_mismatch(google):
    server, client, secrets = google
    account = _connect(server, client, secrets)
    content = b"RIFF" + b"\x00" * 100
    result = client.upload_file(account.account_id, name="episode.wav", parent_id="folder-2",
                                content=content, mime_type="audio/wav")
    assert result["verification"] == []
    assert server.files[result["file_id"]]["md5Checksum"] == hashlib.md5(content).hexdigest()


def test_outcome_unknown_when_create_response_is_lost(google):
    server, client, secrets = google
    account = _connect(server, client, secrets)
    server.drops.add("POST /drive/v3/files")
    server.drops.add("GET /drive/v3/files/file_0001")
    with pytest.raises(GoogleWorkspaceError):
        client.create_document(account.account_id, title="lost")


def test_plan_executes_workspace_journey_and_reuses_on_retry(google, store, tmp_path):
    server, client, secrets = google
    account = _connect(server, client, secrets)
    media = tmp_path / "overview.wav"
    media.write_bytes(b"RIFF" + b"\x11" * 64)

    specs = [
        {"kind": "local_draft", "id": "draft", "title": "Draft the brief",
         "target": {"service": "synthesis", "display": "brief v1"},
         "inputs": {"manifest": "syn_x"}},
        {"kind": "cloud_create", "id": "doc", "title": "Create the brief doc",
         "target": {"service": "docs", "account": account.account_id, "parent_id": "folder-1",
                    "display": "Docs 'Thursday brief' -> folder-1"},
         "inputs": {"title": "Thursday brief", "body_text": "Agenda:\n- review"}},
        {"kind": "cloud_create", "id": "sheet", "title": "Create the tracker",
         "target": {"service": "sheets", "account": account.account_id, "parent_id": "folder-1",
                    "display": "Sheets 'Tracker' -> folder-1"},
         "inputs": {"title": "Tracker", "sheet_titles": ["Runs"]}},
        {"kind": "cloud_edit", "id": "row", "title": "Append the run row",
         "target": {"service": "sheets", "account": account.account_id, "display": "Tracker!Runs"},
         "inputs": {"spreadsheet_id": {"$remote_id": "sheet"},
                    "columns": [{"name": "id", "kind": "text"}, {"name": "n", "kind": "integer"}],
                    "rows": [["run-1", 7]], "sheet_title": "Runs"}},
        {"kind": "cloud_create", "id": "media", "title": "Upload the audio",
         "target": {"service": "drive", "account": account.account_id, "parent_id": "folder-1",
                    "display": "overview.wav -> folder-1"},
         "inputs": {"name": "overview.wav", "mime_type": "audio/wav", "local_path": str(media)}},
    ]
    plan = build_plan("Prepare the meeting package", specs)
    # the reference created the dependency, so the append runs after the sheet exists
    row_step = next(s for s in plan.steps if s.id == "row")
    assert row_step.depends_on == ["sheet"]

    executors = dict(workspace_executors(client))
    executors["local_draft"] = lambda step, plan: ExecutorResult(ok=True, remote_id="brief-v1")
    executed = execute_plan(plan, store=store, executors=executors,
                            approved_hash=plan.approval_scope_hash)
    assert executed.status == "completed", plan_outcome_report(executed)
    sheet_step = next(s for s in executed.steps if s.id == "sheet")
    doc_step = next(s for s in executed.steps if s.id == "doc")
    media_step = next(s for s in executed.steps if s.id == "media")
    assert "Agenda:" in server.docs[doc_step.remote_id]
    assert any(s["title"] == "Runs" for s in server.spreadsheets[sheet_step.remote_id]["sheets"])
    assert server.spreadsheets[sheet_step.remote_id]["sheets"][0]["rows"] == [["run-1", 7]]
    assert server.files[media_step.remote_id]["md5Checksum"]
    assert plan_outcome_report(executed)["counts"]["succeeded"] == 5

    writes = [c for c in server.calls if c["method"] in ("POST", "PATCH")]
    again = execute_plan(plan, store=store, executors=executors,
                         approved_hash=plan.approval_scope_hash)
    assert again.status == "completed"
    assert [c for c in server.calls if c["method"] in ("POST", "PATCH")] == writes
