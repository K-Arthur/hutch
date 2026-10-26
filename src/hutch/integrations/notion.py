"""Notion hosted MCP account authorization, using its public PKCE/DCR flow.

Only the documented Notion origin is contacted. Public client registration is done
by Hutch, not by the user. Tokens remain in the OS credential store. This module
reuses the installed-app callback, file-lock and one-use state primitives, but does
not use Google's endpoints, scopes, token cache or client registration.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx

from ..google_calendar import (
    GoogleCalendarBook, GoogleCalendarError, OAuthStart, SecretToolStore,
    _atomic_private_json, _b64url,
)

ORIGIN = "https://mcp.notion.com"
CALLBACK_PATH = "/api/v1/connections/notion/callback"
ACCOUNT_PATTERN = re.compile(r"^notion_[0-9a-f]{24}$")
MAX_RESPONSE_BYTES = 64_000
NotionError = GoogleCalendarError


class NotionSecretStore(SecretToolStore):
    service = "hutch.notion"
    feature_name = "Notion"
    account_pattern = ACCOUNT_PATTERN
    probe_account = "notion_000000000000000000000000"


class NotionBook(GoogleCalendarBook):
    feature_name = "Notion"
    storage_name = "notion"
    account_pattern = ACCOUNT_PATTERN
    callback_path = CALLBACK_PATH
    secret_store_type = NotionSecretStore

    def __init__(self, state_dir, *, secrets_store=None, transport=None, clock=time.time):
        super().__init__(state_dir, "", secrets_store=secrets_store, transport=transport, clock=clock)

    def _request(self, path: str, *, data=None, body=None) -> dict:
        if path not in {"/register", "/token", "/.well-known/oauth-authorization-server"}:
            raise NotionError("Unsupported Notion authorization endpoint")
        try:
            with self._http() as client:
                with client.stream("GET" if path.startswith("/.well-known/") else "POST", ORIGIN + path,
                                   data=data, json=body, headers={"Accept": "application/json"}) as response:
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) > MAX_RESPONSE_BYTES:
                            raise NotionError("Notion authorization response exceeded its size limit")
                    if response.status_code not in {200, 201}:
                        # Error bodies can echo tokens, code verifiers or registration
                        # details. Never include them in an exception/API/log.
                        if response.status_code in {400, 401, 403}:
                            raise NotionError("Notion authorization was refused; reconnect this account")
                        raise NotionError(f"Notion authorization is unavailable (HTTP {response.status_code}); try again later")
                    value = json.loads(raw)
        except (httpx.HTTPError, ValueError) as exc:
            if isinstance(exc, NotionError):
                raise
            raise NotionError("Notion authorization could not be verified; try connecting again") from None
        if not isinstance(value, dict):
            raise NotionError("Notion returned an invalid authorization response")
        return value

    @staticmethod
    def _public_id(value) -> str:
        if not isinstance(value, str) or not 1 <= len(value) <= 512 or any(ord(c) < 33 or ord(c) == 127 for c in value):
            raise NotionError("Notion returned an invalid application identifier")
        return value

    def start(self, label: str, redirect_uri: str) -> OAuthStart:
        self._validate_callback(redirect_uri)
        if not self.secrets.available():
            raise NotionError("Unlock the operating system's secure credential store before connecting Notion")
        metadata = self._request("/.well-known/oauth-authorization-server")
        expected = {"issuer": ORIGIN, "authorization_endpoint": ORIGIN + "/authorize",
                    "token_endpoint": ORIGIN + "/token", "registration_endpoint": ORIGIN + "/register"}
        if any(metadata.get(key) != value for key, value in expected.items()) or "S256" not in metadata.get("code_challenge_methods_supported", []):
            raise NotionError("Notion's authorization configuration changed; this connection needs a Hutch update")
        registration = self._request("/register", body={"client_name": "Hutch", "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
            "token_endpoint_auth_method": "none"})
        client_id = self._public_id(registration.get("client_id"))
        if registration.get("token_endpoint_auth_method", "none") != "none" or registration.get("client_secret"):
            raise NotionError("Notion did not register a public PKCE client; no credentials were saved")
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
        clean_label = str(label or "Notion").strip()
        if not 1 <= len(clean_label) <= 80 or any(ord(c) < 32 for c in clean_label):
            raise NotionError("Choose a Notion nickname of 1 to 80 plain-text characters")
        pending = {"created_at": self.clock(), "expires_at": self.clock() + 600,
                   "redirect_uri": redirect_uri, "label": clean_label, "verifier": verifier, "client_id": client_id,
                   "issuer_required": metadata.get("authorization_response_iss_parameter_supported") is True}
        _atomic_private_json(self.pending_dir / f"{state}.json", pending)
        return OAuthStart(ORIGIN + "/authorize?" + urlencode({"response_type": "code", "client_id": client_id,
            "redirect_uri": redirect_uri, "scope": "default", "state": state, "code_challenge": challenge,
            "code_challenge_method": "S256", "prompt": "consent", "resource": ORIGIN + "/mcp"}), state)

    def _token_bundle(self, response: dict, *, client_id: str, previous: dict | None = None) -> dict:
        previous = previous or {}
        access = response.get("access_token")
        refresh = response.get("refresh_token") or previous.get("refresh_token")
        if (not isinstance(access, str) or not 1 <= len(access) <= 16_000 or
            not isinstance(refresh, str) or not 1 <= len(refresh) <= 16_000 or
            str(response.get("token_type", "")).lower() != "bearer" or
            any(ord(c) < 33 or ord(c) == 127 for c in access + refresh)):
            raise NotionError("Notion did not return usable renewable credentials; reconnect")
        try:
            ttl = int(response.get("expires_in", 3600))
        except (ValueError, TypeError, OverflowError):
            raise NotionError("Notion returned an invalid token expiry") from None
        if not 1 <= ttl <= 31_536_000:
            raise NotionError("Notion returned an invalid token expiry")
        scopes = response.get("scope", "default")
        if not isinstance(scopes, str) or set(scopes.split()) != {"default"}:
            raise NotionError("Notion returned an unexpected authorization scope; reconnect")
        return {"client_id": client_id, "access_token": access, "refresh_token": refresh,
                "expires_at": self.clock() + ttl}

    def finish(self, state: str, code: str, redirect_uri: str, *, issuer: str = "") -> dict:
        pending = self._read_pending(state)
        self._validate_callback(redirect_uri)
        if (pending["redirect_uri"] != redirect_uri or issuer not in {"", ORIGIN} or
                (pending.get("issuer_required") and issuer != ORIGIN)):
            raise NotionError("Notion sign-in did not match this request; start again")
        if not isinstance(code, str) or not 1 <= len(code) <= 4096:
            raise NotionError("Notion did not return a valid authorization code")
        response = self._request("/token", data={"grant_type": "authorization_code", "code": code,
            "code_verifier": pending["verifier"], "client_id": pending["client_id"],
            "redirect_uri": redirect_uri, "resource": ORIGIN + "/mcp"})
        bundle = self._token_bundle(response, client_id=pending["client_id"])
        account_id = "notion_" + secrets.token_hex(12)
        account = {"id": account_id, "label": pending["label"], "status": "connected", "scopes": ["default"],
                   "created_at": datetime.now(timezone.utc).isoformat()}
        for key in ("workspace_id", "workspace_name", "user_id"):
            value = response.get(key)
            if isinstance(value, str) and len(value) <= 200 and not any(ord(c) < 32 for c in value):
                account[key] = value
        with self._lock_context():
            value = self._read_accounts()
            self.secrets.put(account_id, json.dumps(bundle))
            try:
                value["accounts"][account_id] = account
                self._write_accounts(value)
            except Exception:
                self.secrets.delete(account_id)
                raise
        return account

    def access_token(self, account_id: str) -> str:
        # One cross-process lock covers read, refresh and rotated credential write.
        # There is no independent process-local cache surviving a disconnect.
        if not self.account_pattern.fullmatch(account_id):
            raise NotionError("Notion account reference is invalid")
        with self._lock_context():
            if account_id not in self._read_accounts()["accounts"]:
                raise NotionError("Notion account is disconnected")
            try:
                bundle = json.loads(self.secrets.get(account_id) or "null")
                if not isinstance(bundle, dict):
                    raise ValueError()
                if float(bundle["expires_at"]) > self.clock() + 60:
                    return str(bundle["access_token"])
                response = self._request("/token", data={"grant_type": "refresh_token",
                    "refresh_token": bundle["refresh_token"], "client_id": bundle["client_id"], "resource": ORIGIN + "/mcp"})
                renewed = self._token_bundle(response, client_id=bundle["client_id"], previous=bundle)
                self.secrets.put(account_id, json.dumps(renewed))
                return renewed["access_token"]
            except (KeyError, TypeError, ValueError) as exc:
                if isinstance(exc, NotionError):
                    raise
                raise NotionError("Notion credentials could not be read; reconnect") from None

    def disconnect(self, account_id: str) -> dict:
        self._account(account_id)
        with self._lock_context():
            raw = self.secrets.get(account_id)
            self.secrets.delete(account_id)
            value = self._read_accounts()
            value["accounts"].pop(account_id, None)
            self._write_accounts(value)
        # Local disconnect is immediate. Provider revocation is separately reported;
        # do not claim it succeeded merely because the local credential was erased.
        confirmed = False
        try:
            bundle = json.loads(raw or "{}")
            with self._http() as client:
                with client.stream("POST", ORIGIN + "/token", data={"token": bundle["refresh_token"],
                        "client_id": bundle["client_id"], "token_type_hint": "refresh_token"}) as response:
                    confirmed = response.status_code in {200, 204}
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            pass
        return {"removed": True, "provider_revocation": "confirmed" if confirmed else "not_confirmed"}
