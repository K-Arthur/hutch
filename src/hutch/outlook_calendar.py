"""Local, read-only Microsoft Outlook Calendar client.

The owner connects through Microsoft identity platform's delegated authorization
code flow with S256 PKCE. Hutch stores refresh credentials in Linux Secret
Service, never SQLite or browser storage. Graph requests are fixed to the
Microsoft Graph v1.0 host, redirects are disabled, and only basic event fields
are requested.
"""

from __future__ import annotations

import base64
from .platforms import locking as fcntl
import hashlib
import ipaddress
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
from typing import Any, Protocol
from urllib.parse import quote, urlencode, urlsplit

import httpx

AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
GRAPH_API = "https://graph.microsoft.com/v1.0"
CALENDAR_SCOPE = "Calendars.ReadBasic"
SCOPES = (CALENDAR_SCOPE, "offline_access")
CALLBACK_PATH = "/api/v1/connections/outlook-calendar/callback"
STATE_TTL_SECONDS = 600
ACCOUNT_RE = re.compile(r"^mscal_[0-9a-f]{24}$")
STATE_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
_ACCESS_LOCK = threading.Lock()
_ACCESS_CACHE: dict[tuple[str, str], tuple[float, str]] = {}
_SECRET_PROBE_LOCK = threading.Lock()
_SECRET_PROBE_RESULT: tuple[float, bool] | None = None


class OutlookCalendarError(ValueError):
    """A safe, actionable OAuth or Microsoft Graph failure."""


class SecretStore(Protocol):
    def available(self) -> bool: ...
    def put(self, account_id: str, value: str) -> None: ...
    def get(self, account_id: str) -> str | None: ...
    def delete(self, account_id: str) -> None: ...


class SecretToolStore:
    """Use Linux Secret Service through secret-tool without putting values in argv."""

    service = "hutch.outlook-calendar"
    feature = "Outlook Calendar"
    account_pattern = ACCOUNT_RE
    probe_account = "mscal_000000000000000000000000"

    def __init__(self, *, run=None):
        self._run = run

    @staticmethod
    def _environment() -> dict[str, str]:
        return {key: os.environ[key] for key in (
            "PATH", "LANG", "DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR", "DISPLAY", "WAYLAND_DISPLAY"
        ) if key in os.environ}

    @classmethod
    def _account(cls, account_id: str) -> str:
        if not cls.account_pattern.fullmatch(account_id):
            raise OutlookCalendarError(f"{cls.feature} account reference is invalid")
        return account_id

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
                ready = result.returncode == 0 or (result.returncode == 1 and not result.stderr)
            except (OSError, subprocess.TimeoutExpired):
                ready = False
            _SECRET_PROBE_RESULT = (now, ready)
            return ready

    def _call(self, args: list[str], *, input_text: str | None = None):
        if not self.available():
            raise OutlookCalendarError(
                f"Linux Secret Service is unavailable; install and unlock secret-tool before connecting {self.feature}")
        try:
            runner = self._run or subprocess.run
            result = runner(["secret-tool", *args], input=input_text, text=True, capture_output=True,
                            timeout=10, check=False, env=self._environment())
        except (OSError, subprocess.TimeoutExpired):
            raise OutlookCalendarError(
                "Linux Secret Service did not respond; unlock the desktop keyring and try again") from None
        if result.returncode:
            raise OutlookCalendarError(
                "Linux Secret Service rejected the credential operation; unlock the desktop keyring and retry")
        return result.stdout

    def put(self, account_id: str, value: str) -> None:
        self._call(["store", f"--label=Hutch {self.feature} refresh token", "service", self.service,
                    "account", self._account(account_id)], input_text=value + "\n")

    def get(self, account_id: str) -> str | None:
        value = self._call(["lookup", "service", self.service, "account", self._account(account_id)])
        return value.rstrip("\r\n") or None

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


class OutlookCalendarBook:
    """OAuth accounts and Graph calendar operations for one local Hutch state directory."""

    feature = "Outlook Calendar"
    storage_name = "outlook-calendar"
    account_prefix = "mscal_"
    account_pattern = ACCOUNT_RE
    callback_path = CALLBACK_PATH
    oauth_scopes = SCOPES
    required_scopes = (CALENDAR_SCOPE,)
    secret_store_type = SecretToolStore
    error_type = OutlookCalendarError

    def __init__(self, state_dir: Path, client_id: str, *, secrets_store: SecretStore | None = None,
                 transport: httpx.BaseTransport | None = None, clock=time.time):
        self.root = Path(state_dir) / self.storage_name
        self.pending_dir = self.root / "pending"
        self.accounts_path = self.root / "accounts.json"
        self.lock_path = self.root / ".lock"
        from .oauth_apps import outlook_oauth_client_id
        self.client_id = str(client_id or outlook_oauth_client_id()).strip()
        if len(self.client_id) > 512 or any(ord(c) < 32 for c in self.client_id):
            raise self.error_type(f"Set HUTCH_OUTLOOK_OAUTH_CLIENT_ID to a Microsoft public-client application ID for {self.feature}")
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
            valid = (parts.scheme == "http" and parts.hostname == "localhost" and
                     parts.port is not None and 1 <= parts.port <= 65535 and parts.path == cls.callback_path and
                     not parts.query and not parts.fragment and parts.username is None and parts.password is None)
        except ValueError:
            valid = False
        if not valid:
            raise cls.error_type(f"{cls.feature} sign-in must use Hutch's localhost callback")

    @classmethod
    def callback_uri(cls, request: Any) -> str:
        """Return the registered localhost loopback URI only for a local HTTP request."""
        try:
            host_parts = urlsplit("//" + request.headers.get("host", ""))
            port = int(request.scope["server"][1])
            peer = request.client.host if request.client else ""
            try:
                local_peer = ipaddress.ip_address(peer).is_loopback
            except ValueError:
                local_peer = peer == "testclient"
            valid = (request.url.scheme == "http" and host_parts.hostname in {"localhost", "127.0.0.1"} and
                     host_parts.username is None and host_parts.password is None and
                     (host_parts.port is None or host_parts.port == port) and 1 <= port <= 65535 and local_peer)
        except (KeyError, TypeError, ValueError, IndexError):
            valid = False
        if not valid:
            raise cls.error_type(
                f"{cls.feature} sign-in must start and finish from Hutch on this computer over loopback HTTP")
        return f"http://localhost:{port}{cls.callback_path}"

    def _require_client_id(self) -> None:
        if not self.client_id:
            raise self.error_type(
                "Microsoft sign-in is not enabled in this Hutch build")

    def start(self, label: str, redirect_uri: str) -> OAuthStart:
        self._require_client_id()
        self._validate_callback(redirect_uri)
        clean_label = " ".join(str(label or "").split())
        if not 1 <= len(clean_label) <= 80 or any(ord(c) < 32 or ord(c) == 127 for c in clean_label):
            raise self.error_type(f"Choose an {self.feature} label from 1 to 80 plain-text characters")
        if not self.secrets.available():
            raise self.error_type(
                f"Install and unlock Linux Secret Service (secret-tool) before connecting {self.feature}")
        self.pending_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.pending_dir, 0o700)
        now = self.clock()
        for path in list(self.pending_dir.glob("*.json")):
            try:
                pending = json.loads(path.read_text(encoding="utf-8"))
                if float(pending.get("expires_at", 0)) < now:
                    path.unlink(missing_ok=True)
            except (OSError, ValueError, TypeError):
                path.unlink(missing_ok=True)
        if sum(1 for _ in self.pending_dir.glob("*.json")) >= 10:
            raise self.error_type(f"Too many {self.feature} sign-in requests are pending; wait for one to expire and retry")
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(48)
        challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
        _atomic_private_json(self.pending_dir / f"{state}.json", {
            "created_at": now, "expires_at": now + STATE_TTL_SECONDS,
            "redirect_uri": redirect_uri, "label": clean_label, "verifier": verifier,
        })
        url = AUTH_URL + "?" + urlencode({
            "client_id": self.client_id, "redirect_uri": redirect_uri, "response_type": "code",
            "response_mode": "query", "scope": " ".join(self.oauth_scopes), "prompt": "select_account",
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
            raise self.error_type(
                f"{self.feature} account records are unreadable; preserve the file and inspect it locally") from None
        if not isinstance(value, dict) or value.get("version") != 1 or not isinstance(value.get("accounts"), dict):
            raise self.error_type(f"{self.feature} account records have an unsupported format")
        return value

    def _write_accounts(self, value: dict[str, Any]) -> None:
        _atomic_private_json(self.accounts_path, value)

    def _read_pending(self, state: str) -> dict[str, Any]:
        if not isinstance(state, str) or not STATE_RE.fullmatch(state):
            raise self.error_type(f"This {self.feature} sign-in request is invalid; start again")
        path = self.pending_dir / f"{state}.json"
        with self._lock_context():
            try:
                os.chmod(path, 0o600)
                pending = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raise self.error_type(
                    f"This {self.feature} sign-in request is missing or already used; start again") from None
            try:
                path.unlink()
            except OSError:
                raise self.error_type(f"This {self.feature} sign-in request could not be consumed; start again") from None
        if float(pending.get("expires_at", 0)) < self.clock():
            raise self.error_type(f"This {self.feature} sign-in request expired; start again")
        return pending

    def cancel(self, state: str) -> None:
        """Consume an OAuth callback Microsoft denied; no token exchange occurs."""
        self._read_pending(state)

    def _http(self) -> httpx.Client:
        options: dict[str, Any] = {"timeout": httpx.Timeout(15), "trust_env": False, "follow_redirects": False}
        if self.transport is not None:
            options["transport"] = self.transport
        return httpx.Client(**options)

    def _json(self, response: httpx.Response, purpose: str) -> dict[str, Any]:
        if 300 <= response.status_code < 400:
            raise self.error_type(f"Microsoft redirected the {purpose}; Hutch stopped without forwarding credentials")
        if response.status_code == 401:
            raise self.error_type(f"Microsoft rejected the {purpose}; reconnect {self.feature} and try again")
        if response.status_code == 403:
            raise self.error_type(
                f"Microsoft denied the {purpose}; confirm the requested {self.required_scopes[0]} consent and check any organization policy")
        if response.status_code == 404:
            raise self.error_type(f"Microsoft could not find the selected {self.feature} resource during {purpose}; select it again")
        if response.status_code == 429:
            raise self.error_type(f"Microsoft rate-limited the {purpose}; wait and try again")
        if response.status_code >= 400:
            raise self.error_type(f"Microsoft {purpose} failed (HTTP {response.status_code})")
        try:
            value = response.json()
        except ValueError:
            raise self.error_type(f"Microsoft returned an unreadable {purpose} response") from None
        if not isinstance(value, dict):
            raise self.error_type(f"Microsoft returned an invalid {purpose} response")
        return value

    def finish(self, state: str, code: str, redirect_uri: str) -> dict[str, str]:
        self._validate_callback(redirect_uri)
        if not isinstance(code, str) or not 1 <= len(code) <= 2048 or any(ord(c) < 32 for c in code):
            raise self.error_type("Microsoft did not return a valid authorization code; start sign-in again")
        pending = self._read_pending(state)
        if not secrets.compare_digest(str(pending.get("redirect_uri", "")), redirect_uri):
            raise self.error_type(f"This {self.feature} callback does not match the sign-in request; start again")
        with self._http() as client:
            try:
                response = client.post(TOKEN_URL, data={
                    "client_id": self.client_id, "code": code, "code_verifier": pending["verifier"],
                    "redirect_uri": redirect_uri, "grant_type": "authorization_code",
                })
            except httpx.HTTPError:
                raise self.error_type("Could not contact Microsoft's token service; start a fresh sign-in") from None
        payload = self._json(response, "authorization code exchange")
        refresh = payload.get("refresh_token")
        access = payload.get("access_token")
        expires = payload.get("expires_in")
        scope_set = set(str(payload.get("scope", "")).split())
        scope_granted = all(scope in scope_set or f"https://graph.microsoft.com/{scope}" in scope_set
                            for scope in self.required_scopes)
        if (not isinstance(refresh, str) or not 1 <= len(refresh) <= 4096 or
                not isinstance(access, str) or not 1 <= len(access) <= 4096 or
                any(ord(c) < 33 or ord(c) > 126 for c in access) or
                str(payload.get("token_type", "")).lower() != "bearer" or
                not isinstance(expires, (int, float)) or isinstance(expires, bool) or not 0 < expires <= 86400 or
                not scope_granted):
            raise self.error_type(
                f"Microsoft did not grant the requested {self.required_scopes[0]} permission with offline access; disconnect and reconnect")
        account_id = self.account_prefix + secrets.token_hex(12)
        created = datetime.fromtimestamp(self.clock(), timezone.utc).isoformat()
        account = {"id": account_id, "label": pending["label"], "created_at": created,
                   "scopes": list(self.required_scopes), "status": "connected"}
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

    def accounts(self) -> list[dict[str, str]]:
        with self._lock_context():
            accounts = self._read_accounts()["accounts"]
            return [dict(row) for _, row in sorted(accounts.items(), key=lambda pair: pair[1].get("created_at", ""))]

    def _account(self, account_id: str) -> dict[str, Any]:
        if not isinstance(account_id, str) or not self.account_pattern.fullmatch(account_id):
            raise self.error_type(f"{self.feature} account reference is invalid")
        with self._lock_context():
            account = self._read_accounts()["accounts"].get(account_id)
        if not account:
            raise self.error_type(f"{self.feature} account is not connected; reconnect it from Connections")
        return account

    def access_token(self, account_id: str) -> str:
        self._require_client_id()
        self._account(account_id)
        cache_key = (str(self.root.resolve()), account_id)
        with _ACCESS_LOCK:
            cached = _ACCESS_CACHE.get(cache_key)
            if cached and cached[0] > self.clock() + 60:
                return cached[1]
            refresh = self.secrets.get(account_id)
            if not refresh:
                raise OutlookCalendarError(
                    f"{self.feature} refresh credential is missing; disconnect and reconnect this account")
            with self._http() as client:
                try:
                    response = client.post(TOKEN_URL, data={
                        "client_id": self.client_id, "refresh_token": refresh, "grant_type": "refresh_token",
                    })
                except httpx.HTTPError:
                    raise OutlookCalendarError(
                        f"Could not refresh {self.feature} access; check the network and retry") from None
            payload = self._json(response, "access-token refresh")
            token = payload.get("access_token")
            expires = payload.get("expires_in")
            if (not isinstance(token, str) or not 1 <= len(token) <= 4096 or
                    any(ord(c) < 33 or ord(c) > 126 for c in token) or
                    str(payload.get("token_type", "")).lower() != "bearer" or
                    not isinstance(expires, (int, float)) or isinstance(expires, bool) or not 0 < expires <= 86400):
                raise self.error_type(f"Microsoft returned an invalid {self.feature} access-token response; reconnect this account")
            rotated = payload.get("refresh_token")
            if isinstance(rotated, str) and 1 <= len(rotated) <= 4096:
                self.secrets.put(account_id, rotated)
            _ACCESS_CACHE[cache_key] = (self.clock() + float(expires), token)
            return token

    @staticmethod
    def _validate_graph_url(url: str, expected_path: str | None = None) -> None:
        try:
            parts = urlsplit(url)
            valid = (parts.scheme == "https" and parts.hostname == "graph.microsoft.com" and
                     parts.username is None and parts.password is None and parts.port in (None, 443) and
                     not parts.fragment and (expected_path is None or parts.path == expected_path))
        except ValueError:
            valid = False
        if not valid:
            raise OutlookCalendarError(
                "Refusing a Microsoft Graph destination outside the verified v1.0 API host")

    def _get(self, url: str, account_id: str, params: dict[str, str] | None = None,
             purpose: str = "Calendar data", *, prefer: str = 'outlook.timezone="UTC"') -> dict[str, Any]:
        self._validate_graph_url(url)

        def request(token: str) -> httpx.Response:
            with self._http() as client:
                try:
                    return client.get(url, params=params, headers={
                        "Authorization": f"Bearer {token}", "Accept": "application/json",
                        "Prefer": prefer,
                    })
                except httpx.HTTPError:
                    raise self.error_type(
                        f"Could not contact Microsoft Graph for {purpose}; check the network and retry") from None

        token = self.access_token(account_id)
        response = request(token)
        if response.status_code == 401:
            key = (str(self.root.resolve()), account_id)
            with _ACCESS_LOCK:
                cached = _ACCESS_CACHE.get(key)
                if cached is not None and secrets.compare_digest(cached[1], token):
                    _ACCESS_CACHE.pop(key, None)
            response = request(self.access_token(account_id))
        if response.request.url.host != "graph.microsoft.com" or response.request.url.scheme != "https":
            raise self.error_type("Microsoft Graph request changed destination; no credentials were forwarded")
        return self._json(response, purpose)

    def _next_link(self, value: Any, endpoint_path: str) -> str | None:
        if not isinstance(value, str) or not value:
            return None
        if len(value) > 8192:
            raise OutlookCalendarError("Microsoft returned an oversized calendar continuation link")
        self._validate_graph_url(value, endpoint_path)
        return value

    def list_calendars(self, account_id: str) -> list[dict[str, Any]]:
        self._account(account_id)
        endpoint = f"{GRAPH_API}/me/calendars"
        url = endpoint
        params: dict[str, str] | None = {"$top": "100", "$select": "id,name,isDefaultCalendar"}
        result: list[dict[str, Any]] = []
        for _ in range(5):
            payload = self._get(url, account_id, params, "calendar list")
            values = payload.get("value", [])
            if not isinstance(values, list):
                raise OutlookCalendarError("Microsoft returned an invalid calendar list")
            for item in values:
                if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
                    continue
                result.append({"id": item["id"][:1024], "name": str(item.get("name") or "Calendar")[:200],
                               "primary": bool(item.get("isDefaultCalendar", False))})
                if len(result) >= 500:
                    return result
            next_url = self._next_link(payload.get("@odata.nextLink"), "/v1.0/me/calendars")
            if not next_url:
                break
            url, params = next_url, None
        return result

    @staticmethod
    def _time(value: str, label: str) -> datetime:
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            raise OutlookCalendarError(f"Calendar {label} must be an ISO 8601 date-time with a time zone") from None
        if result.tzinfo is None or result.utcoffset() is None:
            raise OutlookCalendarError(f"Calendar {label} must include a time zone")
        return result.astimezone(timezone.utc)

    @staticmethod
    def _event_time(value: Any) -> str:
        if not isinstance(value, dict):
            return ""
        date_time = str(value.get("dateTime") or "")[:64]
        zone = str(value.get("timeZone") or "UTC")[:80]
        if not date_time:
            return ""
        # Graph returns dateTime without an offset when Prefer: UTC is applied.
        # Keep the zone explicit in Hutch's returned text instead of suggesting
        # the local machine's timezone.
        try:
            parsed = datetime.fromisoformat(date_time.replace("Z", "+00:00"))
        except ValueError:
            raise OutlookCalendarError("Microsoft returned an invalid event time") from None
        if parsed.tzinfo is not None:
            return date_time
        return f"{date_time} {zone}"

    def list_events(self, account_id: str, calendar_id: str, time_min: str, time_max: str,
                    *, limit: int = 25) -> list[dict[str, str]]:
        self._account(account_id)
        if (not isinstance(calendar_id, str) or not 1 <= len(calendar_id) <= 1024 or
                any(ord(c) < 32 for c in calendar_id)):
            raise OutlookCalendarError("Choose a valid calendar from the connected account")
        start, end = self._time(time_min, "start"), self._time(time_max, "end")
        if start >= end or (end - start).total_seconds() > 366 * 24 * 3600:
            raise OutlookCalendarError("Calendar time range must be positive and no longer than 366 days")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 25:
            raise OutlookCalendarError("Outlook Calendar result limit must be between 1 and 25")
        path = f"/v1.0/me/calendars/{quote(calendar_id, safe='')}/calendarView"
        url = f"https://graph.microsoft.com{path}"
        payload = self._get(url, account_id, {
            "startDateTime": start.isoformat().replace("+00:00", "Z"),
            "endDateTime": end.isoformat().replace("+00:00", "Z"),
            "$top": str(limit), "$select": "subject,start,end,location",
        }, "calendar events")
        values = payload.get("value", [])
        if not isinstance(values, list):
            raise OutlookCalendarError("Microsoft returned an invalid calendar event list")
        events: list[dict[str, str]] = []
        for item in values[:limit]:
            if not isinstance(item, dict):
                continue
            location = item.get("location") if isinstance(item.get("location"), dict) else {}
            events.append({
                "summary": str(item.get("subject") or "(untitled event)")[:500],
                "start": self._event_time(item.get("start")),
                "end": self._event_time(item.get("end")),
                "location": str(location.get("displayName") or "")[:500],
            })
        return events

    def disconnect(self, account_id: str) -> dict[str, Any]:
        if not isinstance(account_id, str) or not self.account_pattern.fullmatch(account_id):
            raise self.error_type(f"{self.feature} account reference is invalid")
        try:
            self._account(account_id)
        except OutlookCalendarError as exc:
            if "not connected" in str(exc):
                return {"removed": False, "provider_revocation": "not_needed"}
            raise
        # Microsoft Graph has no user-token revocation endpoint suitable for
        # this local public-client flow. Clear Hutch's refresh token and make
        # the boundary visible; the owner can revoke account consent in their
        # Microsoft account or organisation settings.
        self.secrets.delete(account_id)
        with self._lock_context():
            data = self._read_accounts()
            data["accounts"].pop(account_id, None)
            self._write_accounts(data)
        with _ACCESS_LOCK:
            _ACCESS_CACHE.pop((str(self.root.resolve()), account_id), None)
        return {"removed": True, "provider_revocation": "unavailable"}


__all__ = ["OutlookCalendarBook", "OutlookCalendarError", "OAuthStart", "SecretToolStore"]
