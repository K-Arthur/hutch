# 00 — CAMPAIGN BRIEF (session 4: slice S-a, Phase 5 implementation)

- Product / one-liner: Hutch — local-first, MIT-licensed multi-bot AI assistant platform ("Your bots. Your machine. Your rules."), development preview, Linux-first. GitHub https://github.com/K-Arthur/hutch is the only public entity surface (no live domain, B-01).
- Repo / branch / commit: /home/kevina/CodingProjects/hutch · main · `02c51ebe` (phase-2 artifacts landed; other agent still dirty in src/hutch/server/**, app/**, package.json, pyproject.toml, AGENTS.md, CONTRIBUTING.md, .gitignore — never staged; .pipeline + website confirmed clean in my scope).
- Artifact dir: .pipeline/marketing/2026-10/
- Session type: slice S-a — IMPLEMENTATION (Phase 5) — mandate from NEXT-PROMPT.md (session 3). First slice touching a product file: repair llms.txt availability facts per the human-approved F-01 wording.
- Today / owner: 2026-10-28 / human owner (Claude research lead).
- Write scope: website/llms.txt ONLY + .pipeline/marketing/2026-10/{00-BRIEF,CHANGES,EVIDENCE,HANDOFF,NEXT-PROMPT,DECISION,CLAIM-REGISTER}.md (register status flip for C-15..C-17 is the register's own registered refresh trigger; recorded in DECISION.md S-a-01).
- Explicit non-goals: NO start of S-b (metadata/hero needs Phase 3 front-end gate first); NO paraphrase of approved wording; NO edits to downloads.json (P2-04), robots.txt (D-04), README, index.html, src/**, app/**; NO push/deploy/merge.
- Authority: commit locally only; never push/deploy/merge without explicit human instruction (standing, confirmed 2026-10-28).
- Budget: ~8 files read; short session; diff limited to 1 product file (llms.txt, <10 lines) + pipeline docs.
- Success criteria (from CONTENT-MAP §2 S-a AC + NEXT-PROMPT acceptance):
  1. `grep -in "private preview" website/llms.txt` → 0 hits; llms.txt states source public + MIT + GitHub URL (approved wording verbatim).
  2. Fact parity with README:5,16-22 and index.html:780,793 (C-05, C-11, C-12 spot-check).
  3. `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/audit_site.py` exit 0 with crawl-report.json `llms_txt.mentions_github=true`.
  4. Commit touches website/llms.txt + .pipeline/marketing/2026-10/** only; `npm run check:agent` green.
  5. EVIDENCE.md maps each AC to its evidence; HANDOFF.md points at next slice S-b (opens with Phase 3 front-end gate).
- Previous handoff: .pipeline/marketing/2026-10/HANDOFF.md (session 3, Phase 2 strategy — complete, committed `02c51ebe`; sign-offs D-01/D-04/P2-04/P2-05 recorded).
