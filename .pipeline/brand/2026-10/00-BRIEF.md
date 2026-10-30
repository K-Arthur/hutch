# 00-BRIEF - Hutch brand identity pipeline (Run 4 / Pipeline Run 7, Slice 7A)

PROJECT: Hutch - local-first, open-source multi-bot agent platform ("Your bots. Your machine. Your rules.")
REPO_ROOT: /home/kevina/CodingProjects/hutch
SITE_APP_PATH: website/ (marketing site), src/hutch/server/ (dashboard)
DOCS_PATH: docs/
NATIVE_TARGETS: desktop (Tauri/Rust), web; CLI entry point
EXISTING_BRAND_DOCS: docs/brand-assets.md, docs/design-system.md, DESIGN.md, PRODUCT.md, website/tokens.json, THIRD_PARTY_NOTICES.md
ARTIFACT_DIR: .pipeline/brand/2026-10
TODAY: 2026-10-29
RUN: 4 (Master Prompt implementation stage; Pipeline Run 7, Slice 7A)
HUMAN_AUTHORITY: Explicit dated human authorisation (2026-10-29, D57) to execute Slice 7A; local commits only; never push/deploy/merge without explicit instruction.
CONCURRENCY: Main tree has uncommitted edits on app/src/, src/hutch/server/static/*, src/hutch/server/templates/*, tests/e2e/* from another session. Slice 7A touches only clean paths; never revert, reformat or stage another session's work; never read .worktrees/.
JURISDICTIONS: US, EU, UK, Canada; Nice Classes 9 and 42 (D13)
LICENCE_POSTURE: Open-source (MIT code, SIL OFL 1.1 fonts), zero external spend (D15); IP risk owned by maintainer in writing (D20/D23/D28/D38/D57)
BUDGET: <=15 files read per pass; 3-File / 1-Seam rule per slice; one slice per session

## Scope (this run - Slice 7A: Licence, Font & Brand Docs Reconciliation)
1. Stage production wordmark font subset (`bricolage-grotesque-latin-800.woff2`) and verbatim OFL 1.1 licence (`OFL-bricolage-grotesque.txt`) into `website/assets/fonts/` and `src/hutch/server/static/fonts/`.
2. Reconcile `THIRD_PARTY_NOTICES.md` and distributed copies (`website/THIRD_PARTY_NOTICES.txt`, `src/hutch/server/static/THIRD_PARTY_NOTICES.txt`) to attribute shipped `Geist`, `Geist Mono`, and `Bricolage Grotesque` (resolving B9 stale `Archivo` notice).
3. Update `docs/brand-assets.md` and `docs/design-system.md` to document the decided `"Visor Hutch"` mark (D54), `"hutch."` wordmark (D42), and `website/tokens.json` / `COLOUR-SYSTEM.md` neutral/light-surface rules (closing B10 doc drift).

## Non-goals
No HTML/CSS/JS edits to `website/index.html` (Slice 7B) or `src/hutch/server/` templates/SPA (Slice 7C); no legal clearance or non-infringement claims; no touch of other sessions' uncommitted files; no push/deploy.

## Success criteria
Font subsets + OFL licences staged and checksum-verified; `THIRD_PARTY_NOTICES.md` + `.txt` mirrors, `docs/brand-assets.md`, and `docs/design-system.md` updated; visual proof sheet rendered and inspected; `EVIDENCE.md`, `REVIEW.md`, `CHANGES.md`, `DECISION.md`, `ASSET-INVENTORY.md`, `HANDOFF.md`, and `NEXT-PROMPT.md` complete.
