"""Local Google Desktop OAuth client configuration shared by Calendar and Gmail."""

from __future__ import annotations

import os
import re
from typing import Literal

from .oauth_apps import GOOGLE_CLIENT_PATTERN, publisher_client_id


GOOGLE_OAUTH_CLIENT_ID_KEY = "connections:google_oauth_client_id"
GOOGLE_OAUTH_CLIENT_ID_ENV = "HUTCH_GOOGLE_OAUTH_CLIENT_ID"
GOOGLE_OAUTH_CLIENT_ID_PATTERN = GOOGLE_CLIENT_PATTERN
_CLIENT_ID_RE = re.compile(GOOGLE_OAUTH_CLIENT_ID_PATTERN)


def valid_google_oauth_client_id(value: str) -> bool:
    normalized = str(value or "").strip()
    return len(normalized) <= 512 and bool(_CLIENT_ID_RE.fullmatch(normalized))


def resolve_google_oauth_client_id(store) -> tuple[str, Literal["environment", "hutch", "distribution", "unset"]]:
    """Return the operator override, or the owner's locally saved public client ID."""
    environment_value = os.environ.get(GOOGLE_OAUTH_CLIENT_ID_ENV, "").strip()
    if environment_value:
        return environment_value, "environment"
    saved_value = (store.kv_get(GOOGLE_OAUTH_CLIENT_ID_KEY, "") or "").strip()
    if saved_value:
        return saved_value, "hutch"
    distributed = publisher_client_id("google")
    return (distributed, "distribution") if distributed else ("", "unset")


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
                   "Google sign-in is not enabled in this Hutch build."),
    }
