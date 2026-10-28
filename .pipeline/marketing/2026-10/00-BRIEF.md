# 00 — CAMPAIGN BRIEF (session 2: Phase 1 audit)

- Product / one-liner: Hutch — local-first, open-source multi-bot agent platform ("Your bots. Your machine. Your rules."). Python 3.11+ backend, Tailwind/daisyUI dashboard, static marketing site, Tauri/Rust desktop host.
- Repo / branch / commit: /home/kevina/CodingProjects/hutch · main · `e8d2fa1c` (see RECON §1)
- Artifact dir: .pipeline/marketing/2026-10/
- Session type: audit (Phase 1, read-only recon) — mandate from NEXT-PROMPT.md (session 1)
- Today / owner: 2026-10-28 / human owner (Claude research lead)
- Audience(s) in scope: developers/technical builders evaluating a self-hosted multi-agent tool; privacy/local-first advocates; operators wanting to run bots on their own machine.
- Surfaces in scope: `website/` marketing site (index.html, site.js, styles, llms.txt, robots.txt, downloads.json), README as entity surface, docs/ deploy status, .github/workflows for deploy evidence.
- Explicit non-goals: NO product-file edits; NO copywriting; NO fixes (findings only); NO audit of dashboard app (`src/hutch/server/**`); NO staging other agents' uncommitted work; live-URL work (sitemap ping, canonical URLs, GSC, AI-answer baseline) deferred — site has no live domain (B-01).
- Authority: commit locally only (.pipeline/marketing/ only); never push/deploy/merge.
- Budget: ~25 files read; 1 session wall time; build+serve locally allowed; no product diff.
- Concurrency: single worktree (main); writes `.pipeline/marketing/2026-10/**` only; another agent holds `src/hutch/server/**`, `app/**`, `package.json`, `pyproject.toml`, `AGENTS.md`, `CONTRIBUTING.md`, `.gitignore` (uncommitted, `M` in git status) — read-only where named, never stage.
- Success criteria (from NEXT-PROMPT acceptance):
  1. RECON.md follows template structure; names measured baseline + exact commands.
  2. FINDINGS.md covers all known suspects (llms.txt staleness, no sitemap/no domain, FAQ rich-result deprecation exposure, canonical absence, OG image absence) each with file:line.
  3. DECISION.md A-01..A-06 resolved or marked still-open.
  4. git status shows only .pipeline/ changes from this campaign; commit `marketing(phase-1): audit recon + findings` staged to .pipeline/marketing/ only, not pushed.
- Previous handoff: .pipeline/marketing/2026-10/HANDOFF.md (session 1, Phase 0 research — complete, committed).
