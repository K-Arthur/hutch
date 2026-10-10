"""Local Google Calendar OAuth client with separately requested event creation.

This module uses Google's installed-app authorization-code flow with PKCE. Only
refresh credentials are retained, through the Linux Secret Service CLI; token
responses and calendar data are never written to Hutch's SQLite database or
transcripts. API destinations are fixed Google hosts and redirects are disabled.
"""

from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import quote, urlencode, urlsplit

import httpx

from .google_oauth_config import valid_google_oauth_client_id

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
CALENDAR_API = "https://www.googleapis.com/calendar/v3"
CALENDAR_LIST_SCOPE = "https://www.googleapis.com/auth/calendar.calendarlist.readonly"
CALENDAR_EVENTS_SCOPE = "https://www.googleapis.com/auth/calendar.events.readonly"
CALENDAR_EVENT_CREATE_SCOPE = "https://www.googleapis.com/auth/calendar.events.owned"
SCOPES = (CALENDAR_LIST_SCOPE, CALENDAR_EVENTS_SCOPE)
CALLBACK_PATH = "/api/v1/connections/google-calendar/callback"
STATE_TTL_SECONDS = 600
ACCOUNT_RE = re.compile(r"^gcal_[0-9a-f]{24}$")
_ACCESS_LOCK = threading.Lock()
_ACCESS_CACHE: dict[tuple[str, str], tuple[float, str]] = {}
_SECRET_PROBE_LOCK = threading.Lock()
_SECRET_PROBE_RESULT: tuple[float, bool] | None = None


class GoogleCalendarError(ValueError):
    """A safe, actionable OAuth or Calendar API failure."""


class GoogleCalendarOutcomeUnknown(GoogleCalendarError):
    """A write request may have reached Google but no verifiable receipt returned."""


class SecretStore(Protocol):
    def available(self) -> bool: ...
    def put(self, account_id: str, value: str) -> None: ...
    def get(self, account_id: str) -> str | None: ...
    def delete(self, account_id: str) -> None: ...


class SecretToolStore:
    """Use Linux Secret Service through secret-tool without putting values in argv."""

    service = "hutch.google-calendar"
    feature_name = "Google Calendar"
    account_pattern = ACCOUNT_RE
    probe_account = "gcal_000000000000000000000000"

    def __init__(self, *, run=None):
        self._run = run

    def available(self) -> bool:
        global _SECRET_PROBE_RESULT
        if shutil.which("secret-tool") is None:
            return False
        now = time.monotonic()
        with _SECRET_PROBE_LOCK:
            if _SECRET_PROBE_RESULT and now - _SECRET_PROBE_RESULT[0] < 5:
                return _SECRET_PROBE_RESULT[1]
            runner = self._run or subprocess.run
            try:
                result = runner(["secret-tool", "lookup", "service", self.service, "account",
                                 self.probe_account], text=True, capture_output=True,
                                timeout=3, check=False, env=self._environment())
                # `secret-tool lookup` returns 1 with no output when the service
                # is healthy but no matching item exists; DBus/keyring failures
                # include an error on stderr.
                ready = result.returncode == 0 or (result.returncode == 1 and not result.stderr)
            except (OSError, subprocess.TimeoutExpired):
                ready = False
            _SECRET_PROBE_RESULT = (now, ready)
            return ready

    @staticmethod
    def _environment() -> dict[str, str]:
        return {key: os.environ[key] for key in (
            "PATH", "LANG", "DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR", "DISPLAY", "WAYLAND_DISPLAY"
        ) if key in os.environ}

    @classmethod
    def _account(cls, account_id: str) -> str:
        if not cls.account_pattern.fullmatch(account_id):
            raise GoogleCalendarError(f"{cls.feature_name} account reference is invalid")
        return account_id

    def _call(self, args: list[str], *, input_text: str | None = None):
        if not self.available():
            raise GoogleCalendarError("Linux Secret Service is unavailable; install and unlock secret-tool before connecting an account")
        try:
            runner = self._run or subprocess.run
            result = runner(["secret-tool", *args], input=input_text, text=True, capture_output=True,
                            timeout=10, check=False, env=self._environment())
        except (OSError, subprocess.TimeoutExpired):
            raise GoogleCalendarError("Linux Secret Service did not respond; unlock the desktop keyring and try again") from None
        if result.returncode:
            raise GoogleCalendarError("Linux Secret Service rejected the credential operation; unlock the desktop keyring and retry")
        return result.stdout

    def put(self, account_id: str, value: str) -> None:
        self._call(["store", f"--label=Hutch {self.feature_name} refresh token", "service", self.service,
                    "account", self._account(account_id)], input_text=value + "\n")

    def get(self, account_id: str) -> str | None:
        value = self._call(["lookup", "service", self.service, "account", self._account(account_id)])
        result = value.rstrip("\r\n")
        return result or None

    def delete(self, account_id: str) -> None:
        self._call(["clear", "service", self.service, "account", self._account(account_id)])


@dataclass(frozen=True)
class OAuthStart:
    url: str
    state: str


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _atomic_private_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd, temporary = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        dirfd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


class GoogleCalendarBook:
    """OAuth accounts and Calendar API operations for one local Hutch state directory."""

    feature_name = "Google Calendar"
    client_id_env = "HUTCH_GOOGLE_OAUTH_CLIENT_ID"
    storage_name = "google-calendar"
    account_prefix = "gcal_"
    account_pattern = ACCOUNT_RE
    callback_path = CALLBACK_PATH
    oauth_scopes = SCOPES
    required_scopes = SCOPES
    api_host = "www.googleapis.com"
    api_base = CALENDAR_API
    secret_store_type = SecretToolStore

    def __init__(self, state_dir: Path, client_id: str, *, secrets_store: SecretStore | None = None,
                 transport: httpx.BaseTransport | None = None,
                 clock=time.time):
        self.root = Path(state_dir) / self.storage_name
        self.pending_dir = self.root / "pending"
        self.accounts_path = self.root / "accounts.json"
        self.lock_path = self.root / ".lock"
        self.client_id = str(client_id or "").strip()
        self.secrets = secrets_store or self.secret_store_type()
        self.transport = transport
        self.clock = clock

    @contextmanager
    def _lock_context(self):
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        os.fchmod(fd, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    @classmethod
    def _validate_callback(cls, uri: str) -> None:
        try:
            parts = urlsplit(uri)
            valid = (parts.scheme == "http" and parts.hostname == "127.0.0.1" and
                     parts.port is not None and 1 <= parts.port <= 65535 and parts.path == cls.callback_path and
                     not parts.query and not parts.fragment and parts.username is None and parts.password is None)
        except ValueError:
            valid = False
        if not valid:
            raise GoogleCalendarError(f"{cls.feature_name} sign-in must use Hutch's exact local 127.0.0.1 callback")

    @classmethod
    def callback_uri(cls, request: Any) -> str:
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
            raise GoogleCalendarError(f"{cls.feature_name} sign-in must start and finish from Hutch on this computer at 127.0.0.1")
        return f"http://127.0.0.1:{port}{cls.callback_path}"

    def _require_client_id(self) -> None:
        if not valid_google_oauth_client_id(self.client_id):
            raise GoogleCalendarError(f"{self.feature_name} is not configured with a valid Google Desktop OAuth client ID; check Connections")

    def start(self, label: str, redirect_uri: str, *, allow_event_creation: bool = False) -> OAuthStart:
        self._require_client_id()
        self._validate_callback(redirect_uri)
        clean_label = " ".join(str(label or "").split())
        if not 1 <= len(clean_label) <= 80:
            raise GoogleCalendarError(f"Choose a {self.feature_name} account label from 1 to 80 characters")
        if not self.secrets.available():
            raise GoogleCalendarError(f"Install and unlock Linux Secret Service (secret-tool) before connecting {self.feature_name}")
        self.pending_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.pending_dir, 0o700)
        now = self.clock()
        pending_files = list(self.pending_dir.glob("*.json"))
        for pending_path in pending_files:
            try:
                pending_value = json.loads(pending_path.read_text(encoding="utf-8"))
                if float(pending_value.get("expires_at", 0)) < now:
                    pending_path.unlink(missing_ok=True)
            except (OSError, ValueError, TypeError):
                pending_path.unlink(missing_ok=True)
        if sum(1 for path in self.pending_dir.glob("*.json")) >= 10:
            raise GoogleCalendarError(f"Too many {self.feature_name} sign-in requests are pending; wait for one to expire and retry")
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(48)
        challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
        now = self.clock()
        requested_scopes = list(self.oauth_scopes)
        if allow_event_creation is True:
            requested_scopes.append(CALENDAR_EVENT_CREATE_SCOPE)
        pending = {"created_at": now, "expires_at": now + STATE_TTL_SECONDS,
                   "redirect_uri": redirect_uri, "label": clean_label, "verifier": verifier,
                   "requested_scopes": requested_scopes}
        _atomic_private_json(self.pending_dir / f"{state}.json", pending)
        url = AUTH_URL + "?" + urlencode({
            "client_id": self.client_id, "redirect_uri": redirect_uri, "response_type": "code",
            "scope": " ".join(requested_scopes), "access_type": "offline", "prompt": "consent select_account",
            "code_challenge": challenge, "code_challenge_method": "S256", "state": state,
        })
        return OAuthStart(url, state)

    def _read_accounts(self) -> dict[str, Any]:
        try:
            os.chmod(self.accounts_path, 0o600)
            value = json.loads(self.accounts_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"version": 1, "accounts": {}}
        except (OSError, json.JSONDecodeError):
            raise GoogleCalendarError(f"{self.feature_name} account records are unreadable; preserve the file and inspect it locally") from None
        if not isinstance(value, dict) or value.get("version") != 1 or not isinstance(value.get("accounts"), dict):
            raise GoogleCalendarError(f"{self.feature_name} account records have an unsupported format")
        return value

    def _write_accounts(self, value: dict[str, Any]) -> None:
        _atomic_private_json(self.accounts_path, value)

    def _read_pending(self, state: str) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", state):
            raise GoogleCalendarError(f"This {self.feature_name} sign-in request is invalid; start again")
        path = self.pending_dir / f"{state}.json"
        with self._lock_context():
            try:
                os.chmod(path, 0o600)
                pending = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raise GoogleCalendarError(f"This {self.feature_name} sign-in request is missing or already used; start again") from None
            try:
                path.unlink()
            except OSError:
                raise GoogleCalendarError(f"This {self.feature_name} sign-in request could not be consumed; start again") from None
        if float(pending.get("expires_at", 0)) < self.clock():
            raise GoogleCalendarError(f"This {self.feature_name} sign-in request expired; start again")
        return pending

    def cancel(self, state: str) -> None:
        """Consume an OAuth callback that Google denied; no token exchange occurs."""
        self._read_pending(state)

    def _http(self) -> httpx.Client:
        options: dict[str, Any] = {"timeout": httpx.Timeout(15), "trust_env": False, "follow_redirects": False}
        if self.transport is not None:
            options["transport"] = self.transport
        return httpx.Client(**options)

    @staticmethod
    def _json(response: httpx.Response, purpose: str) -> dict[str, Any]:
        if 300 <= response.status_code < 400:
            raise GoogleCalendarError(f"Google redirected the {purpose}; Hutch stopped without forwarding credentials")
        if response.status_code >= 400:
            if response.status_code in (401, 403):
                raise GoogleCalendarError(f"Google rejected the {purpose}; reconnect the calendar and check its permissions")
            if response.status_code == 429:
                raise GoogleCalendarError(f"Google rate-limited the {purpose}; wait and try again")
            raise GoogleCalendarError(f"Google {purpose} failed (HTTP {response.status_code})")
        try:
            value = response.json()
        except ValueError:
            raise GoogleCalendarError(f"Google returned an unreadable {purpose} response") from None
        if not isinstance(value, dict):
            raise GoogleCalendarError(f"Google returned an invalid {purpose} response")
        return value

    def finish(self, state: str, code: str, redirect_uri: str) -> dict[str, str]:
        self._validate_callback(redirect_uri)
        if not isinstance(code, str) or not 1 <= len(code) <= 2048 or any(ord(c) < 32 for c in code):
            raise GoogleCalendarError("Google did not return a valid authorization code; start sign-in again")
        pending = self._read_pending(state)
        if not secrets.compare_digest(str(pending.get("redirect_uri", "")), redirect_uri):
            raise GoogleCalendarError(f"This {self.feature_name} callback does not match the sign-in request; start again")
        with self._http() as client:
            try:
                response = client.post(TOKEN_URL, data={"client_id": self.client_id, "code": code,
                    "code_verifier": pending["verifier"], "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code"})
            except httpx.HTTPError:
                raise GoogleCalendarError("Could not contact Google's token service; start a fresh sign-in") from None
        payload = self._json(response, "authorization code exchange")
        refresh = payload.get("refresh_token")
        access = payload.get("access_token")
        token_type = str(payload.get("token_type", "")).lower()
        expires = payload.get("expires_in")
        scope_set = set(str(payload.get("scope", "")).split())
        requested_scopes = pending.get("requested_scopes", list(self.oauth_scopes))
        if not isinstance(requested_scopes, list) or not all(isinstance(scope, str) for scope in requested_scopes):
            raise GoogleCalendarError(f"This {self.feature_name} sign-in request is invalid; start again")
        if (not isinstance(refresh, str) or not 1 <= len(refresh) <= 512 or
                not isinstance(access, str) or not 1 <= len(access) <= 2048 or
                any(ord(c) < 33 or ord(c) > 126 for c in access) or token_type != "bearer" or
                not isinstance(expires, (int, float)) or isinstance(expires, bool) or not 0 < expires <= 86400 or
                not set(requested_scopes).issubset(scope_set)):
            raise GoogleCalendarError(f"Google did not grant the requested {self.feature_name} scopes with offline access; disconnect and reconnect")
        account_id = self.account_prefix + secrets.token_hex(12)
        created = datetime.fromtimestamp(self.clock(), timezone.utc).isoformat()
        account = {"id": account_id, "label": pending["label"], "created_at": created,
                   "scopes": sorted(scope_set),
                   "event_creation_opted_in": CALENDAR_EVENT_CREATE_SCOPE in requested_scopes,
                   "status": "connected"}
        try:
            self.secrets.put(account_id, refresh)
            with self._lock_context():
                data = self._read_accounts()
                data["accounts"][account_id] = account
                self._write_accounts(data)
        except Exception:
            try:
                self.secrets.delete(account_id)
            except Exception:
                pass
            raise
        return account

    def accounts(self) -> list[dict[str, Any]]:
        with self._lock_context():
            accounts = self._read_accounts()["accounts"]
            return [dict(row) for _, row in sorted(accounts.items(), key=lambda pair: pair[1].get("created_at", ""))]

    @staticmethod
    def account_can_create_events(account: dict[str, Any]) -> bool:
        scopes = account.get("scopes", [])
        return (account.get("event_creation_opted_in") is True and isinstance(scopes, list) and
                CALENDAR_EVENT_CREATE_SCOPE in scopes)

    def can_create_events(self, account_id: str) -> bool:
        return self.account_can_create_events(self._account(account_id))

    def _account(self, account_id: str) -> dict[str, Any]:
        if not self.account_pattern.fullmatch(account_id):
            raise GoogleCalendarError(f"{self.feature_name} account reference is invalid")
        with self._lock_context():
            account = self._read_accounts()["accounts"].get(account_id)
        if not account:
            raise GoogleCalendarError(f"{self.feature_name} account is not connected; reconnect it from Connections")
        return account

    def access_token(self, account_id: str) -> str:
        self._require_client_id()
        account = self._account(account_id)
        cache_key = (str(self.root.resolve()), account_id)
        with _ACCESS_LOCK:
            cached = _ACCESS_CACHE.get(cache_key)
            if cached and cached[0] > self.clock() + 60:
                return cached[1]
            refresh = self.secrets.get(account_id)
            if not refresh:
                raise GoogleCalendarError(f"{self.feature_name} refresh credential is missing; disconnect and reconnect this account")
            with self._http() as client:
                try:
                    response = client.post(TOKEN_URL, data={"client_id": self.client_id,
                        "refresh_token": refresh, "grant_type": "refresh_token"})
                except httpx.HTTPError:
                    raise GoogleCalendarError(f"Could not refresh {self.feature_name} access; check the network and retry") from None
            payload = self._json(response, "access-token refresh")
            token = payload.get("access_token")
            expires = payload.get("expires_in")
            if (not isinstance(token, str) or not 1 <= len(token) <= 2048 or
                    any(ord(c) < 33 or ord(c) > 126 for c in token) or
                    str(payload.get("token_type", "")).lower() != "bearer" or
                    not isinstance(expires, (int, float)) or isinstance(expires, bool) or not 0 < expires <= 86400):
                raise GoogleCalendarError(f"Google returned an invalid {self.feature_name} access-token response; reconnect this account")
            rotated = payload.get("refresh_token")
            if isinstance(rotated, str) and rotated:
                self.secrets.put(account_id, rotated)
            _ACCESS_CACHE[cache_key] = (self.clock() + float(expires), token)
            return token

    def _api_request(self, method: str, url: str, account_id: str, *, params: dict[str, Any] | None = None,
                     json_body: dict[str, Any] | None = None, purpose="Calendar data") -> dict[str, Any]:
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname != self.api_host or parts.username or parts.password:
            raise GoogleCalendarError(f"Refusing a {self.feature_name} API destination outside Google's verified API host")
        def request(token: str) -> httpx.Response:
            with self._http() as client:
                try:
                    return client.request(method, url, params=params, json=json_body,
                                          headers={"Authorization": f"Bearer {token}",
                                                   "Accept": "application/json"})
                except httpx.HTTPError:
                    if method != "GET":
                        raise GoogleCalendarOutcomeUnknown(
                            f"Google may have received the {purpose}; verify the calendar before trying again") from None
                    raise GoogleCalendarError(f"Could not contact Google for {purpose}; check the network and retry") from None

        token = self.access_token(account_id)
        response = request(token)
        if response.status_code == 401 and method == "GET":
            # Google can reject a locally cached token before its advertised
            # expiry. Invalidate only that exact token: a concurrent request
            # may already have refreshed and installed a newer one.
            cache_key = (str(self.root.resolve()), account_id)
            with _ACCESS_LOCK:
                cached = _ACCESS_CACHE.get(cache_key)
                if cached is not None and secrets.compare_digest(cached[1], token):
                    _ACCESS_CACHE.pop(cache_key, None)
            response = request(self.access_token(account_id))
        if response.request.url.host != self.api_host:
            if method != "GET":
                raise GoogleCalendarOutcomeUnknown(f"Google's response destination changed during {purpose}; verify the calendar before retrying")
            raise GoogleCalendarError(f"Google {self.feature_name} request changed destination; no credentials were forwarded")
        if method != "GET" and (300 <= response.status_code < 400 or response.status_code >= 500):
            raise GoogleCalendarOutcomeUnknown(
                f"Google returned HTTP {response.status_code} during {purpose}; verify the calendar before trying again")
        try:
            return self._json(response, purpose)
        except GoogleCalendarError as exc:
            if method != "GET" and 200 <= response.status_code < 300:
                raise GoogleCalendarOutcomeUnknown(
                    f"Google may have completed {purpose} but returned no verifiable result; verify the calendar before retrying") from None
            raise

    def _get(self, url: str, account_id: str, params: dict[str, Any] | None = None, purpose="Calendar data") -> dict[str, Any]:
        return self._api_request("GET", url, account_id, params=params, purpose=purpose)

    def list_calendars(self, account_id: str) -> list[dict[str, Any]]:
        self._account(account_id)
        url = f"{self.api_base}/users/me/calendarList"
        params: dict[str, str] = {"maxResults": "100", "showDeleted": "false", "showHidden": "false",
                                  "fields": "items(id,summary,primary,accessRole),nextPageToken"}
        result: list[dict[str, Any]] = []
        for _ in range(5):
            payload = self._get(url, account_id, params, "calendar list")
            items = payload.get("items", [])
            if not isinstance(items, list):
                raise GoogleCalendarError("Google returned an invalid calendar list")
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                    continue
                result.append({"id": item["id"], "name": str(item.get("summary", "Calendar"))[:200],
                               "primary": bool(item.get("primary", False)),
                               "access_role": str(item.get("accessRole", "reader"))[:32]})
                if len(result) >= 500:
                    return result
            next_token = payload.get("nextPageToken")
            if not isinstance(next_token, str) or not next_token or len(next_token) > 2048:
                break
            params = {"maxResults": "100", "showDeleted": "false", "showHidden": "false",
                      "fields": "items(id,summary,primary,accessRole),nextPageToken", "pageToken": next_token}
        return result

    @staticmethod
    def _time(value: str, label: str) -> datetime:
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (AttributeError, TypeError, ValueError):
            raise GoogleCalendarError(f"Calendar {label} must be an ISO 8601 date-time with a time zone") from None
        if result.tzinfo is None or result.utcoffset() is None:
            raise GoogleCalendarError(f"Calendar {label} must include a time zone")
        return result.astimezone(timezone.utc)

    def list_events(self, account_id: str, calendar_id: str, time_min: str, time_max: str,
                    *, query: str = "", limit: int = 25) -> list[dict[str, str]]:
        self._account(account_id)
        if not isinstance(calendar_id, str) or not 1 <= len(calendar_id) <= 256 or any(ord(c) < 32 for c in calendar_id):
            raise GoogleCalendarError("Choose a valid calendar from the connected account")
        start, end = self._time(time_min, "start"), self._time(time_max, "end")
        if start >= end or (end - start).total_seconds() > 366 * 24 * 3600:
            raise GoogleCalendarError("Calendar time range must be positive and no longer than 366 days")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise GoogleCalendarError("Calendar result limit must be between 1 and 100")
        if not isinstance(query, str) or len(query) > 200 or any(ord(c) < 32 for c in query):
            raise GoogleCalendarError("Calendar search query must be at most 200 plain-text characters")
        url = f"{self.api_base}/calendars/{quote(calendar_id, safe='')}/events"
        payload = self._get(url, account_id, {"timeMin": start.isoformat().replace("+00:00", "Z"),
            "timeMax": end.isoformat().replace("+00:00", "Z"), "singleEvents": "true", "orderBy": "startTime",
            "maxResults": str(limit), "fields": "items(summary,start,end,location),nextPageToken",
            **({"q": query.strip()} if query.strip() else {})}, "calendar events")
        items = payload.get("items", [])
        if not isinstance(items, list):
            raise GoogleCalendarError("Google returned an invalid Calendar event list")
        events: list[dict[str, str]] = []
        for item in items[:limit]:
            if not isinstance(item, dict):
                continue
            begin = item.get("start") if isinstance(item.get("start"), dict) else {}
            finish = item.get("end") if isinstance(item.get("end"), dict) else {}
            events.append({"summary": str(item.get("summary") or "(untitled event)")[:500],
                           "start": str(begin.get("dateTime") or begin.get("date") or "")[:64],
                           "end": str(finish.get("dateTime") or finish.get("date") or "")[:64],
                           "location": str(item.get("location") or "")[:500]})
        return events

    @staticmethod
    def _event_text(value: Any, label: str, maximum: int, *, required: bool = False) -> str:
        if not isinstance(value, str):
            raise GoogleCalendarError(f"Calendar event {label} must be text")
        result = value.strip()
        if (required and not result) or len(result) > maximum or any(
                ord(character) < 32 and character not in "\n\t" for character in result):
            raise GoogleCalendarError(f"Calendar event {label} must be {('1' if required else '0')} to {maximum} plain-text characters")
        return result

    @classmethod
    def prepare_event(cls, *, summary: str, start: str, end: str, description: str = "",
                      location: str = "") -> dict[str, str]:
        """Validate and normalize the exact guest-free event shown for approval."""
        clean_summary = cls._event_text(summary, "title", 180, required=True)
        clean_description = cls._event_text(description, "description", 2000)
        clean_location = cls._event_text(location, "location", 300)
        start_dt, end_dt = cls._time(start, "start"), cls._time(end, "end")
        if start_dt >= end_dt:
            raise GoogleCalendarError("Calendar event end after start is required")
        if (end_dt - start_dt).total_seconds() > 366 * 24 * 3600:
            raise GoogleCalendarError("Calendar events cannot be longer than 366 days")
        try:
            start_value = datetime.fromisoformat(start.replace("Z", "+00:00")).isoformat()
            end_value = datetime.fromisoformat(end.replace("Z", "+00:00")).isoformat()
        except (AttributeError, TypeError, ValueError):
            raise GoogleCalendarError("Calendar event times must be ISO 8601 date-times with a time zone") from None
        return {"summary": clean_summary, "start": start_value, "end": end_value,
                "description": clean_description, "location": clean_location}

    def create_event(self, account_id: str, calendar_id: str, *, summary: str, start: str, end: str,
                     description: str = "", location: str = "",
                     before_write: Callable[[], str | None] | None = None) -> dict[str, str]:
        """Create a guest-free event on one account-owned calendar using an opted-in write scope.

        The caller must obtain one-time human approval and persist the effect intent before
        calling this method. Unknown HTTP outcomes are raised separately and must not be retried.
        """
        account = self._account(account_id)
        if not isinstance(calendar_id, str) or not 1 <= len(calendar_id) <= 256 or any(ord(c) < 32 for c in calendar_id):
            raise GoogleCalendarError("Choose a valid calendar from the connected account")
        prepared = self.prepare_event(summary=summary, start=start, end=end, description=description,
                                     location=location)
        clean_summary, clean_description, clean_location = (prepared["summary"], prepared["description"],
                                                             prepared["location"])
        start_value, end_value = prepared["start"], prepared["end"]
        start_dt, end_dt = self._time(start_value, "start"), self._time(end_value, "end")
        if not self.account_can_create_events(account):
            raise GoogleCalendarError("This Google account does not have event-creation permission; reconnect with that explicit option")

        calendars = self.list_calendars(account_id)
        selected = next((item for item in calendars if item["id"] == calendar_id), None)
        if selected is None:
            raise GoogleCalendarError("The selected calendar is no longer available; review this Bot's Connections grant")
        if selected.get("access_role") != "owner":
            raise GoogleCalendarError("Google's event-creation scope only covers calendars you own; this Bot can keep read-only access here")

        event = {"summary": clean_summary,
                 "start": {"dateTime": start_value},
                 "end": {"dateTime": end_value}}
        if clean_description:
            event["description"] = clean_description
        if clean_location:
            event["location"] = clean_location
        if before_write is not None:
            refusal = before_write()
            if refusal:
                raise GoogleCalendarError(f"{refusal}; the event was not sent")
        url = f"{self.api_base}/calendars/{quote(calendar_id, safe='')}/events"
        try:
            payload = self._api_request("POST", url, account_id, json_body=event, purpose="event creation")
        except GoogleCalendarOutcomeUnknown:
            raise
        except GoogleCalendarError:
            raise
        event_id = payload.get("id")
        if not isinstance(event_id, str) or not 1 <= len(event_id) <= 256:
            raise GoogleCalendarOutcomeUnknown(
                "Google may have created the event but returned no verifiable ID; check the calendar before retrying")
        verify_url = f"{self.api_base}/calendars/{quote(calendar_id, safe='')}/events/{quote(event_id, safe='')}"
        try:
            verified = self._api_request("GET", verify_url, account_id,
                                         params={"fields": "id,status,summary,start(dateTime),end(dateTime),description,location"},
                                         purpose="created event verification")
            verified_start = verified.get("start") if isinstance(verified.get("start"), dict) else {}
            verified_end = verified.get("end") if isinstance(verified.get("end"), dict) else {}
            actual_start = self._time(verified_start.get("dateTime"), "verified start")
            actual_end = self._time(verified_end.get("dateTime"), "verified end")
            actual_description = verified.get("description", "")
            actual_location = verified.get("location", "")
            if (verified.get("id") != event_id or verified.get("status") != "confirmed" or
                    verified.get("summary") != clean_summary or actual_start != start_dt or actual_end != end_dt or
                    actual_description != clean_description or actual_location != clean_location):
                raise GoogleCalendarOutcomeUnknown(
                    "Google accepted the event request but the created event details could not be verified exactly; check the calendar before retrying")
        except GoogleCalendarOutcomeUnknown:
            raise
        except GoogleCalendarError:
            raise GoogleCalendarOutcomeUnknown(
                "Google may have created the event, but Hutch could not verify it; check the calendar before retrying") from None
        return {"id": event_id, "summary": clean_summary, "start": start_value, "end": end_value}

    def disconnect(self, account_id: str) -> dict[str, Any]:
        if not self.account_pattern.fullmatch(account_id):
            raise GoogleCalendarError(f"{self.feature_name} account reference is invalid")
        try:
            self._account(account_id)
        except GoogleCalendarError as exc:
            if "not connected" in str(exc):
                return {"removed": False, "provider_revocation": "not_needed"}
            raise
        refresh = None
        try:
            refresh = self.secrets.get(account_id)
        except GoogleCalendarError:
            pass
        revoked = False
        if refresh:
            with self._http() as client:
                try:
                    response = client.post(REVOKE_URL, data={"token": refresh})
                    revoked = response.status_code in (200, 204)
                except httpx.HTTPError:
                    revoked = False
        self.secrets.delete(account_id)
        with self._lock_context():
            data = self._read_accounts()
            data["accounts"].pop(account_id, None)
            self._write_accounts(data)
        with _ACCESS_LOCK:
            _ACCESS_CACHE.pop((str(self.root.resolve()), account_id), None)
        return {"removed": True, "provider_revocation": "confirmed" if revoked else "not_confirmed"}
