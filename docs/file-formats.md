# File formats: capability matrix and limits

Status vocabulary (mirrors the realignment conventions): **verified** (deterministic tests + visual
inspection passed on this host, dated), **implemented-unverified** (code ships behind a probe but no
live engine/environment exercised it here), **experimental**, **unsupported** (named, not disguised).
Claims governance: the marketing site may state only what this file marks verified, per
[marketing-site.md](marketing-site.md).

Failure-class motivation for each decision: [research/document-pipeline-failures-2026-10-10.md](research/document-pipeline-failures-2026-10-10.md)
(evidence rows E1–E15 in [realignment/evidence-ledger.md](realignment/evidence-ledger.md#e-document-pipeline-failure-reports-read-2026-10-10)).

## Creation formats

| Format | Engine (pinned) | Creation | Structural validation | Preview | Target end state |
|---|---|---|---|---|---|
| PDF | WeasyPrint 70 (Pango) in a bounded subprocess; pypdf check; page images via pypdfium2 (bundled PDFium) | typed block spec → hutch-authored HTML → PDF | reopen via pypdf: page tree, text extraction spot-check, byte bounds | paginated page images (rendered from the exact version) | **verified 2026-10-11** |
| DOCX | python-docx 1.2 | typed block spec (headings, paragraphs, lists, tables, captions) | reopen via python-docx + zip/XML part integrity | structure preview (extracted outline + tables) | **verified 2026-10-11** |
| XLSX | XlsxWriter 3.2 (write) + openpyxl 3.1 (validate/read) | typed cells, formulas with cached results, number formats, freeze/filters | reopen via openpyxl: cached-value recompute, cell types, dimensions | sheet grid preview (values as cached; formatting not shown) | **verified 2026-10-11** |
| PPTX | python-pptx 1.0 | slide spec with `fit_text()` on probed fonts, notes, tables | reopen via python-pptx: slide count, shape bounds | per-slide text outline preview | **verified 2026-10-11** |
| Markdown / text | direct write | UTF-8, explicit newlines | encoding + newline policy check | inline text | **verified 2026-10-11** |
| CSV | direct write | UTF-8 with BOM, typed serialization | parse-back with csv module; formula-prefix guard (disclosed) | bounded table preview | **verified 2026-10-11** |
| JSON | direct write | UTF-8 | parse-back (stdlib) + size bounds | pretty text preview | **verified 2026-10-11** |
| YAML | PyYAML | UTF-8 | parse-back | text preview | **verified 2026-10-11** |
| ZIP bundle | stdlib zipfile | manifest + safe relative paths, entry/size/depth caps | manifest completeness check, entry audit | manifest listing | **verified 2026-10-11** |

## Editing and conversion

| Capability | State | Limit stated to users |
|---|---|---|
| Scoped revision of a document hutch generated | implemented — `revise_document` compares-and-swaps on the expected version; the stored source specification grounds edits (2026-10-11) | true scoped edits on the stored typed source; unrelated content preserved byte-for-byte where the format allows |
| Revision of an imported arbitrary DOCX/PPTX | unsupported v1 | disclosed as reconstruction, never silently rewritten (E7) |
| Layout-accurate office preview (DOCX/XLSX/PPTX → page images) | implemented-unverified on this host | requires operator-installed LibreOffice (`soffice`); per-job profile, hard timeout, owned process group (E10); preview is an approximate render either way |
| PDF-to-editable conversion | unsupported | would be reconstruction; not offered |
| Redaction / metadata scrubbing | unsupported v1 | not offered; do not confuse with cosmetic hiding |
| VBA macros, password-protected inputs | unsupported | never bypassed |
| Cloud/connector delivery of documents | open (roadmap) | not in this slice |

## Storage, retention, and serving

- Versions are immutable and content-addressed (SHA-256 recorded in SQLite, re-verified before each
  download; `X-Hutch-Artifact-Verified` header). Restoring an old version creates a new current
  revision; history is never rewritten.
- Bounds (engine-enforced): per-file 32 MB, per-run documents 16 files, preview render ≤ 60 pages ×
  ≤ 1600 px, soffice job wall clock 120 s, ZIP entries ≤ 512, uncompressed bundle ≤ 64 MB.
- There is no automatic deletion of promoted versions in v1; abandoned staging is reconciled at
  startup after the owning run is gone. Owner-initiated deletion is roadmap.

## Readiness probe

`GET /api/v1/documents/readiness` reports per format: engine importability, renderer availability
(`soffice` present? pypdfium2 loaded?), font set probed, and the resulting preview mode
(`pages` / `structure` / `download_only`). The UI renders these states honestly instead of
pretending a preview exists.

## Verification log (updated as evidence lands)

- 2026-10-10 — stack smoke on this host: WeasyPrint→PDF (selectable text), pypdfium2 page render,
  pypdf reopen, python-docx roundtrip, XlsxWriter cached formula read back as the true value by
  openpyxl, python-pptx roundtrip. See `uv.lock` pins; evidence rows E15.
- 2026-10-11 — creation formats verified on this host: 60 generator/validator/store/API tests plus
  64 pipeline/revision tests green (`tests/test_docgen_*.py`, `tests/test_documents_*.py`); a real
  browser journey downloaded byte-identical files and labelled previews
  (`tests/e2e/test_documents.py`, Chromium 153); the acceptance report (6 pages, headed sections,
  a 12-row table, lists, quote, appendices) was visually judged page-by-page with no clipping,
  missing glyphs or blank pages, and the workbook's SUM formulas were recomputed against the cached
  values at validation time. Evidence: `docs/realignment/artifacts/document-pipeline-2026-10-11/`
  (documents, page renders, three-viewport UI captures with overflow 0, validation.json).
- 2026-10-11 — completion check found the ZIP bundle generator missing while the matrix
  already claimed it; implemented (`docgen/bundle.py`: manifest audit, CRC re-open, path
  safety, 512-entry/64 MB bounds) and gated by `tests/test_docgen_bundle.py`, then an
  end-to-end tool smoke. Logged here because the claim briefly ran ahead of the code.
- 2026-10-11 — still implemented-unverified on this host: LibreOffice layout rendering for office
  formats (`soffice` absent; the path is skipif-gated in `tests/test_docgen_render.py`), and all
  Word/Excel/PowerPoint desktop-compatibility, physical-phone and screen-reader checks (not exercised).
