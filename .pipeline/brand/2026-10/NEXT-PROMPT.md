# NEXT-PROMPT.md - paste-ready continuation: Run 2

## Session input block

```
PROJECT:              Hutch - local-first, open-source multi-bot agent platform
REPO_ROOT:            /home/kevina/CodingProjects/hutch
SITE_APP_PATH:        website/ (marketing), src/hutch/server/ (dashboard)
DOCS_PATH:            docs/
NATIVE_TARGETS:       desktop (Tauri) + web
EXISTING_BRAND_DOCS:  docs/brand-assets.md, docs/design-system.md, DESIGN.md, PRODUCT.md, docs/marketing-site.md
ARTIFACT_DIR:         .pipeline/brand/2026-10
TODAY:                <YYYY-MM-DD>
RUN:                  2
HUMAN_AUTHORITY:      local commits only; never push/deploy/merge without explicit instruction
CONCURRENCY:          write scope .pipeline/brand/** only (docs/brand/** only if explicitly assigned);
                      never read .worktrees/; stage only files this session wrote and reviewed
JURISDICTIONS:        UNRESOLVED - assumed US/EU; must be confirmed by the human in this run
LICENCE_POSTURE:      open source (MIT code, OFL fonts, vendor marks per docs/brand-assets.md);
                      budget for fonts/assets/counsel: UNRESOLVED - human must state
BUDGET:               <=15 files read per pass; <=~30 min wall; <=15 external fetches
```

## Run 2 = STRATEGY + CONCEPT-LOG (gate before Run 3: human selects direction; IP pre-screen
## + budget/risk accepted)

Preconditions (read, do not assume):
1. Gate 1 sign-off: confirm the human has approved the Run 1 evidence base
   (00-BRIEF, DECISION, RESEARCH, APP-BRAND-AUDIT, ASSET-INVENTORY, FINDINGS). If not signed off,
   stay in Run 1 - do not start strategy.
2. Read in this order: 00-BRIEF.md, DECISION.md (D01-D08, capability probe), FINDINGS.md,
   then docs/brand/00-PLAN.md via 'git show brand/plan:docs/brand/00-PLAN.md' (sections A/B/C/D).
   Use the FINDINGS section 2 corrections when citing plan section A - eight rows are refuted.
3. Decide scope honestly: this run produces STRATEGY.md (product truth -> audience -> surfaces ->
   positioning options) and CONCEPT-LOG.md (named directions, each traced to a product fact,
   audience and surface, with rejected options logged one line each).

Rules for this run:
- Prefer repair/retention over replacement: the shipped identity (hexagon+centre-dot mark,
  emerald #34d399 on ink #09090b, lowercase Geist wordmark, mascot) has equity; any replacement
  direction must justify migration cost (master prompt working method 3).
- No identity implementation, no asset generation, no public files (non-negotiable 3).
- No clearance/distinctiveness claims (non-negotiable 5). IP pre-screen = scope a knockout search
  (name + mark classes 9/42, territories per human answer, common-law + Vienna codes per plan C04)
  and record it as OPEN for counsel - plan gate G1 still requires the human to engage counsel or
  explicitly own the risk in writing.
- Capability: no browser unless the human approved B1's fix; rendered concept previews are
  deferred to Run 3/4. Text-first strategy is unaffected by this limit.
- Surface evidence to cite: route/surface map (APP-BRAND-AUDIT 6), audience signals (PRODUCT.md
  quality gates), category context (plan R.1), failure taxonomy (plan R.2).

Human decisions to collect in this run (blockers B4): keep-name vs rename; tagline retention;
territories/Nice classes; budget + counsel owner; PWA/mobile scope; governing neutral-ramp
document (FINDINGS section 3); acceptance of C23 measurement proxies. Record every answer in
DECISION.md with date; assumptions only where the human defers, never silent.

Deliverables: STRATEGY.md, CONCEPT-LOG.md, DECISION.md updated, HANDOFF.md + NEXT-PROMPT.md at
session end (no exceptions). Commit style: docs(brand): ... , local only, one coherent unit.
Stop rules: any missing product evidence, missing human decision, or capability gap ->
blocker in DECISION.md; a blocker is a valid outcome.
