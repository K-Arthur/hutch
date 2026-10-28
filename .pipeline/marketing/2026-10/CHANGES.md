# CHANGES — Hutch — 2026-10-28

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
- Slices completed: Phase 1 audit (RECON + FINDINGS + DECISION updates)
- Slices partially done / reverted: none
- Not done (with reason): fixes (audit is read-only by design); axe/a11y-gate (no dependency in repo — limitation, not skipped silently); live-URL checks (no domain, B-01); AI-answer baseline (site not live + no engine access, B-01)
- Other agents' work touched? (must be "no"): no
