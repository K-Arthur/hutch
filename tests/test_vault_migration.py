"""Destinations reach a database that already had a vault.

The first version of this table lived inside ``vault.migrate``. That migration runs once, so an
installation already at that schema version would have kept working until the first bind, then
failed. This module proves the ordered migration that fixes it: a real database is put back to the
previous version, reopened, and required to accept a binding.
"""

from __future__ import annotations

import sqlite3

import pytest

from hutch.store import SCHEMA_VERSION, Store
from hutch.vault import Principal, vault_for
from hutch.vault.crypto import ScryptParams
from hutch.vault.refs import Permission
from tests.support.vault_fixtures import BOT_A, CANARY, DESTINATION


def test_a_database_created_before_the_table_gains_it_on_reopen(store, config):
    vault = vault_for(store, scrypt_params=ScryptParams.for_tests())
    vault.create("a-long-enough-vault-passphrase")
    meta = vault.put_secret(scope="workspace", category="api_key", name="api", value=CANARY)

    # Put the database back exactly where an installation of the previous build would be: the old
    # schema version and no destinations table.
    with store._lock:
        store._db.execute("DROP TABLE vault_destinations")
        store._db.execute(f"PRAGMA user_version = {SCHEMA_VERSION - 1}")
        store._db.commit()
    store.close()

    reopened = Store(config)
    try:
        tables = {row[0] for row in reopened._db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
        assert "vault_destinations" in tables
        assert reopened._db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION

        book = vault_for(reopened, scrypt_params=ScryptParams.for_tests())
        book.unlock("a-long-enough-vault-passphrase")
        book.grant(meta.id, Principal.bot(BOT_A), Permission.USE)
        assert book.bind_destination(meta.id, DESTINATION) == DESTINATION
        assert book.resolve_for_use(meta.ref, Principal.bot(BOT_A),
                                    destination=DESTINATION).value() == CANARY
    finally:
        reopened.close()


def test_the_migration_is_idempotent(store):
    from hutch.vault.schema import migrate_destinations
    with store._lock:
        migrate_destinations(store._db)
        migrate_destinations(store._db)
        columns = [row[1] for row in store._db.execute("PRAGMA table_info(vault_destinations)")]
    assert columns == ["secret_id", "origin", "created_at"]


def test_the_table_refuses_a_malformed_origin_at_the_storage_layer(store):
    vault = vault_for(store, scrypt_params=ScryptParams.for_tests())
    vault.create("a-long-enough-vault-passphrase")
    meta = vault.put_secret(scope="workspace", category="api_key", name="api", value=CANARY)
    with pytest.raises(sqlite3.IntegrityError):
        with store._lock:
            store._db.execute("INSERT INTO vault_destinations(secret_id, origin, created_at) "
                              "VALUES (?, ?, '2026-10-31T00:00:00+00:00')", (meta.id, "x"))
            store._db.commit()
    store._db.rollback()


def test_a_deleted_secret_takes_its_destinations_with_it(store):
    vault = vault_for(store, scrypt_params=ScryptParams.for_tests())
    vault.create("a-long-enough-vault-passphrase")
    meta = vault.put_secret(scope="workspace", category="api_key", name="api", value=CANARY)
    vault.bind_destination(meta.id, DESTINATION)
    vault.delete_secret(meta.id, hard=True)
    with store._lock:
        remaining = store._db.execute(
            "SELECT COUNT(*) FROM vault_destinations WHERE secret_id = ?", (meta.id,)).fetchone()[0]
    assert remaining == 0
