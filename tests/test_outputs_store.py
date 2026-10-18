"""Schema v55 (uploads, media_jobs, workspace_sessions) and its Store accessors.

Other lanes consume these accessors instead of touching store.py, so the guards
(idempotency, transitions, generations) are pinned here.
"""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from hutch.store import (SCHEMA_VERSION, IdempotencyConflict, RevisionConflict, Store,
                         UploadLimitExceeded,
                         _ensure_output_tables)
from tests.test_delegation import _remove_later_conversation_schema

V51_TABLES = ("uploads", "media_jobs", "workspace_sessions")


# ------------------------------------------------------------------- migration


def test_outputs_migration_precedes_the_additive_grounding_migration():
    assert SCHEMA_VERSION == 56


def test_output_table_installer_is_idempotent_and_check_constrained():
    db = sqlite3.connect(":memory:")
    try:
        _ensure_output_tables(db)
        _ensure_output_tables(db)
        tables = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('uploads','media_jobs','workspace_sessions')")}
        assert tables == set(V51_TABLES)
        db.execute("INSERT INTO uploads VALUES ('u1', 'c1', 'f.txt', 'text/plain', 3, ?, 'ready', 'now')", ("a" * 64,))
        with pytest.raises(sqlite3.IntegrityError, match="state"):
            db.execute("INSERT INTO uploads VALUES ('u2', 'c1', 'f.txt', 'text/plain', 3, ?, 'bogus', 'now')", ("a" * 64,))
        with pytest.raises(sqlite3.IntegrityError, match="byte_size"):
            db.execute("INSERT INTO uploads VALUES ('u3', 'c1', 'f.txt', 'text/plain', -1, ?, 'ready', 'now')", ("a" * 64,))
        with pytest.raises(sqlite3.IntegrityError, match="status"):
            db.execute("INSERT INTO media_jobs VALUES ('m1', 'r1', 'c1', 'image', 'local', 'bogus', 'k1', NULL, '{}', NULL, NULL, NULL, 'now', 'now')")
        db.execute("INSERT INTO media_jobs VALUES ('m0', 'r1', 'c1', 'image', 'local', 'queued', 'k0', NULL, '{}', NULL, NULL, NULL, 'now', 'now')")
        with pytest.raises(sqlite3.IntegrityError, match="idempotency_key"):
            db.execute("INSERT INTO media_jobs VALUES ('m2', 'r1', 'c1', 'image', 'local', 'queued', 'k0', NULL, '{}', NULL, NULL, NULL, 'now', 'now')")
        with pytest.raises(sqlite3.IntegrityError, match="generation"):
            db.execute("INSERT INTO workspace_sessions VALUES ('c1', 0, 'active', NULL, '/tmp/ws', 'now', 'now')")
    finally:
        db.close()


def test_the_downgrade_helper_knows_v55_and_reopening_recreates_the_tables(store, config):
    """The v55 tables must be droppable by the simulated-legacy helper (the way
    c9dd168 taught it the v50 document tables) and recreated by the upgrade."""
    store.add_upload("conv-1", "notes.txt", "text/plain", 4, "b" * 64)
    store.create_media_job(run_id="run-x", conversation_id="conv-1", kind="image", backend="local",
                           idempotency_key="v55-downgrade", requested={"prompt": "lighthouse"})
    store.upsert_workspace_session("conv-1", 1, "/tmp/ws")
    store.close()

    db = sqlite3.connect(config.db_path)
    _remove_later_conversation_schema(db)
    db.execute("PRAGMA user_version = 50")
    db.commit()
    db.close()

    upgraded = Store(config)
    try:
        assert upgraded.schema_version == SCHEMA_VERSION == 56
        for table in V51_TABLES:
            assert upgraded._db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        # the recreated tables work through their accessors
        up = upgraded.add_upload("conv-2", "post.md", "text/markdown", 9, "c" * 64)
        assert upgraded.get_upload(up["id"])["filename"] == "post.md"
    finally:
        upgraded.close()


def test_historical_output_v51_shape_upgrades_without_losing_uploads(store, config):
    upload = store.add_upload("conv-history", "history.csv", "text/csv", 7, "d" * 64)
    store.close()

    db = sqlite3.connect(config.db_path)
    _remove_later_conversation_schema(db)
    _ensure_output_tables(db)
    db.execute(
        "INSERT INTO uploads VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (upload["id"], "conv-history", "history.csv", "text/csv", 7, "d" * 64, "ready", upload["created_at"]))
    db.execute("PRAGMA user_version = 51")
    db.commit()
    db.close()

    upgraded = Store(config)
    try:
        assert upgraded.schema_version == SCHEMA_VERSION == 56
        assert upgraded.get_upload(upload["id"])["filename"] == "history.csv"
        assert {row[0] for row in upgraded._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")} >= set(V51_TABLES)
    finally:
        upgraded.close()


def test_v54_to_current_preserves_existing_rows(store, config):
    upload = store.add_upload("conv-v54", "history.csv", "text/csv", 7, "e" * 64)
    store.close()
    db = sqlite3.connect(config.db_path)
    db.execute("PRAGMA user_version = 54")
    db.commit()
    db.close()

    upgraded = Store(config)
    try:
        assert upgraded.schema_version == SCHEMA_VERSION == 56
        assert upgraded.get_upload(upload["id"])["sha256"] == "e" * 64
    finally:
        upgraded.close()


def test_concurrent_upload_registrations_cannot_exceed_conversation_quota(store):
    for index in range(199):
        store.add_upload("quota", f"{index}.csv", "text/csv", 1, f"{index:064x}")

    def add(index):
        try:
            store.add_upload("quota", f"last-{index}.csv", "text/csv", 1, f"{index + 500:064x}")
            return "added"
        except UploadLimitExceeded:
            return "full"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(add, (1, 2)))
    assert sorted(outcomes) == ["added", "full"]
    assert len(store.uploads_for_conversation("quota", limit=200)) == 200


# -------------------------------------------------------------- upload accessors


def test_upload_round_trip_and_guards(store):
    created = store.add_upload("conv-1", "notes.txt", "text/plain", 12, "a" * 64)
    assert created["state"] == "ready" and created["id"].startswith("upl_")
    assert store.get_upload(created["id"])["filename"] == "notes.txt"
    assert [u["id"] for u in store.uploads_for_conversation("conv-1")] == [created["id"]]
    assert store.uploads_for_conversation("conv-other") == []
    moved = store.mark_upload_state(created["id"], "quarantined")
    assert moved["state"] == "quarantined" and store.get_upload(created["id"])["state"] == "quarantined"
    with pytest.raises(ValueError, match="unknown upload state"):
        store.mark_upload_state(created["id"], "bogus")
    with pytest.raises(KeyError):
        store.mark_upload_state("upl_missing", "expired")
    with pytest.raises(ValueError, match="sha256"):
        store.add_upload("conv-1", "short.txt", "text/plain", 1, "abc")


# ------------------------------------------------------- media job accessors


def test_media_job_lifecycle_guards_and_idempotency(store):
    job = store.create_media_job(run_id="run-1", conversation_id="conv-1", kind="image",
                                 backend="local-diffusion", idempotency_key="gen-1",
                                 requested={"prompt": "a lighthouse at dusk"})
    assert job["status"] == "queued" and job["requested"] == {"prompt": "a lighthouse at dusk"}
    assert job["result"] is None and job["id"].startswith("mj_")

    with pytest.raises(IdempotencyConflict):
        store.create_media_job(run_id="run-1", conversation_id="conv-1", kind="image",
                               backend="local-diffusion", idempotency_key="gen-1",
                               requested={"prompt": "a different prompt"})

    marked = store.record_upstream_job(job["id"], "upstream-42")
    assert marked["upstream_job_id"] == "upstream-42"

    with pytest.raises(ValueError, match="illegal media job transition"):
        store.transition_media_job(job["id"], "succeeded")     # queued skips running

    running = store.transition_media_job(job["id"], "running")
    assert running["status"] == "running"
    in_flight = store.record_upstream_job(job["id"], "upstream-43")   # in-flight updates stay legal
    assert in_flight["upstream_job_id"] == "upstream-43"

    done = store.transition_media_job(job["id"], "succeeded",
                                      result={"media_id": "media_0f1e2d3c4b5a6978", "version": 1},
                                      cost_note="local: no charge")
    assert done["status"] == "succeeded" and done["result"]["media_id"] == "media_0f1e2d3c4b5a6978"
    assert done["cost_note"] == "local: no charge"

    with pytest.raises(ValueError, match="finished media job"):
        store.record_upstream_job(job["id"], "upstream-late")

    with pytest.raises(ValueError, match="illegal media job transition"):
        store.transition_media_job(job["id"], "running")       # terminal stays terminal

    failed = store.create_media_job(run_id="run-1", conversation_id="conv-1", kind="audio",
                                    backend="local", idempotency_key="gen-2",
                                    requested={"prompt": "chime"}, job_id="mj_fixed000000001")
    ended = store.transition_media_job("mj_fixed000000001", "failed", error="backend unavailable")
    assert failed["status"] == "queued" and ended["status"] == "failed" and \
        ended["error"] == "backend unavailable"
    assert [j["id"] for j in store.media_jobs_for_run("run-1")] == [job["id"], "mj_fixed000000001"]
    with pytest.raises(KeyError):
        store.transition_media_job("mj_missing", "running")
    with pytest.raises(ValueError, match="idempotency_key"):
        store.create_media_job(run_id="run-1", conversation_id="conv-1", kind="image",
                               backend="local", idempotency_key="", requested={})


# ----------------------------------------------- workspace session accessors


def test_workspace_session_upsert_and_generation_guard(store):
    session = store.upsert_workspace_session("conv-1", 2, "/state/ws/conv-1", env_fingerprint="fp-1")
    assert session["generation"] == 2 and session["status"] == "active"
    assert store.get_workspace_session("conv-1")["env_fingerprint"] == "fp-1"
    assert store.get_workspace_session("conv-other") is None

    expired = store.transition_workspace_session("conv-1", "expired", expected_generation=2)
    assert expired["status"] == "expired"

    with pytest.raises(RevisionConflict, match="concurrently advanced"):
        store.transition_workspace_session("conv-1", "active", expected_generation=1)

    back = store.transition_workspace_session("conv-1", "active", expected_generation=2)
    assert back["status"] == "active"

    regenerated = store.upsert_workspace_session("conv-1", 3, "/state/ws/conv-1-g3",
                                                 env_fingerprint="fp-2")
    assert regenerated["generation"] == 3 and regenerated["workspace_dir"].endswith("g3")

    store.transition_workspace_session("conv-1", "expired", expected_generation=3)
    with pytest.raises(ValueError, match="illegal workspace session transition"):
        store.transition_workspace_session("conv-1", "expired", expected_generation=3)  # expired -> expired
    store.transition_workspace_session("conv-1", "terminated", expected_generation=3)
    with pytest.raises(ValueError, match="illegal workspace session transition"):
        store.transition_workspace_session("conv-1", "active", expected_generation=3)   # terminated is terminal
    with pytest.raises(KeyError):
        store.transition_workspace_session("conv-none", "expired", expected_generation=1)
    with pytest.raises(ValueError, match="generation"):
        store.upsert_workspace_session("conv-2", 0, "/tmp/ws")
