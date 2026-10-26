"""Publisher-owned public OAuth application identities, supplied with a build.

These are application identifiers, never user sessions or client secrets. A
development checkout can leave them empty; distributable builds can require
specific registrations before packaging. Operators retain explicit overrides.
"""
from __future__ import annotations

import json
import os
import re
from importlib import resources

MAX_CONFIG_BYTES = 16_384
GOOGLE_CLIENT_PATTERN = r"^[A-Za-z0-9._-]+\.apps\.googleusercontent\.com$"
_MICROSOFT_CLIENT = re.compile(r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")


def validate_oauth_apps(raw: bytes, *, required: tuple[str, ...] = ()) -> dict:
    """Validate a small, public-only release input; refuse secrets/unknown fields."""
    if len(raw) > MAX_CONFIG_BYTES:
        raise ValueError("OAuth application configuration exceeds 16 KiB")
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ValueError("OAuth application configuration must be valid JSON") from None
    if not isinstance(value, dict) or set(value) != {"version", "apps"} or type(value["version"]) is not int or value["version"] != 1:
        raise ValueError("OAuth application configuration must use version 1")
    apps = value["apps"]
    if not isinstance(apps, dict) or set(apps) - {"google", "microsoft"}:
        raise ValueError("OAuth application configuration contains unsupported applications")
    for provider, app in apps.items():
        if not isinstance(app, dict) or set(app) != {"client_id"}:
            raise ValueError("OAuth application entries accept only a public client_id, never a client secret or token")
        client_id = app["client_id"]
        if not isinstance(client_id, str) or len(client_id) > 512:
            raise ValueError("OAuth application identifier is invalid")
        pattern = GOOGLE_CLIENT_PATTERN if provider == "google" else _MICROSOFT_CLIENT
        if client_id and not re.fullmatch(pattern, client_id):
            raise ValueError(f"Invalid {provider} application identifier")
    for provider in required:
        if provider not in {"google", "microsoft"}:
            raise ValueError("Unknown required OAuth application")
        if not apps.get(provider, {}).get("client_id"):
            raise ValueError(f"This build requires the publisher's {provider} OAuth registration")
    return value


def publisher_client_id(provider: str) -> str:
    try:
        path = resources.files("hutch").joinpath("data", "oauth-apps.json")
        with path.open("rb") as stream:
            value = validate_oauth_apps(stream.read(MAX_CONFIG_BYTES + 1))
        return value["apps"].get(provider, {}).get("client_id", "")
    except (OSError, ValueError):
        # An invalid build never guesses or borrows another app's registration.
        # Release preparation validates strictly and reports the configuration error.
        return ""


def outlook_oauth_client_id() -> str:
    return os.environ.get("HUTCH_OUTLOOK_OAUTH_CLIENT_ID", "").strip() or publisher_client_id("microsoft")
