"""Local Sign in with ChatGPT client for Hutch.

This implements the published public-client OAuth flow for a local app. It never
reads ChatGPT browser cookies or tokens from another client. OAuth attempts are
single-use, short-lived, and kept separate from durable account credentials.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
import re
import secrets
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlencode, urlsplit

import fcntl
import httpx

AUTH_ORIGIN = "https://auth.openai.com"
API_ORIGIN = "https://api.openai.com"
PLAN_SCOPE = "chatgpt.tokens.use.direct"
OAUTH_SCOPES = "openid profile email offline_access resource.invoke " + PLAN_SCOPE
RESOURCE = API_ORIGIN + "/v1"
STATE_TTL_SECONDS = 600
ACCOUNT_ID = re.compile(r"^acct_[0-9a-f]{24}$")
_MODEL_CACHE_LOCK = threading.Lock()
_MODEL_CACHE: dict[tuple[str, str], tuple[float, list[dict[str, str]]]] = {}


class ChatGPTAuthError(ValueError):
    """A user-actionable sign-in, permission, or credential error."""


def chatgpt_plan_signin_enabled() -> bool:
    """The local operator must opt into this eligibility-gated preview explicitly."""
    return os.environ.get("HUTCH_ENABLE_CHATGPT_PLAN") == "1"


def loopback_callback_uri(request: Any) -> str:
    """Build the exact supported loopback callback from a local HTTP Hutch request."""
    host = request.headers.get("host", "")
    try:
        parts = urlsplit("//" + host)
        port = int(request.scope["server"][1])
        peer = request.client.host if request.client else ""
        try:
            peer_is_local = ipaddress.ip_address(peer).is_loopback
        except ValueError:
            # Starlette's in-process TestClient uses this synthetic address;
            # real server peers are always numeric.
            peer_is_local = peer == "testclient"
        if (request.url.scheme != "http" or parts.hostname != "127.0.0.1" or
                parts.username is not None or parts.password is not None or
                (parts.port is not None and parts.port != port) or
                not (1 <= port <= 65535) or not peer_is_local):
            raise ValueError
    except (KeyError, TypeError, ValueError, IndexError):
        raise ChatGPTAuthError("Sign in with ChatGPT must start and finish over Hutch's local HTTP 127.0.0.1 address") from None
    return f"http://127.0.0.1:{port}/auth/callback"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


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


class ChatGPTAuthBook:
    """Private token/account records and single-use PKCE attempts for one Hutch state directory."""

    def __init__(self, state_dir: Path, *, transport: httpx.BaseTransport | None = None,
                 clock=time.time):
        self.root = Path(state_dir) / "chatgpt"
        self.pending_dir = self.root / "pending"
        self.accounts_path = self.root / "accounts.json"
        self.lock_path = self.root / ".lock"
        self.transport = transport
        self.clock = clock

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            os.fchmod(fd, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _read_accounts(self) -> dict[str, Any]:
        try:
            os.chmod(self.accounts_path, 0o600)
            value = json.loads(self.accounts_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"version": 1, "host_id": "", "accounts": {}}
        except (OSError, json.JSONDecodeError) as exc:
            raise ChatGPTAuthError("ChatGPT credential storage is unreadable; preserve the file and inspect it locally") from exc
        if not isinstance(value, dict) or value.get("version") != 1 or not isinstance(value.get("accounts"), dict):
            raise ChatGPTAuthError("ChatGPT credential storage has an unsupported format")
        value.setdefault("host_id", "")
        return value

    def _write_accounts(self, value: dict[str, Any]) -> None:
        _atomic_private_json(self.accounts_path, value)

    @staticmethod
    def _valid_callback(uri: str) -> bool:
        try:
            parts = urlsplit(uri)
            return (parts.scheme == "http" and parts.hostname == "127.0.0.1" and
                    parts.port is not None and 1 <= parts.port <= 65535 and
                    parts.path == "/auth/callback" and not parts.query and not parts.fragment and
                    parts.username is None and parts.password is None)
        except ValueError:
            return False

    def start(self, redirect_uri: str, *, account_id: str = "") -> str:
        """Create a fresh OAuth URL; new registrations use the supported dynamic-client flow."""
        if not self._valid_callback(redirect_uri):
            raise ChatGPTAuthError("Sign in must use Hutch's exact local 127.0.0.1 callback")
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(48)
        nonce = secrets.token_urlsafe(32)
        challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
        now = self.clock()
        with self._locked():
            data = self._read_accounts()
            if not data["host_id"]:
                data["host_id"] = "urn:uuid:" + str(uuid.uuid4())
                self._write_accounts(data)
            account = None
            if account_id:
                if not ACCOUNT_ID.fullmatch(account_id):
                    raise ChatGPTAuthError("Unknown ChatGPT account")
                account = data["accounts"].get(account_id)
                if account is None or not account.get("client_id"):
                    raise ChatGPTAuthError("This ChatGPT account must be connected again as a new account")
            client_id = account["client_id"] if account else "dynamic_agent_client"
            pending = {
                "created_at": now, "expires_at": now + STATE_TTL_SECONDS,
                "redirect_uri": redirect_uri, "client_id": client_id,
                "new_registration": account is None, "account_id": account_id,
                "subject": account.get("subject", "") if account else "",
                "verifier": verifier, "nonce": nonce,
            }
            self.pending_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(self.pending_dir, 0o700)
            _atomic_private_json(self.pending_dir / f"{state}.json", pending)
            params = {
                "client_id": client_id,
                "response_type": "code",
                "redirect_uri": redirect_uri,
                "scope": OAUTH_SCOPES,
                "resource": RESOURCE,
                "state": state,
                "nonce": nonce,
                "code_challenge_method": "S256",
                "code_challenge": challenge,
                "ext_agent_host_id": data["host_id"],
            }
            if account is None:
                params["agent_name_hint"] = "Hutch"
            else:
                # OpenAI recommends retaining the selected account's issued
                # client ID and using its verified identity as a returning
                # sign-in hint. The ID token is sent only to the official
                # authorization endpoint; never log this URL.
                if account.get("id_token"):
                    params["id_token_hint"] = account["id_token"]
                if account.get("email_verified") is True and account.get("email"):
                    params["login_hint"] = account["email"]
        return AUTH_ORIGIN + "/api/accounts/authorize?" + urlencode(params)

    def _consume_pending(self, state: str) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z0-9_-]{30,100}", state or ""):
            raise ChatGPTAuthError("The sign-in response did not match a pending Hutch request")
        path = self.pending_dir / f"{state}.json"
        with self._locked():
            try:
                pending = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raise ChatGPTAuthError("This sign-in request is missing or has already been used; start again") from None
            try:
                path.unlink()
            except OSError:
                raise ChatGPTAuthError("The sign-in request could not be consumed; start again") from None
        if float(pending.get("expires_at", 0)) < self.clock():
            raise ChatGPTAuthError("This sign-in request expired; start again")
        return pending

    def _http(self) -> httpx.Client:
        options: dict[str, Any] = {"timeout": httpx.Timeout(20), "trust_env": False,
                                   "follow_redirects": False}
        if self.transport is not None:
            options["transport"] = self.transport
        return httpx.Client(**options)

    @staticmethod
    def _checked_response(response: httpx.Response, purpose: str) -> dict[str, Any]:
        if response.status_code >= 400:
            if response.status_code in (401, 403):
                raise ChatGPTAuthError("ChatGPT rejected the sign-in credentials or permission. Reconnect and review access.")
            if response.status_code == 429:
                raise ChatGPTAuthError("ChatGPT temporarily rate-limited sign-in; wait and try again")
            raise ChatGPTAuthError(f"ChatGPT {purpose} failed (HTTP {response.status_code}); start a fresh sign-in")
        try:
            value = response.json()
        except ValueError:
            raise ChatGPTAuthError(f"ChatGPT returned an unreadable {purpose} response") from None
        if not isinstance(value, dict):
            raise ChatGPTAuthError(f"ChatGPT returned an invalid {purpose} response")
        return value

    @staticmethod
    def _verify_id_token(token: str, *, client_id: str, nonce: str, jwks: dict[str, Any], now: float) -> dict[str, Any]:
        try:
            encoded_header, encoded_claims, encoded_sig = token.split(".")
            header = json.loads(_b64decode(encoded_header))
            claims = json.loads(_b64decode(encoded_claims))
            signature = _b64decode(encoded_sig)
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
                raise ValueError("unsupported signing algorithm")
            keys = [key for key in jwks.get("keys", []) if key.get("kid") == header["kid"]]
            if (len(keys) != 1 or keys[0].get("kty") != "RSA" or keys[0].get("use", "sig") != "sig" or
                    keys[0].get("alg", "RS256") != "RS256" or
                    ("key_ops" in keys[0] and "verify" not in keys[0]["key_ops"])):
                raise ValueError("signing key not found")
            key = keys[0]
            modulus = int.from_bytes(_b64decode(key["n"]), "big")
            exponent = int.from_bytes(_b64decode(key["e"]), "big")
            if modulus.bit_length() < 2048 or exponent < 3 or exponent % 2 == 0:
                raise ValueError("invalid RSA key")
            signed = f"{encoded_header}.{encoded_claims}".encode("ascii")
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding, rsa
            public_key = rsa.RSAPublicNumbers(exponent, modulus).public_key()
            public_key.verify(signature, signed, padding.PKCS1v15(), hashes.SHA256())
            audience = claims.get("aud")
            if claims.get("iss") != AUTH_ORIGIN or not (audience == client_id or
                    (isinstance(audience, list) and client_id in audience)):
                raise ValueError("issuer or audience mismatch")
            if isinstance(audience, list) and claims.get("azp") != client_id:
                raise ValueError("authorized party mismatch")
            if (not isinstance(claims.get("exp"), (int, float)) or isinstance(claims.get("exp"), bool) or
                    float(claims["exp"]) <= now):
                raise ValueError("token expired")
            issued_at = claims.get("iat")
            if (not isinstance(issued_at, (int, float)) or isinstance(issued_at, bool) or
                    float(issued_at) > now + 30 or float(issued_at) > float(claims["exp"])):
                raise ValueError("issued-at claim is missing or in the future")
            if claims.get("nonce") != nonce or not isinstance(claims.get("sub"), str) or not claims["sub"]:
                raise ValueError("nonce or subject mismatch")
            if isinstance(claims.get("nbf"), (int, float)) and float(claims["nbf"]) > now + 30:
                raise ValueError("token is not active yet")
            return claims
        except Exception as exc:
            raise ChatGPTAuthError(f"ChatGPT identity token could not be verified ({exc})") from None

    def _jwks(self) -> dict[str, Any]:
        try:
            with self._http() as client:
                discovery_response = client.get(AUTH_ORIGIN + "/.well-known/openid-configuration")
                discovery = self._checked_response(discovery_response, "OpenID discovery")
                if discovery.get("issuer") != AUTH_ORIGIN:
                    raise ChatGPTAuthError("ChatGPT returned an unexpected OpenID issuer")
                jwks_url = discovery.get("jwks_uri")
                try:
                    parts = urlsplit(jwks_url)
                    authority = (parts.scheme, parts.hostname, parts.port, parts.username, parts.password)
                except (TypeError, ValueError):
                    authority = None
                if authority not in (
                        ("https", "auth.openai.com", None, None, None),
                        ("https", "auth.openai.com", 443, None, None)):
                    raise ChatGPTAuthError("ChatGPT returned an unexpected signing-key location")
                if parts.path != "/.well-known/jwks.json" or parts.query or parts.fragment:
                    raise ChatGPTAuthError("ChatGPT returned an unexpected signing-key location")
                response = client.get(jwks_url)
                value = self._checked_response(response, "signing-key lookup")
        except httpx.HTTPError:
            raise ChatGPTAuthError("Could not verify the ChatGPT sign-in with OpenAI; start a fresh sign-in") from None
        if not isinstance(value.get("keys"), list):
            raise ChatGPTAuthError("ChatGPT returned an invalid signing-key set")
        return value

    def finish(self, *, state: str, code: str = "", returned_client_id: str = "", error: str = "",
               callback_uri: str = "") -> dict[str, str]:
        """Consume one callback, exchange its code, validate identity, and save owner-only credentials."""
        pending = self._consume_pending(state)
        if callback_uri and callback_uri != pending.get("redirect_uri"):
            raise ChatGPTAuthError("This callback does not match the Hutch sign-in request; start again")
        if error:
            if error == "access_denied":
                raise ChatGPTAuthError("ChatGPT access was declined. No connection was saved.")
            raise ChatGPTAuthError("ChatGPT sign-in did not complete. Start again from Connections.")
        if not code or len(code) > 4096 or any(c in code for c in "\r\n"):
            raise ChatGPTAuthError("ChatGPT did not return a valid authorization code")
        expected_client_id = pending["client_id"]
        client_id = returned_client_id or ("" if pending["new_registration"] else expected_client_id)
        if (not re.fullmatch(r"[A-Za-z0-9._~-]{5,256}", client_id or "") or
                client_id == "dynamic_agent_client" or
                (not pending["new_registration"] and client_id != expected_client_id)):
            raise ChatGPTAuthError("The ChatGPT registration did not match this sign-in request")
        form = {
            "grant_type": "authorization_code", "client_id": client_id, "code": code,
            "code_verifier": pending["verifier"], "redirect_uri": pending["redirect_uri"],
            "resource": RESOURCE,
        }
        try:
            with self._http() as client:
                response = client.post(AUTH_ORIGIN + "/api/accounts/oauth/token", data=form)
                tokens = self._checked_response(response, "token exchange")
        except httpx.HTTPError:
            raise ChatGPTAuthError("Could not exchange the ChatGPT authorization; start a fresh sign-in") from None
        access = tokens.get("access_token")
        refresh = tokens.get("refresh_token")
        id_token = tokens.get("id_token")
        expires_in = tokens.get("expires_in")
        scopes = set(str(tokens.get("scope", "")).split())
        if (not all(isinstance(x, str) and x for x in (access, refresh, id_token)) or
                str(tokens.get("token_type", "")).casefold() != "bearer" or
                not isinstance(expires_in, (int, float)) or isinstance(expires_in, bool) or expires_in <= 0):
            raise ChatGPTAuthError("ChatGPT's token response was incomplete; start a fresh sign-in")
        claims = self._verify_id_token(id_token, client_id=client_id, nonce=pending["nonce"], jwks=self._jwks(), now=self.clock())
        if pending.get("subject") and claims["sub"] != pending["subject"]:
            raise ChatGPTAuthError("The selected ChatGPT account changed during reauthorization; existing credentials were kept")
        account_id = "acct_" + hashlib.sha256((client_id + "\0" + claims["sub"]).encode()).hexdigest()[:24]
        if pending.get("account_id") and account_id != pending["account_id"]:
            raise ChatGPTAuthError("This authorization belongs to a different ChatGPT account; existing credentials were kept")
        with self._locked():
            data = self._read_accounts()
            email_verified = claims.get("email_verified") is True
            record = {
                "client_id": client_id, "subject": claims["sub"],
                "email": str(claims.get("email", ""))[:320] if email_verified else "",
                "email_verified": email_verified,
                "issuer": AUTH_ORIGIN, "ext_agent_host_id": data.get("host_id", ""),
                "id_token": id_token, "access_token": access, "refresh_token": refresh,
                "token_type": str(tokens.get("token_type", "Bearer")), "scopes": sorted(scopes),
                "expires_at": self.clock() + float(expires_in), "saved_at": self.clock(),
            }
            if pending.get("account_id"):
                data["accounts"][pending["account_id"]] = record
            else:
                # A dynamic-registration callback may race another callback for this same account.
                prior = next((key for key, item in data["accounts"].items()
                              if item.get("client_id") == client_id and item.get("subject") == claims["sub"]), None)
                data["accounts"][prior or account_id] = record
            self._write_accounts(data)
        return {"account_id": pending.get("account_id") or account_id,
                "email": record["email"],
                "plan_usage": "enabled" if PLAN_SCOPE in scopes else "identity-only"}

    def accounts(self) -> list[dict[str, Any]]:
        with self._locked():
            data = self._read_accounts()
        rows = []
        for account_id, account in sorted(data["accounts"].items()):
            connected = bool(account.get("access_token") or account.get("refresh_token"))
            rows.append({"account_id": account_id,
                         "email": account.get("email", "") if account.get("email_verified") is True else "",
                         "connected": connected, "plan_usage": PLAN_SCOPE in account.get("scopes", []),
                         "expires_at": float(account.get("expires_at", 0) or 0)})
        return rows

    def has_plan_usage(self, account_id: str) -> bool:
        if not ACCOUNT_ID.fullmatch(account_id or ""):
            return False
        with self._locked():
            account = self._read_accounts()["accounts"].get(account_id)
        return bool(account and (account.get("access_token") or account.get("refresh_token")) and
                    PLAN_SCOPE in account.get("scopes", []))

    def access_token(self, account_id: str) -> str:
        """Return a live plan-authorized token; rotating refreshes are serialized across Hutch processes."""
        if not ACCOUNT_ID.fullmatch(account_id or ""):
            raise ChatGPTAuthError("No ChatGPT account is connected")
        with self._locked():
            data = self._read_accounts()
            account = data["accounts"].get(account_id)
            if not account or PLAN_SCOPE not in account.get("scopes", []):
                raise ChatGPTAuthError("Connect ChatGPT and authorize plan usage on the Connections page")
            if account.get("access_token") and float(account.get("expires_at", 0)) > self.clock() + 60:
                return account["access_token"]
            refresh = account.get("refresh_token")
            if not refresh:
                raise ChatGPTAuthError("The ChatGPT sign-in expired; reconnect this account on the Connections page")
            form = {"grant_type": "refresh_token", "client_id": account["client_id"],
                    "refresh_token": refresh, "resource": RESOURCE}
            try:
                with self._http() as client:
                    response = client.post(AUTH_ORIGIN + "/api/accounts/oauth/token", data=form)
                    tokens = self._checked_response(response, "token refresh")
            except httpx.HTTPError:
                raise ChatGPTAuthError("Could not refresh the ChatGPT sign-in; reconnect this account") from None
            access = tokens.get("access_token")
            expires_in = tokens.get("expires_in")
            rotated_refresh = tokens.get("refresh_token")
            if (not isinstance(access, str) or not access or
                    str(tokens.get("token_type", "")).casefold() != "bearer" or
                    not isinstance(expires_in, (int, float)) or isinstance(expires_in, bool) or expires_in <= 0 or
                    (rotated_refresh is not None and (not isinstance(rotated_refresh, str) or not rotated_refresh))):
                raise ChatGPTAuthError("ChatGPT returned an incomplete token refresh; reconnect this account")
            scopes = set(str(tokens.get("scope", " ".join(account["scopes"]))).split())
            if PLAN_SCOPE not in scopes:
                raise ChatGPTAuthError("ChatGPT refresh no longer grants plan usage; reconnect and review access")
            account.update({"access_token": access,
                            "refresh_token": rotated_refresh or refresh,
                            # Keep the ID token we already verified. A refresh response is not a
                            # fresh OIDC authorization and must not replace its account hint with
                            # an unverified value.
                            "id_token": account.get("id_token", ""),
                            "scopes": sorted(scopes), "expires_at": self.clock() + float(expires_in),
                            "saved_at": self.clock()})
            self._write_accounts(data)
            return access

    def list_models(self, account_id: str) -> list[dict[str, str]]:
        cache_key = (str(self.root.resolve()), account_id)
        now = time.monotonic()
        with _MODEL_CACHE_LOCK:
            cached = _MODEL_CACHE.get(cache_key)
            if cached and cached[0] > now:
                return [dict(row) for row in cached[1]]
        token = self.access_token(account_id)
        try:
            with self._http() as client:
                response = client.get(API_ORIGIN + "/v1/models", headers={"Authorization": f"Bearer {token}"})
                body = self._checked_response(response, "model list")
        except httpx.HTTPError:
            raise ChatGPTAuthError("Could not load this ChatGPT account's model list") from None
        rows = body.get("models")
        if not isinstance(rows, list):
            raise ChatGPTAuthError("ChatGPT returned an invalid model catalog")
        models = [{"slug": row["slug"], "display_name": str(row.get("display_name") or row["slug"])}
                  for row in rows if isinstance(row, dict) and row.get("visibility") == "list" and
                  isinstance(row.get("slug"), str) and re.fullmatch(r"[A-Za-z0-9._:-]{1,160}", row["slug"])]
        with _MODEL_CACHE_LOCK:
            _MODEL_CACHE[cache_key] = (time.monotonic() + 60, [dict(row) for row in models])
        return models

    def disconnect(self, account_id: str) -> bool:
        """Revoke first, then clear local tokens; return False if remote revocation could not be confirmed."""
        if not ACCOUNT_ID.fullmatch(account_id or ""):
            raise ChatGPTAuthError("Unknown ChatGPT account")
        with self._locked():
            data = self._read_accounts()
            account = data["accounts"].get(account_id)
            if not account:
                raise ChatGPTAuthError("Unknown ChatGPT account")
            refresh = account.get("refresh_token", "")
            revoked = account.get("revocation_status") == "confirmed"
            if refresh:
                try:
                    with self._http() as client:
                        discovery = self._checked_response(client.get(AUTH_ORIGIN + "/.well-known/openid-configuration"),
                                                           "revocation discovery")
                        if discovery.get("issuer") != AUTH_ORIGIN:
                            raise ChatGPTAuthError("ChatGPT returned an unexpected revocation issuer")
                        endpoint = urlsplit(discovery.get("revocation_endpoint", ""))
                        if (endpoint.scheme, endpoint.hostname, endpoint.port,
                                endpoint.username, endpoint.password) not in (
                                ("https", "auth.openai.com", None, None, None),
                                ("https", "auth.openai.com", 443, None, None)):
                            raise ChatGPTAuthError("ChatGPT returned an unexpected revocation endpoint")
                        if endpoint.path != "/api/accounts/oauth/revoke" or endpoint.query or endpoint.fragment:
                            raise ChatGPTAuthError("ChatGPT returned an unexpected revocation endpoint")
                        response = client.post(discovery["revocation_endpoint"], data={
                            "token": refresh, "token_type_hint": "refresh_token", "client_id": account["client_id"]})
                        revoked = response.status_code == 200
                except (httpx.HTTPError, ChatGPTAuthError, KeyError, ValueError):
                    revoked = False
            account.update({"access_token": "", "refresh_token": "", "id_token": "",
                            "expires_at": 0, "scopes": [], "saved_at": self.clock(),
                            "revocation_status": "confirmed" if revoked else "unconfirmed"})
            self._write_accounts(data)
        with _MODEL_CACHE_LOCK:
            _MODEL_CACHE.pop((str(self.root.resolve()), account_id), None)
        return revoked
