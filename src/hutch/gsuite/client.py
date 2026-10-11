"""OAuth transport for Google Docs/Sheets/Drive, built on the request contracts.

Mirrors ``google_calendar.py``: installed-app authorization-code flow with PKCE, refresh
credentials only in the Linux Secret Service, fixed Google endpoints, redirects disabled,
and one atomic refresh per rotation window. Every write uses the identity/verification
rules from :mod:`hutch.gsuite.requests`; ambiguous outcomes are reported as such and
reconciled by stable identity before any retry:

* Drive creates use ``files.generateIds`` so the caller already knows the id a lost
  response would have produced; reconciliation is a ``files.get`` on that id.
* Spreadsheet creation (server-assigned id) tags the file with a Hutch app property, so a
  lost response reconciles through a bounded ``files.list`` appProperties query.
* Appends reconcile by reading a bounded window for the exact intended row instead of
  re-appending.

The client performs I/O; it is injected into plan executors by the caller.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote, urlencode, urlsplit

import httpx

from ..google_calendar import OAuthStart, SecretStore, SecretToolStore, GoogleCalendarError
from . import requests as ws

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
CALLBACK_PATH = "/api/v1/connections/google-workspace/callback"
STATE_TTL_SECONDS = 600
ACCOUNT_RE = re.compile(r"^gws_[0-9a-f]{24}$")
REQUESTED_SCOPES = ws.GOOGLE_WORKSPACE_SCOPES
#: OpenID noise Google may return with a granted scope string; not an expansion of access.
_ALLOWED_EXTRA_SCOPES = {"openid", "email", "profile"}

_ACCESS_LOCK = threading.Lock()
_ACCESS_CACHE: dict[tuple[str, str], tuple[float, str]] = {}


class GoogleWorkspaceError(ValueError):
    """A safe, actionable OAuth or Workspace API failure."""


class GoogleWorkspaceOutcomeUnknown(GoogleWorkspaceError):
    """A write may have reached Google but no verifiable response returned."""


class WorkspaceSecretToolStore(SecretToolStore):
    """Secret Service store namespaced to the Workspace connection."""

    service = "hutch.google-workspace"
    feature_name = "Google Workspace"
    account_pattern = ACCOUNT_RE
    probe_account = "gws_000000000000000000000000"

    @classmethod
    def _account(cls, account_id: str) -> str:
        if not cls.account_pattern.fullmatch(account_id):
            raise GoogleWorkspaceError(f"{cls.feature_name} account reference is invalid")
        return account_id

    def _call(self, args: list[str], *, input_text: Optional[str] = None):
        try:
            return super()._call(args, input_text=input_text)
        except GoogleCalendarError as exc:  # translate the shared store's error type
            raise GoogleWorkspaceError(str(exc)) from None

    def available(self) -> bool:
        try:
            return super().available()
        except Exception:  # noqa: BLE001 - availability probes never raise
            return False


def _atomic_private_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(path.suffix + f".{secrets.token_hex(6)}.tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def _read_private_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _safe_detail(response: httpx.Response) -> str:
    """A bounded, secret-free error detail from a Google error body."""
    try:
        body = response.json()
        message = str((body.get("error") or {}).get("message") if isinstance(body.get("error"), dict)
                      else body.get("error") or "")
    except ValueError:
        message = response.text[:200]
    return (message or "no detail")[:300]


@dataclass(frozen=True)
class WorkspaceAccount:
    account_id: str
    label: str
    scopes: tuple[str, ...]


class GoogleWorkspaceClient:
    """Docs/Sheets/Drive operations for one or more connected Google accounts."""

    callback_path = CALLBACK_PATH
    feature_name = "Google Workspace"

    @classmethod
    def callback_uri(cls, request: Any) -> str:
        """The exact local callback URI, validated the same way as Google Calendar's."""
        host = request.headers.get("host", "")
        try:
            host_parts = urlsplit("//" + host)
            port = int(request.scope["server"][1])
            peer = request.client.host if request.client else ""
            import ipaddress

            try:
                is_loopback = ipaddress.ip_address(peer).is_loopback
            except ValueError:
                is_loopback = peer == "testclient"
            valid = (request.url.scheme == "http" and host_parts.hostname == "127.0.0.1" and
                     host_parts.username is None and host_parts.password is None and
                     (host_parts.port is None or host_parts.port == port) and 1 <= port <= 65535 and is_loopback)
        except (KeyError, TypeError, ValueError, IndexError):
            valid = False
        if not valid:
            raise GoogleWorkspaceError(
                "Google Workspace sign-in must use Hutch's exact local 127.0.0.1 callback")
        return f"http://127.0.0.1:{port}{CALLBACK_PATH}"

    def __init__(self, state_dir: Path, client_id: str, *, secrets_store: Optional[SecretStore] = None,
                 http_factory=None, docs_base: str = ws.DOCS_API, sheets_base: str = ws.SHEETS_API,
                 drive_base: str = ws.DRIVE_API, upload_base: str = ws.DRIVE_UPLOAD_API,
                 allow_custom_endpoint: bool = False, timeout_s: float = 60.0):
        self.state_dir = Path(state_dir)
        self.client_id = str(client_id or "").strip()
        self.secrets = secrets_store or WorkspaceSecretToolStore()
        self._http_factory = http_factory or (lambda: httpx.Client(timeout=timeout_s, follow_redirects=False))
        if not allow_custom_endpoint:
            for name, url in (("docs", docs_base), ("sheets", sheets_base), ("drive", drive_base),
                              ("upload", upload_base)):
                if not url.startswith(("https://docs.googleapis.com", "https://sheets.googleapis.com",
                                       "https://www.googleapis.com")):
                    raise GoogleWorkspaceError(
                        f"refusing to send Google workspace credentials to a custom {name} endpoint; "
                        "pass allow_custom_endpoint=True only for an explicit test connection")
        self.docs_base = docs_base.rstrip("/")
        self.sheets_base = sheets_base.rstrip("/")
        self.drive_base = drive_base.rstrip("/")
        self.upload_base = upload_base.rstrip("/")

    # ------------------------------------------------------------------ files

    @property
    def _accounts_path(self) -> Path:
        return self.state_dir / "google-workspace-accounts.json"

    @property
    def _pending_path(self) -> Path:
        return self.state_dir / "google-workspace-pending.json"

    def _read_accounts(self) -> dict[str, Any]:
        return _read_private_json(self._accounts_path)

    # ------------------------------------------------------------------ OAuth

    def start(self, label: str, redirect_uri: str) -> OAuthStart:
        if not self.client_id:
            raise GoogleWorkspaceError(
                "no Google OAuth client id is configured; set HUTCH_GOOGLE_OAUTH_CLIENT_ID or "
                "save one in Connections before connecting Workspace")
        if not redirect_uri.startswith("http://127.0.0.1:") and not redirect_uri.startswith("http://localhost:"):
            raise GoogleWorkspaceError("the OAuth redirect must be loopback")
        verifier = _b64url(secrets.token_bytes(48))
        challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
        state = secrets.token_urlsafe(24)
        pending = _read_private_json(self._pending_path)
        now = time.time()
        pending = {k: v for k, v in pending.items()
                   if isinstance(v, dict) and now - float(v.get("created_at", 0)) < STATE_TTL_SECONDS}
        pending[state] = {"verifier": verifier, "redirect_uri": redirect_uri,
                          "label": str(label or "Google Workspace")[:120], "created_at": now,
                          "scopes": list(REQUESTED_SCOPES)}
        _atomic_private_json(self._pending_path, pending)
        query = urlencode({
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(REQUESTED_SCOPES),
            "access_type": "offline",
            "prompt": "consent select_account",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        })
        return OAuthStart(url=f"{AUTH_URL}?{query}", state=state)

    def cancel(self, state: str) -> None:
        pending = _read_private_json(self._pending_path)
        if state in pending:
            pending.pop(state)
            _atomic_private_json(self._pending_path, pending)

    def finish(self, state: str, code: str, redirect_uri: str) -> WorkspaceAccount:
        pending = _read_private_json(self._pending_path)
        entry = pending.pop(state, None)
        if not isinstance(entry, dict):
            raise GoogleWorkspaceError("this Workspace authorization attempt has expired; start again")
        # Consume the state now: an attempt is single-use even when the exchange fails.
        _atomic_private_json(self._pending_path, pending)
        if time.time() - float(entry.get("created_at", 0)) > STATE_TTL_SECONDS:
            raise GoogleWorkspaceError("this Workspace authorization attempt has expired; start again")
        if entry.get("redirect_uri") != redirect_uri:
            raise GoogleWorkspaceError("the OAuth redirect does not match the attempt that started it")
        payload = {
            "client_id": self.client_id,
            "code": code.strip(),
            "code_verifier": entry["verifier"],
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        try:
            with self._http_factory() as http:
                response = http.post(TOKEN_URL, data=payload,
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        except httpx.HTTPError as exc:
            raise GoogleWorkspaceError(f"Google token exchange failed: {type(exc).__name__}") from exc
        if response.status_code != 200:
            raise GoogleWorkspaceError(f"Google rejected the authorization: {_safe_detail(response)}")
        try:
            body = response.json()
            refresh_token = str(body.get("refresh_token") or "")
            scope_set = set(str(body.get("scope") or "").split())
        except (ValueError, AttributeError) as exc:
            raise GoogleWorkspaceError("Google returned an unreadable token response") from exc
        if not refresh_token:
            raise GoogleWorkspaceError(
                "Google returned no refresh token; revoke the app's access and connect again")
        missing = set(REQUESTED_SCOPES) - scope_set
        if missing:
            raise GoogleWorkspaceError(
                "Google did not grant the requested Workspace scopes "
                f"({', '.join(sorted(missing))}); disconnect and reconnect")
        extra = scope_set - set(REQUESTED_SCOPES) - _ALLOWED_EXTRA_SCOPES
        if extra:
            raise GoogleWorkspaceError(
                "Google granted broader scopes than requested "
                f"({', '.join(sorted(extra))}); reconnect and grant only the requested access")
        account_id = "gws_" + secrets.token_hex(12)
        account = WorkspaceAccount(account_id=account_id, label=str(entry.get("label") or "Google Workspace"),
                                   scopes=tuple(sorted(scope_set)))
        self.secrets.put(account_id, json.dumps({"refresh_token": refresh_token,
                                                 "scopes": sorted(scope_set)}))
        accounts = self._read_accounts()
        accounts[account_id] = {"label": account.label, "scopes": list(account.scopes),
                                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        _atomic_private_json(self._accounts_path, accounts)
        return account

    def accounts(self) -> list[WorkspaceAccount]:
        return [WorkspaceAccount(account_id=aid, label=str(row.get("label", "Google Workspace")),
                                 scopes=tuple(row.get("scopes") or ()))
                for aid, row in self._read_accounts().items()]

    def disconnect(self, account_id: str) -> None:
        stored = self.secrets.get(account_id)
        if stored:
            try:
                payload = json.loads(stored)
                token = str(payload.get("refresh_token") or "")
            except ValueError:
                token = ""
            if token:
                try:
                    with self._http_factory() as http:
                        http.post(REVOKE_URL, data={"token": token})
                except httpx.HTTPError:
                    pass  # local removal proceeds even if Google revocation cannot be reached
        self.secrets.delete(account_id)
        accounts = self._read_accounts()
        accounts.pop(account_id, None)
        _atomic_private_json(self._accounts_path, accounts)

    # ------------------------------------------------------------------ tokens

    def access_token(self, account_id: str, *, force: bool = False) -> str:
        key = (account_id, self.client_id)
        now = time.monotonic()
        with _ACCESS_LOCK:
            if not force:
                cached = _ACCESS_CACHE.get(key)
                if cached and cached[0] > now + 30:
                    return cached[1]
        stored = self.secrets.get(account_id)
        if not stored:
            raise GoogleWorkspaceError("this Workspace account is not connected on this machine")
        try:
            refresh_token = str(json.loads(stored).get("refresh_token") or "")
        except ValueError:
            raise GoogleWorkspaceError("the stored Workspace credential is unreadable; reconnect") from None
        if not refresh_token:
            raise GoogleWorkspaceError("the stored Workspace credential has no refresh token; reconnect")
        try:
            with self._http_factory() as http:
                response = http.post(TOKEN_URL, data={
                    "client_id": self.client_id,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                })
        except httpx.HTTPError as exc:
            raise GoogleWorkspaceError(f"Google token refresh failed: {type(exc).__name__}") from exc
        if response.status_code == 400:
            raise GoogleWorkspaceError(
                "Google refused the stored Workspace credential (it may have been revoked); "
                "reconnect the account")
        if response.status_code != 200:
            raise GoogleWorkspaceError(f"Google token refresh failed: {_safe_detail(response)}")
        try:
            body = response.json()
            token = str(body["access_token"])
            expires_in = float(body.get("expires_in", 3000))
        except (ValueError, KeyError) as exc:
            raise GoogleWorkspaceError("Google returned an unreadable token response") from exc
        with _ACCESS_LOCK:
            _ACCESS_CACHE[key] = (time.monotonic() + min(expires_in, 3600), token)
        return token

    # ------------------------------------------------------------------ transport

    def _request(self, method: str, url: str, account_id: str, *, params: Optional[dict] = None,
                 json_body: Optional[dict] = None, content: Optional[bytes] = None,
                 headers: Optional[dict] = None, purpose: str = "Google Workspace request",
                 expected: tuple[int, ...] = (200, 201, 204)) -> httpx.Response:
        write = method in ("POST", "PATCH", "PUT", "DELETE")

        def send(token: str) -> httpx.Response:
            merged = {"Authorization": f"Bearer {token}", **(headers or {})}
            with self._http_factory() as http:
                return http.request(method, url, params=params, json=json_body,
                                    content=content, headers=merged)

        try:
            response = send(self.access_token(account_id))
            if response.status_code == 401:
                response = send(self.access_token(account_id, force=True))
        except httpx.HTTPError as exc:
            if write:
                raise GoogleWorkspaceOutcomeUnknown(
                    f"{purpose}: the request may have reached Google ({type(exc).__name__})") from exc
            raise GoogleWorkspaceError(f"{purpose} failed: {type(exc).__name__}") from exc
        if response.status_code in expected:
            return response
        detail = _safe_detail(response)
        if response.status_code >= 500 or response.status_code == 429:
            if write:
                raise GoogleWorkspaceOutcomeUnknown(
                    f"{purpose}: Google returned {response.status_code} for a write; the effect is "
                    f"unknown ({detail})")
            raise GoogleWorkspaceError(f"{purpose}: Google returned {response.status_code}: {detail}")
        raise GoogleWorkspaceError(f"{purpose}: Google returned {response.status_code}: {detail}")

    def _json(self, method: str, url: str, account_id: str, **kwargs) -> dict[str, Any]:
        response = self._request(method, url, account_id, **kwargs)
        if response.status_code == 204 or not response.content:
            return {}
        try:
            data = response.json()
        except ValueError as exc:
            raise GoogleWorkspaceError("Google returned an unreadable response") from exc
        if not isinstance(data, dict):
            raise GoogleWorkspaceError("Google returned an unexpected response shape")
        return data

    # ------------------------------------------------------------------ Drive

    def generate_file_id(self, account_id: str) -> str:
        data = self._json("GET", f"{self.drive_base}/files/generateIds", account_id,
                          params=ws.drive_generate_ids_request(1), purpose="Drive id generation")
        ids = data.get("ids") or []
        if not ids or not isinstance(ids[0], str):
            raise GoogleWorkspaceError("Drive returned no usable file id")
        return ids[0]

    def file_metadata(self, account_id: str, file_id: str) -> dict[str, Any]:
        fields = "id,name,mimeType,parents,size,md5Checksum,trashed,webViewLink,appProperties,createdTime"
        return self._json("GET", f"{self.drive_base}/files/{file_id}", account_id,
                          params={"fields": fields}, purpose="Drive file read-back")

    def find_files_by_app_key(self, account_id: str, key: str, value: str) -> list[dict[str, Any]]:
        safe_value = value.replace("\\", "\\\\").replace("'", "\\'")
        safe_key = key.replace("\\", "\\\\").replace("'", "\\'")
        params = {
            "q": f"appProperties has {{ key='{safe_key}' and value='{safe_value}' }} and trashed = false",
            "pageSize": 10,
            "fields": "files(id,name,mimeType,parents,size,md5Checksum,createdTime,appProperties)",
        }
        data = self._json("GET", f"{self.drive_base}/files", account_id, params=params,
                          purpose="Drive reconciliation search")
        return list(data.get("files") or [])

    def move_file(self, account_id: str, file_id: str, *, add_parent: str,
                  remove_parents: str = "") -> dict[str, Any]:
        params: dict[str, Any] = {"addParents": add_parent, "fields": "id,parents"}
        if remove_parents:
            params["removeParents"] = remove_parents
        return self._json("PATCH", f"{self.drive_base}/files/{file_id}", account_id,
                          params=params, json_body={}, purpose="Drive move")

    def update_app_properties(self, account_id: str, file_id: str,
                              properties: dict[str, str]) -> dict[str, Any]:
        return self._json("PATCH", f"{self.drive_base}/files/{file_id}", account_id,
                          params={"fields": "id,appProperties"},
                          json_body={"appProperties": properties}, purpose="Drive tagging")

    # ------------------------------------------------------------------ Docs

    def create_document(self, account_id: str, *, title: str, body_text: str = "",
                        parent_folder_id: str = "") -> dict[str, Any]:
        """Create a genuine Google Doc (Drive-native), write the body, and read it back."""
        if len(body_text) > ws.MAX_DOC_INSERT_CHARS:
            raise GoogleWorkspaceError("the document body exceeds the insert budget")
        file_id = self.generate_file_id(account_id)
        metadata = ws.drive_create_file_metadata(
            title, mime_type=ws.DOC_MIME, parent_id=parent_folder_id or "root",
            app_properties={"hutch_created": "1"})
        metadata["id"] = file_id
        try:
            created = self._json("POST", f"{self.drive_base}/files", account_id,
                                 params={"supportsAllDrives": "true", "fields": "id,name,parents,webViewLink"},
                                 json_body=metadata, purpose="Docs creation")
        except GoogleWorkspaceOutcomeUnknown:
            # The id was ours: reconcile by looking for exactly that file.
            existing = self._json("GET", f"{self.drive_base}/files/{file_id}", account_id,
                                  params={"fields": "id,name,parents,trashed,webViewLink"},
                                  purpose="Docs reconciliation")
            if existing.get("trashed"):
                raise
            created = existing
        actual_id = str(created.get("id") or file_id)
        result: dict[str, Any] = {
            "document_id": actual_id,
            "title": str(created.get("name") or title),
            "web_view_link": str(created.get("webViewLink") or ""),
            "tab_id": "",
            "verification": [],
        }
        document = self.read_document(account_id, actual_id)
        tabs = ws.walk_tabs(document)
        if not tabs or not tabs[0]["tab_id"]:
            result["verification"].append("the new document reported no tabs")
            return result
        tab_id = tabs[0]["tab_id"]
        result["tab_id"] = tab_id
        if body_text:
            requests = ws.docs_insert_text_requests(body_text, tab_id=tab_id)
            self._json("POST", f"{self.docs_base}/documents/{actual_id}:batchUpdate", account_id,
                       json_body=ws.docs_batch_update_body(
                           requests, required_revision_id=str(document.get("revisionId") or "")),
                       purpose="Docs body write")
            document = self.read_document(account_id, actual_id)
        problems = ws.docs_verify_text(document, tab_id=tab_id,
                                       expected=body_text.split("\n", 1)[0][:80] if body_text else "")
        result["verification"] = problems
        result["revision_id"] = str(document.get("revisionId") or "")
        return result

    def read_document(self, account_id: str, document_id: str) -> dict[str, Any]:
        return self._json("GET", f"{self.docs_base}/documents/{document_id}", account_id,
                          params={"includeTabsContent": "true"}, purpose="Docs read-back")

    def batch_update_document(self, account_id: str, document_id: str,
                              requests: list[dict[str, Any]], *,
                              required_revision_id: str = "") -> dict[str, Any]:
        return self._json("POST", f"{self.docs_base}/documents/{document_id}:batchUpdate", account_id,
                          json_body=ws.docs_batch_update_body(requests,
                                                              required_revision_id=required_revision_id),
                          purpose="Docs update")

    # ------------------------------------------------------------------ Sheets

    def create_spreadsheet(self, account_id: str, *, title: str, sheet_titles: list[str],
                           parent_folder_id: str = "", hutch_key: str = "") -> dict[str, Any]:
        """Create a spreadsheet with a caller-known file id, then name its sheets.

        Creating through Drive with ``files.generateIds`` gives the same id-based
        reconciliation as documents. Sheet names are applied with a batchUpdate; the
        default sheet is renamed rather than orphaned where possible.
        """
        ws.sheets_create_payload(title, sheet_titles)  # validation only
        file_id = self.generate_file_id(account_id)
        properties = {"hutch_created": "1"}
        if hutch_key:
            properties["hutch_key"] = hutch_key
        metadata = ws.drive_create_file_metadata(title, mime_type=ws.SHEET_MIME,
                                                 parent_id=parent_folder_id or "root",
                                                 app_properties=properties)
        metadata["id"] = file_id
        try:
            self._json("POST", f"{self.drive_base}/files", account_id,
                       params={"supportsAllDrives": "true", "fields": "id,name,webViewLink"},
                       json_body=metadata, purpose="Sheets creation")
        except GoogleWorkspaceOutcomeUnknown:
            existing = self._json("GET", f"{self.drive_base}/files/{file_id}", account_id,
                                  params={"fields": "id,name,trashed,webViewLink"},
                                  purpose="Sheets reconciliation")
            if existing.get("trashed"):
                raise

        current = self._json("GET", f"{self.sheets_base}/spreadsheets/{file_id}", account_id,
                             params={"fields": "spreadsheetId,sheets.properties"},
                             purpose="Sheets naming read")
        existing_titles = [str((s.get("properties") or {}).get("title", ""))
                           for s in current.get("sheets") or []]
        requests: list[dict[str, Any]] = []
        wanted = list(sheet_titles)
        default_sheet_id = None
        for s in current.get("sheets") or []:
            props = s.get("properties") or {}
            if props.get("index") == 0:
                default_sheet_id = props.get("sheetId")
        if default_sheet_id is not None and existing_titles:
            default_title = existing_titles[0]
            if wanted and default_title not in wanted:
                requests.append({"updateSheetProperties": {
                    "properties": {"sheetId": default_sheet_id, "title": wanted[0]},
                    "fields": "title"}})
                existing_titles[0] = wanted[0]
                wanted = wanted[1:]
        for t in wanted:
            if t not in existing_titles:
                requests.append({"addSheet": {"properties": {"title": t}}})
        if requests:
            self._json("POST", f"{self.sheets_base}/spreadsheets/{file_id}:batchUpdate", account_id,
                       json_body={"requests": requests}, purpose="Sheets naming")
        final = self._json("GET", f"{self.sheets_base}/spreadsheets/{file_id}", account_id,
                           params={"fields": "spreadsheetId,sheets.properties,spreadsheetUrl"},
                           purpose="Sheets read-back")
        mapping = {str((s.get("properties") or {}).get("title", "")):
                   int((s.get("properties") or {}).get("sheetId", 0))
                   for s in final.get("sheets") or []}
        verification: list[str] = []
        for t in sheet_titles:
            if t not in mapping:
                verification.append(f"sheet {t!r} is missing from the created spreadsheet")
        return {
            "spreadsheet_id": file_id,
            "web_view_link": str(final.get("spreadsheetUrl") or ""),
            "sheets": mapping,
            "verification": verification,
        }

    def resolve_sheet(self, account_id: str, spreadsheet_id: str, *, sheet_id: Optional[int] = None,
                      title: str = "") -> dict[str, Any]:
        data = self._json("GET", f"{self.sheets_base}/spreadsheets/{spreadsheet_id}", account_id,
                          params={"fields": "spreadsheetId,sheets.properties"}, purpose="Sheets metadata")
        return ws.sheets_resolve_sheet(data, title=title, sheet_id=sheet_id)

    def append_rows(self, account_id: str, spreadsheet_id: str, *, columns, rows,
                    sheet_id: Optional[int] = None, title: str = "",
                    range_start: str = "A1") -> dict[str, Any]:
        """A RAW append with verification and ambiguous-outcome reconciliation."""
        resolved = self.resolve_sheet(account_id, spreadsheet_id, sheet_id=sheet_id, title=title)
        spec = ws.sheets_append_spec(resolved=resolved, columns=columns, rows=rows,
                                     range_start=range_start)
        append_range = quote(spec["range"], safe=",!'()")
        try:
            response = self._json(
                "POST", f"{self.sheets_base}/spreadsheets/{spreadsheet_id}/values/{append_range}:append",
                account_id,
                params={"valueInputOption": spec["value_input_option"],
                        "insertDataOption": spec["insert_data_option"]},
                json_body=spec["body"], purpose="Sheets append")
        except GoogleWorkspaceOutcomeUnknown:
            reconciled = self._reconcile_append(account_id, spreadsheet_id, resolved, spec)
            if reconciled is None:
                raise
            response = reconciled
            response["reconciled"] = True
        problems = ws.sheets_verify_append(response, spec)
        result = {
            "sheet_id": resolved["sheet_id"],
            "sheet_title": resolved["title"],
            "updated_range": str((response.get("updates") or {}).get("updatedRange") or ""),
            "updated_rows": int((response.get("updates") or {}).get("updatedRows") or 0),
            "reconciled": bool(response.get("reconciled")),
            "verification": problems,
            "read_back": [],
        }
        window = ws.sheets_values_lookup_spec(resolved=resolved, first_column=1,
                                              last_column=max(len(spec["values"][0]), 1), max_rows=20)
        if window["range"]:
            values = self.read_values(account_id, spreadsheet_id, window["range"])
            result["read_back"] = [row[: len(spec["values"][0])] for row in (values.get("values") or [])[-3:]]
        return result

    def _reconcile_append(self, account_id: str, spreadsheet_id: str, resolved: dict,
                          spec: dict) -> Optional[dict[str, Any]]:
        """Look for the exact intended row in a bounded tail window of the sheet.

        Returns a synthesized append response when the row is already present, else None
        (the caller re-raises the unknown outcome).
        """
        last_column = max(len(spec["values"][0]), 1)
        window = ws.sheets_values_lookup_spec(resolved=resolved, first_column=1,
                                              last_column=last_column, max_rows=50)
        try:
            data = self.read_values(account_id, spreadsheet_id, window["range"])
        except GoogleWorkspaceError:
            return None
        wanted = [[str(c) for c in row] for row in spec["values"]]
        for offset, row in enumerate(data.get("values") or []):
            cells = [str(c) for c in (row + [""] * len(wanted[0]))[: len(wanted[0])]]
            if cells == wanted[0]:
                row_number = offset + 2  # the lookup window starts at row 2
                return {"updates": {
                    "updatedRange": f"{ws.a1_sheet_title(resolved['title'])}!A{row_number}",
                    "updatedRows": len(wanted),
                    "updatedColumns": len(wanted[0]),
                }}
        return None

    def read_values(self, account_id: str, spreadsheet_id: str, a1_range: str) -> dict[str, Any]:
        encoded = quote(a1_range, safe=",!'()")
        return self._json("GET", f"{self.sheets_base}/spreadsheets/{spreadsheet_id}/values/{encoded}",
                          account_id, params={"majorDimension": "ROWS"}, purpose="Sheets read")

    # ------------------------------------------------------------------ uploads

    def upload_file(self, account_id: str, *, name: str, parent_id: str, content: bytes,
                    mime_type: str, app_properties: Optional[dict[str, str]] = None) -> dict[str, Any]:
        """Upload small media to an explicit folder, with id-based reconciliation."""
        metadata = ws.drive_create_file_metadata(name, mime_type=mime_type, parent_id=parent_id,
                                                 app_properties=app_properties)
        file_id = self.generate_file_id(account_id)
        metadata["id"] = file_id
        body, content_type = ws.drive_multipart_body(metadata, content, mime_type=mime_type)
        try:
            created = self._json("POST", self.upload_base + "/files", account_id,
                                 params={"uploadType": "multipart", "supportsAllDrives": "true",
                                         "fields": "id,name,size,md5Checksum,parents,trashed,webViewLink"},
                                 content=body, headers={"Content-Type": content_type},
                                 purpose="Drive upload")
        except GoogleWorkspaceOutcomeUnknown:
            created = self.file_metadata(account_id, file_id)
            created["reconciled"] = True
        problems = ws.drive_verify_file(created, expected_id=file_id, expected_name=name,
                                        expected_parents=[parent_id])
        if created.get("size") is not None and int(created["size"]) != len(content):
            problems.append(f"remote size {created['size']} does not match uploaded {len(content)} bytes")
        if not ws.drive_is_native(created) and created.get("md5Checksum"):
            import hashlib as _hashlib

            if created["md5Checksum"] != _hashlib.md5(content).hexdigest():
                problems.append("remote md5 does not match the uploaded bytes")
        return {
            "file_id": file_id,
            "web_view_link": str(created.get("webViewLink") or ""),
            "reconciled": bool(created.get("reconciled")),
            "verification": problems,
        }
