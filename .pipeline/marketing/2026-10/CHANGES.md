# CHANGES — Hutch — 2026-10-28

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

## Session summary
- Slices completed: Phase 1 audit (RECON + FINDINGS + DECISION updates); Phase 2 strategy (STRATEGY + CLAIM-REGISTER + CONTENT-MAP + human sign-off)
- Slices partially done / reverted: none
- Not done (with reason): fixes (audit is read-only by design; strategy is sign-off by design); axe/a11y-gate (no dependency in repo — limitation, not skipped silently); live-URL checks (no domain, B-01); AI-answer baseline (site not live + no engine access, B-01); S-a/S-b/S-c/S-d implementation (queued behind sign-off — now unblocked for S-a)
- Other agents' work touched? (must be "no"): no
