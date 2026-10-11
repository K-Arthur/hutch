"""Document revisions: compare-and-swap versions, source-spec regeneration, inspection."""

from __future__ import annotations

import pytest

from hutch.documents import DocumentStorage
from hutch.tools.documents import CreateDocumentTool, InspectDocumentTool, ReviseDocumentTool

from tests.test_documents_pipeline import make_ctx


def _create_csv(ctx) -> dict:
    result = CreateDocumentTool().run(
        {"format": "csv", "filename": "tracker.csv", "title": "Tracker",
         "content": {"header": ["id", "n"], "rows": [["001", 1]]}}, ctx)
    assert result.ok, result.output
    return result.data["document"]


def test_revision_creates_new_version_and_keeps_old(store, config, tmp_path):
    ctx = make_ctx(store, config, tmp_path)
    ref = _create_csv(ctx)
    result = ReviseDocumentTool().run(
        {"document_id": ref["id"], "expected_version": 1,
         "content": {"header": ["id", "n"], "rows": [["001", 1], ["002", 4]]}}, ctx)
    assert result.ok, result.output
    revised = result.data["document"]
    assert revised["version"] == 2
    doc = store.get_document(ref["id"])
    assert doc["current_version"] == 2
    versions = store.list_document_versions(ref["id"])
    assert [v["version"] for v in versions] == [2, 1]
    assert versions[1]["source"] == "generated" and versions[0]["source"] == "revised"
    # old version's bytes are still served and unchanged
    storage = DocumentStorage(config)
    old = storage.read_version(versions[1]["storage_path"], versions[1]["sha256"], versions[1]["bytes"])
    new = storage.read_version(versions[0]["storage_path"], versions[0]["sha256"], versions[0]["bytes"])
    assert old != new and b"002" in new


def test_revision_cas_refuses_stale_version(store, config, tmp_path):
    ctx = make_ctx(store, config, tmp_path)
    ref = _create_csv(ctx)
    ReviseDocumentTool().run({"document_id": ref["id"], "expected_version": 1,
                              "content": {"header": ["id"], "rows": [["9"]]}}, ctx)
    stale = ReviseDocumentTool().run({"document_id": ref["id"], "expected_version": 1,
                                      "content": {"header": ["id"], "rows": [["8"]]}}, ctx)
    assert not stale.ok and "moved on" in stale.output
    assert store.get_document(ref["id"])["current_version"] == 2


def test_revision_requires_same_bot_and_real_document(store, config, tmp_path):
    ctx = make_ctx(store, config, tmp_path)
    assert not ReviseDocumentTool().run(
        {"document_id": "doc_0123456789abcdef", "expected_version": 1,
         "content": {"text": "x"}}, ctx).ok
    ref = _create_csv(ctx)
    from hutch.models import ApprovalMode, Bot
    bot2 = Bot(name="other-bot", model="mock/demo", tools=["documents"],
               approval_mode=ApprovalMode.auto)
    if not store.get_bot(bot2.name):
        store.create_bot(bot2)
    ctx2 = make_ctx(store, config, tmp_path, bot=bot2)
    # ctx2's run belongs to bot2; the document belongs to doc-bot
    denied = ReviseDocumentTool().run({"document_id": ref["id"], "expected_version": 1,
                                       "content": {"header": ["x"], "rows": [["1"]]}}, ctx2)
    assert not denied.ok and "different bot" in denied.output


def test_revision_dry_run_touches_nothing(store, config, tmp_path):
    ctx = make_ctx(store, config, tmp_path)
    ref = _create_csv(ctx)
    ctx.dry_run = True
    result = ReviseDocumentTool().run({"document_id": ref["id"], "expected_version": 1,
                                       "content": {"header": ["id"], "rows": [["2"]]}}, ctx)
    assert result.ok and result.data.get("simulated")
    assert store.get_document(ref["id"])["current_version"] == 1


def test_inspect_returns_spec_and_versions(store, config, tmp_path):
    ctx = make_ctx(store, config, tmp_path)
    ref = _create_csv(ctx)
    result = InspectDocumentTool().run({"document_id": ref["id"]}, ctx)
    assert result.ok
    assert "tracker.csv" in result.output
    assert '"header"' in result.output and "001" in result.output, \
        "inspect returns the stored source specification so revisions are grounded"
    assert "versions: v1 (generated, passed)" in result.output
    assert result.data["document"]["id"] == ref["id"]
    missing = InspectDocumentTool().run({"document_id": ref["id"], "version": 9}, ctx)
    assert not missing.ok
