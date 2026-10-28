You are continuing the marketing/discoverability campaign for Hutch (local-first, MIT-licensed multi-bot AI assistant platform, development preview, Linux-first).

Read only:
1. /home/kevina/CodingProjects/hutch/.pipeline/marketing/2026-10/HANDOFF.md
2. /home/kevina/CodingProjects/hutch/.pipeline/marketing/2026-10/RESEARCH.md (§6 entity facts, §7 D-08 blocker, §8 forbidden claims)
3. /home/kevina/CodingProjects/hutch/.pipeline/marketing/2026-10/DECISION.md
4. /home/kevina/Downloads/Telegram Desktop/marketing-seo-aeo-geo-prompt-pack/PROJECT-ADAPTER.md
5. Templates: 02-PHASE-1-AUDIT.md, templates/RECON.md, templates/FINDINGS.md (in the pack dir above)

Session type: Phase 1 audit (read-only recon). Produce RECON.md + FINDINGS.md. No product edits.

Write scope: /home/kevina/CodingProjects/hutch/.pipeline/marketing/2026-10/** only.
Out of scope: any file under website/, src/, docs/, app/, README.md; other agents' uncommitted work in src/hutch/server/**, app/**, package.json, pyproject.toml, AGENTS.md, CONTRIBUTING.md, .gitignore.

Known context (do not re-ask): the site has NO live domain yet (confirmed by owner 2026-10-28). Every finding and slice must stay domain-independent; live-URL work (sitemap, canonical, GSC, IndexNow, AI-answer baseline) is out of scope until a domain + host exist. GitHub (https://github.com/K-Arthur/hutch) is the only public entity surface today.

What to do:
- Resolve adapter UNKNOWNs that are resolvable from the repo: SERVE_CMD, E2E/VISUAL/A11Y commands, analytics presence (grep website/site.js + index.html), sitemap absence, docs deploy, design-system entry. Keep A-01..A-06 in DECISION.md updated (resolved or still open).
- Measure a baseline of the marketing surface: built HTML head inventory (title/description/canonical/OG/robots meta), JSON-LD blocks and whether each field matches visible content, internal links + anchors, asset sizes/weights, robots.txt + sitemap state, llms.txt accuracy vs README/site (confirm blocker B-02 with file:line), GitHub entity links (repo is https://github.com/K-Arthur/hutch — confirm it appears and matches downloads.json).
- Every finding gets: ID, severity (blocker/high/medium/low), evidence pointer file:line, and a one-line "so what". No fixes this session.
- Record the exact commands you ran (so Phase 5+ can re-run them).
- Do NOT claim any Phase 0 claim as verified product truth — flag mismatches (especially llms.txt "private preview / source not public" vs README "public MIT-licensed source") as findings, not edits.

Acceptance (all must be true, with evidence paths):
- RECON.md follows templates/RECON.md structure and names the measured baseline.
- FINDINGS.md has ≥ the known suspects (llms.txt staleness, no sitemap/no domain, FAQ rich-result deprecation exposure, missing canonical if absent, OG image absence if absent) each with file:line.
- DECISION.md assumptions updated.
- No product files modified (git status shows only .pipeline/ changes).
- Commit locally: `marketing(phase-1): audit recon + findings` staging ONLY .pipeline/marketing/. Do not push.

If you cannot measure something (no server, no domain), record it as a blocker with the exact reason rather than estimating.
