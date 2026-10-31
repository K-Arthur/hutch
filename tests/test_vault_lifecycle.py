"""Vault lifecycle against a real Store, real SQLite and real cryptography.

No fake repository, no mocked cipher and no simulated persistence: each test opens the same
``Store`` the application uses, runs the real migration, and asserts on rows read back from disk.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from hutch.config import hutchConfig
from hutch.store import SCHEMA_VERSION, Store
from hutch.vault import crypto
from hutch.vault.refs import Principal
from hutch.vault.vault import (
    VaultAlreadyExists,
    VaultBook,
    VaultCorrupt,
    VaultLocked,
    VaultNotInitialized,
    VaultThrottled,
    VaultUnlockError,
)
from tests.support.vault_fixtures import CANARY, DESTINATION, PASSPHRASE, make_vault, unlocked


def test_fresh_database_has_no_vault(store):
    vault = make_vault(store)
    status = vault.status()
    assert status.initialized is False
    assert status.unlocked is False
    assert status.secret_count == 0
    with pytest.raises(VaultNotInitialized):
        vault.put_secret(scope="workspace", category="api_key", name="x", value="value")


def test_create_unlocks_and_returns_a_recovery_key_once(store):
    vault = make_vault(store)
    creation = vault.create(PASSPHRASE)

    assert creation.status.initialized is True
    assert creation.status.unlocked is True
    assert creation.status.recovery_configured is True
    assert creation.status.secret_count == 0
    assert len(creation.recovery_key.replace("-", "")) == crypto.RECOVERY_TOTAL_CHARS

    # The recovery key is not persisted anywhere Hutch owns.
    for path in store.config.state_dir.rglob("*"):
        if path.is_file():
            raw = path.read_bytes()
            assert creation.recovery_key.encode() not in raw
            assert creation.recovery_key.replace("-", "").encode() not in raw

    assert [entry.action for entry in vault.audit_log()] == ["create"]


def test_vault_is_never_reinitialised_over_existing_data(store):
    vault = unlocked(store)
    vault.put_secret(scope="workspace", category="api_key", name="keep", value="v1")
    with pytest.raises(VaultAlreadyExists):
        vault.create("another-long-enough-passphrase")
    assert len(vault.list_secrets()) == 1


def test_weak_passphrase_is_refused_before_anything_is_written(store):
    vault = make_vault(store)
    with pytest.raises(Exception) as excinfo:
        vault.create("short")
    assert "12" in str(excinfo.value)
    assert vault.status().initialized is False
    assert store._db.execute("SELECT COUNT(*) FROM vault_meta").fetchone()[0] == 0


def test_locked_vault_refuses_value_operations(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    vault.bind_destination(meta.id, DESTINATION)
    vault.lock()

    assert vault.status().unlocked is False
    with pytest.raises(VaultLocked):
        vault.put_secret(scope="workspace", category="api_key", name="other", value="value")
    with pytest.raises(VaultLocked):
        vault.reveal(meta.ref, Principal.owner())
    with pytest.raises(VaultLocked):
        vault.resolve_for_use(meta.ref, Principal.owner(), destination=DESTINATION)
    # Metadata remains readable while locked.
    assert vault.get_metadata(meta.id).name == "notion"


def test_unlock_with_the_wrong_passphrase_fails_and_is_recorded(store):
    vault = unlocked(store)
    vault.lock()
    with pytest.raises(VaultUnlockError):
        vault.unlock("a-different-long-passphrase")
    assert vault.status().unlocked is False
    denied = [e for e in vault.audit_log() if e.outcome == "denied"]
    assert denied and denied[0].reason == "wrong_passphrase"

    vault.unlock(PASSPHRASE)
    assert vault.status().unlocked is True


def test_unlock_with_the_recovery_key(store):
    vault = make_vault(store)
    creation = vault.create(PASSPHRASE)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    vault.lock()

    vault.unlock_with_recovery_key(creation.recovery_key)
    assert vault.reveal(meta.ref, Principal.owner()).value() == CANARY


def test_unlock_with_a_wrong_recovery_key_is_refused(store):
    vault = make_vault(store)
    vault.create(PASSPHRASE)
    vault.lock()
    _, other_payload = crypto.generate_recovery_key()
    with pytest.raises(VaultUnlockError):
        vault.unlock_with_recovery_key(crypto.format_recovery_key(other_payload))
    assert vault.status().unlocked is False


def test_passphrase_change_rewraps_and_keeps_existing_secrets(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    before = store._db.execute("SELECT ciphertext FROM vault_secret_versions WHERE secret_id = ?",
                               (meta.id,)).fetchone()[0]

    vault.change_passphrase("a-completely-different-passphrase")
    after = store._db.execute("SELECT ciphertext FROM vault_secret_versions WHERE secret_id = ?",
                              (meta.id,)).fetchone()[0]
    assert after == before, "a passphrase change must not rewrite secret ciphertext"
    assert vault.status().key_version == 2

    vault.lock()
    with pytest.raises(VaultUnlockError):
        vault.unlock(PASSPHRASE)
    vault.unlock("a-completely-different-passphrase")
    assert vault.reveal(meta.ref, Principal.owner()).value() == CANARY


def test_passphrase_change_rewraps_at_the_production_cost(store):
    """A vault created cheaply must not inherit that cost after a passphrase change."""
    vault = unlocked(store)
    vault.change_passphrase("a-completely-different-passphrase")
    row = store._db.execute(
        "SELECT params FROM vault_key_wraps WHERE kind='passphrase' AND retired_at=''").fetchone()
    params = json.loads(row[0])
    assert params["n"] == crypto.DEFAULT_SCRYPT.n
    assert params["r"] == crypto.DEFAULT_SCRYPT.r
    assert params["p"] == crypto.DEFAULT_SCRYPT.p


def test_rotating_the_recovery_key_invalidates_the_old_one(store):
    vault = make_vault(store)
    creation = vault.create(PASSPHRASE)
    replacement = vault.rotate_recovery_key()
    assert replacement != creation.recovery_key
    vault.lock()
    with pytest.raises(VaultUnlockError):
        vault.unlock_with_recovery_key(creation.recovery_key)
    vault.unlock_with_recovery_key(replacement)
    assert vault.status().unlocked is True


def test_vault_survives_a_restart_and_comes_back_locked(store, config):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    store.close()

    reopened = Store(hutchConfig(state_dir=config.state_dir))
    try:
        revived = VaultBook(reopened)
        assert revived.status().initialized is True
        assert revived.status().unlocked is False
        with pytest.raises(VaultLocked):
            revived.reveal(meta.ref, Principal.owner())
        revived.unlock(PASSPHRASE)
        assert revived.reveal(meta.ref, Principal.owner()).value() == CANARY
    finally:
        reopened.close()


def test_unlock_attempts_are_throttled_after_repeated_failures(store):
    clock = {"now": datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)}
    vault = make_vault(store, clock=lambda: clock["now"])
    vault.create(PASSPHRASE)
    vault.lock()

    for _ in range(3):
        with pytest.raises(VaultUnlockError):
            vault.unlock("definitely-not-the-passphrase")
    # The fourth failure starts a delay; the next attempt is refused without touching the KDF.
    with pytest.raises(VaultUnlockError):
        vault.unlock("definitely-not-the-passphrase")
    with pytest.raises(VaultThrottled) as excinfo:
        vault.unlock(PASSPHRASE)
    assert excinfo.value.retry_after_seconds >= 1

    clock["now"] += timedelta(seconds=5)
    vault.unlock(PASSPHRASE)
    assert vault.status().unlocked is True


def test_failed_unlock_does_not_change_stored_key_material(store):
    vault = unlocked(store)
    before = store._db.execute("SELECT nonce, wrapped_dek FROM vault_key_wraps ORDER BY version, kind").fetchall()
    vault.lock()
    with pytest.raises(VaultUnlockError):
        vault.unlock("wrong-passphrase-here")
    after = store._db.execute("SELECT nonce, wrapped_dek FROM vault_key_wraps ORDER BY version, kind").fetchall()
    assert [tuple(row) for row in before] == [tuple(row) for row in after]


def test_missing_recovery_wrap_does_not_break_the_passphrase_path(store):
    vault = unlocked(store)
    vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    with store._lock:
        store._db.execute("DELETE FROM vault_key_wraps WHERE kind = 'recovery'")
        store._db.commit()
    meta = vault.list_secrets()[0]
    assert vault.status().recovery_configured is False
    vault.lock()
    vault.unlock(PASSPHRASE)
    assert vault.reveal(meta.ref, Principal.owner()).value() == CANARY


def test_missing_passphrase_wrap_is_corruption_not_a_fallback(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    with store._lock:
        store._db.execute("DELETE FROM vault_key_wraps WHERE kind = 'passphrase'")
        store._db.commit()
    vault.lock()
    with pytest.raises(VaultCorrupt):
        vault.unlock(PASSPHRASE)
    assert vault.status().unlocked is False
    with pytest.raises(VaultLocked):
        vault.reveal(meta.ref, Principal.owner())


def test_a_legacy_installation_gains_a_working_vault_after_upgrade(tmp_path):
    """The v4 fixture was written by baseline code. After the full upgrade it must accept a vault."""
    import shutil
    from pathlib import Path

    fixture = Path(__file__).parent / "fixtures" / "state_v4.db.fixture"
    state = tmp_path / "state"
    state.mkdir()
    shutil.copy(fixture, state / "hutch.db")

    store = Store(hutchConfig(state_dir=state))
    try:
        assert store.schema_version == SCHEMA_VERSION
        assert store._db.execute("SELECT COUNT(*) FROM vault_meta").fetchone()[0] == 0
        bots_before = store._db.execute("SELECT COUNT(*) FROM bots").fetchone()[0]
        assert bots_before == 2, "the migration must not touch existing rows"

        vault = VaultBook(store, scrypt_params=crypto.ScryptParams.for_tests())
        assert vault.status().initialized is False
        creation = vault.create(PASSPHRASE)
        assert creation.status.initialized is True
        meta = vault.put_secret(scope="workspace", category="api_key", name="after-upgrade",
                                value=CANARY)
        assert vault.reveal(meta.ref, Principal.owner()).value() == CANARY
        assert store._db.execute("SELECT COUNT(*) FROM bots").fetchone()[0] == bots_before
    finally:
        store.close()
