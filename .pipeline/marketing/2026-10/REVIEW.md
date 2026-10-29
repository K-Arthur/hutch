# REVIEW — campaign review of slices S-a..S-c (Phase 7) — 2026-10-28 (session 7)

Read-only review of the shipped state on the BUILT site (self-served via audit_site.py on :8899). No product file was read-modified-written; all verdicts below are review records, not fixes. Review scope per NEXT-PROMPT session 6.

## Checks → outputs

| # | Check (mandated by NEXT-PROMPT session 6) | Result | Output / evidence |
|---|---|---|---|
| 1 | `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/audit_site.py` re-run | PASS, exit 0, stderr 0 B | `evidence/review/r7-audit-stdout.txt` (full crawl report), `evidence/review/r7-audit-stderr.txt` (empty) |
| 2 | Head inventory: 8 og + 4 twitter tags; canonical=false; og:url absent | PASS | r7-audit-stdout: og = {title, description, type, site_name, image, image:alt, image:width, image:height}; twitter = {card, title, description, image}; head.canonical=false; og:url absent (B-01 by design) |
| 3 | FAQ parity 20/20; JSON-LD 2/2 parse; anchors 10/10; description_len 157 | PASS | r7-audit-stdout: faq_parity 20/20 0 mismatches; jsonld SoftwareApplication+FAQPage ok; anchors_missing []; description_len 157 |
| 4 | UA parity 6/6 crawler user-agents identical | PASS | r7-audit-stdout ua_parity: default/Googlebot/Bingbot/OAI-SearchBot/ClaudeBot/PerplexityBot — all 200, identical 98,460 B |
| 5 | Only known domain-gated 404s remain | PASS (expected 404s) | fetches: sitemap.xml 404 (F-02), security.txt 404 (F-11); llms.txt 200, mentions_github=true |
| 6 | s_c_render_card.py re-run | SKIPPED per instruction (asset present) | `ls -la`+`file website/assets/og-card-1200x630.png` → 1200×630 RGB PNG, 118,901 B, mtime Oct 28 17:39; card NOT re-rendered or touched |
| 7 | Card asset cache-buster honesty | PASS | sha256(og-card-1200x630.png)[:8] = `b905c417` = `?v=` in og:image (index.html:14) and twitter:image (:21) |
| 8 | Card read at full res; strings mapped to register | PASS | this session re-read the asset image: "Hutch" (entity name); "Local-first AI assistants / that run on your machine." = og:title :10 wording → C-01 (line-start caps, orthographic, DECISION S-c-03); "MIT-licensed · open source · Linux" = P2-01 approved string → C-02/C-03; "Development preview" → C-05. No numbers, benchmarks, superlatives or social proof on card |
| 9 | Head meta claim parity (spot-check) | PASS | index.html:6 title = og:title :10 = twitter:title :19 (byte-identical) → C-01; description :7 = twitter:description :20 (byte-identical) → C-01/C-02/C-03/C-05/C-06 (+ "Choose the models" → C-13); og:description :11 → same rows (pre-existing, S-b-approved untouched); og:image:alt :15 → C-01; JSON-LD :27-37 → C-02 (license), C-03 (OS), C-04 (0.1.0), C-10 (isAccessibleForFree); dateModified :37 = 2026-10-28 → C-24 current (audit software_app confirms) |
| 10 | llms.txt claim parity (spot-check C-15..C-17) | PASS | :3 → C-01/C-02/C-03/C-11 (+C-16 wording); :9 = C-16 verbatim; :10 → C-03/C-12; :11 → C-10 with provider-billing qualifier adjacent; :13/:14/:15/:16/:17 → C-06/C-08/C-18/C-19/C-26; :21-23 "Not claims" → C-11/C-08 qualifiers; :25 = C-17 verbatim (Repository line). "private preview" grep over website/ recursive = 0 hits → C-15 holds |
| 11 | Prohibited-claims grep vs website/ | PASS, 0 hits | strict set `private preview\|free forever\|unhackable\|production-ready\|better than\|nothing leaves your machine\|improves your AI visibility` → 0 matches (exit 1). Soft terms (secure/fastest/benchmark/testimonial/stars/enterprise/"free ") → only qualified-negative "safe" contexts: FAQ index.html:208/211/929/930 (C-25 anchor "not a virtual machine … do not guarantee safe decisions"), :712 ("cannot make an allowed action safe"), :533 ("cannot establish a safe estimate"; "Estimates are not provider billing guarantees"), :418 ("safe checkpoint" — coordinator mechanics). "macOS" :782 ("still in progress") + :821 ("unavailable") = C-03/C-12 qualifiers; no "works on macOS/Windows" claim |
| 12 | S-b trust line still shipped | PASS | index.html:290 "MIT-licensed · open source · Linux" (P2-01 string) present in hero actions |
| 13 | `npm run check:agent` | FAIL — RED, pre-existing B-07 family, NOT campaign-caused | 1 violation: `tests/test_commit_attribution.py` (419 lines, committed bee491d5). Note: session 6 recorded 2 violations; B-07b (hutch-composer.css) is NO LONGER named by the gate — the file still exists but the other workstream appears to be splitting it (new untracked hutch-composer-context.css). Not touched, not verified by this campaign |
| 14 | git hygiene: no product file touched | PASS | review writes = .pipeline/marketing/2026-10/** only; other agent's dirty tree (src/hutch/server/**, app/**, tests/**, package*.json, pyproject.toml, AGENTS.md, CONTRIBUTING.md, .gitignore + untracked .ai/, .codex/, hutch-composer*.css …) never staged |

## Findings verdicts (vs FINDINGS.md baseline)

| ID | Verdict | Evidence (this session) |
|---|---|---|
| F-01 | CLOSED by S-a | llms.txt:3,9 read = approved C-16 wording; "private preview" 0 hits; audit llms_txt 200/mentions_github=true |
| F-04 | CLOSED by S-c | head.og 8 keys + twitter 4 keys in r7 audit; canonical=false (og:url absent by design, B-01); ?v= hash parity verified |
| F-06 | CLOSED by S-a | llms.txt:25 = C-17 verbatim; mentions_github=true |
| F-08 | CLOSED by S-b | description_len=157, :7 ends "Development preview." (complete sentence); twitter:description mirrors :7 |
| F-12 | CLOSED by S-b | trust line index.html:290 above the fold (S-b visual evidence + this session's presence check) |
| F-02 | OPEN — blocked-human (B-01) | sitemap.xml 404 + robots.txt Sitemap-directive-absent re-confirmed (r7 audit robots_txt text) |
| F-03 | OPEN — blocked-human (B-01) | head.canonical=false re-confirmed |
| F-05 | accepted (D-03), no action | FAQPage parity 20/20 re-confirmed; markup stays while FAQ is visible; quarterly changelog check remains the trigger |
| F-07 | OPEN — needs-human (B-06/P2-04) | downloads.json owned by desktop release pipeline; campaign never edits |
| F-09 | OPEN — needs-human (B-03) | no analytics/verification properties; domain-gated |
| F-10 | CLOSED-BY-DECISION (D-01 Option A, P2-01) | H1 intentionally unchanged; trust words lifted above fold via F-12 fix; residual (category terms live in title/eyebrow/sub, not H1) accepted by the human decision |
| F-11 | OPEN — deferred (domain + human contact address) | security.txt 404 re-confirmed (r7 audit) |

## Verdict

All five closed findings remain closed on the built site with fresh evidence; no regression detected; no new defect found. All open findings are blocked on the same recorded human inputs (B-01 domain, B-03 properties, B-06 manifest owner, B-11 contact address) — none is a review-time regression. Claim parity and the prohibited-claims policy hold across card, head meta and llms.txt. Campaign state is healthy; the single next step remains the human domain decision (slice S-d).
