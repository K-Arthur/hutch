# HANDOFF — Hutch — 2026-10-28 — session 5 (slice S-b implementation)

## State
- Repo/branch/commit: /home/kevina/CodingProjects/hutch · main · `4a307b88` at session start (this session commits `seo(slice-s-b): …`; the other agent's dirty product files remain untouched/un-staged — note their set has grown: .gitignore, AGENTS.md, CONTRIBUTING.md, app/**, package*.json, pyproject.toml, src/hutch/server/**, tests/** + untracked .ai/, .codex/, .dshignore, .file-size-baseline.json, .githooks/, .ignore …)
- Worktree: none (main)
- Artifact dir: .pipeline/marketing/2026-10/
- Deployed? live commit: N/A — no public domain (owner-confirmed 2026-10-28, B-01). The only live public surface is the GitHub repo (README).
- Campaign phase machine: Phases 0-2 committed; Phase 5 second slice (S-b) DONE this session; Phase 6 evidence in EVIDENCE.md; Phase 7/8 = this handoff.

## What changed this session
- website/index.html, 3 regions: :7 meta description 198→157 ch (sentence-complete, "Development preview." kept, JSON-LD description untouched); :37 dateModified 2026-10-26→2026-10-28 (C-24 trigger); :281 NEW trust line "MIT-licensed · open source · Linux" as first child of section.hero .hero-actions (P2-01 Option A, human-approved Route A; classes w-full/text-xs/text-ink-3 all pre-existing in committed app.css — no CSS change, no rebuild).
- .pipeline/marketing/2026-10/: EVIDENCE.md rewritten (AC1-9 + image observations); new evidence/audit/s_b_focus_capture.py (closes P1-06: real keyboard focus-ring capture) + s-b-audit-{stdout,stderr}.txt + regenerated shots/* (Phase-1 baseline shots superseded in worktree, old versions recoverable at commit 44d66918); updated 00-BRIEF, CHANGES, DECISION (S-b-01..06), CLAIM-REGISTER (C-24 refresh + review log), this file, NEXT-PROMPT.

## Decisions (do not reverse without new evidence)
| ID | Decision | Reason | Date | Owner |
|---|---|---|---|---|
| S-b-01 | Phase 3 five questions reconstructed (pack template not on disk; adapter-unknown rule) and recorded in DECISION.md | Template arrived via prior adapter paste only | 2026-10-28 | campaign |
| S-b-02 | Rendered change justified (F-12 measured on rendered first screen; SERP copy cannot fix it) | Phase 3 gate answers Q1-Q5 in DECISION.md | 2026-10-28 | campaign |
| S-b-03 | impeccable PRODUCT.md stale line ("source and downloads are private") observed, NOT acted on — flagged to design-workflow owner | Outside write scope; claim register is campaign source of truth | 2026-10-28 | campaign |
| S-b-04 | og:description (:11, 168 ch) deliberately NOT trimmed | F-08/S-b AC scope names only the meta description; opportunistic edits break slice discipline | 2026-10-28 | campaign |
| S-b-05 | Route A (trust line above CTAs) — HUMAN APPROVED via question tool; B/C/D rejected with reasons in DECISION.md | Research: posthog/ghost/supabase captures inspected 2026-10-28; Figma Community blocked (CloudFront 403), disclosed | 2026-10-28 | human/campaign |
| S-b-06 | Trust line placed inside .hero-actions flex (w-full/text-xs/text-ink-3) for spacing without CSS edits | No margin utilities compiled; flex row-gap gives 12px above buttons; grep confirmed site.js untouched by .hero-actions | 2026-10-28 | campaign |
| D-01..D-08, P2-01..P2-06, S-a-01..03 | unchanged | see DECISION.md | 2026-10-28 | human/campaign |

## Evidence map
- Slice proof: EVIDENCE.md (AC1-9 table + visual observations); evidence/audit/s-b-audit-stdout.txt (description_len=157, ua_parity 6/6 @97686 B, FAQ 20/20, anchors 0 missing); shots/s-b-focus-hero.png + s-b-hero-actions-clip-{desktop,mobile}.png
- Gates: audit_site.py exit 0 · visual gate ALL images read (desktop/mobile/narrow/200%-zoom/focus) · check:agent FAIL = pre-existing B-07 (same single violation, tests/test_commit_attribution.py from bee491d5; chain stops at context-hygiene)
- Phase 2 (unchanged): STRATEGY.md, CLAIM-REGISTER.md (C-24 refreshed), CONTENT-MAP.md
- Phase 1 (unchanged baseline): RECON.md, FINDINGS.md (F-08/F-12 now fixed by S-b; F-02/F-03/F-09/F-11 remain domain-gated), evidence/audit/crawl-report.json
- Phase 0 (unchanged): RESEARCH.md + evidence/research/sources.md; AI-answer baseline still BLOCKED (B-01), prompt set v1 in RESEARCH §5

## Open risks / blockers
| ID | Risk/blocker | Impact | Owner | Next action | Trigger |
|---|---|---|---|---|---|
| B-01 | No live domain (pre-launch) | sitemap/canonical/GSC/IndexNow/AI baseline/CWV field/og:url all parked | human | choose domain + host → slice S-d | whenever ready |
| B-03 | No analytics/GSC/Bing properties | week-0 measurement impossible | human | create at domain time | domain chosen |
| B-07 | Repo gate `npm run check:agent` red on main: tests/test_commit_attribution.py 419 lines (bee491d5) + (per S-a run) stale untracked .ai/ map | every future session's repo gate stays red until fixed; NOT campaign-caused | git-attribution/agent-map workstream | split the test file; regenerate the map (`python scripts/generate_agent_map.py --write`) | their next session |
| B-08 (new, low) | 320×568: second stacked hero CTA edge ~19px lower after trust line (pre-existing column-stacking at tiny viewports) | cosmetic; primary CTA fully visible | campaign (future polish) | only if a hero-CSS slice is ever approved | next hero-touching slice |
| B-09 (new, info) | impeccable PRODUCT.md carries stale "source and downloads are private" instruction (S-b-03) | design-workflow agents could reintroduce F-01-style wording | design-workflow owner | refresh PRODUCT.md positioning tail | their next session |

## Next slice (one only)
- **S-c: social cards, domain-independent part** (CONTENT-MAP §2, P2) — og:image asset rendered from existing brand tokens/mascot (≥1200×630, <300 KB, references only committed assets) + og:site_name/og:image/og:image:alt + twitter:card/twitter:title/twitter:description/twitter:image tags. og:url NOT added (needs domain, B-01). Finding: F-04.
- **MUST open with the Phase 3 front-end gate** (DECISION.md front-end-necessity note: even a new static asset is gated) + standing design-workflow research requirement (web research, ≥3 inspected examples from ≥2 sources, Figma Community scouting via web since Figma MCP 403) + 3-4 route options + HUMAN route approval via question tool BEFORE creating/committing the asset or editing the head. Asset generation approach itself is a route decision (pure-CSS/SVG composition vs mascot render export vs text-card); no invented benchmarks/claims on the card — approved register wording only ("Development preview." / "MIT-licensed · open source · Linux" are available and verified).
- Write scope: `website/index.html` + new file under `website/assets/` (ONE asset) + .pipeline/marketing/2026-10/** only. NO CSS-source edits (if the card needs new CSS, it must ship as an SVG file, not new classes).
- Acceptance (CONTENT-MAP §2 S-c): image ≥1200×630 and <300 KB; references only committed assets; audit_site.py head inventory shows new tags; no third-party requests (input.css:5 contract); visual capture of the asset itself INSPECTED; twitter:card=summary_large_image; FAQ/schema parity unaffected (audit exit 0); dateModified only if visible copy changes (C-24); screenshots captured and LOOKED AT.
- Commit: `seo(slice-s-c): …` locally; do not push.

## Environment facts
- Build: `npm run build:css:site` only if site CSS touched (S-c should NOT need it — SVG asset + head meta only)
- Serve/crawl: `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/audit_site.py` (self-serves website/ on :8899); screenshots via evidence/audit/capture_site.py (regenerates shots/) or a new s-c-prefixed script for asset captures
- Tests: `npm run check:agent` — currently RED for B-07 (pre-existing); report it as such, do NOT "fix" it in a marketing session
- Pre-commit hook `.githooks/pre-commit` exists but is NOT active (core.hooksPath unset) — other workstream's; do not enable
- Concurrency: other agent holds uncommitted work in src/hutch/server/**, app/**, tests/**, package.json, pyproject.toml, AGENTS.md, CONTRIBUTING.md, .gitignore + untracked .ai/, .codex/, .githooks/ etc. — never touch/stage; use `git show HEAD:<file>` for committed-state reads
- AI targets: Google AIO/AI Mode, ChatGPT Search, Perplexity, Copilot, Gemini, Claude

## Do not do
- Do not edit llms.txt (approved state), downloads.json (P2-04), robots.txt (D-04), README.md, or any src/ file in the S-c session.
- Do not flip the H1 (P2-01 Option A keeps "A little help with what's next.").
- Do not add og:url, canonical, or sitemap (B-01 domain-gated; would need a fake URL).
- Do not add claims beyond the register; prohibited-claims table in CLAIM-REGISTER.md is campaign-wide and has no expiry (no star counts, no benchmarks, no "best").
- Do not push/deploy/merge. Do not claim a gate passed without naming its evidence path.
