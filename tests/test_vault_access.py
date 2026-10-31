"""Grants and the use/reveal boundary: who may do what, and what the audit records."""

from __future__ import annotations

import pytest

from hutch.vault.refs import Permission, Principal
from hutch.vault.destinations import DestinationError
from hutch.vault.vault import AccessDenied
from tests.support.vault_fixtures import BOT_A, BOT_B, CANARY, DESTINATION, unlocked


def test_bot_without_a_grant_is_refused_and_recorded(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    with pytest.raises(AccessDenied):
        vault.resolve_for_use(meta.ref, Principal.bot(BOT_A), destination=DESTINATION)
    denied = [e for e in vault.audit_log() if e.outcome == "denied"]
    assert denied and denied[0].reason == "no_grant"
    assert denied[0].actor == f"bot:{BOT_A}"


def test_granted_bot_may_use_but_not_reveal(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    vault.grant(meta.id, Principal.bot(BOT_A), Permission.USE)
    vault.bind_destination(meta.id, DESTINATION)

    usable = vault.resolve_for_use(meta.ref, Principal.bot(BOT_A), destination=DESTINATION)
    assert usable.value() == CANARY
    assert CANARY not in repr(usable) and CANARY not in str(usable)
    assert usable.destination == DESTINATION

    with pytest.raises(AccessDenied):
        vault.reveal(meta.ref, Principal.bot(BOT_A))


def test_reveal_grant_is_separate_from_use(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    vault.grant(meta.id, Principal.bot(BOT_A), Permission.REVEAL)
    vault.bind_destination(meta.id, DESTINATION)
    with pytest.raises(AccessDenied):
        vault.resolve_for_use(meta.ref, Principal.bot(BOT_A), destination=DESTINATION)
    assert vault.reveal(meta.ref, Principal.bot(BOT_A)).value() == CANARY


def test_a_bot_cannot_reach_another_bots_secret_even_with_a_grant(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope=f"bot:{BOT_A}", category="api_key", name="private", value=CANARY)
    with pytest.raises(AccessDenied):
        vault.grant(meta.id, Principal.bot(BOT_B), Permission.USE)
    with pytest.raises(AccessDenied):
        vault.resolve_for_use(meta.ref, Principal.bot(BOT_B), destination=DESTINATION)
    vault.grant(meta.id, Principal.bot(BOT_A), Permission.USE)
    vault.bind_destination(meta.id, DESTINATION)
    assert vault.resolve_for_use(meta.ref, Principal.bot(BOT_A), destination=DESTINATION).value() == CANARY


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
    vault.bind_destination(meta.id, DESTINATION)
    assert vault.resolve_for_use(meta.ref, Principal.bot(BOT_A), destination=DESTINATION).value() == CANARY
    vault.revoke(meta.id, Principal.bot(BOT_A), Permission.USE)
    with pytest.raises(AccessDenied):
        vault.resolve_for_use(meta.ref, Principal.bot(BOT_A), destination=DESTINATION)
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
        vault.resolve_for_use(meta.ref, Principal.bot(BOT_A), destination=DESTINATION)


def test_owner_always_has_access(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    assert vault.reveal(meta.ref, Principal.owner()).value() == CANARY
    vault.bind_destination(meta.id, DESTINATION)
    assert vault.resolve_for_use(meta.ref, Principal.owner(), destination=DESTINATION).value() == CANARY


def test_audit_records_who_used_what_and_for_which_destination(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    vault.grant(meta.id, Principal.bot(BOT_A), Permission.USE)
    vault.bind_destination(meta.id, DESTINATION)
    vault.resolve_for_use(meta.ref, Principal.bot(BOT_A), destination=DESTINATION)
    entry = next(e for e in vault.audit_log() if e.action == "use")
    assert entry.actor == f"bot:{BOT_A}"
    assert entry.secret_id == meta.id
    assert entry.scope == "workspace"
    assert entry.outcome == "ok"
    assert entry.destination == DESTINATION
    assert CANARY not in entry.destination


def test_a_url_that_is_not_an_origin_is_refused_not_normalised(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    vault.grant(meta.id, Principal.bot(BOT_A), Permission.USE)
    for bad in ("api.notion.com", "https://api.notion.com/../evil?token=abc",
                "https://api.notion.com/v1/pages", "https://user:pw@api.notion.com"):
        with pytest.raises(DestinationError):
            vault.resolve_for_use(meta.ref, Principal.bot(BOT_A), destination=bad)


def test_reveal_and_use_are_recorded_as_different_actions(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    vault.bind_destination(meta.id, DESTINATION)
    vault.resolve_for_use(meta.ref, Principal.owner(), destination=DESTINATION)
    vault.reveal(meta.ref, Principal.owner())
    actions = [e.action for e in vault.audit_log()]
    assert "use" in actions and "reveal" in actions


def test_use_without_a_destination_binding_is_denied_and_recorded(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    vault.grant(meta.id, Principal.bot(BOT_A), Permission.USE)
    with pytest.raises(AccessDenied):
        vault.resolve_for_use(meta.ref, Principal.bot(BOT_A), destination=DESTINATION)
    denied = [e for e in vault.audit_log() if e.outcome == "denied"]
    assert denied and denied[0].reason == "no_destination"
    assert denied[0].destination == DESTINATION


def test_a_binding_for_one_secret_does_not_authorize_another(store):
    vault = unlocked(store)
    first = vault.put_secret(scope="workspace", category="api_key", name="one", value="first")
    second = vault.put_secret(scope="workspace", category="api_key", name="two", value="second")
    for meta in (first, second):
        vault.grant(meta.id, Principal.bot(BOT_A), Permission.USE)
    vault.bind_destination(first.id, DESTINATION)
    assert vault.destinations(first.id) == [DESTINATION]
    assert vault.destinations(second.id) == []
    with pytest.raises(AccessDenied):
        vault.resolve_for_use(second.ref, Principal.bot(BOT_A), destination=DESTINATION)


def test_unbinding_takes_effect_immediately(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    vault.grant(meta.id, Principal.bot(BOT_A), Permission.USE)
    vault.bind_destination(meta.id, DESTINATION)
    assert vault.resolve_for_use(meta.ref, Principal.bot(BOT_A), destination=DESTINATION).value() == CANARY
    vault.unbind_destination(meta.id, DESTINATION)
    with pytest.raises(AccessDenied):
        vault.resolve_for_use(meta.ref, Principal.bot(BOT_A), destination=DESTINATION)


def test_only_the_owner_can_bind_or_unbind_a_destination(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    with pytest.raises(Exception):
        vault.bind_destination(meta.id, DESTINATION, actor=Principal.bot(BOT_A))
    vault.bind_destination(meta.id, DESTINATION)
    with pytest.raises(Exception):
        vault.unbind_destination(meta.id, DESTINATION, actor=Principal.bot(BOT_A))


def test_binding_is_idempotent_and_canonical(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    assert vault.bind_destination(meta.id, "HTTPS://API.NOTION.COM:443/") == DESTINATION
    assert vault.bind_destination(meta.id, DESTINATION) == DESTINATION
    assert vault.destinations(meta.id) == [DESTINATION]


def test_a_binding_to_a_different_origin_does_not_match(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    vault.grant(meta.id, Principal.bot(BOT_A), Permission.USE)
    vault.bind_destination(meta.id, DESTINATION)
    for other in ("https://evil.example", "http://api.notion.com", "https://api.notion.com:8443"):
        with pytest.raises(AccessDenied):
            vault.resolve_for_use(meta.ref, Principal.bot(BOT_A), destination=other)
