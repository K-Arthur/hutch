# 00-BRIEF - Hutch brand identity pipeline

PROJECT: Hutch - local-first, open-source multi-bot agent platform ("Your bots. Your machine. Your rules.")
REPO_ROOT: /home/kevina/CodingProjects/hutch
SITE_APP_PATH: website/ (marketing site), src/hutch/server/ (dashboard)
DOCS_PATH: docs/
NATIVE_TARGETS: desktop (Tauri/Rust), web; CLI entry point
EXISTING_BRAND_DOCS: docs/brand-assets.md, docs/design-system.md, website/tokens.json
ARTIFACT_DIR: .pipeline/brand/2026-10
TODAY: 2026-10-28
RUN: 1 (evidence base - inferred: no .pipeline/brand artifacts existed at session start)
HUMAN_AUTHORITY: local commits only; never push/deploy/merge without explicit instruction
CONCURRENCY: main tree shared with other sessions; this run writes only under .pipeline/brand/**;
  .worktrees/brand-phase1 and .worktrees/brand-plan exist and are NOT read (AGENTS.md forbids .worktrees/)
JURISDICTIONS: assumed US/EU (unconfirmed - assumption logged in DECISION.md)
LICENCE_POSTURE: open-source project; SIL OFL fonts; vendor artwork per docs/brand-assets.md (budget unconfirmed)
BUDGET: <=15 files read per pass; <=~30 min wall; <=12 external page fetches

## Scope (this run)
Run 1 evidence only: two cited, dated research tracks; audit of real product surfaces
(dashboard + marketing site); asset inventory with provenance/licence status; findings.

## Non-goals
No new or altered identity marks, no direction selection, no public assets, no source/UI
code changes, no legal clearance or non-infringement claims, no push/deploy, no reads of
.worktrees/, no files written outside .pipeline/brand/**.

## Success criteria
RESEARCH.md, APP-BRAND-AUDIT.md, ASSET-INVENTORY.md, FINDINGS.md, DECISION.md complete and
reviewed by the lead; HANDOFF.md + NEXT-PROMPT.md written; human signs off the evidence base
before Run 2.

## Stop rules
Missing product evidence for a claim, absent capability, or missing human sign-off => record
a blocker in DECISION.md. A blocker is a valid outcome.
