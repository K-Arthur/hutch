# FINDINGS — Hutch — 2026-10-28 (session 2, Phase 1 audit)

Severity: S0 blocks core task/legal exposure · S1 major friction/frequent error · S2 minor-but-real · S3 opportunity.
Status: confirmed (measured) · probable · needs-human · blocked-human.
Evidence root: `.pipeline/marketing/2026-10/evidence/audit/` (crawl-report.json = C, shots/ = S).

| ID | Sev | Status | Surface | Page(s) | Evidence (file:line / path / command) | User impact | Fix level | Slice |
|---|---|---|---|---|---|---|---|---|
| F-01 | S1 | confirmed | machine | llms.txt | llms.txt:3 ("private preview: there is no public download yet") + llms.txt:9 ("Source and downloads are not public") vs README:5 (public MIT-licensed) + index.html:793 ("public on GitHub"); C llms_txt | AI agents/tools reading llms.txt will tell users the source is private — false availability answer; contradicts the one fact every evaluator needs | content | S-a entity-surface repair |
| F-02 | S1 | blocked-human (B-01) | machine | site-wide | sitemap.xml 404 (C fetches); robots.txt:1-2; no domain (owner-confirmed 2026-10-28) | No domain ⇒ no sitemap/canonical/GSC/IndexNow; discoverability work beyond repo surfaces is impossible | config | S-d domain-gated (human) |
| F-03 | S2 | blocked-human (B-01) | metadata | `/` | C head.canonical=false; index.html:3-217 has no canonical link | Engines must consolidate duplicate/parameterized URLs themselves once a domain exists; trivial now, required at launch | config | S-d domain-gated |
| F-04 | S2 | confirmed | metadata | `/` | C head.og = {title,description,type} only; twitter = {} ; index.html:10-12 | Shares on X/Discord/LinkedIn/Slack render bare text, no image/URL — weaker CTR and weaker entity presentation | content+asset | S-c social cards (og:image asset domain-independent; og:url waits for domain) |
| F-05 | S3 | confirmed (accepted risk, D-03) | schema | `/` | FAQPage block index.html:40-207; parity 20/20 exact (C faq_parity); Google removed FAQ rich results May 2026 (RESEARCH §9 source log) | No rich-result loss possible (feature gone); markup is parity-clean so no manual-action exposure; keep only while FAQ visible | document | Phase 2 claim register (refresh trigger: quarterly changelog check) |
| F-06 | S2 | confirmed | machine | llms.txt | C llms_txt.mentions_github=false; llms.txt:1-25 never links https://github.com/K-Arthur/hutch | An agent quoting llms.txt cannot cite the canonical entity surface (GitHub README) — weaker AI-answer citation path (D-05/D-06) | content | S-a entity-surface repair |
| F-07 | S2 | needs-human | machine | downloads.json | downloads.json:9-38 lists windows-x64/macos-arm64/macos-x64/ubuntu-x64, all `artifacts: []`, no per-platform status; site says macOS/Windows executors unavailable (index.html:811) | Machine readers can misread a platform list as support; humans read the site's honest table and get a different picture | config (manifest contract) | S-a but requires manifest-owner decision first |
| F-08 | S3 | confirmed | metadata | `/` | C description_len=198; index.html:7 | SERP snippet likely truncates mid-sentence ("Development preview." may be cut) | content | S-b on-page metadata trim |
| F-09 | S2 | needs-human (B-03) | measurement | site-wide | no analytics in site.js (full read) or index.html; no verification files; workflows = CI/desktop only | Week-0 measurement impossible even after domain until properties exist; AI-answer baseline stays blocked | config | S-d domain-gated (human creates GSC+Bing) |
| F-10 | S3 | confirmed (pending D-01 sign-off) | content | `/` hero | H1 index.html:278 "A little help with what's next." carries no category terms; eyebrow above H1 does (index.html:277); title tag has them (index.html:6) | H1 remains the strongest on-page entity signal; category is one line up, so cost is small — but D-01 may want it stronger | content | positioning slice (Phase 2) |
| F-11 | S3 | confirmed | machine | site-wide | security.txt 404 (C fetches) | No vulnerability-reporting pointer for researchers on the public surface (SECURITY.md exists in repo only) | content/config | deferred until domain (needs contact address = human) |
| F-12 | S3 | confirmed | content | `/` hero | desktop-top.png observation: "MIT-licensed / open source / Linux" absent from first desktop screen; they appear in meta description, #get (index.html:772), footer (index.html:983) | Dev-tool evaluators scan for open-source/licence signals immediately; the strongest trust words sit one scroll down | content | positioning slice (Phase 2, ties to D-01) |

## Detail (S0/S1)

### F-01 — llms.txt states the source is private (it is public)
- What happens: `website/llms.txt` line 3 says "It is a private preview: there is no public download yet" and line 9 says "Status: private preview. Source and downloads are not public". The repository and the site both state the source is public MIT-licensed on GitHub.
- Reproduction: `cat website/llms.txt` (lines 3, 9) vs `sed -n '5p' README.md` vs open `website/index.html` line 793 ("MIT-licensed development source is public on GitHub"). Programmatic proof in crawl-report.json (`llms_txt`, `downloads_manifest.github_links_in_html`).
- Evidence: llms.txt:3, llms.txt:9, README:5, index.html:793; downloads.json:5 proves the public repo URL is the same entity.
- Why it matters: llms.txt is written for AI agents. The current text will produce exactly wrong answers to the #1 evaluator question ("can I get the source?") and contradicts the site + README — the entity-consistency failure Phase 0 predicted (HANDOFF B-02, now confirmed). It also undercuts every honest "development preview" statement by over-rotating into "not public".
- Root cause / seam: `website/llms.txt` was drafted at an earlier stage and never refreshed when the repo went public; no refresh trigger existed (claim register gap).
- Proposed slice: S-a (content-only fix to llms.txt + register refresh trigger in Phase 2 claim register). Do NOT touch in this audit session.
- Confidence / unknowns: high on the contradiction; the exact replacement wording is Phase 2's call (needs claim-register parity with README/site).

### F-02 — no sitemap and no domain (known blocker, now measured)
- What happens: `/sitemap.xml` returns 404 on the built site; robots.txt has no Sitemap directive and explains why (robots.txt:1-2). The site has no public domain (owner-confirmed 2026-10-28), so no absolute URL can exist.
- Reproduction: crawl-report.json `fetches["sitemap.xml"].status == 404`; `cat website/robots.txt`.
- Evidence: website/robots.txt:1-2; crawl-report.json; no deploy workflow in `.github/workflows/` (ci.yml, desktop-linux.yml, native-platform.yml).
- Why it matters: without domain + sitemap, IndexNow/GSC/Bing submission and canonical consolidation cannot start; every technical-SEO slice is parked behind this single human decision.
- Root cause / seam: pre-launch product state, not a defect — recorded so no one "fixes" it with a fake URL.
- Proposed slice: S-d — human chooses domain + host; then sitemap.xml + Sitemap directive + canonical land in one technical slice.
- Confidence / unknowns: high; the only unknown is the human's domain/host choice and whether the host serves proper Content-Type/caching (python http.server does not — deploy-phase verification list in HANDOFF).

## Review verdicts (campaign review, session 7, 2026-10-28)

Recorded as a review record; the baseline table above is intentionally unmodified. Full check→output map in `REVIEW.md`; fresh crawl in `evidence/review/r7-audit-stdout.txt`.

| ID | Verdict | Reason + evidence (session 7) |
|---|---|---|
| F-01 | CLOSED (by slice S-a) | llms.txt:3,9 re-read = approved C-16 wording; `private preview` grep over website/ = 0 hits; audit llms_txt 200, mentions_github=true |
| F-02 | OPEN — blocked-human (B-01) | sitemap.xml 404 + robots.txt without Sitemap directive re-confirmed (r7 audit); domain decision still pending |
| F-03 | OPEN — blocked-human (B-01) | head.canonical=false re-confirmed (r7 audit); canonical lands with S-d |
| F-04 | CLOSED (by slice S-c) | r7 audit head: 8 og + 4 twitter tags; canonical=false / og:url absent by design (B-01); og:image `?v=` = asset sha256[:8] verified |
| F-05 | accepted (D-03), no action | FAQPage parity 20/20 re-confirmed; quarterly changelog check remains the registered trigger |
| F-06 | CLOSED (by slice S-a) | llms.txt:25 Repository line = C-17 verbatim; mentions_github=true |
| F-07 | OPEN — needs-human (B-06, P2-04) | downloads.json owned by the desktop release pipeline; campaign never edits; status-field request still unfiled (pipeline touch not yet known) |
| F-08 | CLOSED (by slice S-b) | description_len=157; index.html:7 ends "Development preview." complete; twitter:description mirrors :7 byte-identical |
| F-09 | OPEN — needs-human (B-03) | no analytics/GSC/Bing properties; domain-gated; AI-answer baseline still blocked |
| F-10 | CLOSED-BY-DECISION (D-01 Option A, P2-01) | H1 "A little help with what's next." intentionally kept; the trust-word gap delivered as F-12's fix; residual (category terms not in H1) accepted by the human decision |
| F-11 | OPEN — deferred (domain + human contact address) | security.txt 404 re-confirmed (r7 audit); needs a contact address = human input at domain time |
