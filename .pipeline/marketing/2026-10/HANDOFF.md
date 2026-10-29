# HANDOFF — Hutch — 2026-10-28 — session 7 (campaign review, Phase 7)

## State
- Repo/branch/commit: /home/kevina/CodingProjects/hutch · main · `f152b9b6` at session start (this session commits the review artifacts; the other agent's dirty product files remain untouched/un-staged — set includes .gitignore, AGENTS.md, CONTRIBUTING.md, app/**, package*.json, pyproject.toml, src/hutch/server/** (incl. untracked hutch-composer.css, hutch-composer-context.css), tests/** + untracked .ai/, .codex/, .dshignore, .githooks/, docs/*.md …)
- Worktree: none (main)
- Artifact dir: .pipeline/marketing/2026-10/
- Deployed? live commit: N/A — no public domain (owner-confirmed 2026-10-28, B-01). The only live public surface is the GitHub repo (README).
- Campaign phase machine: Phases 0-2 committed; Phase 5 slices S-a/S-b/S-c landed (commits 4a307b88 / 0ccad1e1 / f152b9b6); Phase 6 evidence complete; Phase 7 campaign review DONE this session; Phase 8 = this handoff.

## What changed this session (review — no product file touched)
- REVIEW.md: NEW — full check→output map (14 checks) + findings verdict table. Audit re-run exit 0 fresh report at evidence/review/r7-audit-{stdout,stderr}.txt.
- FINDINGS.md: appended "Review verdicts (session 7)" section (baseline table unmodified): F-01/F-04/F-06/F-08/F-12 CLOSED with fresh evidence; F-10 CLOSED-BY-DECISION (D-01 Option A); F-05 accepted (D-03); F-02/F-03/F-07/F-09/F-11 remain OPEN (all blocked on recorded human inputs, none a regression).
- EVIDENCE.md: one-line review-appendix pointer added (S-c AC table left intact as shipped history).
- DECISION.md: R7-01..R7-05 recorded (card re-render skipped per instruction; REVIEW.md as appendix vehicle; F-10 verdict; B-07b status refinement; zero-defect-found ⇒ zero product edits).
- 00-BRIEF.md, CHANGES.md, this file, NEXT-PROMPT.md updated.

## Review verdict (one line)
All five closed findings remain closed on the built site with fresh evidence; claim parity and prohibited-claims policy hold across card/head-meta/llms.txt; no regression, no new defect; the only next step is the human domain decision (S-d).

## Decisions (do not reverse without new evidence)
| ID | Decision | Reason | Date | Owner |
|---|---|---|---|---|
| R7-01..R7-05 | see DECISION.md (card not re-rendered; REVIEW.md appendix; F-10 closed-by-decision; B-07b no longer gate-named; no product edits) | review-phase discipline | 2026-10-28 | campaign |
| S-c-01..04, S-b-01..06, S-a-01..03, P2-01..06, D-01..D-08 | unchanged | see DECISION.md | 2026-10-28 | human/campaign |

## Evidence map
- Review proof: REVIEW.md; evidence/review/r7-audit-stdout.txt (exit-0 crawl: canonical=false, 8 og + 4 twitter, FAQ 20/20, UA 6/6 @98,460 B, description_len 157, JSON-LD 2/2, anchors 10/10, llms.txt mentions_github=true, only sitemap.xml + security.txt 404)
- Slice proofs (unchanged): EVIDENCE.md AC tables for S-a/S-b/S-c; evidence/audit/{s-a,s-b,s-c}-audit-stdout.txt; shots/
- Phase 2/1/0 (unchanged): STRATEGY.md, CLAIM-REGISTER.md, CONTENT-MAP.md; RECON.md, FINDINGS.md (+ review verdicts), crawl-report.json; RESEARCH.md + evidence/research/sources.md (AI-answer baseline still BLOCKED B-01, prompt set v1 in RESEARCH §5)

## Open risks / blockers
| ID | Risk/blocker | Impact | Owner | Next action | Trigger |
|---|---|---|---|---|---|
| B-01 | No live domain (pre-launch) | sitemap/canonical/GSC/IndexNow/AI baseline/CWV field/og:url + ABSOLUTE og:image URL all parked; S-d cannot start | human | choose domain + host → slice S-d | whenever ready |
| B-03 | No analytics/GSC/Bing properties | week-0 measurement impossible | human | create at domain time | domain chosen |
| B-06 | downloads.json manifest contract (F-07) | machine readers may misread platform list | human/desktop pipeline | campaign files a status-field request when the pipeline's next touch is known | pipeline activity |
| B-07 | Repo gate `npm run check:agent` red: tests/test_commit_attribution.py 419 lines (bee491d5) — now the ONLY named violation (was 2) | repo gate stays red; NOT campaign-caused | git-attribution/agent-map workstream | split the test file | their next session |
| B-07b (resolved-by-other-workstream, info) | hutch-composer.css no longer named by the gate although the file exists (split appears in progress: untracked hutch-composer-context.css) | gate improved 2→1 violations without campaign action | composer/dashboard workstream | finish/commit their split | their next commit |
| B-08 (low) | 320×568: second stacked hero CTA edge ~19px lower after trust line (pre-existing) | cosmetic; primary CTA fully visible | campaign (future polish) | only if a hero-CSS slice is ever approved | next hero-touching slice |
| B-09 (info) | impeccable PRODUCT.md carries stale "source and downloads are private" instruction (S-b-03) | design-workflow agents could reintroduce F-01-style wording | design-workflow owner | refresh PRODUCT.md positioning tail | their next session |
| B-10 (low, info) | og:image/twitter:image are RELATIVE URLs (DECISION S-c-04); Facebook strictly requires absolute | FB/WhatsApp shares may render no image until S-d; X/Slack/Discord resolve relative | campaign (S-d) | rewrite both tags absolute + add og:url at domain time | domain chosen |
| B-11 (info) | security.txt 404 (F-11) | no vulnerability-reporting pointer on public surface | human (contact address) + campaign | add at domain time | domain chosen |

## Next step (one only)
- **Human domain+host decision (B-01) → slice S-d** is the ONLY remaining step. No domain-independent slice exists (review complete; S-a..S-c landed and verified).
- If the human HAS chosen a domain: run S-d per CONTENT-MAP §2 (sitemap.xml + robots Sitemap directive, canonical, og:url + absolute og:image/twitter:image (B-10), GSC/Bing verification, IndexNow, deploy-host header checks, AI-answer baseline with RESEARCH §5 prompt set, CWV lab). Open question for that session: og:image size strategy (keep 1200×630 static vs 2× retina) — current card is 1× and passes spec.
- If no domain: do NOT invent one; the next session has no campaign work — say so rather than manufacturing a slice.

## Environment facts
- Build: no site-CSS rebuild needed (none run this session; no CSS touched). `npm run build:css:site` only if site CSS is ever touched
- Serve/crawl: `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/audit_site.py` (self-serves website/ on :8899; latest green run = evidence/review/r7-audit-stdout.txt)
- Card re-render (only if card text ever changes): `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/s_c_render_card.py` — NOT run this session (asset present)
- Tests: `npm run check:agent` — RED for B-07 only (other workstream); report as such, do NOT "fix" in a marketing session
- Pre-commit hook `.githooks/pre-commit` exists but is NOT active (core.hooksPath unset) — other workstream's; do not enable
- Concurrency: other agent holds uncommitted work in src/hutch/server/**, app/**, tests/**, package.json, pyproject.toml, AGENTS.md, CONTRIBUTING.md, .gitignore + untracked .ai/, .codex/, .githooks/, hutch-composer*.css etc. — never touch/stage; use `git show HEAD:<file>` for committed-state reads
- AI targets: Google AIO/AI Mode, ChatGPT Search, Perplexity, Copilot, Gemini, Claude

## Do not do
- Do not edit llms.txt (approved state), downloads.json (P2-04/B-06), robots.txt (D-04 allow-all stands; Sitemap directive only at S-d), README.md, or any src/ file in a marketing session.
- Do not flip the H1 (P2-01 Option A keeps "A little help with what's next.").
- Do not add og:url, canonical, sitemap, or an ABSOLUTE og:image URL (all B-01 domain-gated; would need a fake URL — prohibited).
- Do not add claims beyond the register; prohibited-claims table in CLAIM-REGISTER.md is campaign-wide and has no expiry (no star counts, no benchmarks, no "best").
- Do not re-render the card with new text without (a) register-approved wording and (b) bumping the `?v=` in both image tags (index.html:14, :21) to the new sha256[:8].
- Do not push/deploy/merge. Do not claim a gate passed without naming its evidence path.
