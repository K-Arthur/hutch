"""Storage, schema-v52 and store round-trip tests for the synthesis lane."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path

import pytest

from hutch.store import SCHEMA_VERSION, Store, _migrate_58, _migrate_59
from hutch.synthesis.storage import (
    SynthesisIntegrityError,
    SynthesisStorage,
    SynthesisStorageError,
    mime_for,
    sanitize_storage_name,
)

MANIFEST_ID = "syn_" + "a" * 16


# ---------------------------------------------------------------------------
# storage


def test_stage_commit_and_read_round_trip(config):
    storage = SynthesisStorage(config)
    data = b"RIFF....fake wav bytes"
    staged = storage.stage_bytes("audio_overview", "episode 1.wav", data)
    assert staged.sha256 == hashlib.sha256(data).hexdigest()
    rel = storage.commit(staged, MANIFEST_ID, 1)
    assert rel.endswith("/audio_overview/" + storage.version_dir_name(1, staged.sha256) + "/episode-1.wav")
    assert storage.read_artifact(rel, staged.sha256, len(data)) == data
    # staged file was promoted, not copied
    assert not staged.path.exists()


def test_tampered_bytes_fail_verification(config):
    storage = SynthesisStorage(config)
    staged = storage.stage_bytes("script", "script.json", b'{"v": 1}')
    rel = storage.commit(staged, MANIFEST_ID, 1)
    target = config.synthesis_dir / rel
    os.chmod(target, 0o600)
    target.write_bytes(b'{"v": 2}')
    with pytest.raises(SynthesisIntegrityError):
        storage.read_artifact(rel, staged.sha256, staged.bytes)
    with pytest.raises(SynthesisStorageError):
        storage.read_artifact("../../etc/passwd", staged.sha256, staged.bytes)


def test_stage_rejects_bad_kind_extension_and_oversize(config):
    storage = SynthesisStorage(config)
    with pytest.raises(SynthesisStorageError):
        storage.stage_bytes("executable", "x.exe", b"!!")
    with pytest.raises(SynthesisStorageError):
        storage.stage_bytes("script", "noext", b"{}")
    with pytest.raises(SynthesisStorageError):
        storage.stage_bytes("transcript", "x.vtt", b"")  # empty
    big = b"x" * (8_000_001)
    with pytest.raises(SynthesisStorageError):
        storage.stage_bytes("transcript", "big.vtt", big)


def test_commit_rolls_back_when_row_insert_fails(config):
    storage = SynthesisStorage(config)
    staged = storage.stage_bytes("infographic", "figure.svg", b"<svg/>")

    def boom():
        raise RuntimeError("row insert failed")

    with pytest.raises(RuntimeError):
        storage.commit(staged, MANIFEST_ID, 1, insert_row=boom)
    kind_dir = config.synthesis_dir / MANIFEST_ID / "infographic"
    if kind_dir.is_dir():
        assert list(kind_dir.iterdir()) == []  # nothing reachable remains


def test_reconcile_removes_unreferenced_versions_and_staging(config):
    storage = SynthesisStorage(config)
    kept = storage.stage_bytes("brief", "brief.md", b"# brief")
    kept_rel = storage.commit(kept, MANIFEST_ID, 1)
    orphan = storage.stage_bytes("brief", "orphan.md", b"# orphan")
    orphan_rel = storage.commit(orphan, MANIFEST_ID, 2)
    leftover = storage.stage_bytes("table", "rows.csv", b"a,b\n1,2\n")

    known = {"/".join(kept_rel.split("/")[:3])}
    removed = storage.reconcile(lambda rel: rel in known)
    assert "/".join(orphan_rel.split("/")[:3]) in removed
    assert config.synthesis_dir.joinpath(kept_rel).exists()
    assert not config.synthesis_dir.joinpath(orphan_rel).exists()
    assert not leftover.path.parent.exists()


def test_reconcile_unlinks_symlinks_without_touching_external_targets(config, tmp_path):
    storage = SynthesisStorage(config)
    storage.ensure_root()
    outside = tmp_path / "outside"
    (outside / "kind" / "v001-deadbeef").mkdir(parents=True)
    sentinel = outside / "kind" / "v001-deadbeef" / "sentinel.txt"
    sentinel.write_text("keep")
    manifest_link = storage.root / MANIFEST_ID
    manifest_link.symlink_to(outside, target_is_directory=True)

    removed = storage.reconcile(lambda _rel: False)

    assert manifest_link.is_symlink() is False
    assert sentinel.read_text() == "keep"
    assert removed == []

    real_manifest = storage.root / ("syn_" + "b" * 16)
    real_manifest.mkdir()
    kind_link = real_manifest / "brief"
    kind_link.symlink_to(outside / "kind", target_is_directory=True)
    version_link = real_manifest / "table"
    version_link.mkdir()
    linked_version = version_link / "v001-deadbeef"
    linked_version.symlink_to(outside / "kind" / "v001-deadbeef", target_is_directory=True)
    staging_target = tmp_path / "staging-target"
    staging_target.mkdir()
    (staging_target / "important").write_text("keep")
    staging_link = storage.staging / ("a" * 8)
    staging_link.symlink_to(staging_target, target_is_directory=True)

    storage.reconcile(lambda _rel: False)
    assert not kind_link.is_symlink() and not linked_version.is_symlink()
    assert not staging_link.is_symlink()
    assert (staging_target / "important").read_text() == "keep"


def test_reconcile_rejects_symlinked_root(config, tmp_path):
    storage = SynthesisStorage(config)
    outside = tmp_path / "outside-root"
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_text("keep")
    storage.root.parent.mkdir(parents=True, exist_ok=True)
    storage.root.symlink_to(outside, target_is_directory=True)

    with pytest.raises(SynthesisStorageError, match="root"):
        storage.reconcile(lambda _rel: False)
    assert sentinel.read_text() == "keep"


def test_names_and_mime(config):
    assert sanitize_storage_name("Episode 1: Intro?.wav", "wav") == "Episode-1-Intro.wav"
    assert sanitize_storage_name("../../evil.wav", "wav") == "evil.wav"
    assert mime_for("x.wav") == "audio/wav" and mime_for("x.vtt").startswith("text/vtt")


# ---------------------------------------------------------------------------
# schema + store


def test_migrations_58_and_59_are_idempotent_and_preserve_existing_rows():
    assert SCHEMA_VERSION >= 59
    db = sqlite3.connect(":memory:")
    _migrate_58(db)
    _migrate_59(db)
    db.execute("INSERT INTO syn_sources (id, kind, identity, doc, created_at, updated_at) "
               "VALUES ('src_1', 'thread', 'thread:1', '{}', 'now', 'now')")
    _migrate_58(db)
    _migrate_59(db)
    names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"syn_sources", "syn_manifests", "syn_manifest_revisions", "syn_artifacts",
            "syn_effects", "syn_plans"} <= names
    assert db.execute("SELECT id FROM syn_sources").fetchone()[0] == "src_1"
    db.close()


def test_store_source_revision_is_content_addressed(store):
    rec = {"id": "src_" + "1" * 16, "kind": "thread", "identity": "https://social.example/t/1",
           "title": "A thread", "content_sha256": "a" * 64}
    first = store.record_synthesis_source(rec, conversation_id="conv_1")
    assert first["revision"] == 1
    same = store.record_synthesis_source({**rec, "id": "src_" + "2" * 16})
    assert same["id"] == first["id"] and same["revision"] == 1  # identical content: one revision
    changed = store.record_synthesis_source({**rec, "content_sha256": "b" * 64,
                                             "id": "src_" + "3" * 16})
    assert changed["revision"] == 2
    assert store.get_synthesis_source("https://social.example/t/1")["revision"] == 2
    assert store.get_synthesis_source("https://social.example/t/1", revision=1)["revision"] == 1
    with pytest.raises(ValueError):
        store.record_synthesis_source({"kind": "thread"})


def test_store_manifest_revisions_are_retained(store):
    manifest = {"id": MANIFEST_ID, "revision": 1, "conversation_id": "conv_1",
                "language": "en", "policy": "source_only", "status": "draft",
                "claims": [], "audience": "test"}
    first = store.save_synthesis_manifest(manifest)
    assert first["created"] is True and first["revision"] == 1

    manifest["revision"] = 2
    manifest["claims"] = [{"id": "cl_x", "text": "corrected"}]
    second = store.save_synthesis_manifest(manifest, reason="number correction")
    assert second["created"] is False and second["revision"] == 2
    assert second["doc"]["claims"][0]["text"] == "corrected"

    old = store.get_synthesis_manifest_revision(MANIFEST_ID, 1)
    assert old["doc"]["revision"] == 1 and old["doc"]["claims"] == []
    assert store.get_synthesis_manifest_revision(MANIFEST_ID, 2)["doc"]["claims"]
    assert [m["id"] for m in store.list_synthesis_manifests(conversation_id="conv_1")] == [MANIFEST_ID]


def test_store_artifact_rows_are_the_reachability_index(store, config):
    storage = SynthesisStorage(config)
    staged = storage.stage_bytes("transcript", "episode.vtt", b"WEBVTT\n")
    artifact_id = "art_" + "f" * 16

    def insert_row():
        store.record_synthesis_artifact(
            artifact_id=artifact_id, manifest_id=MANIFEST_ID, kind="transcript", version=1,
            status="committed", storage_path="", storage_name=staged.storage_name,
            mime=staged.mime, bytes_=staged.bytes, sha256=staged.sha256)

    rel = storage.commit(staged, MANIFEST_ID, 1, insert_row=insert_row)
    # The row was inserted before the storage path was known; update it to the real path.
    with store._lock:
        store._db.execute("UPDATE syn_artifacts SET storage_path = ? WHERE id = ?", (rel, artifact_id))
        store._db.commit()

    assert store.get_synthesis_artifact(artifact_id)["storage_path"] == rel
    known = store.known_synthesis_version_dirs()
    assert "/".join(rel.split("/")[:3]) in known
    with pytest.raises(ValueError):
        store.record_synthesis_artifact(
            artifact_id="art_" + "e" * 16, manifest_id=MANIFEST_ID, kind="transcript", version=1,
            status="committed", storage_path=rel, storage_name="x.vtt", mime="text/vtt",
            bytes_=1, sha256="c" * 64)


def test_effect_ledger_idempotency(store):
    first = store.begin_synthesis_effect(
        effect_id="eff_1", plan_id="plan_1", step_id="step_doc", kind="gdocs.create",
        idempotency_key="key-123", request_hash="h" * 64, target={"title": "Brief"})
    assert first["created"] is True and first["status"] == "prepared"
    again = store.begin_synthesis_effect(
        effect_id="eff_2", plan_id="plan_1", step_id="step_doc", kind="gdocs.create",
        idempotency_key="key-123", request_hash="h" * 64, target={"title": "Brief"})
    assert again["created"] is False and again["id"] == "eff_1"
    store.finish_synthesis_effect("eff_1", status="succeeded",
                                  result={"documentId": "doc123"}, remote_id="doc123")
    row = store.find_synthesis_effect("key-123")
    assert row["status"] == "succeeded" and row["remote_id"] == "doc123"
    assert [r["id"] for r in store.list_synthesis_effects(plan_id="plan_1")] == ["eff_1"]
