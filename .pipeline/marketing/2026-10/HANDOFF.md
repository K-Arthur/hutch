# HANDOFF — Hutch — 2026-10-28 — session 3 (Phase 2 strategy)

## State
- Repo/branch/commit: /home/kevina/CodingProjects/hutch · main · `44d66918` at session start (site untouched; this campaign has only .pipeline commits; another commit `bee491d5` predates)
- Worktree: none (main; strategy-only)
- Artifact dir: .pipeline/marketing/2026-10/
- Deployed? live commit: N/A — no public domain (owner-confirmed 2026-10-28, B-01)

## What changed this session
- No product files edited (strategy phase rule; git status shows only .pipeline changes + the other agent's pre-existing dirty files, untouched).
- Created: STRATEGY.md (positioning, message hierarchy, D-01 option table, audience/intent map, content plan), CLAIM-REGISTER.md (C-01..C-26 + prohibited claims + volatile-facts index + F-01 wording draft), CONTENT-MAP.md (6 surfaces, ranked slices S-a..S-d with AC/rollback). Updated: 00-BRIEF.md (session-3 scope), DECISION.md (P2-01..P2-06), CHANGES.md, this file, NEXT-PROMPT.md.

## Decisions (do not reverse without new evidence)
| ID | Decision | Reason | Date | Owner |
|---|---|---|---|---|
| D-01 | **APPROVED — Option A**: keep warm H1; lift "MIT-licensed · open source · Linux" trust row above fold (slice S-b) | Measured: category words already in title/eyebrow/hero-sub (RECON §9); trust words below fold (F-12) | 2026-10-28 | human ✓ |
| D-02..D-03 | unchanged (llms.txt = agent affordance; FAQPage parity-clean, zero rich-result expectation) | Phase 0/1, re-affirmed by register | 2026-10-28 | campaign |
| D-04 | **ANSWERED — allow all crawlers incl. training bots** (status quo); no robots.txt change needed at S-d for this reason | Human values call; revisitable | 2026-10-28 | human ✓ |
| D-05..D-08 | unchanged (entity source order README→site FAQ→llms.txt; no mention-chasing; GSC+Bing+prompt-set measurement; B-01 domain blocker stands) | — | 2026-10-28 | campaign/human |
| P2-05 | Claim register C-01..C-26 + prohibitions + F-01 wording APPROVED | Question tool sign-off | 2026-10-28 | human ✓ |
| P2-04 | **B-06 ANSWERED — desktop release pipeline owns downloads.json**; campaign files requests, never edits | Human owner confirmation | 2026-10-28 | human ✓ |

## Evidence map
- Phase 2 artifacts: STRATEGY.md, CLAIM-REGISTER.md, CONTENT-MAP.md (.pipeline/marketing/2026-10/)
- Live re-verifications this session: `cat website/llms.txt` (F-01 stale text confirmed present, lines 3/9); `ls docs/marketing-site.md docs/realignment/baseline.md docs/realignment/ledger.md` (all exist — C-26); `git show HEAD:pyproject.toml | grep version` (0.1.0 — C-04); index.html head/hero/#get/FAQ/footer ranges read and cited
- Phase 1 baseline (unchanged): RECON.md, FINDINGS.md, evidence/audit/{crawl-report.json,shots/}
- Phase 0 research (unchanged): RESEARCH.md + evidence/research/sources.md
- AI-answer baseline: still BLOCKED (no live domain). Prompt set v1 in RESEARCH §5 (16 prompts).

## Open risks / blockers
| ID | Risk/blocker | Impact | Owner | Next action | Trigger |
|---|---|---|---|---|---|
| B-01 | Site has NO live domain — pre-launch (human-confirmed) | All live-URL work gated (sitemap, canonical, GSC, IndexNow, AI-answer baseline, CWV field) | human | Choose domain + host; then slice S-d | whenever ready |
| B-02 | llms.txt contradiction (F-01) — NOW WITH APPROVED WORDING | AI answers still misstate availability until S-a runs | campaign | Execute slice S-a (next session) | sign-off ✓ done |
| B-03 | No analytics/GSC/Bing properties | Measurement week-0 impossible | human | Create at domain time | domain chosen |
| B-06 | RESOLVED: desktop pipeline owns downloads.json | F-07 status-field gap remains but is their call | human/desktop pipeline | File a request when the pipeline's next touch is known | optional |

## Next slice (one only)
- **S-a: llms.txt entity-surface repair** — the first IMPLEMENTATION slice (Phase 5 machine). Apply approved wording from CLAIM-REGISTER ("F-01 draft replacement wording"): llms.txt:3, llms.txt:9, add GitHub repository line (F-06). Files touched: `website/llms.txt` ONLY.
- Write scope: `website/llms.txt` + `.pipeline/marketing/2026-10/**` (CHANGES/EVIDENCE updates). Nothing else. The other agent's dirty files (src/hutch/server/**, app/**, package.json, pyproject.toml, AGENTS.md, CONTRIBUTING.md, .gitignore) remain untouched/un-staged.
- Acceptance (from CONTENT-MAP §2 S-a): (1) `grep -in "private preview" website/llms.txt` → 0 hits; (2) public + MIT + GitHub URL stated; (3) fact-parity with README:5,16-22 and index.html:780,793 (C-05/C-11/C-12); (4) `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/audit_site.py` exit 0 with llms_txt.mentions_github=true; (5) commit touches website/llms.txt only.
- Visual gate: NONE needed (plain-text machine file, not rendered). Crawler checks = audit_site.py re-run (multi-UA).
- Commit: `seo(slice-s-a): repair llms.txt availability facts + add GitHub link` (or `marketing(slice-s-a): ...`) — stage website/llms.txt + .pipeline only. Do not push.
- Estimated size: 1 short session. After S-a: S-b (metadata trim + trust row per D-01 Option A) — needs Phase 3 front-end gate first.

## Environment facts
- Build: `npm run build:css:site` (NOT needed for S-a — no CSS/HTML change)
- Serve/crawl: `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/audit_site.py` (self-serves website/ on :8899)
- Tests: `npm run check:agent` (repo gate; run before reporting complete)
- Deploy/analytics/consoles: none (B-01, B-03)
- Concurrency: other agent holds uncommitted work in src/hutch/server/**, app/**, package.json, pyproject.toml, AGENTS.md, CONTRIBUTING.md, .gitignore — never touch/stage; use `git show HEAD:<file>` for committed-state reads
- AI targets: Google AIO/AI Mode, ChatGPT Search, Perplexity, Copilot, Gemini, Claude

## Do not do
- Do not paraphrase the approved F-01 wording — apply it as drafted (minor grammar glue only; any semantic change returns to the register).
- Do not edit downloads.json (P2-04), robots.txt (D-04 resolved allow-all), README, index.html, or any src/ file in the S-a session.
- Do not add llms.txt "SEO" language — the file is an agent-navigation affordance only (D-02).
- Do not push/deploy/merge. Do not claim a gate passed without naming its evidence path.
