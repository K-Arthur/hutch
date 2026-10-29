# NEXT-PROMPT.md - paste-ready continuation: Run 5

## Session input block

```
PROJECT:              Hutch - local-first, open-source multi-bot agent platform
REPO_ROOT:            /home/kevina/CodingProjects/hutch
SITE_APP_PATH:        website/ (marketing), src/hutch/server/ (dashboard)
DOCS_PATH:            docs/
NATIVE_TARGETS:       desktop (Tauri) + web
EXISTING_BRAND_DOCS:  docs/brand-assets.md, docs/design-system.md, DESIGN.md, PRODUCT.md,
                      docs/marketing-site.md, docs/brand/03-CLEARANCE-PROTOCOL.md
ARTIFACT_DIR:         .pipeline/brand/2026-10
TODAY:                <YYYY-MM-DD>
RUN:                  5
HUMAN_AUTHORITY:      local commits only; never push/deploy/merge without explicit instruction
CONCURRENCY:          write scope .pipeline/brand/** only; docs/brand/** needs a fresh explicit
                      assignment; never read .worktrees/; stage only files this session wrote
JURISDICTIONS:        CONFIRMED 2026-10-28 (D13): US + EU + UK + Canada; Nice classes 9 and 42 only
LICENCE_POSTURE:      open source (MIT code, OFL fonts, vendor marks per docs/brand-assets.md);
                      zero external spend (D15); IP risk owned by the maintainer in writing
                      (D20/D23/D28) - but see B10: that ownership was given while classes were
                      unverified; no funded counsel until re-decided
BUDGET:               <=15 files read per pass; <=~30 min wall; <=15 external fetches
```

## Run 5 = decision gate first; B10 blocks all asset work

Run 4 confirmed that two live UK HUTCH registrations cover Nice classes 9 and 42
(UK00003791602 and UK00902129492; IP-CLEARANCE section 0 addendum and 11.3; DECISION D36/B10). That is
a confirmed core-class overlap on pre-screen evidence. It is not a finding of infringement, but it
means Run 5 must NOT start by making assets.

Run 5 starts by looking for a new dated human decision on B10: retain the name with the written risk
re-confirmed after this evidence, change the name, or narrow the offering. If that decision is absent,
the run's valid output is a recorded blocker plus text/evidence work. A blocker is a valid outcome;
do not infer approval from a draft, a direction shortlist or an earlier risk acceptance.

## Preconditions (read, do not assume)

1. DECISION.md shows the Run 4 section (D30-D37) and blockers B10, B9, B7, B8. If B10 is missing,
   re-read Run 4 before doing anything else.
2. Read in this order: DECISION.md (Run 4 and B10), IP-CLEARANCE.md (section 0 addendum and sections
   11.3-11.6), CONCEPTS-D3-D4.md (sections 1, 2 and the section 4 selection aid), CONCEPTS-D1-D2.md
   (sections 1-4 and 6), CLEARANCE-PROTOCOL.md (sections 3-5 and 9), PROVENANCE-REGISTER.md, then
   STRATEGY.md 7.
3. No asset file, master SVG, favicon, manifest icon, render or character image is produced unless the
   human has given a new dated instruction that explicitly names the surfaces. Text and specifications
   only otherwise. No product or source change in any case without its own instruction.

## Step list

1. Gate check. Look for three things: (a) a dated B10 decision (retain / change / narrow); (b) an
   explicit dated authorisation for asset production naming the surfaces; (c) a direction selection
   from the D1-D4 rubric, or an instruction to defer it. Record all three verbatim in DECISION.md with
   the date. If (a) is absent: do steps 5-7 only (evidence and close-out); the blocker stays B10.
2. If "change the name" is decided: do NOT design a new name asset inside this pipeline's existing
   concept set - D1-D4 were elaborated for the retained name. Record the decision, close the asset
   question, and open a rename scope as a new decision item (it needs its own shortlist and its own
   clearance pass). A blocker-shaped handoff is acceptable.
3. If "retain" is decided AND assets are explicitly authorised: produce the master and variants from
   CONCEPTS-D1-D2 (1.1 geometry, 1.3 small-size rule, 1.4 clear space, 6.2-6.4 wordmark and lockups)
   and CONCEPTS-D3-D4 (1.4 mono-first favicon, 1.5 PWA layers). One master; every copy derives from it;
   no redraw. Run the 16px, monochrome and forced-colours tests in the installed Chromium; record named
   evidence per CLEARANCE-PROTOCOL section 4. Add a PROVENANCE-REGISTER row per asset (author,
   tool/version, date, licence, approver, master file). The character stays marketing-only (D25); no
   expanded character use before the C27 terms statement.
4. If "narrow the offering" is decided: record it; the asset question stays open until the goods and
   services scope is settled. No asset in this run.
5. Evidence-gap work that is allowed without any asset decision (all free, dated, within the fetch
   budget): EUIPO eSearch, TMview and CIPO in the browser for HUTCH in classes 9 and 42; a USPTO
   interactive TSDR session for serials 99695333 and 87196849 (do not create an API account without a
   decision); app stores for apps named Hutch; exact combined-form phrases "Hutch app", "Hutch AI",
   "Hutch assistant". Append dated rows to IP-CLEARANCE.md. A blocked source is unreachable, never clear.
6. Selection aid: if the human has not chosen a direction, walk the CONCEPTS-D3-D4 section 4 rubric
   with the new evidence and record the human's choice if one is given. Do not choose for them; the
   confirmed UK overlap is a name-level risk that applies to all four directions equally.
7. Close-out: update DECISION.md (D38+ and blocker state), rewrite HANDOFF.md and NEXT-PROMPT.md
   (Run 6), commit one coherent unit with the docs(brand): prefix, local only.

## Rules for this run

- No clearance, distinctiveness or non-infringement claims. "Pre-screen, not clearance"; "risk rated".
  Anything stronger only for what is documented.
- No asset of any kind without a new dated human decision naming the surfaces; no product or source
  change without its own instruction. Text-only is the default and a blocker is a valid run result.
- Evidence convention: URL + retrieval date per source; every hit, miss and unreachable recorded with
  the exact query. A bot-blocked source is "unreachable", never "clear".
- No emoji. No docs/brand/** writes without a fresh explicit assignment. Never read .worktrees/.
- Stop rules: missing human decision, a newly confirmed core-class hit, or a capability gap -> blocker
  in DECISION.md. Do not substitute inference or memory for a register page you could not read.
- If the human re-confirms the written risk ownership: record it verbatim with a new D-number and
  date; re-confirm it at each later gate. If counsel is funded, gates 3-4 move to counsel and stay
  OPEN until a report exists.
- Do not bypass CAPTCHAs, logins or paywalls; do not create accounts without a decision.

## Deliverables (conditional on the gate)

- If a dated B10 decision and an explicit asset authorisation exist: master file and the authorised
  variants, evidence captures (16px, mono, forced-colours), PROVENANCE-REGISTER rows, updated
  DECISION.md (D38+), HANDOFF.md and NEXT-PROMPT.md.
- If no such decision exists: updated DECISION.md (blocker state and any new evidence), updated
  IP-CLEARANCE.md (dated rows from step 5), updated HANDOFF.md and NEXT-PROMPT.md. No asset.
- Either way: one local commit, docs(brand): prefix, staging only files the session wrote.
