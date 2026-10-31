"""Secret storage behaviour: Versions, names, deletion and the metadata/value boundary."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from hutch.vault.refs import Principal, SecretRef
from hutch.vault.vault import SecretConflict, SecretNotFound
from tests.support.vault_fixtures import BOT_A, CANARY, unlocked


def test_secret_metadata_never_contains_the_value(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="Notion API",
                            value=CANARY, description="workspace integration")
    listed = vault.list_secrets()
    assert [item.id for item in listed] == [meta.id]
    rendered = repr(meta) + repr(listed) + meta.ref + meta.name + meta.description
    assert CANARY not in rendered
    assert SecretRef.parse(meta.ref).secret_id == meta.id


def test_duplicate_live_names_conflict(store):
    vault = unlocked(store)
    vault.put_secret(scope="workspace", category="api_key", name="notion", value="a")
    with pytest.raises(SecretConflict):
        vault.put_secret(scope="workspace", category="api_key", name="notion", value="b")
    # A different scope may reuse the name.
    vault.put_secret(scope=f"bot:{BOT_A}", category="api_key", name="notion", value="c")


def test_update_creates_a_new_version_and_keeps_old_versions_readable(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value="first-value")
    updated = vault.update_secret(meta.id, "second-value", description="rotated")
    assert updated.current_version == 2
    assert updated.description == "rotated"
    assert vault.reveal(SecretRef.local_ref(meta.id), Principal.owner()).value() == "second-value"
    assert vault.reveal(SecretRef.local_ref(meta.id, version=1), Principal.owner()).value() == "first-value"


def test_stale_update_cannot_overwrite_a_newer_version(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value="first")
    vault.update_secret(meta.id, "second")
    row = store._db.execute("SELECT current_version FROM vault_secrets WHERE id = ?", (meta.id,)).fetchone()
    assert row[0] == 2
    # The newest value is the one the AAD for version 2 protects.
    assert vault.reveal(meta.ref, Principal.owner()).value() == "second"


def test_soft_delete_hides_the_secret_then_restore_brings_it_back(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    vault.delete_secret(meta.id)

    assert vault.list_secrets() == []
    assert [item.id for item in vault.list_secrets(include_deleted=True)] == [meta.id]
    with pytest.raises(SecretNotFound):
        vault.reveal(meta.ref, Principal.owner())

    vault.restore_secret(meta.id)
    assert vault.reveal(meta.ref, Principal.owner()).value() == CANARY


def test_hard_delete_removes_versions_and_grants(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    vault.grant(meta.id, Principal.bot(BOT_A), "use")
    vault.delete_secret(meta.id, hard=True)

    assert store._db.execute("SELECT COUNT(*) FROM vault_secret_versions WHERE secret_id = ?",
                             (meta.id,)).fetchone()[0] == 0
    assert store._db.execute("SELECT COUNT(*) FROM vault_grants WHERE secret_id = ?",
                             (meta.id,)).fetchone()[0] == 0
    # The audit history outlives the secret on purpose.
    assert any(entry.secret_id == meta.id and entry.action == "delete_secret" for entry in vault.audit_log())
    with pytest.raises(SecretNotFound):
        vault.get_metadata(meta.id)


def test_expiry_is_validated_and_stored(store):
    vault = unlocked(store)
    when = (datetime.now(timezone.utc) + timedelta(days=30)).replace(microsecond=0)
    meta = vault.put_secret(scope="workspace", category="api_key", name="soon", value="v",
                            expires_at=when.isoformat())
    assert meta.expires_at == when.isoformat()
    with pytest.raises(Exception):
        vault.put_secret(scope="workspace", category="api_key", name="bad", value="v",
                         expires_at="next tuesday")
    with pytest.raises(Exception):
        vault.put_secret(scope="workspace", category="api_key", name="naive", value="v",
                         expires_at="2030-01-01T00:00:00")


def test_category_size_bound_is_enforced(store):
    vault = unlocked(store)
    with pytest.raises(Exception) as excinfo:
        vault.put_secret(scope="workspace", category="webhook_signing_secret", name="big",
                         value="x" * 5000)
    assert "4096" in str(excinfo.value)
    with pytest.raises(Exception):
        vault.put_secret(scope="workspace", category="api_key", name="nul", value="a\x00b")
    with pytest.raises(Exception):
        vault.put_secret(scope="workspace", category="api_key", name="empty", value="")


def test_listing_can_be_scoped_and_ordered(store):
    vault = unlocked(store)
    workspace = vault.put_secret(scope="workspace", category="api_key", name="a", value="1")
    private = vault.put_secret(scope=f"bot:{BOT_A}", category="api_key", name="b", value="2")
    assert [m.id for m in vault.list_secrets(scope="workspace")] == [workspace.id]
    assert [m.id for m in vault.list_secrets(scope=f"bot:{BOT_A}")] == [private.id]
    assert len(vault.list_secrets()) == 2


def test_metadata_reports_the_reference_and_version(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="n", value="v")
    assert meta.current_version == 1
    assert meta.ref == f"secret://hutch/local/{meta.id}"
    assert meta.deleted is False
    assert meta.created_at.endswith("+00:00")
