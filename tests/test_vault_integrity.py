"""Integrity: at-rest exposure, tampering, audit immutability and log leakage.

These are the tests that would catch a regression turning the vault into decoration.
"""

from __future__ import annotations

import logging
import sqlite3

import pytest

from hutch.vault.refs import Principal
from hutch.vault.vault import AccessDenied, VaultCorrupt
from tests.support.vault_fixtures import BOT_A, BOT_B, CANARY, unlocked


def test_ciphertext_is_absent_from_the_database_files(store):
    vault = unlocked(store)
    vault.put_secret(scope="workspace", category="api_key", name="canary", value=CANARY)
    with store._lock:
        store._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    files = list(store.config.state_dir.glob("hutch.db*"))
    assert files, "expected database files to exist"
    for path in files:
        assert CANARY.encode() not in path.read_bytes(), f"plaintext found in {path.name}"


def test_a_tampered_ciphertext_is_refused_not_guessed(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    with store._lock:
        row = store._db.execute("SELECT ciphertext FROM vault_secret_versions WHERE secret_id = ?",
                                (meta.id,)).fetchone()
        broken = bytearray(row[0])
        broken[-1] ^= 0x01
        store._db.execute("UPDATE vault_secret_versions SET ciphertext = ? WHERE secret_id = ?",
                          (bytes(broken), meta.id))
        store._db.commit()
    with pytest.raises(VaultCorrupt):
        vault.reveal(meta.ref, Principal.owner())
    assert any(e.reason == "corrupt" for e in vault.audit_log())


def test_ciphertext_cannot_be_moved_between_secrets(store):
    vault = unlocked(store)
    first = vault.put_secret(scope="workspace", category="api_key", name="one", value="value-one")
    second = vault.put_secret(scope="workspace", category="api_key", name="two", value="value-two")
    with store._lock:
        stolen = store._db.execute("SELECT nonce, ciphertext FROM vault_secret_versions WHERE secret_id = ?",
                                   (first.id,)).fetchone()
        store._db.execute("UPDATE vault_secret_versions SET nonce = ?, ciphertext = ? WHERE secret_id = ?",
                          (stolen[0], stolen[1], second.id))
        store._db.commit()
    with pytest.raises(VaultCorrupt):
        vault.reveal(second.ref, Principal.owner())


def test_a_version_cannot_be_replayed_under_a_newer_number(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value="first")
    vault.update_secret(meta.id, "second")
    with store._lock:
        old = store._db.execute(
            "SELECT nonce, ciphertext FROM vault_secret_versions WHERE secret_id = ? AND version = 1",
            (meta.id,)).fetchone()
        store._db.execute("UPDATE vault_secret_versions SET nonce = ?, ciphertext = ? "
                          "WHERE secret_id = ? AND version = 2",
                          (old[0], old[1], meta.id))
        store._db.commit()
    with pytest.raises(VaultCorrupt):
        vault.reveal(meta.ref, Principal.owner())


def test_audit_rows_cannot_be_rewritten_or_deleted(store):
    unlocked(store)
    with pytest.raises(sqlite3.IntegrityError):
        with store._lock:
            store._db.execute("UPDATE vault_audit SET outcome = 'ok' WHERE id = 1")
    with pytest.raises(sqlite3.IntegrityError):
        with store._lock:
            store._db.execute("DELETE FROM vault_audit WHERE id = 1")
    store._db.rollback()


def test_audit_rejects_free_text_that_could_carry_a_value(store):
    vault = unlocked(store)
    with pytest.raises(Exception):
        vault._audit(Principal.owner(), "use", "ok", reason=CANARY)


def test_values_never_reach_the_log(caplog, store):
    caplog.set_level(logging.DEBUG)
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    vault.grant(meta.id, Principal.bot(BOT_A), "use")
    vault.resolve_for_use(meta.ref, Principal.bot(BOT_A))
    vault.reveal(meta.ref, Principal.owner())
    vault.lock()
    with pytest.raises(Exception):
        vault.unlock("wrong-passphrase-here")
    assert CANARY not in caplog.text


def test_values_never_reach_the_event_or_run_tables(store):
    vault = unlocked(store)
    vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    for table in ("events", "runs", "messages", "vault_audit", "vault_secrets"):
        rows = store._db.execute(f"SELECT * FROM {table}").fetchall()
        for row in rows:
            assert CANARY not in repr(tuple(row)), f"plaintext found in {table}"


def test_scope_cannot_be_smuggled_through_a_reference(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope=f"bot:{BOT_A}", category="api_key", name="private", value=CANARY)
    # The reference carries no scope; the row decides it. Another bot naming the id gets nothing.
    with pytest.raises(AccessDenied):
        vault.resolve_for_use(meta.ref, Principal.bot(BOT_B))
    forged = f"secret://hutch/local/{meta.id}"
    with pytest.raises(AccessDenied):
        vault.resolve_for_use(forged, Principal.bot(BOT_B))
    assert any(e.reason == "wrong_scope" for e in vault.audit_log() if e.outcome == "denied")


def test_a_stored_value_is_never_returned_without_an_explicit_call(store):
    """The API surface must not grow a ``value`` field on metadata."""
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="notion", value=CANARY)
    assert "value" not in {field for field in vars(meta)}
    assert not hasattr(meta, "value")
