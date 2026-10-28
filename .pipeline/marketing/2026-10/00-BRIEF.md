# 00 — CAMPAIGN BRIEF

- Product / one-liner: Hutch — local-first, open-source multi-bot agent platform ("Your bots. Your machine. Your rules."). Python 3.11+ backend, Tailwind/daisyUI dashboard, static marketing site, Tauri/Rust desktop host.
- Repo / branch / commit: /home/kevina/CodingProjects/hutch · main · (see `git rev-parse --short HEAD` at session start)
- Artifact dir: .pipeline/marketing/2026-10/
- Session type: research (Phase 0)
- Today / owner: 2026-10-28 / human owner (Claude research lead)
- Audience(s) in scope: developers/technical builders evaluating a self-hosted multi-agent tool; privacy/local-first advocates; operators wanting to run bots on their own machine.
- Surfaces in scope: `website/` marketing site (index.html, site.js, styles, llms.txt, robots.txt, downloads.json), README, docs/ landing.
- Explicit non-goals: NO product-file edits this session; NO copywriting; NO code/UI changes; NO audit of dashboard app (`src/hutch/server/**`); NO committing generated artifacts or other agents' uncommitted work.
- Authority: commit locally only; never push/deploy/merge without explicit human instruction.
- Budget: max ~25 files read; no diff (research-only); wall time ~1 session. AI answer-engine live probing = best-effort, documented as limitation if no access.
- Concurrency: single worktree (main); claims `website/**` + `.pipeline/marketing/2026-10/**` only; another agent holds `src/hutch/server/**`, `app/**`, `package.json`, `pyproject.toml`, `AGENTS.md`, `CONTRIBUTING.md`, `.gitignore` (uncommitted) — do not touch.
- Success criteria for this session (≤5, measurable):
  1. `RESEARCH.md` written with all 10 required sections populated.
  2. Every decision-critical claim carries a primary-source URL + published + fetched date (or marked `[unverified memory]`).
  3. Track B (failures) has >= as much decision-relevant evidence as Track A.
  4. "Claims we must NOT make" table non-empty and specific to Hutch.
  5. 5+ decision memos each state recommendation + evidence + confidence + falsifier.
- Previous handoff (path): none (first session)

**Assumptions** (resolve in Phase 1, record in DECISION.md):
1. `website/` is the only public marketing surface; no separate docs site is deployed (docs/ is repo-internal).
2. No analytics is currently installed on the site (verify in Phase 1).
3. No sitemap.xml exists yet (only robots.txt + llms.txt spotted).
4. Deploy target for the site is unknown — the repo's CI workflows do not build/deploy `website/`.
5. English-only audience.
