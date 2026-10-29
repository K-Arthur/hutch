# HANDOFF.md - session end, Run 2

Run: 2 - Project: Hutch - Date: 2026-10-28 (America/Vancouver) - Session: DSH "lead"
Commit: one coherent unit, `docs(brand):` prefix, local only (this file and NEXT-PROMPT.md
included; hash in git log).
Authority used: local commits only; nothing pushed, deployed or merged; .worktrees/ never read; no
file outside .pipeline/brand/2026-10/ created or modified; zero external fetches; no asset or code
generation.

## Artifact state (Run 1 committed at 40b35322/6a744aaf; Run 2 in this commit)

| Artifact | Status | Review note |
|---|---|---|
| 00-BRIEF.md | complete (Run 1) | unchanged this run |
| DECISION.md | updated | Run 1 D01-D08 + Run 2 D09-D20; Gate 1 signed off, Gate 2 closed; B4 resolved, B6 added |
| RESEARCH.md / APP-BRAND-AUDIT.md / ASSET-INVENTORY.md / FINDINGS.md | complete (Run 1) | cited, not modified |
| STRATEGY.md | NEW, complete | product truth T1-T15 -> audiences A1-A4 -> surfaces -> PO-1..3; IP pre-screen scope section 7 (OPEN) |
| CONCEPT-LOG.md | NEW, complete | D1-D4 directions traced to fact/audience/surface; 8 rejections one line each; selection record filled from gate answers |
| HANDOFF.md, NEXT-PROMPT.md | rewritten for Run 3 | this pair |
| CLEARANCE-PROTOCOL.md, IP-CLEARANCE.md, PROVENANCE-REGISTER.md | NOT WRITTEN | Run 3 |
| Concept renders / guidelines / provenance-backed assets | NOT WRITTEN | Run 3 only after G1 sign-off; renders need B1 |

## Gate state leaving this run

- GATE 1: SIGNED OFF 2026-10-28 (DECISION D09).
- GATE 2 (Run 2 exit): CLOSED 2026-10-28 - direction selected (D19: D1 "Centre Dot" base + D2
  "Local Hub" lead territory), IP pre-screen scoped and budget/risk accepted (D20: scope OPEN for
  counsel, zero spend, IP risk owned by the maintainer in writing for now, no funded counsel).
- Plan hard gate G1: OPEN - no clearance protocol exists. Run 3 ordering is fixed by this:
  protocol draft -> human sign-off -> only then any asset generation (including a faithful master
  extracted from the shipped hexagon path). Knockout SEARCH (not creation) may run immediately.

## What the next session inherits

- Run 2 was strategy only: STRATEGY.md (product truth, audiences, surfaces, positioning PO-1..3,
  IP pre-screen scope) and CONCEPT-LOG.md (four named directions, eight rejected options). No
  identity implementation, no renders, no legal conclusions anywhere.
- Decisions now binding: keep name "Hutch" (D10), tagline verbatim (D11), tokens.json is the
  governing neutral ramp (D12), territories US/EU/UK/CA and Nice 9/42 for knockout scope (D13),
  budget zero external spend (D15), PWA manifest + icons in scope (D16), C23 proxies accepted (D17).
- Strategy citations use the FINDINGS section 2 corrections whenever plan section A is referenced
  (eight plan rows refuted - base.html 10 stylesheets, Studio 15, tokens 28/12/7, JSON-LD screenshot
  property exists, --fs-* lives in style.css, brand alias is marketing-only, mascot rules exist,
  social renderer exists).
- Capability facts unchanged unless re-probed: NO browser/screenshot capability (B1 never approved);
  read_image works; web fetch works but was not used this run; asking the human works (one 120 s
  timeout, retry succeeded).
- The Phase 0 plan (brand/plan, PR #11) still needs its 8 corrections folded in (B2) - Run 2 did not
  touch it; the two programs stay reconciled through DECISION.md.

## Blockers (owner -> next action)

- B1 - No visual/screenshot capability. Owner: human. Action: approve `uv sync --extra browser` (or
  name an existing capture harness) before any run claims rendered evidence; Run 3 concepts stay
  text-first without it, Run 4's visual gate cannot run at all.
- B2 - Phase 0 plan PR #11 pending review + 8 refutations (FINDINGS 2). Owner: human/plan owner.
- B3 - Stale brand/phase-1 worktree evidence uncommitted and unreadable here. Owner: human.
- B5 - Open citations: Anthropic press-kit URL, X/Facebook card dimensions (U17), and 6
  shell-rendered citations needing a rendering-browser re-check. Owner: session/human.
- B6 (new) - IP risk posture: owned by the maintainer in writing, no funded counsel (D20), while
  D14's "engage counsel" intent stays unfunded (D15). Owner: human. Action: at each later gate,
  re-confirm the written ownership or fund counsel; G1 protocol sign-off is owed regardless before
  any asset generation.

## Deliberately deferred

- All asset generation, renders, guidelines, press kit, trademark policy (Runs 3-4, gated on G1).
- Source fixes found in Run 1 (docs/design-system.md conflicts, THIRD_PARTY_NOTICES font list,
  stale 2026-10-10 research doc) - documented, not fixed.
- Domain/handle state (U21/C15) - the Run 3 common-law search may surface conflicts for the human.
- Adoption of pipeline artifacts into docs/brand/** - requires an explicit docs/brand assignment
  from the human; write scope stays .pipeline/brand/** otherwise.
