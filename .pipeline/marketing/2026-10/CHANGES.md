# CHANGES — Hutch — 2026-10-28

## Session 9 - PUBLIC LAUNCH (GitHub Pages, public-repo docs, community prerequisites) - 2026-10-28
Files: README.md, SECURITY.md, PRODUCT.md, CONTRIBUTING.md (2 public-wording hunks), CODE_OF_CONDUCT.md (new), docs/README.md (new), docs/brand-assets.md, docs/marketing-site.md, docs/discoverability.md (new), website/index.html, website/robots.txt, website/sitemap.xml (new), website/.nojekyll (new), website/.well-known/security.txt (new), website/security.txt (new), website/llms.txt, website/assets/github-social-preview-1280x640.png (new), .github/ISSUE_TEMPLATE/{bug_report,feature_request,config}.yml (new), .github/pull_request_template.md (new), .github/CODEOWNERS (new), .github/dependabot.yml (new), .github/workflows/pages.yml (new), CITATION.cff (new), tests/e2e/test_website.py (one locator line), .pipeline/marketing/2026-10/** (this record), evidence/brand/** (new render script, evidence, thumbnail).
Commits: `076563b6 docs(public): reconcile the public repo surface and add GitHub community files`; `b44e62fd seo(site): publish the marketing site on GitHub Pages with canonical metadata`; plus this session's fix and record commits (see HANDOFF for the pushed range).
What changed (user-visible): the marketing site is now live at https://k-arthur.github.io/hutch/ with canonical, og:url, absolute social image, sitemap, security.txt and a GitHub Pages deploy workflow. The public README is rebuilt for discoverability and answer engines (badges, tagline, screenshot, quickstart, availability table, six common questions, docs map). GitHub gains topics, a keyword-rich description, Discussions, issue forms, PR template, CODEOWNERS, CITATION, Dependabot and security features. The repository's public docs no longer describe a private preview.
Claims affected: no new product claims. Register additions C-27..C-30 (live Pages URL, v0.1.0 source pre-release, repository metadata, public MIT source). Existing C-01..C-26 wording unchanged.
Docs updated: README, SECURITY, PRODUCT, CONTRIBUTING, CODE_OF_CONDUCT, docs/README, docs/brand-assets, docs/marketing-site, docs/discoverability.
Gates run (command -> result):
- Unauthenticated GitHub API -> 200, visibility public; 20 topics applied; discussions, secret scanning, push protection, private vulnerability reporting, Dependabot security updates, delete-branch-on-merge and auto-merge enabled.
- gitleaks over the 40 unpublished commits -> no leaks; staged-blob scans -> no leaks; scripts/check_repo_hygiene.py staged check -> passed.
- `.pipeline/marketing/2026-10/evidence/audit/audit_site.py` -> exit 0, stderr 0 B: canonical true; 9 og keys; 4 twitter keys; sitemap.xml and security.txt 200; six crawler user-agents identical bytes; FAQ parity 20/20; description 157 chars; anchors 10/10.
- `pytest -q tests/e2e/test_website.py` -> 42 passed, 0 failed (after R9-05/R9-06/R9-07 fixes); structured-data e2e included.
- `npm run check:agent` -> FAIL, pre-existing B-07 only: tests/test_commit_attribution.py 419 lines. No new violation from this session (test_website.py stayed at its frozen 1449 lines).
- `scripts/audit_emoji.py` -> clean.
Evidence paths: .pipeline/marketing/2026-10/EVIDENCE-session-9.md; docs/discoverability.md; .pipeline/marketing/2026-10/evidence/brand/README.md; RELEASE-NOTES-v0.1.0.md.
Residual risk: 54 open Dependabot alerts (8 critical; top follow-up); social preview upload manual; Search Console and Bing verification owner-gated; origin-root robots.txt and security.txt need a custom domain; CI on the final pushed commit must be watched; repository size stays about 1.37 GB.
Next: HANDOFF.md + NEXT-PROMPT.md.

## Session 7 — CAMPAIGN REVIEW (Phase 7, read-only on product) — 2026-10-28
Files: .pipeline/marketing/2026-10/{00-BRIEF,REVIEW,FINDINGS,EVIDENCE,DECISION,CHANGES,HANDOFF,NEXT-PROMPT}.md + NEW evidence/review/{r7-audit-stdout.txt,r7-audit-stderr.txt}
Commits: `marketing(review): verify shipped S-a..S-c state, close F-01/F-04/F-06/F-08/F-12 with fresh evidence` (this commit; .pipeline/marketing/ only)
What changed (user-visible): NOTHING on the product surface (review phase rule; zero product files touched, other agent's dirty tree never staged).
Claims affected: none published; parity VERIFIED — every card/head-meta/llms.txt string spot-checked against register rows C-01/C-02/C-03/C-05/C-06/C-10..C-13/C-15..C-19/C-24/C-26 (REVIEW.md checks 8-11); prohibited-claims grep = 0 hits.
Docs updated: n/a (no behavior change)
Gates run (command → result):
- `uv run --frozen --no-sync python evidence/audit/audit_site.py` → exit 0, stderr 0 B: canonical=false; 8 og + 4 twitter tags; description_len=157; FAQ parity 20/20; JSON-LD 2/2; anchors 10/10; UA parity 6/6 identical (98,460 B); llms.txt 200 mentions_github=true; only known domain-gated 404s (sitemap.xml, security.txt) — evidence/review/r7-audit-stdout.txt
- sha256(og-card)[:8] = b905c417 = ?v= in og:image/twitter:image; card re-render SKIPPED per instruction (asset present); card read at full res, strings = register rows only (REVIEW.md check 6-8)
- prohibited-claims strict grep over website/ → 0 hits; soft terms only in qualified-negative "safe" contexts (C-25 anchor) (REVIEW.md check 11)
- `npm run check:agent` → FAIL (pre-existing B-07): now ONE violation (tests/test_commit_attribution.py, 419 lines, bee491d5); B-07b no longer named by the gate (other workstream splitting hutch-composer.css — untouched/unverified by campaign)
Evidence paths: REVIEW.md (check→output map + findings verdicts); evidence/review/r7-audit-{stdout,stderr}.txt; FINDINGS.md "Review verdicts" section
Residual risk: unchanged from session 6 — B-01 domain gates S-d (sitemap/canonical/og:url/absolute og:image/AI baseline/CWV field); B-03/B-06/B-11 human-owned items open.
Next slice: NO domain-independent slice exists. Next step = human domain+host decision → slice S-d (CONTENT-MAP §2); see NEXT-PROMPT.md.

## Slice S-c — og:image asset + social meta tags (Phase 5 implementation) — 2026-10-28 (session 6)
Files: website/index.html (1 region: 10 new head tags after :12) + NEW website/assets/og-card-1200x630.png + .pipeline/marketing/2026-10/{00-BRIEF,EVIDENCE,CHANGES,DECISION,CLAIM-REGISTER,HANDOFF,NEXT-PROMPT}.md + evidence/audit/{s_c_render_card.py,s-c-audit-stdout.txt,s-c-audit-stderr.txt,shots/s-c-card-preview-{desktop,mobile}.png}
Commits: `seo(slice-s-c): add og:image asset + social meta tags` (this commit; website/index.html + website/assets/og-card-1200x630.png + .pipeline/marketing/ only)
What changed (user-visible): shares of the site on X/Slack/Discord/LinkedIn/Slack no longer render as bare text (F-04). New 1200×630 brand card (Route A, human-approved: hexagon mark + "Hutch" + two-tone "Local-first AI assistants / that run on your machine." + muted "MIT-licensed · open source · Linux · Development preview" footer) referenced via og:image/twitter:image; og:site_name, og:image:alt/width/height and twitter:card (summary_large_image)/title/description added. The page itself is visually unchanged (no layout/DOM/CSS edit). og:url NOT added (B-01 domain-gated; relative image URL recorded as the known compromise — DECISION S-c-04).
Claims affected: NO new claims — every card string is register-approved (og:title wording/C-01, P2-01 trust line verbatim, C-05). C-24 trigger fired (share-surface copy) but same-day ⇒ dateModified stays 2026-10-28 (no edit). Review-log note added to CLAIM-REGISTER.
Docs updated: n/a for product docs (no behavior/limit/pricing/licence change; card restates facts already public in README:5,16-22 + index.html).
Gates run (command → result):
- `file`/`wc -c`/`strings|grep http` on the asset → 1200×630 PNG, 118,901 B (<300 KB), 0 URL strings ✓
- `uv run --frozen --no-sync python evidence/audit/s_c_render_card.py` → card + 1440/390 unfurl previews rendered from committed Geist woff2 + committed tokens only; ALL 3 images read at full res, observations in EVIDENCE.md
- `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/audit_site.py` → exit 0, stderr empty; head inventory shows all 8 og + 4 twitter tags; canonical=false; og/twitter:url absent; ua_parity 6/6 identical (98,460 B, +774 = the tags); FAQ parity 20/20; anchors 10/10; JSON-LD 2/2 — EVIDENCE.md AC table
- live-serve curl of `assets/og-card-1200x630.png?v=b905c417` → 200 image/png ✓
- `npm run check:agent` → FAIL, PRE-EXISTING B-07 family: context hygiene now names 2 violations — tests/test_commit_attribution.py (419 lines, bee491d5) AND src/hutch/server/static/hutch-composer.css (449 lines, other workstream's in-flight uncommitted file). Neither in this diff. Not campaign-caused; not fixed here.
Evidence paths: .pipeline/marketing/2026-10/EVIDENCE.md (AC1-9 → evidence + image observations); evidence/audit/s-c-audit-stdout.txt (crawl report; s-b report preserved)
Residual risk: relative og:image URL — Facebook is strict about absolute URLs; conversion is S-d with the real domain (B-01). check:agent grew a second violation (hutch-composer.css) — still the other workstreams'. Card render is font-limited: future text edits must re-run s_c_render_card.py and bump ?v=.
Next slice: S-d is domain-gated (B-01). If still unresolved, the next session should be a review/handoff session or the human's domain decision — see NEXT-PROMPT.md.

## Slice S-b — on-page metadata trim + above-fold trust row (Phase 5 implementation) — 2026-10-28 (session 5)
Files: website/index.html (3 regions: :7 description, :37 dateModified, :281 trust line) + .pipeline/marketing/2026-10/{00-BRIEF,EVIDENCE,CHANGES,DECISION,CLAIM-REGISTER,HANDOFF,NEXT-PROMPT}.md + evidence/audit/{s_b_focus_capture.py,s-b-audit-stdout.txt,s-b-audit-stderr.txt,shots/*}
Commits: `seo(slice-s-b): trim meta description + add above-fold trust row` (this commit; website/index.html + .pipeline/marketing/ only)
What changed (user-visible): (1) meta description 198→157 ch, sentence-complete, "Development preview." kept — SERP/share snippets no longer risk a mid-sentence cut (F-08). (2) New muted line "MIT-licensed · open source · Linux" above the hero CTAs on desktop AND mobile — dev-tool evaluators now see the licence/OSS/platform trust words on the first screen instead of one scroll down (F-12; P2-01 Option A as human-approved Route A). H1 unchanged.
Claims affected: C-01/C-02/C-03/C-05/C-06 wording re-verified in the new description; C-24 dateModified refreshed 2026-10-26→2026-10-28 (registered trigger fired by visible-copy change); C-02/C-03 gain a hero placement (review-log note). No new claims introduced — trust-row wording is P2-01's approved string verbatim.
Docs updated: n/a for product docs (no behavior/limit/pricing/licence change; the row restates C-02/C-03 already documented in README:5,20 + LICENSE).
Gates run (command → result):
- python length/JSON checks → desc 157 ch, ends "Development preview.", JSON-LD description byte-unchanged, 2 blocks parse ✓
- `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/audit_site.py` → exit 0; head.description_len=157; ua_parity 6/6 identical (97686 B); FAQ parity 20/20; anchors 10/10; only known domain-gated 404s — EVIDENCE.md AC table
- `capture_site.py` + new `s_b_focus_capture.py` → shots regenerated at 4 viewports + 2× clips + keyboard focus-ring capture on the hero CTA (P1-06 closed); ALL images read and observations recorded in EVIDENCE.md
- `npm run check:agent` → FAIL, PRE-EXISTING B-07 (same single violation: tests/test_commit_attribution.py 419 lines from bee491d5, not in this diff; chain stops at context-hygiene). Not campaign-caused; not fixed here.
Evidence paths: .pipeline/marketing/2026-10/EVIDENCE.md (AC1-9 → evidence + image observations); evidence/audit/s-b-audit-stdout.txt (crawl report; phase-1 baseline crawl-report.json preserved)
Residual risk: at 320×568 the second stacked CTA sits ~19 px lower (pre-existing small-viewport stacking, styles.css:260-261) — noted, not fixed (out of slice). og:description (:11, 168 ch) left as-is by scope discipline (S-b-04). Repo gate B-07 belongs to another workstream.
Next slice: S-c social cards — domain-independent part first: og:image asset rendered from existing brand tokens + og:site_name/twitter:* tags minus og:url (needs domain, B-01). Opens with the Phase 3 gate (new static asset, not a layout change — still gated per DECISION.md front-end note).

## Slice S-a — llms.txt entity-surface repair (Phase 5 implementation) — 2026-10-28 (session 4)
Files: website/llms.txt (3+/3-) + .pipeline/marketing/2026-10/{00-BRIEF,EVIDENCE,CHANGES,DECISION,CLAIM-REGISTER,HANDOFF,NEXT-PROMPT}.md + evidence/audit/s-a-crawl-{stdout,stderr}.txt
Commits: `seo(slice-s-a): repair llms.txt availability facts + add GitHub link` (this commit; website/llms.txt + .pipeline/marketing/ only)
What changed (user-visible): llms.txt no longer tells AI agents the source is private. :3 now states the source is public and MIT-licensed on GitHub with no packaged desktop installers; :9 now reads "Status: development preview…" with the same facts; :25 tail replaced by the approved Repository line (GitHub URL + README/evidence-ledger canonical pointer). This was the campaign's only S1 measured contradiction (F-01) and the missing entity link (F-06).
Claims affected: C-15/C-16 (stale "private preview" claims REMOVED from the public surface), C-17 (GitHub link added); wording applied verbatim per human sign-off 2026-10-28 (CLAIM-REGISTER review log). Register rows flipped to approved-with-pointer this session (decision S-a-01, DECISION.md — the rows' own registered refresh trigger).
Docs updated: n/a for product docs (no behavior/limit/pricing change; llms.txt now MATCHES README:5,16-22 + index.html:780,793 — parity restored, nothing new to document).
Gates run (command → result):
- `grep -in "private preview" website/llms.txt` → 0 hits (exit 1) ✓
- `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/audit_site.py` → exit 0; llms_txt.mentions_github false→true; ua_parity 6/6 identical; anchors 10/10; JSON-LD 2/2 parse; FAQ parity 20/20; only known 404s (sitemap.xml, security.txt — domain-gated F-02/F-11) — EVIDENCE.md AC table
- `npm run check:agent` → FAIL, PRE-EXISTING and out of slice: context hygiene flags tests/test_commit_attribution.py (419 lines, commit bee491d5 — not in this diff); agent-map --check stale on untracked .ai/ (other workstream; 0 refs to my files); tool-contracts + constitution PASS. Recorded as B-07 with owner.
Evidence paths: .pipeline/marketing/2026-10/EVIDENCE.md (AC→evidence); evidence/audit/s-a-crawl-stdout.txt (full S-a crawl report; phase-1 baseline crawl-report.json preserved)
Residual risk: none new; llms.txt remains a hand-maintained derived file — refresh trigger now lives in the claim register (C-15..C-17 rows). Repo gate B-07 belongs to another workstream.
Next slice: S-b on-page metadata trim (description 198→≤160 ch + D-01 Option A trust row) — MUST open with the Phase 3 front-end gate + design-route research/approval per the standing design workflow; website/index.html is a rendered surface.

## Phase 2 strategy — positioning, claim register, content map — 2026-10-28 (session 3)
Files: .pipeline/marketing/2026-10/{00-BRIEF.md,STRATEGY.md,CLAIM-REGISTER.md,CONTENT-MAP.md,DECISION.md,CHANGES.md,HANDOFF.md,NEXT-PROMPT.md}
Commits: `marketing(phase-2): strategy, claim register, content map` (this commit; .pipeline/marketing/ only)
What changed (user-visible): NOTHING on the product surface (strategy phase rule; no file under website/, src/, docs/, app/, README.md modified).
Claims affected: none published; register C-01..C-26 created and human-approved. F-01 fix WORDING drafted (llms.txt:3,9 + GitHub link) — applied later in slice S-a.
Docs updated: n/a (no behavior change)
Human decisions recorded (DECISION.md P2-01..P2-05): D-01 = Option A (keep warm H1, lift trust words above fold); D-04 = allow-all crawlers incl. training bots (status quo); B-06 = desktop release pipeline owns downloads.json (campaign never edits).
Gates run (command → result): none this phase (no rendered change; strategy artifacts only). Prior-phase gates remain green (see session-2 entry).
Evidence paths: STRATEGY/CLAIM-REGISTER/CONTENT-MAP cite RECON/FINDINGS measurements; llms.txt evidence re-verified live (cat website/llms.txt); docs pointers re-verified (`ls docs/marketing-site.md docs/realignment/baseline.md docs/realignment/ledger.md` → all exist); version re-verified both worktree and `git show HEAD:pyproject.toml` → 0.1.0.
Residual risk: C-09 comparison facts go stale quarterly (refresh trigger registered); C-24 dateModified is a manual field with a registered trigger; S-b hero change will need the full front-end gate.
Next slice: S-a llms.txt entity-surface repair (content-only, website/llms.txt), per CONTENT-MAP §2 AC + rollback.

## Phase 1 audit — read-only recon + findings baseline — 2026-10-28
Files: .pipeline/marketing/2026-10/{00-BRIEF.md,RECON.md,FINDINGS.md,DECISION.md,HANDOFF.md,NEXT-PROMPT.md,CHANGES.md} + evidence/audit/{audit_site.py,capture_site.py,crawl-report.json,focus-trace.txt,shots/*.png}
Commits: `marketing(phase-1): audit recon + findings` (this commit; .pipeline/marketing/ only)
What changed (user-visible): NOTHING on the product surface (audit phase rule; `git status` shows only .pipeline additions + the pre-existing other-agent dirty files, untouched).
Claims affected: none published yet (claim register arrives Phase 2). llms.txt contradiction CONFIRMED as F-01 but not fixed this session.
Docs updated: n/a (no behavior change)
Gates run (command → result):
- `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/audit_site.py` → exit 0; all 6 crawler UAs 200/identical bytes; 29 internal refs fetched: only sitemap.xml + security.txt 404; anchors 10/10 resolve; 2 JSON-LD blocks parse; FAQ parity 20/20 exact; downloads.json repository URL matches HTML links
- `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/capture_site.py` → 14 screenshots written; reduced-motion check 0 elements at opacity<0.99
- manual image inspection of 9 captures + post-failsafe full page (observations in RECON §9)
Evidence paths: .pipeline/marketing/2026-10/evidence/audit/ (crawl-report.json, focus-trace.txt, shots/)
Residual risk: axe + screen-reader spot-check + lab CWV not run (no tooling/origin; recorded as limitations in RECON §8/§7); F-07 needs manifest-owner input.
Next slice: S-a entity-surface repair (llms.txt freshness + GitHub URL), pending Phase 2 claim-register wording OR — per phase machine — Phase 2 strategy first. See NEXT-PROMPT.md.

## Session 10 - post-launch CI/deploy verification + owner-gated steps - 2026-10-29
Files: .pipeline/marketing/2026-10/{00-BRIEF.md,EVIDENCE-session-10.md,DECISION.md,CHANGES.md,HANDOFF.md,NEXT-PROMPT.md} + evidence/ci/run-40813421173/{jobs.json,3.12-failure-section.txt,3.13-failed-lines.txt}
Commits: one docs/evidence commit for this session (see git log after push).
What changed (user-visible): NOTHING on any public surface. README badge row deliberately unchanged (CI red, R10-04). Site, docs, claims untouched.
Claims affected: none. Claim register unchanged.
Docs updated: campaign artifacts only (evidence + handoff). docs/discoverability.md unchanged (no host change).
Gates run (command → result):
- GitHub API/gh CLI: run 40813421173 conclusion failure (jobs.json); Pages run 40813421201 success; live site + sitemap/llms/security/robots 200; live tokens.css stamp matches record commit; repo settings + v0.1.0 pre-release re-verified.
- Attribution: `git log --name-only b5fee054..577e1154` — no session-9 commit touches the failing test files or src/hutch/server/static/**.
Evidence paths: EVIDENCE-session-10.md; evidence/ci/run-40813421173/.
Residual risk: public CI badge withheld until green; product e2e failures (4 distinct tests across 3.12/3.13) remain open for the product workstream; B-03 (Search Console/Bing) and R9-D1 (54 alerts) untouched owner items.
Next session: re-check CI on main (new runs from merged work), then the badge; owner steps per HANDOFF.

## Session summary
- Slices completed: Phase 1 audit (RECON + FINDINGS + DECISION updates); Phase 2 strategy (STRATEGY + CLAIM-REGISTER + CONTENT-MAP + human sign-off)
- Slices partially done / reverted: none
- Not done (with reason): fixes (audit is read-only by design; strategy is sign-off by design); axe/a11y-gate (no dependency in repo — limitation, not skipped silently); live-URL checks (no domain, B-01); AI-answer baseline (site not live + no engine access, B-01); S-a/S-b/S-c/S-d implementation (queued behind sign-off — now unblocked for S-a)
- Other agents' work touched? (must be "no"): no