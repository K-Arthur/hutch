"""Real-browser journey for committed documents: the Files card, a structure preview,
the SHA-256-verified download, and version history — the parts unit tests cannot see.

Skipped automatically when no Playwright browser is installed.
"""

from __future__ import annotations

import hashlib
import threading
import time
import uuid

import pytest

pw = pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402

from hutch.config import hutchConfig  # noqa: E402
from hutch.documents import DocumentStorage, new_document_id  # noqa: E402
from hutch.models import ApprovalMode, Bot  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from hutch.store import Store  # noqa: E402


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        b = None
        errors = []
        for engine in (p.chromium, p.firefox):
            try:
                b = engine.launch()
                break
            except Exception as exc:
                errors.append(f"{engine.name}: {exc}")
        if b is None:
            pytest.skip("no Playwright browser is installed: " + "; ".join(errors))
        yield b
        b.close()


@pytest.fixture()
def live(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", lifespan="on"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}", app, tmp_path / "state"
    server.should_exit = True
    t.join(timeout=10)


def _seed_document(state_dir, bot_name: str = "doc-e2e") -> tuple[str, bytes]:
    """Create a bot, a chat, and one committed CSV document through the real protocol."""
    config = hutchConfig(state_dir=state_dir)
    store = Store(config)
    try:
        bot = Bot(name=bot_name, model="mock/demo", tools=["files", "documents"],
                  approval_mode=ApprovalMode.auto)
        if not store.get_bot(bot.name):
            store.create_bot(bot)
        conversation, _created = store.create_conversation(
            bot_id=bot.id, title="Docs", idem_key=f"seed-{uuid.uuid4().hex}",
            request_hash="seed")
        data = b"\xef\xbb\xbfregion,orders\nnorth,12\nsouth,7\n"
        storage = DocumentStorage(config)
        staged = storage.stage_bytes(uuid.uuid4().hex[:16], "csv", "orders-summary.csv", data)
        doc_id = new_document_id()
        row = {"version": 1, "filename": "orders-summary.csv", "storage_name": staged.storage_name,
               "mime": "text/csv; charset=utf-8", "bytes": staged.bytes, "sha256": staged.sha256,
               "storage_path": storage.version_rel_path(doc_id, 1, staged.sha256, staged.storage_name),
               "source": "generated", "generator": "hutch texty 1.0", "validation_state": "passed",
               "findings": [], "preview_mode": "structure", "preview_data": {"kind": "table"},
               "page_count": None}
        storage.commit(staged, doc_id, 1, insert_row=lambda: store.create_document(
            document_id=doc_id, bot_id=bot.id,
            conversation_id=conversation["id"], title="Orders", fmt="csv",
            version=row))
        return bot.name, data
    finally:
        store.close()


def test_document_card_preview_and_verified_download(browser, live):
    base, _app, state_dir = live
    bot_name, data = _seed_document(state_dir)
    page = browser.new_page(viewport={"width": 1100, "height": 800})
    try:
        page.goto(f"{base}/#/chat/{bot_name}")
        page.wait_for_selector("#composer-menu-btn", timeout=15_000)
        page.click("#composer-menu-btn")
        page.click("#conversation-files-open")
        card = page.locator(".document-card")
        card.wait_for(state="visible", timeout=10_000)
        assert "orders-summary.csv" in card.inner_text()
        assert "Verified" in card.inner_text(), "the card pairs the check glyph with the word"

        # The Files modal and the preview share one modal root, so the download
        # and version history run first; the preview replaces the list last.
        with page.expect_download() as download_info:
            page.click(".document-card a:has-text('Download')")
        download = download_info.value
        received = download.path()
        assert received is not None
        saved = received.read_bytes()
        assert hashlib.sha256(saved).hexdigest() == hashlib.sha256(data).hexdigest(), \
            "the bytes the browser saved must equal the committed version"

        page.click("[data-doc-versions]")
        versions = page.locator("#doc-versions-list")
        versions.wait_for(state="visible", timeout=10_000)
        assert "v1" in versions.inner_text()
        page.keyboard.press("Escape")

        page.goto(f"{base}/#/chat/{bot_name}")
        page.wait_for_selector("#composer-menu-btn", timeout=15_000)
        page.click("#composer-menu-btn")
        page.click("#conversation-files-open")
        page.locator(".document-card").wait_for(state="visible", timeout=10_000)
        page.click("[data-doc-preview]")
        body = page.locator("#doc-preview-body")
        body.wait_for(state="visible", timeout=10_000)
        assert "north" in body.inner_text(), "the CSV structure preview shows extracted rows"
        modal_text = page.locator(".modal-card").inner_text()
        assert "extracted" in modal_text.lower(), \
            "the preview must label itself as extracted content, not the rendered layout"
    finally:
        page.close()
