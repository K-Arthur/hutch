"""Document tools — create validated, durably stored documents from typed content.

The model drafts a structured content specification; deterministic renderers produce the
bytes, validators gate them, and the storage layer commits an immutable version. The
model never supplies file bytes or paths: the storage name is derived from the requested
filename, the display filename is preserved separately, and the download route is built
from the committed document id. Creation is ask-by-default (sticky key
``documents:create``) and receives the same intent/receipt bracketing as file writes.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from ..documents import (MIME_BY_FORMAT, MAX_DOCUMENTS_PER_RUN, DocumentStorage,
                         new_document_id, new_job_id)
from ..documents.docgen import DocumentGenerationError, generate, supported_formats
from ..documents.docgen.render import RenderError, render_pdf_pages
from ..documents.storage import DocumentStorageError
from ..safety import Decision, Verdict
from .base import Tool, ToolContext, ToolResult, _schema, rehearsed

_DOCUMENT_DECISION = Decision(
    verdict=Verdict.ask,
    reason="creating a document writes a new durable file",
    sticky_key="documents:create",
    rule="documents:create",
    risk="low",
)


def _document_ref(doc_id: str, version_row: dict[str, Any], *, title: str, fmt: str) -> dict[str, Any]:
    return {
        "id": doc_id,
        "version": int(version_row["version"]),
        "name": version_row["filename"],
        "format": fmt,
        "mime": version_row["mime"],
        "bytes": int(version_row["bytes"]),
        "sha256": version_row["sha256"],
        "title": title,
        "validation_state": version_row["validation_state"],
        "validation_findings": version_row.get("validation_findings",
                                               version_row.get("findings", [])),
        "preview_mode": version_row["preview_mode"],
        "download_url": f"/api/v1/documents/{doc_id}/versions/{int(version_row['version'])}/download",
        "created_at": version_row.get("created_at", ""),
    }


def _describe_spec(fmt: str, spec: dict[str, Any]) -> str:
    """Short human summary for the approval card; the full spec stays out of receipts."""
    if not isinstance(spec, dict):
        return "invalid content"
    if "text" in spec and isinstance(spec["text"], str):
        return f"{len(spec['text']):,} characters of text"
    if "value" in spec:
        return "structured value"
    if "rows" in spec:
        rows = spec.get("rows") or []
        header = spec.get("header")
        extra = " +header" if header else ""
        return f"{len(rows):,} data rows{extra}"
    if "blocks" in spec:
        return f"{len(spec.get('blocks') or [])} content blocks"
    if "sheets" in spec:
        return f"{len(spec.get('sheets') or [])} sheets"
    if "slides" in spec:
        return f"{len(spec.get('slides') or [])} slides"
    if "files" in spec:
        return f"{len(spec.get('files') or [])} bundled files"
    return "content"


def _render_pdf_preview(doc_id: str, version_row: dict[str, Any], *,
                        data: bytes, storage_path: str, config, store) -> str:
    """Render page previews for a committed pdf and record the outcome on its version row.

    The version directory is derived from the storage path the store committed (its parts
    minus the file name, under ``documents_dir``). Success records ``rendered_pages`` on
    ``preview_data``; any failure — ``RenderError`` or an unexpected renderer crash —
    downgrades ``preview_mode`` to ``download_only`` with a ``preview_render_failed``
    finding appended to the stored findings. The document itself stays valid and
    downloadable: generation and storage are never failed by preview rendering. Returns a
    short note for the tool output ("" when previews rendered normally).
    """
    version_dir = config.documents_dir.joinpath(*PurePosixPath(storage_path).parts[:-1])
    preview_error: str | None = None
    try:
        rendered = render_pdf_pages(data, version_dir)
    except RenderError as exc:
        preview_error = str(exc)
    except Exception as exc:  # a renderer crash must never fail a committed document
        preview_error = f"the preview renderer failed unexpectedly: {exc}"
    if preview_error is None:
        preview_data = dict(version_row["preview_data"])
        preview_data["rendered_pages"] = rendered
        store.set_document_preview(doc_id, int(version_row["version"]),
                                   version_row["preview_mode"], preview_data)
        version_row["preview_data"] = preview_data
        return ""
    stored = store.get_document_version(doc_id, int(version_row["version"]))
    findings = list(stored["validation_findings"]) if stored else list(version_row["findings"])
    findings.append({"code": "preview_render_failed", "detail": preview_error})
    store.set_document_preview(doc_id, int(version_row["version"]), "download_only",
                               dict(version_row["preview_data"]), findings=findings)
    version_row["preview_mode"] = "download_only"
    version_row["findings"] = findings
    return "; page previews are unavailable, the document is download-only"


class CreateDocumentTool(Tool):
    name = "create_document"
    description = (
        "Create a durable, validated document (pdf, docx, xlsx, pptx, md, txt, csv, json, yaml, zip) "
        "from a structured content specification. Returns a verified, downloadable version.")
    parameters = _schema(
        ["format", "filename", "title", "content"],
        {
            "format": {"type": "string", "enum": supported_formats(),
                       "description": "Output format; unsupported formats are refused, never approximated"},
            "filename": {"type": "string", "description": "Display filename, e.g. 'Q4 report.pdf'"},
            "title": {"type": "string", "description": "Human title recorded as document metadata"},
            "content": {"type": "object", "description":
                        "Format-specific content: {text} for txt/md; {value} for json/yaml; "
                        "{header, rows} for csv; {blocks} for docx/pdf; {sheets} for xlsx; "
                        "{slides} for pptx; {files, manifest} for zip"},
        },
    )

    def effect(self, args: dict[str, Any], ctx: ToolContext) -> str:
        return "fs"

    def recorded_arguments(self, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        content = args.get("content")
        return {"format": args.get("format"), "filename": args.get("filename"),
                "title": args.get("title"),
                "content_summary": _describe_spec(str(args.get("format")), content)
                if isinstance(content, dict) else "invalid content"}

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        fmt, filename = str(args.get("format", "")), str(args.get("filename", "")).strip()
        title = str(args.get("title", "")).strip() or filename or "Untitled document"
        spec = args.get("content")
        if fmt not in supported_formats():
            return ToolResult(ok=False, output=(
                f"error: unsupported format '{fmt}'; supported: {', '.join(supported_formats())}"))
        if not filename or len(filename) > 200:
            return ToolResult(ok=False, output="error: provide a filename of at most 200 characters")
        if ctx.dry_run:
            return rehearsed(f"create {filename} ({_describe_spec(fmt, spec)})", _DOCUMENT_DECISION)
        if ctx.store.count_run_documents(ctx.run.id) >= MAX_DOCUMENTS_PER_RUN:
            return ToolResult(ok=False, output=(
                f"error: this run already produced {MAX_DOCUMENTS_PER_RUN} documents; "
                "revise an existing document instead"))
        try:
            ctx.gate.decide("documents", f"create {filename} ({fmt})",
                            {"format": fmt, "filename": filename, "title": title,
                             "content_summary": _describe_spec(fmt, spec) if isinstance(spec, dict) else "invalid"},
                            _DOCUMENT_DECISION)
        except Exception as exc:
            return ToolResult(ok=False, output=f"error: {exc}")
        try:
            generated = generate(fmt, spec if isinstance(spec, dict) else {})
        except DocumentGenerationError as exc:
            return ToolResult(ok=False, output=f"error: the content was rejected before anything was stored ({exc})")
        storage = DocumentStorage(ctx.config)
        doc_id = new_document_id()
        try:
            staged = storage.stage_bytes(new_job_id(), fmt, filename, generated.data)
            version_row = {
                "version": 1,
                "filename": filename,
                "storage_name": staged.storage_name,
                "mime": MIME_BY_FORMAT[fmt],
                "bytes": staged.bytes,
                "sha256": staged.sha256,
                "storage_path": "",  # filled once the version directory is known
                "source": "generated",
                "run_id": ctx.run.id,
                "generator": generated.generator,
                "validation_state": generated.validation_state,
                "findings": generated.findings,
                "preview_mode": generated.preview_mode,
                "preview_data": generated.preview_data,
                "page_count": generated.page_count,
            }
            version_row["storage_path"] = storage.version_rel_path(
                doc_id, 1, staged.sha256, staged.storage_name)

            def insert_row() -> None:
                ctx.store.create_document(document_id=doc_id, bot_id=ctx.bot.id,
                                          conversation_id=ctx.run.conversation_id,
                                          title=title, fmt=fmt, version=version_row)
            storage.commit(staged, doc_id, 1, insert_row=insert_row)
        except DocumentStorageError as exc:
            return ToolResult(ok=False, output=f"error: {exc}")
        except Exception as exc:
            return ToolResult(ok=False, output=f"error: the document could not be committed ({exc})")
        preview_note = ""
        if fmt == "pdf":
            preview_note = _render_pdf_preview(
                doc_id, version_row, data=generated.data,
                storage_path=version_row["storage_path"], config=ctx.config, store=ctx.store)
        ref = _document_ref(doc_id, version_row, title=title, fmt=fmt)
        warnings = f"; {len(generated.findings)} note(s)" if generated.findings else ""
        return ToolResult(ok=True,
                          output=(f"created {filename} ({fmt}, {staged.bytes:,} bytes, "
                                  f"validation {generated.validation_state}{warnings}"
                                  f"{preview_note}); "
                                  f"document {doc_id} v1 is ready to download"),
                          data={"document": ref})
