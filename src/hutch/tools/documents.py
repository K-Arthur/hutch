"""Document tools: create validated, durably stored documents from typed content.

The model drafts a structured content specification; deterministic renderers produce the
bytes, validators gate them, and the storage layer commits an immutable version. The
model never supplies file bytes or paths: the storage name is derived from the requested
filename, the display filename is preserved separately, and the download route is built
from the committed document id. Creation is ask-by-default (sticky key
``documents:create``) and receives the same intent/receipt bracketing as file writes.
"""

from __future__ import annotations

import json
import re
from pathlib import PurePosixPath
from typing import Any

from ..documents import (MIME_BY_FORMAT, MAX_DOCUMENTS_PER_RUN, DocumentStorage,
                         new_document_id, new_job_id)
from ..documents.docgen import DocumentGenerationError, generate, supported_formats
from ..documents.docgen.render import RenderError, render_pdf_pages
from ..documents.storage import DocumentStorageError
from ..safety import Decision, Verdict
from .base import Tool, ToolContext, ToolResult, _schema, rehearsed

_DOCUMENT_ID_FULL_RE = re.compile(r"^doc_[0-9a-f]{16}$")

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
    ``preview_data``; any failure (``RenderError`` or an unexpected renderer crash)
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
                "source_spec": _bounded_spec(spec),
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


class ReviseDocumentTool(Tool):
    name = "revise_document"
    description = ("Create the next version of an existing document from a revised content "
                   "specification. The previous version stays downloadable; refuses on a "
                   "concurrent revision.")
    parameters = _schema(
        ["document_id", "expected_version", "content"],
        {
            "document_id": {"type": "string", "description": "The document to revise (doc_…)"},
            "expected_version": {"type": "integer", "description":
                                 "The version you saw (inspect_document); revision refuses otherwise"},
            "content": {"type": "object", "description":
                        "The full revised content specification, same shape as create_document"},
        },
    )

    def effect(self, args: dict[str, Any], ctx: ToolContext) -> str:
        return "fs"

    def recorded_arguments(self, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        content = args.get("content")
        return {"document_id": args.get("document_id"),
                "expected_version": args.get("expected_version"),
                "content_summary": _describe_spec("",
                                                  content if isinstance(content, dict) else {})}

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        doc_id = str(args.get("document_id", ""))
        expected = args.get("expected_version")
        spec = args.get("content")
        if not _DOCUMENT_ID_FULL_RE.fullmatch(doc_id):
            return ToolResult(ok=False, output="error: provide the document id (doc_…)")
        if not isinstance(expected, int) or expected < 1:
            return ToolResult(ok=False, output="error: expected_version must be the integer version you inspected")
        if not isinstance(spec, dict) or not spec:
            return ToolResult(ok=False, output="error: content must be a non-empty content specification")
        doc = ctx.store.get_document(doc_id)
        if doc is None:
            return ToolResult(ok=False, output=f"error: no such document: {doc_id}")
        if doc["bot_id"] != ctx.bot.id:
            return ToolResult(ok=False, output="error: this document belongs to a different bot")
        fmt = str(doc["format"])
        if fmt not in supported_formats():
            return ToolResult(ok=False, output=f"error: this build cannot render {fmt} documents")
        current = ctx.store.get_document_version(doc_id, int(doc["current_version"]))
        if current is None:
            return ToolResult(ok=False, output="error: the current version record is missing")
        if ctx.dry_run:
            return rehearsed(f"revise {current['filename']} to v{doc['current_version'] + 1}",
                             _DOCUMENT_DECISION)
        try:
            ctx.gate.decide("documents", f"revise {current['filename']} (v{doc['current_version']} → v{doc['current_version'] + 1})",
                            {"document_id": doc_id, "expected_version": expected,
                             "filename": current["filename"],
                             "content_summary": _describe_spec(fmt, spec)},
                            _DOCUMENT_DECISION)
        except Exception as exc:
            return ToolResult(ok=False, output=f"error: {exc}")
        if int(doc["current_version"]) != expected:
            return ToolResult(ok=False, output=(
                f"error: the document moved on: current version is v{doc['current_version']}, "
                f"you inspected v{expected}. Inspect it again and re-apply your change."))
        if ctx.store.count_run_documents(ctx.run.id) >= MAX_DOCUMENTS_PER_RUN:
            return ToolResult(ok=False, output="error: this run reached its document limit")
        try:
            generated = generate(fmt, spec)
        except DocumentGenerationError as exc:
            return ToolResult(ok=False, output=f"error: the revised content was rejected ({exc})")
        storage = DocumentStorage(ctx.config)
        next_version = expected + 1
        try:
            staged = storage.stage_bytes(new_job_id(), fmt, current["filename"], generated.data)
            version_row = {
                "version": next_version,
                "filename": current["filename"],
                "storage_name": staged.storage_name,
                "mime": current["mime"],
                "bytes": staged.bytes,
                "sha256": staged.sha256,
                "storage_path": storage.version_rel_path(doc_id, next_version, staged.sha256,
                                                         staged.storage_name),
                "source": "revised",
                "run_id": ctx.run.id,
                "generator": generated.generator,
                "validation_state": generated.validation_state,
                "findings": generated.findings,
                "preview_mode": generated.preview_mode,
                "preview_data": generated.preview_data,
                "page_count": generated.page_count,
                "source_spec": _bounded_spec(spec),
            }

            def insert_row() -> None:
                ctx.store.add_document_version(doc_id, expected, version_row)

            storage.commit(staged, doc_id, next_version, insert_row=insert_row)
        except ValueError as exc:
            return ToolResult(ok=False, output=(
                f"error: {exc}. Inspect the document again and re-apply your change."))
        except DocumentStorageError as exc:
            return ToolResult(ok=False, output=f"error: {exc}")
        except Exception as exc:
            return ToolResult(ok=False, output=f"error: the revision could not be committed ({exc})")
        preview_note = ""
        if fmt == "pdf":
            preview_note = _render_pdf_preview(
                doc_id, version_row, data=generated.data,
                storage_path=version_row["storage_path"], config=ctx.config, store=ctx.store)
        ref = _document_ref(doc_id, version_row, title=str(doc["title"]), fmt=fmt)
        warnings = f"; {len(generated.findings)} note(s)" if generated.findings else ""
        return ToolResult(ok=True,
                          output=(f"revised {current['filename']} to v{next_version} "
                                  f"({staged.bytes:,} bytes, validation "
                                  f"{generated.validation_state}{warnings}{preview_note}); "
                                  f"v{expected} remains downloadable"),
                          data={"document": ref})


def _bounded_spec(spec: dict[str, Any], limit: int = 200_000) -> dict[str, Any]:
    """Store the source specification so revisions regenerate instead of reconstructing."""
    text = json.dumps(spec, ensure_ascii=False)
    if len(text) > limit:
        raise DocumentGenerationError("the content specification exceeds the stored-source limit")
    return spec


class InspectDocumentTool(Tool):
    name = "inspect_document"
    description = ("Inspect a stored document: its content specification (for revisions), "
                   "extracted text or structure, and version list.")
    parameters = _schema(
        ["document_id"],
        {"document_id": {"type": "string", "description": "The document to inspect (doc_…)"},
         "version": {"type": "integer", "description": "Specific version (default: current)"}},
    )

    def effect(self, args: dict[str, Any], ctx: ToolContext) -> str:
        return ""

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        doc_id = str(args.get("document_id", ""))
        if not _DOCUMENT_ID_FULL_RE.fullmatch(doc_id):
            return ToolResult(ok=False, output="error: provide the document id (doc_…)")
        doc = ctx.store.get_document(doc_id)
        if doc is None:
            return ToolResult(ok=False, output=f"error: no such document: {doc_id}")
        requested = args.get("version")
        version_number = int(requested) if isinstance(requested, int) and requested >= 1             else int(doc["current_version"])
        row = ctx.store.get_document_version(doc_id, version_number)
        if row is None:
            return ToolResult(ok=False, output=f"error: no version {version_number} of {doc_id}")
        lines = [
            f"{doc['title']} ({doc['format']}) v{version_number} of {doc['current_version']}",
            f"file {row['filename']} · {row['bytes']:,} bytes · sha256 {row['sha256'][:16]}… · "
            f"validation {row['validation_state']}",
        ]
        for finding in row.get("validation_findings") or []:
            lines.append(f"note: {finding.get('code', 'finding')}: {finding.get('detail', '')}")
        spec = row.get("source_spec") or {}
        if spec:
            lines.append("content specification (revise this):")
            lines.append(json.dumps(spec, ensure_ascii=False)[:20_000])
        else:
            lines.append("content specification: not stored for this version")
        preview = row.get("preview_data") or {}
        text = preview.get("text")
        if isinstance(text, str) and text:
            lines.append("extracted content (truncated):")
            lines.append(text[:8_000])
        versions = ctx.store.list_document_versions(doc_id, limit=20)
        lines.append("versions: " + ", ".join(
            f"v{v['version']} ({v['source']}, {v['validation_state']})" for v in versions))
        output = "\n".join(lines)[:24_000]
        return ToolResult(ok=True, output=output,
                          data={"document": _document_ref(doc_id, row,
                                                          title=str(doc["title"]),
                                                          fmt=str(doc["format"]))})

