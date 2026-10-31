"""Grants and the use/reveal boundary: who may do what, and what the audit records."""

from __future__ import annotations

import pytest

from hutch.vault.refs import Permission, Principal
from hutch.vault.vault import AccessDenied
from tests.support.vault_fixtures import BOT_A, BOT_B, CANARY, unlocked


def test_bot_without_a_grant_is_refused_and_recorded(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    with pytest.raises(AccessDenied):
        vault.resolve_for_use(meta.ref, Principal.bot(BOT_A))
    denied = [e for e in vault.audit_log() if e.outcome == "denied"]
    assert denied and denied[0].reason == "no_grant"
    assert denied[0].actor == f"bot:{BOT_A}"


def test_granted_bot_may_use_but_not_reveal(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    vault.grant(meta.id, Principal.bot(BOT_A), Permission.USE)

    usable = vault.resolve_for_use(meta.ref, Principal.bot(BOT_A), destination="api.notion.com")
    assert usable.value() == CANARY
    assert CANARY not in repr(usable) and CANARY not in str(usable)
    assert usable.destination == "api.notion.com"

    with pytest.raises(AccessDenied):
        vault.reveal(meta.ref, Principal.bot(BOT_A))


def test_reveal_grant_is_separate_from_use(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    vault.grant(meta.id, Principal.bot(BOT_A), Permission.REVEAL)
    with pytest.raises(AccessDenied):
        vault.resolve_for_use(meta.ref, Principal.bot(BOT_A))
    assert vault.reveal(meta.ref, Principal.bot(BOT_A)).value() == CANARY


def test_a_bot_cannot_reach_another_bots_secret_even_with_a_grant(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope=f"bot:{BOT_A}", category="api_key", name="private", value=CANARY)
    with pytest.raises(AccessDenied):
        vault.grant(meta.id, Principal.bot(BOT_B), Permission.USE)
    with pytest.raises(AccessDenied):
        vault.resolve_for_use(meta.ref, Principal.bot(BOT_B))
    vault.grant(meta.id, Principal.bot(BOT_A), Permission.USE)
    assert vault.resolve_for_use(meta.ref, Principal.bot(BOT_A)).value() == CANARY


def test_connectors_skills_and_workspace_never_reach_bot_scoped_secrets(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope=f"bot:{BOT_A}", category="api_key", name="private", value=CANARY)
    for principal in (Principal("connector", "notion"), Principal("skill", "gmail"), Principal.workspace()):
        with pytest.raises(AccessDenied):
            vault.grant(meta.id, principal, Permission.USE)


def test_revoked_grant_takes_effect_immediately(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    vault.grant(meta.id, Principal.bot(BOT_A), Permission.USE)
    assert vault.resolve_for_use(meta.ref, Principal.bot(BOT_A)).value() == CANARY
    vault.revoke(meta.id, Principal.bot(BOT_A), Permission.USE)
    with pytest.raises(AccessDenied):
        vault.resolve_for_use(meta.ref, Principal.bot(BOT_A))
    reasons = [e.reason for e in vault.audit_log() if e.outcome == "denied"]
    assert "no_grant" in reasons


def test_only_the_owner_may_change_grants(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    with pytest.raises(AccessDenied):
        vault.grant(meta.id, Principal.bot(BOT_A), Permission.USE, actor=Principal.bot(BOT_A))
    with pytest.raises(AccessDenied):
        vault.revoke(meta.id, Principal.bot(BOT_A), Permission.USE, actor=Principal.bot(BOT_A))


def test_owner_only_permissions_cannot_be_delegated(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    for permission in (Permission.ROTATE, Permission.DELETE):
        with pytest.raises(Exception):
            vault.grant(meta.id, Principal.bot(BOT_A), permission)


def test_grants_are_listed_with_their_principal(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    vault.grant(meta.id, Principal.bot(BOT_A), Permission.USE)
    vault.grant(meta.id, Principal.bot(BOT_A), Permission.METADATA)
    grants = vault.grants(meta.id)
    assert {g.permission for g in grants} == {"use", "metadata"}
    assert {g.principal.label for g in grants} == {f"bot:{BOT_A}"}


def test_granting_the_same_permission_twice_is_idempotent(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    vault.grant(meta.id, Principal.bot(BOT_A), Permission.USE)
    vault.grant(meta.id, Principal.bot(BOT_A), Permission.USE)
    assert len(vault.grants(meta.id)) == 1


def test_a_deleted_secret_cannot_be_granted_or_used(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    vault.delete_secret(meta.id)
    with pytest.raises(Exception):
        vault.grant(meta.id, Principal.bot(BOT_A), Permission.USE)
    with pytest.raises(Exception):
        vault.resolve_for_use(meta.ref, Principal.bot(BOT_A))


def test_owner_always_has_access(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    assert vault.reveal(meta.ref, Principal.owner()).value() == CANARY
    assert vault.resolve_for_use(meta.ref, Principal.owner()).value() == CANARY


def test_audit_records_who_used_what_and_for_which_destination(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    vault.grant(meta.id, Principal.bot(BOT_A), Permission.USE)
    vault.resolve_for_use(meta.ref, Principal.bot(BOT_A), destination="api.notion.com")
    entry = next(e for e in vault.audit_log() if e.action == "use")
    assert entry.actor == f"bot:{BOT_A}"
    assert entry.secret_id == meta.id
    assert entry.scope == "workspace"
    assert entry.outcome == "ok"
    assert entry.destination == "api.notion.com"
    assert CANARY not in entry.destination


def test_a_bogus_destination_is_dropped_not_stored(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    vault.grant(meta.id, Principal.bot(BOT_A), Permission.USE)
    vault.resolve_for_use(meta.ref, Principal.bot(BOT_A),
                          destination="api.notion.com/../evil?token=abc")
    entry = next(e for e in vault.audit_log() if e.action == "use")
    assert entry.destination == ""


def test_reveal_and_use_are_recorded_as_different_actions(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    vault.resolve_for_use(meta.ref, Principal.owner())
    vault.reveal(meta.ref, Principal.owner())
    actions = [e.action for e in vault.audit_log()]
    assert "use" in actions and "reveal" in actions
