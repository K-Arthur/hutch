"""Local Google Desktop OAuth client configuration shared by Calendar and Gmail."""

from __future__ import annotations

import os
import re
from typing import Literal


GOOGLE_OAUTH_CLIENT_ID_KEY = "connections:google_oauth_client_id"
GOOGLE_OAUTH_CLIENT_ID_ENV = "HUTCH_GOOGLE_OAUTH_CLIENT_ID"
GOOGLE_OAUTH_CLIENT_ID_PATTERN = r"^[A-Za-z0-9._-]+\.apps\.googleusercontent\.com$"
_CLIENT_ID_RE = re.compile(GOOGLE_OAUTH_CLIENT_ID_PATTERN)


def valid_google_oauth_client_id(value: str) -> bool:
    normalized = str(value or "").strip()
    return len(normalized) <= 512 and bool(_CLIENT_ID_RE.fullmatch(normalized))


def resolve_google_oauth_client_id(store) -> tuple[str, Literal["environment", "hutch", "unset"]]:
    """Return the operator override, or the owner's locally saved public client ID."""
    environment_value = os.environ.get(GOOGLE_OAUTH_CLIENT_ID_ENV, "").strip()
    if environment_value:
        return environment_value, "environment"
    saved_value = (store.kv_get(GOOGLE_OAUTH_CLIENT_ID_KEY, "") or "").strip()
    return (saved_value, "hutch") if saved_value else ("", "unset")


def google_oauth_client_settings(store) -> dict:
    client_id, source = resolve_google_oauth_client_id(store)
    valid = valid_google_oauth_client_id(client_id)
    return {
        "client_id": client_id,
        "source": source,
        "editable": source != "environment",
        "configured": valid,
        "valid": valid,
        "detail": ("Ready for Google sign-in." if valid else
                   "Enter a Google Desktop OAuth client ID ending in .apps.googleusercontent.com."),
    }
