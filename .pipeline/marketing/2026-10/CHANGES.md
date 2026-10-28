# CHANGES — Hutch — 2026-10-28

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
