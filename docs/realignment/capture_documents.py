"""Capture document-pipeline acceptance evidence: real generated documents, their rendered
pages, and the Studio UI at three viewports.

Run from the repository root of an hutch checkout with the venv active:

    .venv/bin/python docs/realignment/capture_documents.py

Writes docs/realignment/artifacts/document-pipeline-<date>/ containing the committed
acceptance documents (bytes + SHA-256), rendered page PNGs from the committed PDF, UI
screenshots at desktop/tablet/phone widths, and validation.json with overflow checks and
source hashes. Screenshots are of the real app with a temporary state directory; no mock
provider output is shown.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from importlib.metadata import version as package_version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from hutch.config import hutchConfig  # noqa: E402
from hutch.documents import DocumentStorage, new_document_id  # noqa: E402
from hutch.documents.docgen import generate  # noqa: E402
from hutch.models import ApprovalMode, Bot  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from hutch.store import Store  # noqa: E402

VIEWPORTS = (("desktop", 1440, 1000), ("tablet", 900, 1024), ("phone", 390, 844))
SOURCE_FILES = [
    "src/hutch/documents/storage.py",
    "src/hutch/documents/docgen/__init__.py",
    "src/hutch/documents/docgen/texty.py",
    "src/hutch/documents/docgen/docxgen.py",
    "src/hutch/documents/docgen/xlsx.py",
    "src/hutch/documents/docgen/pptx.py",
    "src/hutch/documents/docgen/pdfdoc.py",
    "src/hutch/documents/docgen/render.py",
    "src/hutch/tools/documents.py",
    "src/hutch/server/app.py",
    "src/hutch/server/static/app.js",
    "src/hutch/server/static/style.css",
    "src/hutch/store.py",
]


def _commit(store: Store, config: hutchConfig, bot: Bot, conversation_id: str,
            fmt: str, filename: str, title: str, spec: dict) -> tuple[str, bytes, dict]:
    """Create a document through the real generate→validate→stage→commit protocol."""
    generated = generate(fmt, spec)
    storage = DocumentStorage(config)
    staged = storage.stage_bytes(uuid.uuid4().hex[:16], fmt, filename, generated.data)
    doc_id = new_document_id()
    row = {"version": 1, "filename": filename, "storage_name": staged.storage_name,
           "mime": {"pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    "csv": "text/csv; charset=utf-8"}[fmt],
           "bytes": staged.bytes, "sha256": staged.sha256,
           "storage_path": storage.version_rel_path(doc_id, 1, staged.sha256, staged.storage_name),
           "source": "generated", "generator": generated.generator,
           "validation_state": generated.validation_state,
           "findings": generated.findings, "preview_mode": generated.preview_mode,
           "preview_data": generated.preview_data, "page_count": generated.page_count,
           "source_spec": spec}
    storage.commit(staged, doc_id, 1, insert_row=lambda: store.create_document(
        document_id=doc_id, bot_id=bot.id, conversation_id=conversation_id,
        title=title, fmt=fmt, version=row))
    return doc_id, generated.data, row


def main() -> int:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = ROOT / "docs" / "realignment" / "artifacts" / f"document-pipeline-{date}"
    out_dir.mkdir(parents=True, exist_ok=True)
    state = Path(tempfile.mkdtemp(prefix="hutch-doc-capture-"))
    os.environ["HUTCH_STATE_DIR"] = str(state)
    os.environ.setdefault("HUTCH_ALLOWED_HOSTS", "127.0.0.1 testserver localhost")

    import uvicorn
    from playwright.sync_api import sync_playwright

    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error",
                                           lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    base = f"http://127.0.0.1:{port}"

    config = hutchConfig(state_dir=state)
    store = Store(config)
    bot = Bot(name="doc-capture", model="mock/demo", tools=["files", "documents"],
              approval_mode=ApprovalMode.auto)
    store.create_bot(bot)
    conversation, _ = store.create_conversation(bot_id=bot.id, title="Document capture",
                                                idem_key=f"capture-{uuid.uuid4().hex}",
                                                request_hash="capture")

    # --- acceptance documents through the real pipeline -----------------------
    report_spec = {
        "title": "Field Operations Review",
        "subtitle": "Prepared by the operations assistant",
        "blocks": [
            {"h1": "Field Operations Review"}, {"p": "This quarterly review summarises "
             "field activity across the three regions, with order volumes, response times and the "
             "follow-up commitments raised during the June site visits. " * 3},
            {"h2": "Regional order volumes"}, {"p": "The table below lists per-region order "
             "counts with their month-over-month change. Values are illustrative fixture data, "
             "generated locally by Hutch's document pipeline."},
            {"table": {"header": ["Region", "Orders", "Change", "Notes"],
             "rows": [[f"Region {chr(65 + i)}", str(120 + i * 37), f"+{6 + i}%",
                       "Follow-ups scheduled" if i % 2 == 0 else "Steady"] for i in range(12)]}},
            {"h2": "Response times"}, {"p": "Median response time stayed inside the "
             "four-hour commitment in every region. The northern depot improved most after the "
             "roster change described in the next section."},
            {"bullets": ["Northern depot: median 2h41m, down from 3h22m",
                         "Southern depot: median 3h05m, unchanged",
                         "Eastern depot: median 3h44m, improving after staffing"]},
            {"quote": "Every number in this report traces to the accompanying workbook, "
                      "including the totals that were computed and cached at generation time."},
            {"h2": "Follow-up commitments"},
            {"numbers": ["Confirm the northern roster change with the depot lead",
                         "Publish the response-time dashboard to the regional group",
                         "Re-review volumes after the July promotion window"]},
        ] + [block for i in range(4) for block in (
            {"pagebreak": True},
            {"h2": f"Appendix {chr(65 + i)}"},
            {"p": "Additional supporting detail for the appendix section, deliberately repeated "
                  "to exercise multi-page pagination, headers and footers in the rendered "
                  "output. " * 6},
        )],
    }
    tracker_spec = {
        "sheets": [{
            "name": "Orders", "header": ["Order ID", "Region", "Units", "Unit price", "Total"],
            "freeze_header": True,
            "rows": ([[f"00{i:02d}", f"Region {chr(65 + i % 3)}", 3 + (i * 7) % 23,
                       19.5 + (i % 4) * 2.5,
                       {"formula": f"=C{i + 2}*D{i + 2}", "value": (3 + (i * 7) % 23) * (19.5 + (i % 4) * 2.5)}]
                      for i in range(40)]
                     + [["", "", "", "Total",
                         {"formula": "=SUM(E2:E41)", "value": sum((3 + (i * 7) % 23) * (19.5 + (i % 4) * 2.5) for i in range(40))}]]),
        }],
    }
    deck_spec = {"slides": [
        {"layout": "title", "title": "Field Operations Review", "subtitle": "Quarterly summary — prepared locally"},
        {"title": "Regional order volumes", "bullets": [
            "Region A: 120 orders, +6% month over month",
            "Region B: 157 orders, +7% month over month",
            "Region C: 194 orders, +8% month over month"]},
        {"title": "Response times", "bullets": [
            "Every region inside the four-hour commitment",
            "Northern depot improved most after the roster change"]},
        {"title": "Follow-up commitments", "bullets": [
            "Confirm the northern roster change",
            "Publish the response-time dashboard",
            "Re-review volumes after the July window"],
         "notes": "Owner asked for these three commitments verbatim."},
    ]}
    seeds = []
    for fmt, filename, title, spec in [
        ("pdf", "field-operations-review.pdf", "Field Operations Review", report_spec),
        ("xlsx", "orders-tracker.xlsx", "Orders tracker", tracker_spec),
        ("pptx", "operations-review-deck.pptx", "Operations deck", deck_spec),
        ("csv", "orders-summary.csv", "Orders summary",
         {"header": ["Region", "Orders"], "rows": [["A", 120], ["B", 157], ["C", 194]]}),
    ]:
        doc_id, data, row = _commit(store, config, bot, conversation["id"], fmt, filename, title, spec)
        if fmt == "pdf":
            # the create_document tool does this after commit; the capture path does too
            from hutch.documents.docgen.render import render_pdf_pages
            version_dir = config.documents_dir.joinpath(*row["storage_path"].split("/")[:-1])
            row["preview_data"]["rendered_pages"] = render_pdf_pages(data, version_dir)
            store.set_document_preview(doc_id, 1, row["preview_mode"], row["preview_data"])
        seeds.append((doc_id, filename, data, row))
        (out_dir / filename).write_bytes(data)
        # copy the rendered page images the pipeline produced for the pdf
        if fmt == "pdf":
            version_dir = config.documents_dir.joinpath(*row["storage_path"].split("/")[:-1])
            pages = sorted(version_dir.glob("preview-*.png"))
            for page in pages:
                shutil.copy(page, out_dir / f"pdf-{page.name}")
    store.close()

    evidence = {
        "test": "documents pipeline acceptance capture",
        "command": ".venv/bin/python docs/realignment/capture_documents.py",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "state_dir": "temporary empty directory; no provider calls",
        "browser": {},
        "source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                          for p in SOURCE_FILES if (ROOT / p).exists()},
        "documents": {doc_id: {"filename": filename, "bytes": len(data),
                               "sha256": hashlib.sha256(data).hexdigest()}
                      for doc_id, filename, data, _row in seeds},
        "viewports": [],
    }

    with sync_playwright() as p:
        browser = p.chromium.launch()
        evidence["browser"]["chromium"] = browser.version
        evidence["browser"]["playwright"] = package_version("playwright")
        for name, width, height in VIEWPORTS:
            page = browser.new_page(viewport={"width": width, "height": height})
            overflow = page.evaluate("document.documentElement.scrollWidth")
            page.goto(f"{base}/#/chat/doc-capture")
            page.wait_for_selector("#composer-menu-btn", timeout=15_000)
            page.click("#composer-menu-btn")
            page.click("#conversation-files-open")
            page.locator(".document-card").first.wait_for(state="visible", timeout=15_000)
            overflow = page.evaluate(
                "Math.max(document.documentElement.scrollWidth - window.innerWidth, 0)")
            page.screenshot(path=str(out_dir / f"files-{name}.png"), full_page=False)
            evidence["viewports"].append({"name": name, "width": width, "height": height,
                                          "surface": "files", "overflow": overflow})
            if name == "desktop":
                def reopen_files():
                    page.click("#composer-menu-btn")
                    page.click("#conversation-files-open")
                    page.locator(".document-card").first.wait_for(state="visible", timeout=15_000)

                # The Files list and each preview share one modal root, so reopen the
                # list after every Escape.
                page.click(f"[data-doc-preview='{seeds[3][0]}']")
                page.locator("#doc-preview-body").wait_for(state="visible", timeout=10_000)
                page.screenshot(path=str(out_dir / "preview-structure-csv.png"))
                page.keyboard.press("Escape")
                reopen_files()
                page.click(f"[data-doc-preview='{seeds[0][0]}']")
                page.locator(".document-pages img").first.wait_for(state="visible", timeout=20_000)
                page.wait_for_timeout(1500)
                page.screenshot(path=str(out_dir / "preview-pages-pdf.png"))
                first_page = page.locator(".document-pages img").first
                first_page.scroll_into_view_if_needed()
                first_page.screenshot(path=str(out_dir / "preview-page-1-zoom.png"))
                page.keyboard.press("Escape")
                reopen_files()
                page.click("[data-doc-versions]")
                page.locator("#doc-versions-list").wait_for(state="visible", timeout=10_000)
                page.screenshot(path=str(out_dir / "versions-dialog.png"))
            page.close()
        browser.close()

    server.should_exit = True
    thread.join(timeout=10)
    shutil.rmtree(state, ignore_errors=True)
    (out_dir / "validation.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(f"captured {len(evidence['viewports'])} viewport surfaces and {len(seeds)} documents")
    print(f"evidence: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
