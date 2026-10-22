# Hutch: first-class document & file pipeline — implementation plan

## Goal
Reliable local creation, revision, preview, and download of PDF, DOCX, XLSX, PPTX, plus text/Markdown/CSV/JSON/YAML and ZIP bundles, as **verified artifacts**: typed generation → safe immutable storage → validation gates → honest previews → hash-verified downloads → chat UI cards → docs + marketing-site updates, with visual validation throughout. Extend the existing verified text-artifact pipeline; never fake a format; classify honestly what is verified.

## Ground truth from exploration
- Hutch already ships a verified **text-only** artifact path: `save_artifact` (src/hutch/runtime/steps.py:100, ≤4MB `.txt`, 0400, sha256) → event refs → strict-regex download routes (src/hutch/server/app.py:3914–3975, hash-verified, nosniff) → Files cards in app.js (223–263, 4292–4333) + share grants. Document work extends this identity/verification model to binary formats.
- No document libraries installed; `write_file` is UTF-8 text-only; store migrations at v50 (add `_migrate_50` → "Schema v51" changelog convention); `config.downloads_dir` unused; website/ + claims governance + realignment evidence conventions + Playwright e2e/design-system tests all exist.
- **Branches**: no `master` exists; `main` is the integration branch (451 commits ahead of stale origin/main). `wcag22-audit-fixes` diverged from main 3↔2 commits; working tree is code-clean (only `.gitignore` + 9 trace zips).

## Slice 0 — integrate onto main (per your "work on master, no new branch")
1. Commit the in-flight `.gitignore` + artifact zips on `wcag22-audit-fixes`.
2. Merge `wcag22-audit-fixes` into `main` (main is checked out in `.worktrees/main-merge`; verify that worktree is clean, merge there — or if clean, remove it and merge in the primary checkout). Resolve likely server/static conflicts (routines work vs WCAG/quick-connect), run the test suite, commit the merge.
3. All feature work then lands **directly on main** with progressive commits. No pushes (origin untouched).
4. Environment probe → evidence ledger: `uv add` the new deps (repairs the stale venv once, updates pyproject/uv.lock); probe `soffice`, Pango, bundled/probed fonts; record availability.

## Dependencies (`uv add`, all permissive licenses, versions verified 2026-10-10)
python-docx 1.2.0 (MIT), XlsxWriter 3.2.9 (BSD-2), openpyxl 3.1.5 (MIT), python-pptx 1.0.2 (MIT), weasyprint 70 (BSD-3; needs system Pango — probe, **fallback reportlab** if absent), pypdf 6.20 (BSD-3), pypdfium2 5.14 (BSD/Apache, bundles PDFium). LibreOffice = **optional system dep**: absent → download-only office previews, honestly labeled.

## Architecture
**Data model (schema v51, `_migrate_50`):** `documents` (id `doc_<hex>`, bot_id, conversation_id, title, format, current_version, created_at) + `document_versions` (version int, display filename, mime, bytes, sha256, storage path, source generated|revised, run_id+seq provenance, generator versions, validation state+findings, preview state, page_count). Tool results also carry a `document:{id,version,sha256,bytes,name,mime,download_url}` ref in event data (chat rendering + SQL listing like today's `artifact_records`); DB rows give stable cross-restart identity.

**Storage:** `<state>/documents/<doc_id>/v<NN>-<sha8>/<filename>`; staging under `.staging/<job>/` → write+fsync → validate → rename-promote → fsync dir → DB insert; journal + reconciliation GC covers crash between rename and insert; 0700/O_NOFOLLOW/no-exec. Every change is a new version (CAS on expected version+sha); failed validation is never promoted as ready.

**Tools (`tools/documents.py`):** `create_document` (typed content spec: markdown-ish blocks for DOCX/PDF; sheets/cells for XLSX; slides for PPTX; text/rows for texty; manifest list for ZIP), `revise_document` (doc id, expected version, scoped edits), `inspect_document` (bounded extraction). The model drafts structured content; deterministic Python renders — never model-authored binaries, never trusted paths. Approval: new ask-by-default sticky key `documents:create`, effect "fs" with the existing intent/receipt bracketing.

**Generators (`src/hutch/documents/docgen/`)** with researched trap defenses baked in:
- DOCX (python-docx): semantic styles/tables/captions; edits never assign `paragraph.text` (python-docx#1251 run destruction) — run-level surgery.
- XLSX (XlsxWriter + openpyxl validator): `write_formula(..., value=)` cached results + auto calc mode (defeats "formulas show 0" — XlsxWriter#864/#877); typed cells, IDs as text, freeze/filters, UTF-8 BOM CSV.
- PPTX (python-pptx): `fit_text(font_file=probed)` instead of the inert autofit flag (#973); render every slide for check.
- PDF (WeasyPrint, sanitized HTML + print CSS): pre-styled tables (defeats #2417 clipping), custom url_fetcher denying `file://` + all network (vendor security guidance), subprocess-isolated with CPU/memory/time caps.
- Texty + ZIP: JSON/CSV parse-back validation, explicit encodings/newlines; ZIP manifest, safe relative paths, entry-count/size bounds.
- Shared brand-neutral document theme (not Hutch app colors, per mission).

**Validation gates (`docgen/validate.py`):** independent reopen (openpyxl/python-docx/pypdf), zip/XML integrity, placeholder scan, XLSX cached-value recompute spot-checks, page/cell/size bounds → states passed / passed_with_warnings / failed with findings. Generation ≠ validation ≠ preview ≠ download; retries re-run only the failed stage.

**Previews (`docgen/render.py` + routes):** PDF → pypdfium2 page PNGs (bounded count/DPI); DOCX/PPTX/XLSX → `soffice --headless` with per-job `-env:UserInstallation`, hard timeout, owned process group killed on cancel (defeats gotenberg#407/#516, unoconv#225/#299/#449 failure classes) → PDF → page PNGs, labeled "approximate render"; soffice absent → explicit download-only state.

**Server (app.py):** `GET /api/v1/documents` (list), `/{doc_id}` (detail+versions), `/{doc_id}/versions/{v}/download` (FileResponse: correct MIME, RFC 5987 unicode `filename*`, ETag=sha256, nosniff, range requests), `/versions/{v}/preview` (page manifest), `/versions/{v}/pages/{n}.png`; `GET /api/v1/documents/readiness` (per-format availability). Staging never served; hash verified at serve (extends `verified_artifact_response`); conversation listing via SQL over event JSON.

**Frontend (app.js/style.css):** `documentCardHtml` following the existing card patterns: format icon, name, size, version, validation badge (glyph+word — non-color state rule), Preview dialog (paginated images, lazy-loaded, alt "Page N of M — approximate render", focus trap/Escape/restore, aria-live status), Download, version-history disclosure, provenance line. New download-URL regexes mirrored server-side. Responsive 360/768/1440, keyboard-only, reduced-motion.

## Failure-class defenses (user-complaint evidence → mechanism)
Documented as a traceability table (new `docs/research/document-pipeline-failures-2026-10-10.md` + evidence-ledger rows): session-scoped downloads dying (OpenAI community 769469/793962/1247404) → durable local store; generated-but-unreachable files (open-webui#27984/#30340, GPT-4.1 /mnt/data orphans) → first-class records + event refs; preview≠downloaded-bytes (open-webui#31912/#7241, Gemini stale/corrupt downloads) → content-addressed immutable versions, previews derived from the exact sha; 401-on-new-tab/expiring URLs (open-webui#28583) → same-origin session downloads, no signed URLs; "unreadable content" repair prompts (PhpSpreadsheet#4619/#2368) → validation gate before promotion; formulas-as-zero (XlsxWriter#864/#877/#926) → real cached values + recompute checks; LO headless lockups (gotenberg#407/#516, unoconv#225/#299/#449) → per-job profiles/timeouts/kill; silent font substitution (wkhtmltopdf#4949/#4703) → font probe + embedding + fit_text; data mangling (pandas#59882/#60230, CSV mojibake) → explicit typing + BOM; download-path bugs (nextcloud#59152/#27354, iOS Safari blob limits) → `filename*`, range, streaming, no blob-only paths.

## Tests & acceptance
Unit tests per generator/validator/migration/route (TestClient); crash-injection tests for the staging→promote protocol; e2e Playwright download flow (saved bytes hash-compared + reopened); acceptance subset: 10–15-page report (PDF+DOCX), multi-sheet workbook with formulas + verified cached values, 8–12-slide deck, ZIP bundle, targeted DOCX revision preserving unrelated content, unicode-filename download, staging crash recovery, cross-conversation access denial, soffice-absent honest state. Evidence under `docs/realignment/artifacts/document-pipeline-2026-10-10/` (validation.json, viewport PNGs, overflow=0, source sha256s — existing conventions). Formats classified verified / implemented-unverified / unsupported.

## Visual validation (not skipped)
1. **Documents**: render every page of acceptance artifacts via pypdfium2 → dispatch visual-judge agents on the PNG sets; bounded repair loop on findings.
2. **UI**: Playwright captures at 360/768/1440 → visual-judge; overflow + a11y assertions via the design-system test extensions.
3. **Website**: post-change captures at three widths → visual-judge + `tests/e2e/test_website.py` green.

## Marketing website
`website/index.html`: a "Files & documents" feature block + 2–3 new receipts-table rows citing the researched public reports (session-expired ChatGPT download links; open-webui#27984; XlsxWriter#864) with hutch answers — copy constrained to **post-verification** claims per `docs/marketing-site.md` governance (that doc updated too). Rebuild via `npm run build:css` (hash stamping); `tests/test_site_tokens.py` + website e2e; recapture screenshots per provenance rules.

## Docs
CHANGELOG (Schema v51 block + entries, repo style); docs/architecture.md + docs/operations.md (storage layout, bounds/retention, optional LibreOffice); new docs/file-formats.md capability matrix; docs/marketing-site.md; new research file; README feature list; docs/realignment/evidence-ledger.md rows.

## Execution & orchestration
Per your `/workflow`: implementation runs through CreateWorkflow scripts in phases with me as integrator, committing at every slice gate on main (no push). Phases: (A) slice 0–1 merge/probe/research; (B) schema+storage+text formats end-to-end; (C) office/PDF generators (file-disjoint fan-out) + preview pipeline; (D) frontend; (E) revisions + e2e + acceptance; (F) website + docs; (G) visual-validation wave, repairs, final report. Tests run via the repo convention (`.venv/bin/python -m pytest -q`) after `uv sync` repairs the venv.

## Explicit v1 limits (classified honestly, not hidden)
Arbitrary imported DOCX/PPTX targeted edits are reconstruction-level and disclosed as such (generated documents get true scoped revisions); no VBA, no password bypass, no cloud delivery in this slice (connections later); one PDF engine; office previews are approximate renders. All recorded in file-formats.md and reflected in marketing copy.