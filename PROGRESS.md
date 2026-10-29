# Brand Program - Phase 0 (Planning)

Worktree: `.worktrees/brand-plan` (branch `brand/plan`), created from `main` @ 577e1154.
Main checkout `/home/kevina/CodingProjects/hutch` was not edited. Session scope: planning only - no
code, designs, or asset edits.
Deliverable: `docs/brand/00-PLAN.md` (sections A inventory, R research, B phases, C gap register,
D unknowns, risks, appendices).

## Done
- [x] Isolated worktree; branch `brand/plan`; main checkout untouched.
- [x] Recon: brief-declared paths vs actual repo (Next.js paths absent; equivalents documented in
      plan A.9), docs/ top-level listing, tracked asset/font inventory, deploy/test/build context.
- [x] Declared-input reads + evidence: token counts, 23 unique literal hex in declared files, 107
      custom props, WCAG contrast table (brand 10.35:1), surface/route inventory, asset formats,
      no PWA manifest/service worker, data-URI-only favicon, no press kit, no visual-regression
      tests, GitHub Pages deploy on push to main, Tauri bundle inactive with no icon list.
- [x] Four research streams delegated and delivered (shared tasks task-1..task-4 completed):
      category patterns + failure forensics + identity tax; IP/legal clearance + AI authorship +
      font/OSS licensing; platform icon/favicon constraints; frontend audit practice + rollout +
      do-no-harm + a11y. Sources carry URLs and retrieval date 2026-10-28; unverified items marked.
- [x] Plan written and reviewed: 907 lines, 32 gap-register rows (>=15 required), 26 explicit
      unknowns, 35 [COUNSEL] and 40 [HUMAN DECISION] flags, research citations with dates.
- [x] Final plan lint: no placeholders, no emoji, no banned "legally safe/unique/original" claims.

## In progress (file:function)
- None. Phase 0 complete pending maintainer review.

Phase 0 PR: https://github.com/K-Arthur/hutch/pull/11 (branch `brand/plan`).

## Next
- Maintainer review of 00-PLAN.md; resolve Phase 2 gate decisions (name, territories, budget,
  counsel, PWA/mobile scope).
- Phase 1: create `brand/audit` worktree, read the six existing brand/design docs, capture baseline
  screenshots/axe results, produce `docs/brand/01-AUDIT.md` + asset manifest.
- Do not start Phase 3 until the Phase 2 clearance protocol is signed off [COUNSEL] (G1).

## Blocked
- Brief-declared paths absent in this repo: `src/app/layout.*`, `src/styles/globals.css`,
  `tailwind.config.*` (Tailwind v4 CSS-first), `public/manifest.json`, root `index.html`,
  favicon files. Equivalents used, documented; no contents guessed.
- Six existing brand/design docs + prior icon research are tracked but outside Phase 0 declared
  inputs; listed only (plan A.8, U01). Phase 1 must reconcile before new direction.
- Phase 2 gates need human/counsel input: name decision, classes/territories, budget, counsel/filing
  owner, PWA/mobile roadmap. No removal of these blockers possible from within Phase 0.

## Decisions
- Worktree at `.worktrees/brand-plan` instead of `../wt-plan`: parent directory is outside the
  writable workspace sandbox; `.worktrees/` is the repo's established worktree location.
- "Equivalent" inputs used for absent Next.js paths; every substitution recorded; no assumptions.
- Planning used Impeccable modes Persuade (marketing) + Operate (dashboard); no render inspected.
- Worktree-per-phase branch naming: `brand/plan`, `brand/audit`, `brand/strategy`,
  `brand/concepts`, `brand/assets`, `brand/tokens`, `brand/rollout`, `brand/materials`,
  `brand/validation`, `brand/governance`. Commit prefixes per plan Appendix B.
