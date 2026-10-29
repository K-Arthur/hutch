# Brand Program - Phase 0 (Planning)

Worktree: `.worktrees/brand-plan` (branch `brand/plan`), created from `main` @ 577e1154.
Main checkout `/home/kevina/CodingProjects/hutch` is intentionally untouched (it is dirty with
another session's work). Session scope: planning only - no code, designs, or asset edits.
Plan file: `docs/brand/00-PLAN.md`.

## Done
- [x] Isolated worktree created; branch `brand/plan`.
- [x] Recon: brief-declared paths vs actual repo; docs/ top-level listing.
- [x] Tracked asset/font inventory (git ls-files, file metadata).
- [x] Declared-input reads: README.md, package.json, templates/base.html, website/index.html
      (head/nav/hero/footer + OG/meta greps), website/tokens.css, website/src/input.css,
      app/src/input.css (1-120 + theme/import greps), Studio shell static/index.html,
      generated brand-tokens.css + token source website/tokens.json (chain implied by imports).
- [x] Evidence collected: token counts, 23 unique literal hex across declared files, 107 custom
      props in tokens.css, WCAG contrast table (brand 10.35:1 etc.), route/surface inventory,
      asset formats (icns/ico 6 sizes/256 RGBA png/svg 295B), no PWA manifest/service worker,
      no web favicon raster, no apple-touch-icon, no press kit, no visual-regression tests,
      GitHub Pages deploy on push to main (website/**), token source -> two generated CSS files.
- [x] Four research streams delegated (shared tasks task-1..4, owners research-*).

## In progress (file:function)
- Waiting on four research streams; synthesizing findings into 00-PLAN.md sections R + C + D.

## Next
- Write `docs/brand/00-PLAN.md` (A inventory, B phases, C gap register >=15, D unknowns).
- Review against brief constraints; commit; push phase boundary; report deviations.

## Blocked
- Brief-declared paths absent in this repo: `src/app/layout.*`, `src/styles/globals.css`,
  `tailwind.config.*` (Tailwind v4 CSS-first; no config file), `public/manifest.json`,
  root `index.html`, favicon files. Equivalents used and documented; no contents guessed.
- `docs/brand-assets.md`, `docs/design-system.md`, `docs/marketing-site.md`, `DESIGN.md`,
  `PRODUCT.md`, `docs/research/icon-and-chat-interface-references-2026-10-10.md` exist but are
  outside Phase 0 declared inputs; listed only. Phase 1 must reconcile with them.

## Decisions
- Worktree lives at `.worktrees/brand-plan` instead of `../wt-plan`: the parent directory is
  outside the writable workspace sandbox; `.worktrees/` is the repo's established worktree home.
- "Equivalent" inputs are used where the brief names Next.js paths; every substitution is recorded
  in the plan and no file content is assumed.
- Planning is Impeccable mode `Persuade` (marketing) + `Operate` (dashboard); no render inspected.
- Commit prefixes: `docs(brand):` for planning docs; later phases get their own prefixes.
