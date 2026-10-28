# HANDOFF — Hutch — 2026-10-28 — session 2 (Phase 1 audit)

## State
- Repo/branch/commit: /home/kevina/CodingProjects/hutch · main · `e8d2fa1c` at session start (site untouched; this campaign has only .pipeline commits)
- Worktree: none (main; audit-only)
- Artifact dir: .pipeline/marketing/2026-10/
- Deployed? live commit: N/A — no public domain (owner-confirmed 2026-10-28, B-01)

## What changed this session
- No product files edited (Phase 1 rule; git status shows only .pipeline additions + other agent's pre-existing dirty files).
- Created/updated: 00-BRIEF.md (session-2 scope), RECON.md (measured baseline, §1-§11), FINDINGS.md (F-01..F-12), DECISION.md (A-01..A-06 resolved; P1-01..P1-06), CHANGES.md, evidence/audit/{audit_site.py, capture_site.py, crawl-report.json, focus-trace.txt, shots/ (15 png)}.

## Decisions (do not reverse without new evidence)
| ID | Decision | Reason | Date | Owner |
|---|---|---|---|---|
| D-01 | Positioning: "governed local-first AI assistants" (control/approvals/budgets/evidence), keep human-tone hero | Competitor incidents + white-space analysis (RESEARCH §1, §3B2); F-10/F-12 are inputs to this | 2026-10-28 | human sign-off pending (Phase 2) |
| D-02 | Keep llms.txt as agent-navigation affordance; never as SEO claim; fix stale facts | Google ignores it for Search; F-01 measured: file contradicts README/site today | 2026-10-28 | campaign |
| D-03 | Keep SoftwareApplication; FAQPage only while FAQ visible, zero rich-result expectation | FAQ rich results removed May 2026; parity 20/20 measured clean (F-05) | 2026-10-28 | campaign |
| D-04 | robots.txt allow all search/user-fetch bots; training-bot policy = human decision | Per-engine docs; blocking = exclusion from that engine | 2026-10-28 | human |
| D-05 | Entity source order: README/docs → site FAQ → llms.txt (derived) | Measured conflict live in llms.txt:3,9 (F-01); MS/Google consistency guidance | 2026-10-28 | campaign |
| D-06 | Off-site: honest GitHub presence + original evidence assets; no mention-chasing | Google AI guide; GEO paper; Pew; GitHub links triangulated consistent | 2026-10-28 | human (Phase 2) |
| D-07 | Measurement: GSC + Bing AI Performance + fixed dated prompt set; no traffic promises | Pew 1% source clicks; measurement currently IMPOSSIBLE (F-09, B-03) | 2026-10-28 | campaign |
| D-08 | BLOCKER: public domain + deploy target must come from human before technical-SEO slices | robots.txt:1-2; no site deploy workflow (re-confirmed Phase 1) | 2026-10-28 | human |

## Evidence map
- RECON baseline: .pipeline/marketing/2026-10/RECON.md (§4 machine layer, §5 schema parity, §6 claims, §9 visual)
- Findings: FINDINGS.md (F-01 S1 llms.txt staleness w/ repro; F-02 S1 sitemap/domain; F-03..F-12)
- Crawl report (machine-readable): evidence/audit/crawl-report.json — UA parity, 29 fetches, anchors, head inventory, JSON-LD parse, FAQ parity 20/20, downloads manifest
- Screenshots: evidence/audit/shots/ (14 viewport/state captures + desktop-full-failsafe.png); observations written in RECON §9 (gate satisfied by inspection, not just pixel capture)
- Focus/motion trace: evidence/audit/focus-trace.txt
- Phase 0 research: RESEARCH.md + evidence/research/sources.md (unchanged)
- AI-answer baseline: still BLOCKED (no live domain). Prompt set v1 in RESEARCH §5 (16 prompts).

## Open risks / blockers
| ID | Risk/blocker | Impact | Owner | Next action | Trigger |
|---|---|---|---|---|---|
| B-01 | Site has NO live domain — pre-launch (human-confirmed) | All live-URL work gated (sitemap, canonical, GSC, IndexNow, AI-answer baseline, CWV field); repo-based work unaffected | human | Choose domain + host; then slice S-d | Phase 2 sign-off |
| B-02 | llms.txt contradicts README/site — NOW MEASURED as F-01 (S1) | AI answers will misstate availability until fixed | campaign | First implementation slice (after Phase 2 wording sign-off) | F-01 confirmed ✓ |
| B-03 | No analytics/GSC/Bing properties exist (F-09) | Measurement week-0 impossible | human | Create properties when domain exists | domain chosen |
| B-04 | Training-crawler policy undecided (GPTBot/ClaudeBot/Google-Extended) | robots.txt slice cannot finalize | human | Decide allow/block preference | Phase 2 sign-off |
| B-05 | Wording-drift class (site FAQ comparisons vs llms.txt "Not claims") | Claim-register risk | campaign | Cover in Phase 2 claim register | Phase 2 |
| B-06 | NEW: downloads.json platform list ambiguity (F-07) — may be owned by desktop release pipeline | Manifest edits could collide with another workstream | human | Confirm manifest owner + contract before S-a touches it | before S-a |

## Next slice (one only)
- **Phase 2 strategy** (NOT an implementation slice): STRATEGY.md + CLAIM-REGISTER.md + CONTENT-MAP.md, ending in HUMAN sign-off on positioning (D-01), claims (incl. llms.txt replacement wording for F-01), and non-goals (D-04/D-06).
- Write scope: .pipeline/marketing/2026-10/** only.
- Acceptance: template STRATEGY/CLAIM-REGISTER/CONTENT-MAP filled; every public factual claim from RECON §6 has wording+evidence+refresh trigger; F-01 fix wording drafted (not applied); slice list ranked; human sign-off recorded or BLOCKER written.
- Front-end level: none (strategy).
- Estimated size: 1 session.
- After Phase 2 sign-off: first implementation slice S-a = llms.txt repair + GitHub URL (content-only, website/llms.txt), needs F-07 owner answer only if the manifest is included.

## Environment facts
- Build: `npm run build:css:site` (only if website CSS sources change; site HTML is hand-written; committed CSS is the runtime, input.css:1-5)
- Serve: `python -m http.server -d website` (verified working; sends no Content-Type on / — real-host check at deploy)
- Tests: `npm run check:agent` (repo gate); no site-specific tests exist; e2e = python playwright in tests/e2e (needs uv env; chromium cached)
- Visual/a11y: re-run `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/capture_site.py` (or audit_site.py for the crawl); axe not available (limitation)
- Deploy/analytics/consoles: none (B-01, B-03)
- Concurrency: other agent holds uncommitted work in src/hutch/server/**, app/**, package.json, pyproject.toml, AGENTS.md, CONTRIBUTING.md, .gitignore — never touch/stage; use `git show HEAD:<file>` for committed-state reads
- AI targets: Google AIO/AI Mode, ChatGPT Search, Perplexity, Copilot, Gemini, Claude

## Do not do
- Do not treat RESEARCH.md secondary sources ([secondary] tags) as quotable facts without re-fetching the primary.
- Do not add pages, schema or copy before Phase 2 human sign-off (D-01/D-06 need approval).
- Do not "fix" sitemap/canonical with a made-up domain (F-02/F-03 are domain-gated by design).
- Do not edit downloads.json before B-06 owner confirmation.
- Do not push/deploy/merge. Do not claim any phase gate passed without evidence paths.
