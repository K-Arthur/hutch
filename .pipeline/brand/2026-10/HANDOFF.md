# HANDOFF.md - session end, Run 5 (2026-10-29, America/Vancouver)

Commit: local only, docs(brand): prefix; nothing pushed or merged. Authority used: local commits,
write scope .pipeline/brand/2026-10/**; no product/site/docs/desktop write; .worktrees/ never read.

## Headline

1. Research method installed: PRINCIPLES.md, derived from the Anthropic "canvas-design" and
   "frontend-design" skills (fetched 2026-10-29) plus optical-correction practice. It records the
   method (philosophy first, subject-grounded, one bold move, two redrawn size tiers, refine-don't-add)
   and a written diagnosis of why rounds 1-12 failed it.
2. Colour worked as a first-class track: COLOUR-SYSTEM.md with 24 measured WCAG pairs, light-surface
   ramp (emerald-400 fails on paper at 1.65:1 -> emerald-700 at 4.69:1), brand=success token collision,
   CVD simulation, print approximations. Evidence: assets/concepts/sheets/colour-sheet.png.
3. Wordmark decided by the human: Bricolage Grotesque 800, lowercase "hutch" + emerald period (D42).
4. Mark: twelve rounds of concepts were produced and ALL were rejected by the human on 2026-10-29
   ("these are all horrible"; D51). The work is archived as non-candidates
   (assets/archive/rejected-marks-2026-10-29/, manifest inside; D52). NO mark asset is live, current
   or proposed. Mark design continues in Run 6 from a clean sheet.

## Artifact state

| Artifact | Status |
|---|---|
| PRINCIPLES.md | NEW: researched method + rulebook R1-R11 |
| COLOUR-SYSTEM.md | NEW: measured colour system, findings F1-F7, proposed surfaces |
| assets/concepts/sheets/colour-sheet.png, colour-sheet.html | NEW evidence |
| assets/concepts/fonts/ (8 OFL candidates), wordmark-sheet.png | wordmark evidence; Bricolage selected |
| assets/archive/rejected-marks-2026-10-29/ | ARCHIVED, NOT CANDIDATES (98 files: sheets, scripts, candidate pack, legacy hexagon pack) |
| DECISION.md | D39-D52 |
| CONCEPT-LOG.md | 6.1-6.8 incl. the rejected-vocabulary table |
| PROVENANCE-REGISTER.md | Appendices B and C |
| RESEARCH.md, APP-BRAND-AUDIT.md, ASSET-INVENTORY.md, FINDINGS.md, STRATEGY.md | unchanged from Runs 1-2 |
| BRAND-GUIDELINES.md, press kit, platform icon package, production wordmark | NOT PRODUCED - Run 6 scope |

## Decisions binding

Name "Hutch" retained (D38); tagline verbatim (D11); tokens.json governs the ramp (D12); jurisdictions
US/EU/UK/CA + Nice 9/42 (D13); zero external spend (D15); PWA in scope (D16); written IP risk
ownership (D20/D23/D28, re-confirmed at D38); mascot marketing-only until C27 terms (D25); full asset
package authorised pipeline-only (D42); researched method mandatory (D48/D50); marked work archived as
non-candidates (D51/D52).

## Blockers (owner -> next action)

- B10 (human) - confirmed UK class 9/42 overlap; name retained under written risk. No asset may imply
  clearance; a similarity screen for the eventual mark is owed.
- B7 (human) - US serials 99695333 / 87196849 still unretrieved from an official source.
- B8 - still owed: EUIPO eSearch, TMview, CIPO, app stores, exact combined-form phrases.
- B9 (human) - bare-name domains/handles occupied; marketing handle strategy undecided.
- B6 - counsel review owed if funded; gates 3-4 OPEN.

## Next step (one)

Run 6 per NEXT-PROMPT.md: design the mark from a clean sheet to PRINCIPLES, at most two directions,
human picks; then the remaining identity deliverables (guidelines, press kit, production wordmark,
platform icon package, validation matrix, IP updates).

## Environment facts

- Browser renders: .venv with Playwright Chromium 153.0.8010.12; UV_CACHE_DIR=/tmp/uv-cache when the uv
  cache is read-only.
- Colour evidence regeneration: .venv/bin/python assets/concepts/render_colour.py
- Wordmark sheet regeneration: .venv/bin/python assets/concepts/wordmark_sheet.py
- Archived mark generators are in assets/archive/rejected-marks-2026-10-29/scripts/ (reference only).
- The website/ and src/ trees still carry the OLD inline hexagon mark; they were not touched and are a
  later integration slice.

## Do not do

- Do not revive, rename or "improve" anything from the archive; it cannot be a candidate (D52).
- Do not integrate any mark into website/docs/src/desktop without its own dated authorisation.
- Do not claim clearance, distinctiveness or non-infringement; do not state a legal conclusion.
- Do not stage other workstreams' uncommitted files; do not force-push; no emoji.
