"""Projection of one saved ChatGPT account into an explicit credential state.

The auth store owns tokens and the refresh lock. This module answers only what a person needs to
see: is the credential active (an unexpired access token or a refresh token), expired (an access
token with no way to refresh), revoked (disconnect cleared it, with or without provider
confirmation), or missing. It never returns a token or a token-derived value.
"""

from __future__ import annotations

from typing import Any

EXPIRY_SKEW_SECONDS = 60


def account_row(account_id: str, account: dict[str, Any], now: float, plan_scope: str) -> dict[str, Any]:
    """One safe account row for pages and readiness. No credential value is included."""
    access = account.get("access_token") if isinstance(account.get("access_token"), str) else ""
    refresh = account.get("refresh_token") if isinstance(account.get("refresh_token"), str) else ""
    scopes = account.get("scopes") if isinstance(account.get("scopes"), list) else []
    try:
        expires_at = float(account.get("expires_at", 0) or 0)
    except (TypeError, ValueError):
        expires_at = 0.0
    revocation = str(account.get("revocation_status", ""))
    if revocation in ("confirmed", "unconfirmed"):
        state = "revoked"
    elif refresh or (access and expires_at > now + EXPIRY_SKEW_SECONDS):
        state = "active"
    elif access:
        state = "expired"
    else:
        state = "missing"
    return {
        "account_id": account_id,
        "email": account.get("email", "") if account.get("email_verified") is True else "",
        "connected": bool(access or refresh),
        "plan_usage": plan_scope in scopes,
        "expires_at": expires_at,
        "credential_state": state,
        "can_refresh": bool(refresh),
        "revocation_status": revocation,
    }
