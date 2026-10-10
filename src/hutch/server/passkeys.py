"""WebAuthn ceremonies for private, single-operator Hutch installations."""

from __future__ import annotations

import os
import re
from urllib.parse import urlsplit

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import (options_to_json, parse_authentication_credential_json,
                              parse_registration_credential_json)
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)


class PasskeyConfigError(ValueError):
    """The relying-party hostname or HTTPS origin is absent or invalid."""


def relying_party() -> tuple[str, str]:
    rp_id = os.environ.get("HUTCH_WEBAUTHN_RP_ID", "").strip().lower()
    origin = os.environ.get("HUTCH_WEBAUTHN_ORIGIN", "").strip()
    if not rp_id or not origin:
        raise PasskeyConfigError("set HUTCH_WEBAUTHN_RP_ID and HUTCH_WEBAUTHN_ORIGIN to the canonical HTTPS hostname")
    if (len(rp_id) > 253 or ":" in rp_id or not re.fullmatch(
            r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*",
            rp_id)):
        raise PasskeyConfigError("HUTCH_WEBAUTHN_RP_ID must be a DNS hostname without a port")
    try:
        parsed = urlsplit(origin)
        _ = parsed.port
    except ValueError:
        raise PasskeyConfigError("HUTCH_WEBAUTHN_ORIGIN must be one exact HTTPS origin") from None
    # The RP ID is a DNS hostname, while the exact origin may carry a
    # non-default HTTPS port (for example, a private LAN listener on :8787).
    # Browsers canonicalize :443 away, so accepting it here would create a
    # configured origin that cannot match the browser's serialized origin.
    try:
        port = parsed.port
    except ValueError:
        raise PasskeyConfigError("HUTCH_WEBAUTHN_ORIGIN must be one exact HTTPS origin") from None
    canonical_netloc = rp_id if port is None else f"{rp_id}:{port}"
    if (parsed.scheme != "https" or parsed.hostname != rp_id or parsed.netloc != canonical_netloc
            or port == 443 or parsed.username is not None or parsed.password is not None
            or parsed.path or parsed.query or parsed.fragment):
        raise PasskeyConfigError("HUTCH_WEBAUTHN_ORIGIN must be HTTPS and use the exact configured RP hostname")
    return rp_id, origin


def registration_options(rp_id: str, user_handle: bytes, excluded: list[bytes], challenge: bytes) -> str:
    return options_to_json(generate_registration_options(
        rp_id=rp_id,
        rp_name="Hutch",
        user_name="Hutch operator",
        user_display_name="Hutch operator",
        user_id=user_handle,
        challenge=challenge,
        timeout=120_000,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            require_resident_key=True,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=value) for value in excluded],
    ))


def authentication_options(rp_id: str, challenge: bytes) -> str:
    # No allowCredentials list: phones can use a discoverable (synced) passkey.
    return options_to_json(generate_authentication_options(
        rp_id=rp_id,
        challenge=challenge,
        timeout=120_000,
        user_verification=UserVerificationRequirement.REQUIRED,
    ))


def verify_registration(credential: dict, challenge: bytes, rp_id: str, origin: str,
                        user_handle: bytes) -> dict:
    try:
        result = verify_registration_response(
            credential=parse_registration_credential_json(credential),
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            require_user_presence=True,
            require_user_verification=True,
        )
    except WebAuthnException as exc:
        raise ValueError("invalid passkey registration response") from exc
    if not result.user_verified:
        raise ValueError("the passkey did not verify the user")
    return {
        "credential_id": result.credential_id,
        "public_key": result.credential_public_key,
        "sign_count": result.sign_count,
        "backup_eligible": result.credential_device_type.value == "multi_device",
        "backed_up": result.credential_backed_up,
        "user_handle": user_handle,
    }


def authentication_credential_id(credential: dict) -> tuple[bytes, bytes | None]:
    try:
        parsed = parse_authentication_credential_json(credential)
    except WebAuthnException as exc:
        raise ValueError("invalid passkey authentication response") from exc
    return parsed.raw_id, parsed.response.user_handle


def verify_authentication(credential: dict, challenge: bytes, rp_id: str, origin: str,
                          stored: dict) -> dict:
    try:
        result = verify_authentication_response(
            credential=parse_authentication_credential_json(credential),
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=bytes(stored["public_key"]),
            # Synced passkeys can be used by more than one authenticator and may
            # report a zero or non-monotonic counter. Hutch uses single-use server
            # challenges for replay protection and only enforces counters for keys
            # declared single-device by the authenticator.
            credential_current_sign_count=0 if stored["backup_eligible"] else int(stored["sign_count"]),
            require_user_verification=True,
        )
    except WebAuthnException as exc:
        raise ValueError("invalid passkey authentication response") from exc
    if not result.user_verified:
        raise ValueError("the passkey did not verify the user")
    return {
        "credential_id": result.credential_id,
        "credential_row_id": stored["id"],
        "sign_count": result.new_sign_count,
        "backed_up": result.credential_backed_up,
        "user_handle": bytes(stored["user_handle"]),
    }
