"""The saved ChatGPT account is projected into an explicit, non-secret credential state."""

from __future__ import annotations

from hutch.chatgpt_status import EXPIRY_SKEW_SECONDS, account_row

SCOPE = "chatgpt.tokens.use.direct"
NOW = 1_000.0


def _row(**account):
    return account_row("acct_" + "a" * 24, account, NOW, SCOPE)


def test_a_refresh_token_keeps_the_credential_active_even_after_access_expiry():
    row = _row(access_token="", refresh_token="refresh-1", expires_at=NOW - 1, scopes=[SCOPE])
    assert row["credential_state"] == "active"
    assert row["can_refresh"] is True
    assert row["connected"] is True
    assert row["plan_usage"] is True


def test_an_unexpired_access_token_outside_the_skew_is_active():
    row = _row(access_token="access-1", refresh_token="", expires_at=NOW + EXPIRY_SKEW_SECONDS + 1)
    assert row["credential_state"] == "active"


def test_an_access_token_inside_the_skew_without_refresh_is_expired():
    row = _row(access_token="access-1", refresh_token="", expires_at=NOW + 1)
    assert row["credential_state"] == "expired"
    assert row["can_refresh"] is False


def test_a_cleared_credential_with_revocation_is_revoked_not_active():
    row = _row(access_token="", refresh_token="", expires_at=0, revocation_status="confirmed")
    assert row["credential_state"] == "revoked"
    assert row["connected"] is False


def test_an_empty_record_is_missing():
    assert _row()["credential_state"] == "missing"


def test_unverified_email_is_never_returned():
    assert _row(email="owner@example.test", email_verified=False)["email"] == ""
    assert _row(email="owner@example.test", email_verified=True)["email"] == "owner@example.test"
