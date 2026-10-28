# HANDOFF — Hutch — 2026-10-28 — session 4 (slice S-a implementation)

## State
- Repo/branch/commit: /home/kevina/CodingProjects/hutch · main · `02c51ebe` at session start (this session commits `seo(slice-s-a): …`; the other agent's 78 dirty product files remain untouched/un-staged)
- Worktree: none (main)
- Artifact dir: .pipeline/marketing/2026-10/
- Deployed? live commit: N/A — no public domain (owner-confirmed 2026-10-28, B-01). The only live public surface is the GitHub repo (README).
- Campaign phase machine: Phases 0-2 committed; Phase 5 first slice (S-a) DONE this session; Phase 6 evidence in EVIDENCE.md; Phase 7/8 = this handoff.

## What changed this session
- website/llms.txt: 3 line edits (approved F-01 wording verbatim): :3 availability clause, :9 status line, :25 tail → Repository line (GitHub URL + README/ledger canonical pointer). The S1 contradiction "source is private" is gone; agents reading llms.txt now get the same facts as README:5,16-22 and index.html:780,793.
- .pipeline/marketing/2026-10/: new EVIDENCE.md (AC→evidence), s-a-crawl-{stdout,stderr}.txt (audit report; phase-1 crawl-report.json baseline preserved); updated 00-BRIEF, CHANGES, DECISION (S-a-01..03), CLAIM-REGISTER (C-15..C-17 resolved + review log), this file, NEXT-PROMPT.

## Decisions (do not reverse without new evidence)
| ID | Decision | Reason | Date | Owner |
|---|---|---|---|---|
| S-a-01 | Repository line replaces the old site-canonical tail (avoids dual canonical-summary pointers); C-15..C-17 register statuses flipped (their own refresh trigger) | Both placements were pre-approved; keeping the old tail would recreate an F-01-style contradiction | 2026-10-28 | campaign |
| S-a-02 | Repo-gate failures NOT fixed by this campaign (B-07) | Pre-existing, other workstream's files (bee491d5 test file; untracked .ai/ tooling) | 2026-10-28 | campaign |
| S-a-03 | Visual gate N/A for llms.txt (plain-text machine file) | Pre-authorized in session-3 NEXT-PROMPT | 2026-10-28 | campaign |
| D-01..D-08, P2-01..P2-06 | unchanged (Option A approved; allow-all crawlers; manifest owned by desktop pipeline; register approved) | see DECISION.md | 2026-10-28 | human/campaign |

## Evidence map
- Slice proof: EVIDENCE.md (AC1-7 table); evidence/audit/s-a-crawl-stdout.txt (mentions_github true, ua_parity 6/6, anchors 10/10, FAQ parity 20/20, only known 404s)
- Gates: audit_site.py exit 0 · grep "private preview" 0 hits · check:agent FAIL = pre-existing B-07 (tool-contracts PASS, constitution PASS, context-hygiene flags bee491d5 file, agent-map stale on untracked .ai/)
- Phase 2 (unchanged): STRATEGY.md, CLAIM-REGISTER.md (C-15..C-17 now resolved), CONTENT-MAP.md
- Phase 1 (unchanged baseline): RECON.md, FINDINGS.md (F-01/F-06 now fixed by S-a; F-02/F-03/F-09/F-11 remain domain-gated), evidence/audit/crawl-report.json
- Phase 0 (unchanged): RESEARCH.md + evidence/research/sources.md; AI-answer baseline still BLOCKED (B-01), prompt set v1 in RESEARCH §5

## Open risks / blockers
| ID | Risk/blocker | Impact | Owner | Next action | Trigger |
|---|---|---|---|---|---|
| B-01 | No live domain (pre-launch) | sitemap/canonical/GSC/IndexNow/AI baseline/CWV field all parked | human | choose domain + host → slice S-d | whenever ready |
| B-02 | RESOLVED this session (F-01 llms.txt contradiction fixed, verified) | — | — | — | — |
| B-03 | No analytics/GSC/Bing properties | week-0 measurement impossible | human | create at domain time | domain chosen |
| B-07 | Repo gate `npm run check:agent` red on main: tests/test_commit_attribution.py 419 lines (bee491d5) + stale untracked .ai/repo-map.generated.md | every future session's repo gate stays red until fixed; NOT campaign-caused | git-attribution/agent-map workstream | split the test file; regenerate the map (`python scripts/generate_agent_map.py --write`) | their next session |

## Next slice (one only)
- **S-b: on-page metadata trim** (CONTENT-MAP §2, P1) — meta description 198→≤160 ch keeping "Development preview." intact (F-08) AND D-01 Option A trust row ("MIT-licensed · open source · Linux") above the fold (F-12). File: `website/index.html` head + hero block ONLY.
- **MUST open with the Phase 3 front-end gate** (DECISION.md front-end-necessity section): index.html is a rendered surface, and the user's standing design workflow additionally requires online UI/UX research (≥3 concrete examples from ≥2 sources, Figma Community scouting via web research since the Figma MCP is 403) + 3-4 route options + HUMAN route approval BEFORE implementation. The description-only half is copy work inside existing tokens (no route research needed); the trust-row half is a rendered change (full visual gate + C-24 dateModified trigger + FAQ/schema parity re-check via audit_site.py).
- Write scope: `website/index.html` + .pipeline/marketing/2026-10/** only. Never stage the other agent's dirty files.
- Acceptance (from CONTENT-MAP §2 S-b): description ≤160 ch, no mid-sentence cut, "Development preview." intact, JSON-LD description untouched (separate text, index.html:23); if hero changed: visual gate (desktop+mobile+narrow, dark (site is dark-only BY DESIGN, DECISION P1-03), focus states per P1-06), audit_site.py green incl. FAQ parity 20/20, dateModified updated (C-24), screenshots captured and LOOKED AT in evidence/.
- Commit: `seo(slice-s-b): …` locally; do not push.

## Environment facts
- Build: `npm run build:css:site` only if site CSS touched (S-b description/trust-row likely needs NO CSS change; if tokens suffice)
- Serve/crawl: `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/audit_site.py` (self-serves website/ on :8899); screenshots via evidence/audit/capture_site.py
- Tests: `npm run check:agent` — currently RED for B-07 (pre-existing); report it as such, do not "fix" it in a marketing session
- Pre-commit hook `.githooks/pre-commit` exists but is NOT active (core.hooksPath unset) — other workstream's; do not enable
- Concurrency: other agent holds uncommitted work in src/hutch/server/**, app/**, tests/test_workflow_usage_budget.py, package.json, pyproject.toml, AGENTS.md, CONTRIBUTING.md, .gitignore + untracked .ai/, .codex/, .opencode/, .githooks/, docs/agent-workflow.md etc. — never touch/stage; use `git show HEAD:<file>` for committed-state reads
- AI targets: Google AIO/AI Mode, ChatGPT Search, Perplexity, Copilot, Gemini, Claude

## Do not do
- Do not edit downloads.json (P2-04), robots.txt (D-04 allow-all resolved), README.md, llms.txt (now approved-state), or any src/ file in the S-b session.
- Do not flip the H1 (D-01 Option A keeps "A little help with what's next."; only ADD the trust row).
- Do not add claims beyond the register; prohibited-claims table in CLAIM-REGISTER.md is campaign-wide and has no expiry.
- Do not push/deploy/merge. Do not claim a gate passed without naming its evidence path.
