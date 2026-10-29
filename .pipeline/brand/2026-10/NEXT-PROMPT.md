# NEXT-PROMPT.md - paste-ready continuation: Run 4

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
RUN:                  4
HUMAN_AUTHORITY:      local commits only; never push/deploy/merge without explicit instruction
CONCURRENCY:          write scope .pipeline/brand/** only; docs/brand/** needs a fresh explicit
                      assignment (the Run 3 assignment covered only the protocol adoption);
                      never read .worktrees/; stage only files this session wrote and reviewed
JURISDICTIONS:        CONFIRMED 2026-10-28 (D13): US + EU + UK + Canada; Nice classes 9 and 42 only
LICENCE_POSTURE:      open source (MIT code, OFL fonts, vendor marks per docs/brand-assets.md);
                      zero external spend (D15); IP risk owned by the maintainer in writing (D20/D23);
                      no funded counsel until re-decided
BUDGET:               <=15 files read per pass; <=~30 min wall; <=15 external fetches
```

## Run 4 = resolve the knockout stop condition first, then (only if clean) text-first concept
## elaboration for D1+D2; write a dated class-verification record either way

Preconditions (read, do not assume):
1. DECISION.md shows D21 (creation paused until manual class check), D22 (protocol signed and
   adopted), D23 (written risk ownership), D24 (browser approved), D25 (mascot marketing-only) and
   B7/B8 (the stop condition and the coverage gaps). If any is absent, re-read Run 3 first.
2. Read in this order: DECISION.md, IP-CLEARANCE.md (section 0 and section 8), CLEARANCE-PROTOCOL.md
   (sections 3-5 and 9), PROVENANCE-REGISTER.md, then STRATEGY.md 7 and CONCEPT-LOG.md D1/D2.
3. Order is mandatory: (a) class check first; (b) if any observed HUTCH entry covers Nice 9 or 42 in
   the US, EU, UK or Canada, stop - escalate, no design talk, no asset work; (c) only if the name is
   clear of core-class overlap (or the human accepts a documented, dated risk position) may concept
   elaboration start, and even then text and specs only.

## Step list

1. Capability step (first): run `uv sync --extra browser` (approved, D24) and verify the Playwright
   Chromium revision works. If it fails, record the exact error as blocker B1 and fall back to a
   human-supplied capture harness.
2. Class verification (highest value): open the register pages in the browser - USPTO serials
   99695333 and 87196849; UKIPO UK00003791602, UK00902129492, UK00915655715; plus EUIPO, TMview,
   WIPO Global Brand Database and CIPO for "Hutch" in classes 9 and 42. Record for each: holder,
   status, Nice classes, goods/services wording, filing/priority dates, URL and retrieval date. Add
   dated rows to IP-CLEARANCE.md; never record an unreachable page as clear. If CAPTCHA still blocks,
   record "unreachable - human browser pass required" and ask the human to do it.
3. Stop-condition decision: if a core-class overlap is confirmed, or remains unverifiable, ask the
   human in plain language what to do (pause, fund counsel, narrow goods/services, or reconsider the
   name) and record the answer in DECISION.md. No concept files in that case.
4. U21 (D26): run the free RDAP checks (hutch.com, .app, .ai, .dev) and the GitHub / npm / PyPI /
   social-handle checks; record observed conflicts with dates.
5. Vienna codes: open the WIPO Vienna browser, record the edition number, the codes for a polygon
   outline and a centred dot, and their verbatim definitions. Do not cite codes before this.
6. Conditional (only after step 3 clears): text-first concept elaboration for D1 "Centre Dot" +
   D2 "Local Hub" - written specs only: master geometry rules (32-unit grid, hexagon path, centre-dot
   radius, stroke width), lockup architecture and casing rule, clear space and minimum sizes, a 16px
   legibility test plan and a monochrome/forced-colours test plan, described not drawn. No assets, no
   renders. Confirm whether D3 "Quiet Chrome" or D4 "Character Tiering" joins the shortlist.
7. Close-out: update DECISION.md; rewrite HANDOFF.md and NEXT-PROMPT.md (Run 5); commit one coherent
   unit, docs(brand): prefix, local only.

## Rules for this run

- No clearance, distinctiveness or non-infringement claims. Results are "pre-screen, not clearance"
  and "risk rated"; "cleared to the extent documented" only for what is actually documented.
- A confirmed core-class hit is a stop condition: escalate, no design talk.
- No asset generation in this run. Text-first only. No renders unless the human asks for them after
  the class check clears and G1's design gate is opened by a dated decision.
- Evidence convention: URL + retrieval date per source; every hit, miss and unreachable recorded
  with the exact query. A bot-blocked register is "unreachable", never "clear".
- No emoji. No docs/brand/** writes without a fresh assignment. Never read .worktrees/.
- Stop rules: missing sign-off, a confirmed hit, missing human decision, or capability gap -> blocker
  in DECISION.md; a blocker is a valid outcome.

Deliverables: updated IP-CLEARANCE.md with the dated class-verification rows; updated DECISION.md
(D28+, blockers); conditional CONCEPTS-D1-D2.md (text specs only); updated HANDOFF.md and
NEXT-PROMPT.md (Run 5). If a core-class overlap is confirmed: no concept file, a blocker instead.
