from __future__ import annotations

import base64
import hashlib
import json
import secrets

import cbor2
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError
from fastapi.testclient import TestClient

from hutch.server.app import PasskeyVerifyRequest, create_app
from hutch.server.security import MAX_PASSKEY_VERIFY_BODY_BYTES
from hutch.server.passkeys import verify_authentication, verify_registration


RP_ID = "hutch.example"
ORIGIN = "https://hutch.example"


def test_passkey_verification_rejects_oversized_credential_payload():
    with pytest.raises(ValidationError, match="passkey credential payload is too large"):
        PasskeyVerifyRequest.model_validate({
            "challenge_id": "challenge",
            "credential": {"response": {"clientDataJSON": "x" * (256 * 1024 + 1)}},
        })


def test_passkey_verification_rejects_oversized_http_body_before_json_parsing(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    payload = b'{"challenge_id":"x","credential":{}}' + b" " * MAX_PASSKEY_VERIFY_BODY_BYTES
    with TestClient(app) as client:
        response = client.post("/api/v1/passkeys/login/verify", content=payload,
                               headers={"Origin": "http://testserver", "X-Hutch-Request": "1"})
    assert response.status_code == 413


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _client_data(kind: str, challenge: bytes, origin: str) -> bytes:
    return json.dumps({"type": kind, "challenge": _b64(challenge), "origin": origin,
                       "crossOrigin": False}, separators=(",", ":")).encode("utf-8")


def _registration(challenge: bytes, *, rp_id: str = RP_ID, origin: str = ORIGIN,
                  user_handle: bytes | None = None, flags: int = 0x45):
    credential_id = secrets.token_bytes(24)
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(serialization.Encoding.Raw,
                                                        serialization.PublicFormat.Raw)
    cose_key = cbor2.dumps({1: 1, 3: -8, -1: 6, -2: public_key})  # EdDSA / Ed25519
    auth_data = (hashlib.sha256(rp_id.encode("ascii")).digest() + bytes([flags]) + bytes(4)
                 + bytes(16) + len(credential_id).to_bytes(2, "big") + credential_id + cose_key)
    attestation = cbor2.dumps({"fmt": "none", "authData": auth_data, "attStmt": {}})
    body = {
        "id": _b64(credential_id), "rawId": _b64(credential_id), "type": "public-key",
        "response": {"attestationObject": _b64(attestation),
                     "clientDataJSON": _b64(_client_data("webauthn.create", challenge, origin)),
                     "transports": ["internal"]},
        "clientExtensionResults": {}, "authenticatorAttachment": "platform",
    }
    return body, private_key, credential_id, user_handle or secrets.token_bytes(32)


def _assertion(private_key: Ed25519PrivateKey, credential_id: bytes, challenge: bytes, user_handle: bytes,
               *, rp_id: str = RP_ID, origin: str = ORIGIN, flags: int = 0x05, counter: int = 1,
               signature_change: bool = False) -> dict:
    auth_data = (hashlib.sha256(rp_id.encode("ascii")).digest() + bytes([flags]) + counter.to_bytes(4, "big"))
    client_data = _client_data("webauthn.get", challenge, origin)
    signature = private_key.sign(auth_data + hashlib.sha256(client_data).digest())
    if signature_change:
        signature = signature[:-1] + bytes([signature[-1] ^ 1])
    return {
        "id": _b64(credential_id), "rawId": _b64(credential_id), "type": "public-key",
        "response": {"authenticatorData": _b64(auth_data), "clientDataJSON": _b64(client_data),
                     "signature": _b64(signature), "userHandle": _b64(user_handle)},
        "clientExtensionResults": {}, "authenticatorAttachment": "platform",
    }


def test_webauthn_registration_and_assertion_reject_wrong_origin_rp_challenge_signature_and_uv():
    registration_challenge = secrets.token_bytes(32)
    registration, private_key, credential_id, user_handle = _registration(
        registration_challenge, user_handle=secrets.token_bytes(32))
    registered = verify_registration(registration, registration_challenge, RP_ID, ORIGIN, user_handle)
    assert registered["credential_id"] == credential_id
    assert registered["public_key"]
    assert registered["user_handle"] == user_handle

    for bad_origin in ("https://evil.example", "http://hutch.example"):
        bad, *_ = _registration(registration_challenge, origin=bad_origin, user_handle=user_handle)
        with pytest.raises(ValueError, match="invalid passkey registration"):
            verify_registration(bad, registration_challenge, RP_ID, ORIGIN, user_handle)

    bad_challenge, *_ = _registration(secrets.token_bytes(32), user_handle=user_handle)
    with pytest.raises(ValueError, match="invalid passkey registration"):
        verify_registration(bad_challenge, registration_challenge, RP_ID, ORIGIN, user_handle)
    with pytest.raises(ValueError, match="invalid passkey registration"):
        verify_registration(registration, registration_challenge, "other.example", ORIGIN, user_handle)

    auth_challenge = secrets.token_bytes(32)
    stored = {"id": "credential", "public_key": registered["public_key"],
              "backup_eligible": False, "sign_count": 0, "user_handle": user_handle}
    valid = _assertion(private_key, credential_id, auth_challenge, user_handle)
    assert verify_authentication(valid, auth_challenge, RP_ID, ORIGIN, stored)["credential_id"] == credential_id

    failures = [
        (_assertion(private_key, credential_id, auth_challenge, user_handle, origin="https://evil.example"), RP_ID),
        (_assertion(private_key, credential_id, auth_challenge, user_handle), "other.example"),
        (_assertion(private_key, credential_id, secrets.token_bytes(32), user_handle), RP_ID),
        (_assertion(private_key, credential_id, auth_challenge, user_handle, signature_change=True), RP_ID),
        (_assertion(private_key, credential_id, auth_challenge, user_handle, flags=0x01), RP_ID),
    ]
    for credential, expected_rp in failures:
        with pytest.raises(ValueError, match="invalid passkey authentication"):
            verify_authentication(credential, auth_challenge, expected_rp, ORIGIN, stored)

    synced_registration, synced_private, synced_id, synced_handle = _registration(
        registration_challenge, user_handle=secrets.token_bytes(32), flags=0x5D)
    synced = verify_registration(synced_registration, registration_challenge, RP_ID, ORIGIN, synced_handle)
    assert synced["backup_eligible"] and synced["backed_up"]
    synced_stored = {"id": "synced", "public_key": synced["public_key"], "backup_eligible": True,
                     "sign_count": 7, "user_handle": synced_handle}
    # A multi-device passkey may report zero again on a different authenticator.
    synced_assertion = _assertion(synced_private, synced_id, auth_challenge, synced_handle,
                                  flags=0x1D, counter=0)
    assert verify_authentication(synced_assertion, auth_challenge, RP_ID, ORIGIN,
                                 synced_stored)["sign_count"] == 0


def test_pairing_and_login_verify_real_passkey_proofs_and_user_handle(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "1")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", RP_ID)
    monkeypatch.setenv("HUTCH_WEBAUTHN_RP_ID", RP_ID)
    monkeypatch.setenv("HUTCH_WEBAUTHN_ORIGIN", ORIGIN)
    app = create_app()
    headers = {"Host": RP_ID, "Origin": ORIGIN, "X-Hutch-Request": "1"}
    with TestClient(app, base_url=ORIGIN) as client:
        pair = client.post("/api/v1/pairing/exchange", json={"code": app.state.store.create_pairing_code()},
                           headers=headers)
        assert pair.status_code == 200, pair.text
        options_response = client.post("/api/v1/passkeys/registration/options", headers=headers)
        assert options_response.status_code == 200, options_response.text
        options = options_response.json()
        challenge = _unb64(options["challenge"])
        user_handle = _unb64(options["user"]["id"])
        registration, private_key, credential_id, _ = _registration(
            challenge, user_handle=user_handle)
        registered = client.post("/api/v1/passkeys/registration/verify",
                                 json={"challenge_id": options["challenge_id"], "credential": registration},
                                 headers=headers)
        assert registered.status_code == 200, registered.text
        assert "token" not in registered.text
        assert client.cookies.get("hutch_session")
        assert client.get("/api/bots", headers={"Host": RP_ID}).status_code == 200

        client.cookies.clear()
        login_options = client.post("/api/v1/passkeys/login/options", headers=headers)
        assert login_options.status_code == 200, login_options.text
        options = login_options.json()
        challenge = _unb64(options["challenge"])
        wrong_handle = secrets.token_bytes(32)
        assertion = _assertion(private_key, credential_id, challenge, wrong_handle)
        rejected = client.post("/api/v1/passkeys/login/verify",
                              json={"challenge_id": options["challenge_id"], "credential": assertion},
                              headers=headers)
        assert rejected.status_code == 401
        assert client.cookies.get("hutch_session") is None

        login_options = client.post("/api/v1/passkeys/login/options", headers=headers)
        options = login_options.json()
        challenge = _unb64(options["challenge"])
        assertion = _assertion(private_key, credential_id, challenge, user_handle)
        unlocked = client.post("/api/v1/passkeys/login/verify",
                               json={"challenge_id": options["challenge_id"], "credential": assertion},
                               headers=headers)
        assert unlocked.status_code == 200, unlocked.text
        assert unlocked.json()["authenticated"] is True
        assert client.get("/api/bots", headers={"Host": RP_ID}).status_code == 200
