"""End-to-end document pipeline: text-format generation, tool contract, and API routes."""

from __future__ import annotations

import hashlib
import sqlite3

import pytest
from fastapi.testclient import TestClient

from hutch.documents import DocumentStorage, new_document_id
from hutch.documents.docgen import DocumentGenerationError, generate, supported_formats
from hutch.models import ApprovalMode, Bot, Event, EventType, Run, RunStatus
from hutch.safety import PolicyEngine
from hutch.store import Store
from hutch.tools.base import ToolContext
from hutch.tools.documents import CreateDocumentTool

# --------------------------------------------------------------------- generators


def test_supported_text_formats_present():
    assert {"txt", "md", "csv", "json", "yaml"} <= set(supported_formats())


def test_json_roundtrip_and_rejection():
    result = generate("json", {"value": {"a": 1, "b": [1, 2, "three"]}})
    assert result.validation_state == "passed"
    import json
    assert json.loads(result.data.decode("utf-8")) == {"a": 1, "b": [1, 2, "three"]}
    with pytest.raises(DocumentGenerationError, match="serializable"):
        generate("json", {"value": {1, 2}})
    with pytest.raises(DocumentGenerationError, match="value"):
        generate("json", {"text": "not the right key"})


def test_yaml_roundtrip():
    result = generate("yaml", {"value": {"name": "季度", "items": [1, 2]}})
    import yaml
    assert yaml.safe_load(result.data.decode("utf-8")) == {"name": "季度", "items": [1, 2]}


def test_csv_typing_bom_and_formula_guard():
    result = generate("csv", {"header": ["id", "delta", "note"],
                              "rows": [["00123", -4.5, "=cmd|' /C calc'!A0"], ["00456", 2, "@sum"]]})
    text = result.data.decode("utf-8-sig")
    assert text.startswith("id,delta,note\r\n")
    assert "'=cmd" in text and "'@sum" in text, "formula-prefixed cells must be neutralized"
    assert "-4.5" in text, "negative numbers survive the guard"
    assert result.validation_state == "passed"
    assert any(f["code"] == "csv_formula_guard" for f in result.findings)


def test_csv_rejects_invalid_specs():
    with pytest.raises(DocumentGenerationError, match="rows"):
        generate("csv", {"rows": "not-a-list"})
    with pytest.raises(DocumentGenerationError, match="array"):
        generate("csv", {"rows": [["ok"], "nope"]})
    with pytest.raises(DocumentGenerationError, match="columns"):
        generate("csv", {"rows": [["x"] * 300]})


def test_txt_md_explicit_encoding():
    for fmt in ("txt", "md"):
        result = generate(fmt, {"text": "héllo\r\nworld"})
        assert result.data == "héllo\nworld".encode("utf-8"), "newlines normalized, UTF-8 explicit"


# --------------------------------------------------------------------- tool contract


def make_ctx(store: Store, config, tmp_path, bot: Bot | None = None):
    bot = bot or Bot(name="doc-bot", model="mock/demo", tools=["documents"],
                     approval_mode=ApprovalMode.auto)
    if not store.get_bot(bot.name):
        store.create_bot(bot)
    run = Run(bot_id=bot.id, prompt="test", status=RunStatus.running)
    store.create_run(run)
    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)
    emitted: list[Event] = []

    def emit(ev: Event):
        emitted.append(ev)
        store.append_event(ev)

    from hutch.approvals import ApprovalGate
    gate = ApprovalGate(store, bot, run, PolicyEngine(), emit, poll_seconds=0.01)
    ctx = ToolContext(bot=bot, run=run, store=store, policy=gate.policy, gate=gate,
                      config=config, workspace=workspace, emit=emit)
    ctx._emitted = emitted
    return ctx


def test_create_document_csv_end_to_end(store, config, tmp_path):
    ctx = make_ctx(store, config, tmp_path)
    tool = CreateDocumentTool()
    result = tool.run({"format": "csv", "filename": "Tracker 2026.csv", "title": "Tracker",
                       "content": {"header": ["id", "total"], "rows": [["001", 5]]}}, ctx)
    assert result.ok, result.output
    ref = result.data["document"]
    assert ref["download_url"] == f"/api/v1/documents/{ref['id']}/versions/1/download"
    assert ref["validation_state"] == "passed"
    doc = store.get_document(ref["id"])
    assert doc["current_version"] == 1 and doc["conversation_id"] == ctx.run.conversation_id
    version = store.get_document_version(ref["id"], 1)
    assert version["run_id"] == ctx.run.id
    storage = DocumentStorage(config)
    served = storage.read_version(version["storage_path"], version["sha256"], version["bytes"])
    assert served.startswith(b"\xef\xbb\xbfid,total")


def test_create_document_records_receipt_without_full_content(store, config, tmp_path):
    ctx = make_ctx(store, config, tmp_path)
    tool = CreateDocumentTool()
    spec = {"text": "x" * 5_000}
    recorded = tool.recorded_arguments({"format": "txt", "filename": "a.txt", "title": "A",
                                        "content": spec}, ctx)
    assert "content" not in recorded and "5,000 characters" in recorded["content_summary"]


def test_create_document_dry_run_stores_nothing(store, config, tmp_path):
    ctx = make_ctx(store, config, tmp_path)
    ctx.dry_run = True
    result = CreateDocumentTool().run({"format": "txt", "filename": "a.txt", "title": "A",
                                       "content": {"text": "hi"}}, ctx)
    assert result.ok and result.data.get("simulated")
    assert store.count_run_documents(ctx.run.id) == 0


def test_create_document_rejects_bad_content_before_storing(store, config, tmp_path):
    ctx = make_ctx(store, config, tmp_path)
    result = CreateDocumentTool().run({"format": "json", "filename": "a.json", "title": "A",
                                       "content": {"value": {1, 2}}}, ctx)
    assert not result.ok and "rejected" in result.output
    assert store.count_run_documents(ctx.run.id) == 0
    result = CreateDocumentTool().run({"format": "exe", "filename": "evil.exe", "title": "E",
                                       "content": {}}, ctx)
    assert not result.ok and "unsupported format" in result.output


def test_create_document_pdf_renders_preview_pages(store, config, tmp_path):
    ctx = make_ctx(store, config, tmp_path)
    result = CreateDocumentTool().run(
        {"format": "pdf", "filename": "report.pdf", "title": "Report",
         "content": {"title": "Report", "blocks": [{"p": "Hello."}, {"pagebreak": True},
                                                   {"p": "World."}]}}, ctx)
    assert result.ok, result.output
    ref = result.data["document"]
    assert ref["preview_mode"] == "pages"
    version = store.get_document_version(ref["id"], 1)
    assert version["preview_mode"] == "pages"
    assert version["preview_data"].get("rendered_pages") == 2
    assert version["validation_state"] == "passed"
    storage = DocumentStorage(config)
    page = storage.read_preview_png(version["storage_path"], 1)
    assert page is not None and page.startswith(b"\x89PNG\r\n\x1a\n")


def test_create_document_pdf_survives_preview_render_failure(store, config, tmp_path, monkeypatch):
    import hutch.tools.documents as documents_tool
    from hutch.documents.docgen.render import RenderError

    def boom(data, version_dir, **kwargs):
        raise RenderError("the preview renderer exploded")

    monkeypatch.setattr(documents_tool, "render_pdf_pages", boom)
    ctx = make_ctx(store, config, tmp_path)
    result = CreateDocumentTool().run(
        {"format": "pdf", "filename": "report.pdf", "title": "Report",
         "content": {"title": "Report", "blocks": [{"p": "Hello."}]}}, ctx)
    assert result.ok, f"generation must never fail because preview rendering did: {result.output}"
    assert "download-only" in result.output
    ref = result.data["document"]
    assert ref["preview_mode"] == "download_only"
    assert any(f["code"] == "preview_render_failed" for f in ref["validation_findings"])
    version = store.get_document_version(ref["id"], 1)
    assert version["preview_mode"] == "download_only"
    assert any(f["code"] == "preview_render_failed" for f in version["validation_findings"])
    assert version["validation_state"] == "passed", "validation stays untouched by the downgrade"
    storage = DocumentStorage(config)
    served = storage.read_version(version["storage_path"], version["sha256"], version["bytes"])
    assert served.startswith(b"%PDF"), "the document stays valid and downloadable"


def test_create_document_ask_mode_requires_approval_then_sticks(store, config, tmp_path):
    bot = Bot(name="doc-ask-bot", model="mock/demo", tools=["documents"], approval_mode=ApprovalMode.ask)
    ctx = make_ctx(store, config, tmp_path, bot=bot)
    import threading
    from hutch.runtime.steps import call_tool
    result: dict = {}

    def invoke():
        result["value"] = call_tool(ctx.run, ctx, {"create_document": CreateDocumentTool()},
                                    "create_document",
                                    {"format": "txt", "filename": "a.txt", "title": "A",
                                     "content": {"text": "hello"}})

    worker = threading.Thread(target=invoke)
    worker.start()
    import time
    deadline = time.time() + 5
    while time.time() < deadline and not store.pending_approvals():
        time.sleep(0.01)
    [approval] = store.pending_approvals()
    assert approval.sticky_key == "documents:create"
    assert "content_summary" in approval.detail and "content" not in approval.detail
    from hutch.approvals import resolve_approval_ex
    resolve_approval_ex(store, approval.id, approve=True, by="test")
    worker.join(timeout=5)
    assert result["value"].ok, result["value"].output
    assert store.count_run_documents(ctx.run.id) == 1
    # the tool_result event carries the document reference for chat rendering
    events = store.list_events(ctx.run.id)
    document_events = [e for e in events if e.type is EventType.tool_result and "document" in e.data]
    assert document_events and document_events[-1].data["document"]["id"].startswith("doc_")


# --------------------------------------------------------------------- API routes


@pytest.fixture()
def seeded_document(config, tmp_path):
    """Commit one CSV document directly through the storage protocol."""
    store = Store(config)
    try:
        storage = DocumentStorage(config)
        data = b"\xef\xbb\xbfcol1,col2\r\na,b\r\n"
        staged = storage.stage_bytes("0ceed0005eed1", "csv", "résultats-季度.csv", data)
        doc_id = new_document_id()
        row = {"version": 1, "filename": "résultats-季度.csv", "storage_name": staged.storage_name,
               "mime": "text/csv; charset=utf-8", "bytes": staged.bytes, "sha256": staged.sha256,
               "storage_path": storage.version_rel_path(doc_id, 1, staged.sha256, staged.storage_name),
               "source": "generated", "generator": "hutch texty 1.0", "validation_state": "passed",
               "findings": [], "preview_mode": "structure", "preview_data": {"kind": "table"},
               "page_count": None}
        storage.commit(staged, doc_id, 1, insert_row=lambda: store.create_document(
            document_id=doc_id, bot_id="bot_0123456789abcdef", conversation_id=None,
            title="Seed", fmt="csv", version=row))
    finally:
        store.close()
    return doc_id


@pytest.fixture()
def api_client(config, monkeypatch):
    from hutch.server.app import create_app
    with TestClient(create_app()) as client:
        yield client


def test_document_list_get_and_download_routes(api_client, seeded_document):
    listed = api_client.get("/api/v1/documents")
    assert listed.status_code == 200
    docs = listed.json()["documents"]
    assert [d["id"] for d in docs] == [seeded_document]
    assert docs[0]["version"]["sha256"]
    detail = api_client.get(f"/api/v1/documents/{seeded_document}")
    assert detail.status_code == 200 and detail.json()["title"] == "Seed"
    versions = api_client.get(f"/api/v1/documents/{seeded_document}/versions")
    assert versions.status_code == 200 and len(versions.json()["versions"]) == 1


def test_document_download_unicode_name_headers_and_range(api_client, seeded_document):
    res = api_client.get(f"/api/v1/documents/{seeded_document}/versions/1/download")
    assert res.status_code == 200
    assert res.headers["x-hutch-artifact-verified"] == "sha256"
    assert res.headers["etag"].startswith('"')
    disposition = res.headers["content-disposition"]
    assert "filename*=utf-8''" in disposition and "%E5%AD%A3%E5%BA%A6" in disposition
    assert "attachment" in disposition
    assert res.content.startswith(b"\xef\xbb\xbfcol1")
    ranged = api_client.get(f"/api/v1/documents/{seeded_document}/versions/1/download",
                            headers={"Range": "bytes=0-9"})
    assert ranged.status_code == 206 and ranged.headers["content-range"].endswith(f"/{len(res.content)}")
    assert ranged.content == res.content[:10]


def test_document_download_rejects_tampered_bytes(config, api_client, seeded_document):
    import os
    store = Store(config)
    try:
        storage = DocumentStorage(config)
        version = store.get_document_version(seeded_document, 1)
        stored = storage.root / version["storage_path"]
        os.chmod(stored, 0o600)
        stored.write_bytes(b"\xef\xbb\xbfcol1,col2\r\nX,Y\r\n")
        os.chmod(stored, 0o400)
    finally:
        store.close()
    res = api_client.get(f"/api/v1/documents/{seeded_document}/versions/1/download")
    assert res.status_code == 409 and "SHA-256" in res.json()["detail"]


def test_document_preview_text_and_readiness(api_client, seeded_document):
    preview = api_client.get(f"/api/v1/documents/{seeded_document}/versions/1/preview")
    assert preview.status_code == 200
    body = preview.json()
    assert body["mode"] == "structure" and body["text"].startswith("col1,col2")
    readiness = api_client.get("/api/v1/documents/readiness")
    assert readiness.status_code == 200
    formats = {f["format"]: f for f in readiness.json()["formats"]}
    assert formats["csv"]["available"] is True and formats["csv"]["preview_mode"] == "structure"
    # readiness lists only genuinely supported formats; absent formats are absent, never disguised
    for fmt in formats.values():
        assert fmt["preview_mode"] in ("pages", "structure", "download_only")


def test_document_routes_reject_unknown_ids(api_client):
    assert api_client.get("/api/v1/documents/doc_ffffffffffffffff").status_code == 404
    assert api_client.get("/api/v1/documents/not-a-doc").status_code == 404
    assert api_client.get("/api/v1/documents/doc_0123456789abcdef/versions/9/download").status_code == 404
