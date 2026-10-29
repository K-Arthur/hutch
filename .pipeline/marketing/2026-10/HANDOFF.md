# HANDOFF — Hutch — 2026-10-28 — session 6 (slice S-c implementation)

## State
- Repo/branch/commit: /home/kevina/CodingProjects/hutch · main · `0ccad1e1` at session start (this session commits `seo(slice-s-c): add og:image asset + social meta tags`; the other agent's dirty product files remain untouched/un-staged — set includes .gitignore, AGENTS.md, CONTRIBUTING.md, app/**, package*.json, pyproject.toml, src/hutch/server/** (now incl. untracked hutch-composer.css), tests/** + untracked .ai/, .codex/, .dshignore, .file-size-baseline.json, .githooks/, .ignore …)
- Worktree: none (main)
- Artifact dir: .pipeline/marketing/2026-10/
- Deployed? live commit: N/A — no public domain (owner-confirmed 2026-10-28, B-01). The only live public surface is the GitHub repo (README).
- Campaign phase machine: Phases 0-2 committed; Phase 5 third slice (S-c) DONE this session; Phase 6 evidence in EVIDENCE.md; Phase 7/8 = this handoff.

## What changed this session
- website/index.html: 10 NEW head tags inserted after :12 (og:site_name, og:image, og:image:alt, og:image:width/height; twitter:card=summary_large_image, twitter:title, twitter:description, twitter:image). og:title/og:description/og:type (:10-12) byte-unchanged; og:url/canonical NOT added (B-01); dateModified :37 unchanged (C-24 trigger fired but same-day). Page body/DOM/CSS untouched — visually identical page.
- website/assets/og-card-1200x630.png: NEW 1200×630 PNG (118,901 B) — Route A dark text card (human-approved): hexagon mark + "Hutch" Geist wordmark; two-tone statement "Local-first AI assistants / that run on your machine."; muted footer "MIT-licensed · open source · Linux · Development preview". Rendered from committed tokens (tokens.css palette) + committed Geist woff2 via evidence/audit/s_c_render_card.py (Playwright; zero external requests, input.css:5 intact).
- .pipeline/marketing/2026-10/: EVIDENCE.md rewritten for S-c (AC1-9 + image observations); new evidence/audit/s_c_render_card.py + s-c-audit-{stdout,stderr}.txt + shots/s-c-card-preview-{desktop,mobile}.png; updated 00-BRIEF, CHANGES, DECISION (S-c-01..04), CLAIM-REGISTER (review log), this file, NEXT-PROMPT.

## Decisions (do not reverse without new evidence)
| ID | Decision | Reason | Date | Owner |
|---|---|---|---|---|
| S-c-01 | Phase 3 gate PASSED (five questions answered in DECISION.md; UI level = new static asset + head meta, lowest level for F-04) | share unfurl is rendered by platforms, not the page; no layout change | 2026-10-28 | campaign |
| S-c-02 | Research: 5 live dev-tool og:images inspected (posthog/supabase/tailwind/raycast/zed); Figma Community frames still CloudFront-blocked (disclosed, metadata-only) | ≥3 examples / ≥2 sources requirement met with real assets | 2026-10-28 | campaign |
| S-c-03 | Route A (minimal dark text card, Supabase-pattern) — HUMAN APPROVED via question tool; B (product shot)/C (mascot)/D (mark-only) rejected with reasons in DECISION.md | most on-brand, tiny file, safest crop, all strings register-approved | 2026-10-28 | human/campaign |
| S-c-04 | Relative og:image URL (domain-gated compromise); asset name og-card-1200x630.png; ?v=b905c417 (sha256[:8]); twitter:title/description mirror existing approved og/meta copy verbatim | absolute URL would require a fabricated domain — prohibited (B-01); relative resolves on X/Slack/Discord | 2026-10-28 | campaign |
| D-01..D-08, P2-01..P2-06, S-a-01..03, S-b-01..06 | unchanged | see DECISION.md | 2026-10-28 | human/campaign |

## Evidence map
- Slice proof: EVIDENCE.md (AC1-9 table + visual observations); evidence/audit/s-c-audit-stdout.txt (8 og + 4 twitter tags in head inventory, canonical=false, description_len=157, ua_parity 6/6 @98460 B, FAQ 20/20, anchors 0 missing); shots/s-c-card-preview-{desktop,mobile}.png + the asset itself read at full res
- Gates: asset checks (1200×630 / 118901 B / 0 URL strings) · live-serve curl 200 image/png · audit_site.py exit 0 · visual gate ALL 3 images read · check:agent FAIL = pre-existing B-07 family (see risks — now 2 violations, both other workstreams)
- Phase 2 (unchanged): STRATEGY.md, CLAIM-REGISTER.md (S-c review-log row added), CONTENT-MAP.md
- Phase 1 (unchanged baseline): RECON.md, FINDINGS.md (F-04 now fixed by S-c; F-02/F-03/F-09/F-11 remain domain-gated), evidence/audit/crawl-report.json
- Phase 0 (unchanged): RESEARCH.md + evidence/research/sources.md; AI-answer baseline still BLOCKED (B-01), prompt set v1 in RESEARCH §5

## Open risks / blockers
| ID | Risk/blocker | Impact | Owner | Next action | Trigger |
|---|---|---|---|---|---|
| B-01 | No live domain (pre-launch) | sitemap/canonical/GSC/IndexNow/AI baseline/CWV field/og:url + ABSOLUTE og:image URL all parked | human | choose domain + host → slice S-d | whenever ready |
| B-03 | No analytics/GSC/Bing properties | week-0 measurement impossible | human | create at domain time | domain chosen |
| B-07 | Repo gate `npm run check:agent` red on main: tests/test_commit_attribution.py 419 lines (bee491d5) | every future session's repo gate stays red until fixed; NOT campaign-caused | git-attribution/agent-map workstream | split the test file | their next session |
| B-07b (new this session, low) | context hygiene now ALSO names src/hutch/server/static/hutch-composer.css (449 lines) — the other workstream's in-flight UNCOMMITTED file | gate stays red even after B-07 until they split/commit it | composer/dashboard workstream | split before commit | their next commit |
| B-08 (low) | 320×568: second stacked hero CTA edge ~19px lower after trust line (pre-existing) | cosmetic; primary CTA fully visible | campaign (future polish) | only if a hero-CSS slice is ever approved | next hero-touching slice |
| B-09 (info) | impeccable PRODUCT.md carries stale "source and downloads are private" instruction (S-b-03) | design-workflow agents could reintroduce F-01-style wording | design-workflow owner | refresh PRODUCT.md positioning tail | their next session |
| B-10 (new, low, info) | og:image/twitter:image are RELATIVE URLs (DECISION S-c-04); Facebook strictly requires absolute | FB/WhatsApp shares may render no image until S-d; X/Slack/Discord resolve relative | campaign (S-d) | rewrite both tags with absolute https://<domain>/… URL + add og:url at domain time | domain chosen |

## Next slice (one only)
- **S-d remains domain-gated (B-01)** — sitemap/canonical/verification/absolute-og-URL/AI-baseline work cannot start without a human domain+host decision.
- If B-01 is still unresolved next session, the session should be a REVIEW/HANDOFF session (campaign review of all landed slices S-a..S-c on the built site) or the human's domain decision itself — do not invent a domain.
- If the human HAS chosen a domain: run S-d per CONTENT-MAP §2 (sitemap.xml + robots Sitemap directive, canonical, og:url + absolute og:image/twitter:image (B-10), GSC/Bing verification, IndexNow, deploy-host header checks, AI-answer baseline with RESEARCH §5 prompt set, CWV lab). AC + rollback there; open question to bring to the human at that point: og:image size strategy (keep1200×630 static vs 2× for retina) — current card is 1× and passes spec.
- Write scope for S-d will be announced by that session's brief; expect website/index.html head, robots.txt (Sitemap directive ONLY — D-04 allow-all stands), new sitemap.xml, .pipeline/**.
- Commit: `seo(slice-s-d): …` locally; do not push.

## Environment facts
- Build: no site-CSS rebuild needed for S-c (none run; no CSS touched). `npm run build:css:site` only if site CSS is ever touched (avoid — write scopes have forbidden it so far)
- Card re-render: `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/s_c_render_card.py` (regenerates website/assets/og-card-1200x630.png + both unfurl previews; needs Playwright chromium — present in env)
- Serve/crawl: `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/audit_site.py` (self-serves website/ on :8899); screenshots via evidence/audit/capture_site.py
- Tests: `npm run check:agent` — currently RED for B-07 + B-07b (both other workstreams); report as such, do NOT "fix" in a marketing session
- Pre-commit hook `.githooks/pre-commit` exists but is NOT active (core.hooksPath unset) — other workstream's; do not enable
- Concurrency: other agent holds uncommitted work in src/hutch/server/**, app/**, tests/**, package.json, pyproject.toml, AGENTS.md, CONTRIBUTING.md, .gitignore + untracked .ai/, .codex/, .githooks/, hutch-composer.css etc. — never touch/stage; use `git show HEAD:<file>` for committed-state reads
- AI targets: Google AIO/AI Mode, ChatGPT Search, Perplexity, Copilot, Gemini, Claude

## Do not do
- Do not edit llms.txt (approved state), downloads.json (P2-04), robots.txt (D-04 allow-all stands; Sitemap directive only at S-d), README.md, or any src/ file in a marketing session.
- Do not flip the H1 (P2-01 Option A keeps "A little help with what's next.").
- Do not add og:url, canonical, sitemap, or an ABSOLUTE og:image URL (all B-01 domain-gated; would need a fake URL — prohibited).
- Do not add claims beyond the register; prohibited-claims table in CLAIM-REGISTER.md is campaign-wide and has no expiry (no star counts, no benchmarks, no "best").
- Do not re-render the card with new text without (a) register-approved wording and (b) bumping the `?v=` in both image tags (index.html:15, :21).
- Do not push/deploy/merge. Do not claim a gate passed without naming its evidence path.
