"""Schema v51 document records and the durable document storage protocol."""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

import pytest

from hutch.config import hutchConfig
from hutch.documents import (DocumentIntegrityError, DocumentStorage, DocumentStorageError,
                             MAX_DOCUMENT_BYTES, new_document_id, reconcile_documents_store,
                             sanitize_storage_name)
from hutch.store import SCHEMA_VERSION, Store


def _version_rows(data: bytes, filename: str = "report.pdf", version: int = 1,
                  storage_path: str | None = None, storage_name: str = "report.pdf",
                  generator: str = "test-gen 1.0") -> dict:
    return {
        "version": version,
        "filename": filename,
        "storage_name": storage_name,
        "mime": "application/pdf",
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "storage_path": storage_path or f"doc_0123456789abcdef/v{version:03d}-{hashlib.sha256(data).hexdigest()[:8]}/{storage_name}",
        "source": "generated",
        "generator": generator,
        "validation_state": "passed",
        "findings": [],
        "preview_mode": "structure",
        "preview_data": {"pages": 1},
        "page_count": 1,
    }


def test_schema_v50_tables_exist(store: Store):
    assert SCHEMA_VERSION == 50
    names = {row["name"] for row in store._db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"documents", "document_versions"} <= names


def test_create_document_and_versions_roundtrip(store: Store):
    doc_id = new_document_id()
    store.create_document(document_id=doc_id, bot_id="bot_0123456789abcdef",
                          conversation_id="c1", title="Quarterly report", fmt="pdf",
                          version=_version_rows(b"v1-bytes", version=1))
    doc = store.get_document(doc_id)
    assert doc["current_version"] == 1 and doc["format"] == "pdf" and doc["title"] == "Quarterly report"
    current = store.get_document_version(doc_id, 1)
    assert current["sha256"] == hashlib.sha256(b"v1-bytes").hexdigest()
    assert current["validation_state"] == "passed" and current["preview_data"] == {"pages": 1}
    listing = store.list_documents(conversation_id="c1")
    assert len(listing) == 1 and listing[0]["cur_sha256"] == current["sha256"]
    assert store.list_documents(conversation_id="other") == []


def test_document_revision_cas(store: Store):
    doc_id = new_document_id()
    store.create_document(document_id=doc_id, bot_id="bot_0123456789abcdef", conversation_id=None,
                          title="Deck", fmt="pptx", version=_version_rows(b"a", version=1))
    with pytest.raises(ValueError, match="concurrently"):
        store.add_document_version(doc_id, expected_version=2, version=_version_rows(b"b", version=2))
    store.add_document_version(doc_id, expected_version=1, version=_version_rows(b"b", version=2))
    assert store.get_document(doc_id)["current_version"] == 2
    assert [v["version"] for v in store.list_document_versions(doc_id)] == [2, 1]
    with pytest.raises(KeyError, match="no such document"):
        store.add_document_version("doc_ffffffffffffffff", 1, _version_rows(b"x"))


def test_set_document_preview_updates_only_preview_columns(store: Store):
    doc_id = new_document_id()
    store.create_document(document_id=doc_id, bot_id="bot_0123456789abcdef", conversation_id=None,
                          title="Report", fmt="pdf", version=_version_rows(b"pv-bytes"))
    store.set_document_preview(doc_id, 1, "pages", {"kind": "pages", "rendered_pages": 3})
    version = store.get_document_version(doc_id, 1)
    assert version["preview_mode"] == "pages"
    assert version["preview_data"] == {"kind": "pages", "rendered_pages": 3}
    assert version["validation_state"] == "passed", "validation_state stays untouched"
    assert version["sha256"] == hashlib.sha256(b"pv-bytes").hexdigest(), "content columns stay untouched"
    # the RenderError downgrade: preview_mode lowered and findings replaced in one transaction
    findings = version["validation_findings"] + [{"code": "preview_render_failed", "detail": "boom"}]
    store.set_document_preview(doc_id, 1, "download_only", {"kind": "pages"}, findings=findings)
    version = store.get_document_version(doc_id, 1)
    assert version["preview_mode"] == "download_only"
    assert [f["code"] for f in version["validation_findings"]] == ["preview_render_failed"]
    assert version["validation_state"] == "passed"
    with pytest.raises(KeyError, match="no such document version"):
        store.set_document_preview("doc_ffffffffffffffff", 1, "pages", {})
    with pytest.raises(ValueError, match="unknown preview mode"):
        store.set_document_preview(doc_id, 1, "posters", {})


def _commit_pdf(storage: DocumentStorage, store: Store, *, doc_id: str, version: int,
                data: bytes | None = None) -> str:
    data = data if data is not None else f"pdf-bytes-{version}".encode()
    staged = storage.stage_bytes(f"{version:08d}aaaa0000", "pdf", f"report-{version}.pdf", data)
    row = _version_rows(data, version=version,
                        storage_name=staged.storage_name)
    row["storage_path"] = storage.version_rel_path(doc_id, version, staged.sha256, staged.storage_name)
    rel = storage.commit(staged, doc_id, version, insert_row=lambda: store.add_document_version(
        doc_id, version - 1, row) if version > 1 else store.create_document(
        document_id=doc_id, bot_id="bot_0123456789abcdef", conversation_id=None,
        title="Report", fmt="pdf", version=row))
    return rel


def test_commit_promotes_verified_immutable_version(config: hutchConfig, store: Store):
    storage = DocumentStorage(config)
    doc_id = new_document_id()
    rel = _commit_pdf(storage, store, doc_id=doc_id, version=1, data=b"committed-bytes")
    stored = storage.root / Path(rel)
    assert stored.is_file() and not stored.is_symlink()
    assert (oct(stored.stat().st_mode & 0o777)) == "0o400"
    served = storage.read_version(rel, hashlib.sha256(b"committed-bytes").hexdigest(),
                                  len(b"committed-bytes"))
    assert served == b"committed-bytes"
    assert not list((storage.staging).glob("*.json")), "journal must be cleared after commit"


def test_read_version_detects_tamper_and_missing(config: hutchConfig, store: Store):
    storage = DocumentStorage(config)
    doc_id = new_document_id()
    rel = _commit_pdf(storage, store, doc_id=doc_id, version=1, data=b"original-bytes")
    stored = storage.root / Path(rel)
    os.chmod(stored, 0o600)
    stored.write_bytes(b"tampered-bytes!")
    os.chmod(stored, 0o400)
    with pytest.raises(DocumentIntegrityError, match="SHA-256"):
        storage.read_version(rel, hashlib.sha256(b"original-bytes").hexdigest(), 15)
    with pytest.raises(DocumentIntegrityError, match="size"):
        storage.read_version(rel, hashlib.sha256(b"tampered-bytes!").hexdigest(), 4)
    with pytest.raises(DocumentStorageError, match="missing"):
        storage.read_version("doc_ffffffffffffffff/v001-aaaaaaaa/report.pdf",
                             hashlib.sha256(b"x").hexdigest(), 1)


def test_commit_rolls_back_when_row_insert_fails(config: hutchConfig):
    storage = DocumentStorage(config)
    doc_id = new_document_id()
    staged = storage.stage_bytes("0badf00df00d01", "pdf", "never-promoted.pdf", b"doomed")
    def boom() -> None:
        raise RuntimeError("db unavailable")
    with pytest.raises(RuntimeError):
        storage.commit(staged, doc_id, 1, insert_row=boom)
    assert not (storage.root / doc_id / storage.version_dir_name(1, staged.sha256)).exists()
    assert not (storage.staging / "0badf00df00d01.json").exists()


def test_reconcile_removes_orphan_versions_and_stale_staging(config: hutchConfig, store: Store):
    storage = DocumentStorage(config)
    doc_id = new_document_id()
    rel = _commit_pdf(storage, store, doc_id=doc_id, version=1, data=b"kept")
    # orphan: promoted bytes with no committed row
    orphan_staged = storage.stage_bytes("0abcdef424242", "pdf", "orphan.pdf", b"orphan")
    orphan_dir = storage.root / doc_id / storage.version_dir_name(99, orphan_staged.sha256)
    orphan_dir.mkdir(parents=True)
    (orphan_dir / "orphan.pdf").write_bytes(b"orphan")
    # abandoned staging older than the window
    stale = storage.staging / "stalejob0001"
    stale.mkdir()
    (stale / "draft.pdf").write_bytes(b"abandoned")
    old = time.time() - 25 * 3600
    os.utime(stale, (old, old))

    result = reconcile_documents_store(
        config, lambda d, v: d == doc_id and v == 1, max_staging_age=3600)
    assert result["removed_versions"] >= 1 and result["removed_staging"] >= 1
    assert (storage.root / Path(rel)).is_file(), "the committed version must survive reconciliation"
    assert not orphan_dir.exists()
    assert not stale.exists()


def test_stage_bounds_and_format_guards(config: hutchConfig):
    storage = DocumentStorage(config)
    with pytest.raises(DocumentStorageError, match="unsupported document format"):
        storage.stage_bytes("0bad00000exe1", "exe", "evil.exe", b"MZ")
    with pytest.raises(DocumentStorageError, match="32 MB"):
        storage.stage_bytes("0bad00000big1", "pdf", "big.pdf", b"x" * (MAX_DOCUMENT_BYTES + 1))
    with pytest.raises(DocumentStorageError, match="empty"):
        storage.stage_bytes("0bad0000empty", "pdf", "empty.pdf", b"")
    with pytest.raises(DocumentStorageError, match="already exists"):
        storage.stage_bytes("0bad0000d0011", "pdf", "a.pdf", b"1")
        storage.stage_bytes("0bad0000d0011", "pdf", "b.pdf", b"2")


def test_sanitize_storage_name_slugs_and_falls_back():
    assert sanitize_storage_name("Reports/2026: Q4 — final?.pdf", "pdf") == "2026-Q4-final-.pdf"
    assert sanitize_storage_name("../../etc/passwd", "csv") == "passwd.csv"
    assert sanitize_storage_name("", "csv") == "document.csv"
    assert sanitize_storage_name("报表.xlsx", "xlsx") == "xlsx.xlsx", "extension is always kept"
    assert sanitize_storage_name("a.docx", "pdf") == "a.pdf", "storage name never lies about type"
    long = sanitize_storage_name("x" * 300 + ".pdf", "pdf")
    assert len(long) <= 120 and long.endswith(".pdf")


def test_reconcile_ignores_symlink_and_foreign_entries(config: hutchConfig, store: Store):
    storage = DocumentStorage(config)
    storage.ensure_root()
    foreign = storage.root / "not-a-doc-id"
    foreign.mkdir(exist_ok=True)
    (foreign / "junk").write_text("x")
    result = reconcile_documents_store(config, lambda d, v: False)
    assert foreign.exists(), "entries outside the doc-id namespace must be left alone"
