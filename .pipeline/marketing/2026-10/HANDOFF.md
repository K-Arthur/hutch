# HANDOFF — Hutch — 2026-10-28 — session 1 (Phase 0 research)

## State
- Repo/branch/commit: /home/kevina/CodingProjects/hutch · main · HEAD at session start `git rev-parse --short HEAD` (see commit)
- Worktree: none (main; research-only)
- Artifact dir: .pipeline/marketing/2026-10/
- Deployed? live commit: N/A — site has no public domain chosen (`website/robots.txt:1-2`); deploy target unknown

## What changed this session
- No product files edited (Phase 0 rule).
- Created: 00-BRIEF.md, RESEARCH.md, DECISION.md (assumptions), evidence/research/sources.md, HANDOFF.md, NEXT-PROMPT.md.
- Adapter filled outside repo: /home/kevina/Downloads/Telegram Desktop/marketing-seo-aeo-geo-prompt-pack/PROJECT-ADAPTER.md

## Decisions (do not reverse without new evidence)
| ID | Decision | Reason | Date | Owner |
|---|---|---|---|---|
| D-01 | Positioning: "governed local-first AI assistants" (control/approvals/budgets/evidence), keep human-tone hero | Competitor incidents + white-space analysis (RESEARCH §1, §3B2) | 2026-10-28 | human sign-off pending (Phase 2) |
| D-02 | Keep llms.txt as agent-navigation affordance; never as SEO claim; fix stale facts | Google ignores it for Search; file contradicts README today | 2026-10-28 | campaign |
| D-03 | Keep SoftwareApplication; FAQPage only while FAQ visible, zero rich-result expectation | FAQ rich results removed May 2026 (Google changelog) | 2026-10-28 | campaign |
| D-04 | robots.txt allow all search/user-fetch bots; training-bot policy = human decision | Per-engine docs; blocking = exclusion from that engine | 2026-10-28 | human |
| D-05 | Entity source order: README/docs → site FAQ → llms.txt (derived) | Live llms.txt conflict; MS/Google consistency guidance | 2026-10-28 | campaign |
| D-06 | Off-site: honest GitHub presence + original evidence assets; no mention-chasing | Google AI guide; GEO paper; Pew citation dominance | 2026-10-28 | human (Phase 2) |
| D-07 | Measurement: GSC + Bing AI Performance + fixed dated prompt set; no traffic promises | Pew 1% source clicks; first-party dashboards exist | 2026-10-28 | campaign |
| D-08 | BLOCKER: public domain + deploy target must come from human before technical-SEO slices | robots.txt + no CI deploy | 2026-10-28 | human |

## Evidence map
- RESEARCH: .pipeline/marketing/2026-10/RESEARCH.md (28 sources, both tracks, 8 decision memos, 10 forbidden claims)
- Source log: .pipeline/marketing/2026-10/evidence/research/sources.md
- AI-answer baseline: BLOCKED (no engine access; site likely not live). Prompt set v1 in RESEARCH §5 (16 prompts).
- Screenshots/crawler matrix: none this phase.

## Open risks / blockers
| ID | Risk/blocker | Impact | Owner | Next action | Trigger |
|---|---|---|---|---|---|
| B-01 | RESOLVED (human, 2026-10-28): site has NO live domain yet — pre-launch | All live-URL work (sitemap, canonical, GSC, IndexNow, AI-answer baseline) gated until a domain + deploy target exist; repo-based work unaffected | human | Choose domain + host before any technical-SEO slice; keep slices domain-independent until then | Phase 3 slice selection |
| B-02 | llms.txt contradicts README ("source not public") | AI answers will misstate stage/availability | campaign | Phase 1 finding → first slice | Phase 1 confirms |
| B-03 | No analytics/Search Console/Bing access known | Measurement week-0 impossible | human | Confirm access or create properties | Phase 1 |
| B-04 | Training-crawler policy undecided (GPTBot/ClaudeBot/Google-Extended) | Robots.txt slice cannot finalize | human | Decide allow/block preference | Phase 2 sign-off |
| B-05 | site:llms.txt "Not claims" vs site FAQ comparisons — wording drift class | Claim-register risk | campaign | Cover in Phase 2 claim register | Phase 2 |

## Next slice (one only)
- Phase 1 audit (read-only recon), NOT an implementation slice. Outcome: RECON.md + FINDINGS.md with measured baseline and file:line evidence.
- Write scope: .pipeline/marketing/2026-10/** only. No product edits.
- Acceptance: template RECON/FINDINGS filled; every finding has file:line; baseline commands recorded; assumptions A-01..A-06 resolved or marked.
- Evidence plan: built-HTML head capture of website/index.html; JSON-LD parse; link check; asset sizes; robots/sitemap state.
- Front-end level: none (audit).
- Estimated size: 1 session.

## Environment facts
- Build: npm run build:css:site (only if website CSS sources change); site HTML is hand-written
- Serve: python -m http.server -d website (verify in Phase 1)
- Tests: npm run check:agent (repo gate); website has no dedicated tests known
- Deploy/analytics/consoles: no live domain (owner-confirmed 2026-10-28); analytics/console access unknown (B-03)
- Concurrency: another agent holds uncommitted work in src/hutch/server/**, app/**, package.json, pyproject.toml, AGENTS.md, CONTRIBUTING.md, .gitignore — never touch/stage
- AI targets: Google AIO/AI Mode, ChatGPT Search, Perplexity, Copilot, Gemini, Claude

## Do not do
- Do not treat RESEARCH.md secondary sources ([secondary] tags) as quotable facts without re-fetching the primary.
- Do not add pages, schema or copy before Phase 2 human sign-off (D-01/D-06 need approval).
- Do not push/deploy/merge. Do not claim any phase gate passed without evidence paths.
